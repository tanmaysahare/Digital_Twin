"""Scenario injection. T-027 to T-029, PRD.md Section 6.

Eight scenarios, defined in `config/plantsim/scenarios.yaml` and not in code. An
injection changes exactly one thing about the plant, which is what makes a
control run a fair comparison: every other parameter is identical because it
came from the same file and the same seed.

Two of the eight are worth naming here. SC-05 slows a station that no sensor
observes, so nothing but the virtual sensors can see it at all. SC-06 injects
nothing, and a run in which the twin raises an alert on it is a failure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from plantsim.truth import InjectionTruth
from twin.config.line import Strict
from twin.config.loader import ConfigurationError, load_config

Mechanism = Literal[
    "cycle_drift",
    "cycle_step",
    "variance_step",
    "humidity_excursion",
    "lot_defect",
    "source_outage",
]

# The variance multiplies, the spread is its square root. Writing the scenario
# in terms of variance keeps it in the language PRD Section 6 uses.
_VARIANCE_TO_SPREAD = math.sqrt


class Injection(Strict):
    """One change to the plant, with the time window it applies over."""

    mechanism: Mechanism
    starts_at_s: float = Field(ge=0.0)
    # Null means the change persists to the end of the run, which is what a
    # worn fixture does until somebody replaces it.
    ends_at_s: float | None = Field(default=None, ge=0.0)
    station_id: str | None = None
    zone_id: str | None = None
    gate_id: str | None = None
    lot_id: str | None = None
    parameters: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def window_runs_forward(self) -> Self:
        """An injection cannot end before it starts."""
        if self.ends_at_s is not None and self.ends_at_s <= self.starts_at_s:
            message = (
                f"{self.mechanism}: ends_at_s ({self.ends_at_s}) must be after "
                f"starts_at_s ({self.starts_at_s})"
            )
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def mechanism_has_what_it_needs(self) -> Self:
        """Each mechanism needs its own target and parameters."""
        required: dict[Mechanism, tuple[tuple[str, ...], tuple[str, ...]]] = {
            "cycle_drift": (("station_id",), ("from_cycle_s", "to_cycle_s")),
            "cycle_step": (("station_id",), ("from_cycle_s", "to_cycle_s")),
            "variance_step": (("station_id",), ("variance_multiplier",)),
            "humidity_excursion": (("zone_id",), ("delta_pct",)),
            "lot_defect": (("lot_id", "gate_id"), ("odds_multiplier",)),
            "source_outage": ((), ()),
        }
        targets, parameters = required[self.mechanism]
        for name in targets:
            if getattr(self, name) is None:
                message = f"{self.mechanism}: needs {name}"
                raise ValueError(message)
        for name in parameters:
            if name not in self.parameters:
                message = f"{self.mechanism}: needs parameters.{name}"
                raise ValueError(message)
        ramps = {"cycle_drift", "cycle_step"}
        if self.mechanism in ramps and self.parameters["from_cycle_s"] <= 0:
            message = f"{self.mechanism}: from_cycle_s must be above zero"
            raise ValueError(message)
        if self.mechanism == "cycle_drift" and self.ends_at_s is None:
            message = "cycle_drift: needs ends_at_s, because a ramp has a length"
            raise ValueError(message)
        return self

    def covers(self, at_s: float) -> bool:
        """Whether this injection is in force at an instant."""
        if at_s < self.starts_at_s:
            return False
        return self.ends_at_s is None or at_s < self.ends_at_s

    def truth(self, scenario_id: str, line_id: str) -> InjectionTruth:
        """The ground-truth record of what was injected."""
        return InjectionTruth(
            scenario_id=scenario_id,
            line_id=line_id,
            station_id=self.station_id,
            injected_at_s=self.starts_at_s,
            ends_at_s=self.ends_at_s,
            mechanism=self.mechanism,
            parameters=dict(self.parameters)
            | {
                key: value
                for key, value in (
                    ("zone_id", self.zone_id),
                    ("gate_id", self.gate_id),
                    ("lot_id", self.lot_id),
                )
                if value is not None
            },
        )


class ScenarioDefinition(Strict):
    """One scenario as it is written in the catalogue."""

    scenario_id: str = Field(alias="id", min_length=1)
    line_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    what_the_twin_should_do: str = Field(default="", max_length=800)
    injections: tuple[Injection, ...] = ()
    # A scenario built from others, so that the concurrent-fault case cannot
    # drift away from the two it is made of.
    includes: tuple[str, ...] = ()


class ScenarioCatalogue(Strict):
    """Every scenario, for every line."""

    scenarios: tuple[ScenarioDefinition, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def identifiers_are_unique_per_line(self) -> Self:
        """A scenario identifier means one thing on one line."""
        seen: set[tuple[str, str]] = set()
        for scenario in self.scenarios:
            key = (scenario.line_id, scenario.scenario_id)
            if key in seen:
                message = (
                    f"scenarios: {scenario.scenario_id} appears more than once "
                    f"for line {scenario.line_id}"
                )
                raise ValueError(message)
            seen.add(key)
        return self

    @model_validator(mode="after")
    def included_scenarios_exist(self) -> Self:
        """A composite scenario names scenarios that are defined on the same line."""
        known = {
            (scenario.line_id, scenario.scenario_id) for scenario in self.scenarios
        }
        for scenario in self.scenarios:
            for included in scenario.includes:
                if (scenario.line_id, included) not in known:
                    message = (
                        f"scenarios.{scenario.scenario_id}: includes {included}, "
                        f"which is not defined for line {scenario.line_id}"
                    )
                    raise ValueError(message)
        return self

    def for_line(self, line_id: str) -> tuple[ScenarioDefinition, ...]:
        """Every scenario defined for one line."""
        return tuple(
            scenario for scenario in self.scenarios if scenario.line_id == line_id
        )

    def build(self, scenario_id: str, line_id: str) -> Scenario:
        """Assemble a runnable scenario, resolving anything it includes."""
        definition = self._find(scenario_id, line_id)
        injections: list[Injection] = list(definition.injections)
        for included in definition.includes:
            injections.extend(self._find(included, line_id).injections)
        return Scenario(
            scenario_id=definition.scenario_id,
            name=definition.name,
            line_id=definition.line_id,
            injections=tuple(injections),
        )

    def _find(self, scenario_id: str, line_id: str) -> ScenarioDefinition:
        for scenario in self.scenarios:
            if scenario.scenario_id == scenario_id and scenario.line_id == line_id:
                return scenario
        available = ", ".join(
            sorted(scenario.scenario_id for scenario in self.for_line(line_id))
        )
        message = (
            f"no scenario {scenario_id} for line {line_id}. "
            f"This line has: {available or 'none'}"
        )
        raise ConfigurationError(message)


@dataclass(frozen=True)
class Scenario:
    """A scenario ready to run, and the effect it has at any instant.

    Every hook returns the neutral value when nothing applies, so the null
    scenario and a scenario outside its window behave identically to no
    scenario at all. That is what makes a control run a control.
    """

    scenario_id: str
    name: str
    line_id: str
    injections: tuple[Injection, ...]

    def cycle_scale(self, station_id: str, at_s: float) -> float:
        """How much a station's cycle time is multiplied at this instant.

        A ramp holds at its target once it has finished. `ends_at_s` on a
        `cycle_drift` says when the ramp stops climbing, not when the wear
        stops existing: a worn fixture stays worn until somebody replaces it.
        Reverting at the end of the window made SC-01 a fault that healed
        itself after 90 minutes, and a scenario whose consequence disappears
        before a 120 minute forecast horizon closes cannot be forecast at all.
        """
        scale = 1.0
        for injection in self.injections:
            if injection.station_id != station_id or at_s < injection.starts_at_s:
                continue
            start = injection.parameters.get("from_cycle_s")
            target = injection.parameters.get("to_cycle_s")
            if start is None or target is None:
                continue
            if injection.mechanism == "cycle_step":
                if not injection.covers(at_s):
                    continue
                scale *= target / start
            elif injection.mechanism == "cycle_drift":
                # Linear is the honest default: the shape of real wear is
                # unknown and a curve here would be a claim we cannot support.
                assert injection.ends_at_s is not None
                span = injection.ends_at_s - injection.starts_at_s
                progress = min(1.0, (at_s - injection.starts_at_s) / span)
                scale *= (start + (target - start) * progress) / start
        return scale

    def cycle_spread_scale(self, station_id: str, at_s: float) -> float:
        """How much a station's cycle-time spread is multiplied at this instant."""
        scale = 1.0
        for injection in self.injections:
            if injection.mechanism != "variance_step":
                continue
            if injection.station_id != station_id or not injection.covers(at_s):
                continue
            scale *= _VARIANCE_TO_SPREAD(injection.parameters["variance_multiplier"])
        return scale

    def humidity_offset(self, zone_id: str, at_s: float) -> float:
        """How far a zone's humidity is displaced at this instant."""
        offset = 0.0
        for injection in self.injections:
            if injection.mechanism != "humidity_excursion":
                continue
            if injection.zone_id != zone_id or not injection.covers(at_s):
                continue
            offset += injection.parameters["delta_pct"]
        return offset

    def lot_odds_scale(self, lot_id: str, gate_id: str) -> float:
        """How much a lot multiplies the odds of failing a gate."""
        scale = 1.0
        for injection in self.injections:
            if injection.mechanism != "lot_defect":
                continue
            if injection.lot_id == lot_id and injection.gate_id == gate_id:
                scale *= injection.parameters["odds_multiplier"]
        return scale

    def is_source_silent(self, at_s: float) -> bool:
        """Whether the source is not reporting at this instant."""
        return any(
            injection.mechanism == "source_outage" and injection.covers(at_s)
            for injection in self.injections
        )

    def truth(self) -> tuple[InjectionTruth, ...]:
        """The ground-truth record of everything this scenario injected."""
        return tuple(
            injection.truth(self.scenario_id, self.line_id)
            for injection in self.injections
        )


NULL_SCENARIO = Scenario(
    scenario_id="none",
    name="No scenario",
    line_id="",
    injections=(),
)


def load_scenarios(path: Path | str) -> ScenarioCatalogue:
    """Read and validate the scenario catalogue."""
    return load_config(path, ScenarioCatalogue, "scenario catalogue")
