"""The simulator's own parameters, and why they are not in the line definition.

The twin loads `config/lines/*.yaml`. If the true cycle times, failure rates and
defect causes lived there, the twin would be reading the answer to the question
the evaluation asks. They live in `config/plantsim/*.yaml` instead, loaded only
by the simulator, and the ground truth they produce goes to a database schema
the twin's role cannot read (AC-104).

Nothing here is in code, for the same reason nothing in the line definition is
(CODING_STANDARDS.md 1.3). A different line is a different file.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, model_validator

from twin.config.line import LineDefinition, Strict
from twin.config.loader import load_config

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveSeconds = Annotated[float, Field(gt=0.0)]


class StationDefaults(Strict):
    """What every station uses unless it overrides it."""

    # Coefficient of variation of the processing time. Small, because an
    # assembly station is paced work, not a queue of arbitrary jobs.
    cycle_cv: float = Field(gt=0.0, le=1.0)
    # Mean production seconds between in-process failures. Failures are
    # operation-dependent: a station cannot fail while it is not working, which
    # is the standard assumption for paced assembly and is what makes a dark
    # station's repair time part of its processing time rather than a separate
    # unobservable state.
    mtbf_s: PositiveSeconds
    mttr_median_s: PositiveSeconds
    mttr_sigma: float = Field(gt=0.0, le=2.0)


class StationParameters(Strict):
    """One station's true behaviour."""

    station_id: str = Field(alias="id", min_length=1)
    base_cycle_s: PositiveSeconds
    cycle_cv: float | None = Field(default=None, gt=0.0, le=1.0)
    mtbf_s: PositiveSeconds | None = None
    mttr_median_s: PositiveSeconds | None = None


class ZoneEnvironment(Strict):
    """A zone's ambient conditions and how much its work varies by variant."""

    zone_id: str = Field(alias="id", min_length=1)
    temperature_c: float
    temperature_sd_c: float = Field(gt=0.0)
    humidity_pct: float = Field(ge=0.0, le=100.0)
    humidity_sd_pct: float = Field(gt=0.0)
    # Paint work barely varies by variant; trim work varies a great deal. A
    # single line-wide factor would either make the paint zone the bottleneck
    # for the long-wheelbase variant or understate the trim effect.
    variant_cycle_factor: dict[str, float]


class GateParameters(Strict):
    """One inspection gate and its true base failure rate."""

    gate_id: str = Field(alias="id", min_length=1)
    base_failure_rate: Probability


class DefectModel(Strict):
    """How a unit's history turns into a probability of failing a gate.

    The multipliers act on the odds rather than on the probability, so that
    combining two causes cannot produce a probability above one and so that a
    cause has the same effect wherever the base rate sits.
    """

    # A unit whose cycle time ran high at a station in the gate's span is more
    # likely to fail it. This is the coupling the defect model has to find.
    cycle_deviation_odds_per_sigma: float = Field(gt=0.0)
    # Only deviation beyond this counts. Without a threshold the worst of
    # sixteen stations is above nominal on every unit by construction, so every
    # unit would carry the multiplier and the feature would separate nothing.
    cycle_deviation_threshold_sigma: float = Field(default=1.0, ge=0.0, le=4.0)
    # Above the zone's nominal humidity, per percentage point.
    humidity_odds_per_pct_above: float = Field(gt=0.0)
    # Lot quality varies. Each lot draws a multiplier from a lognormal with this
    # spread, which is what makes a containment list meaningful.
    lot_quality_sigma: float = Field(ge=0.0, le=2.0)
    # A unit that has already been through rework is more likely to fail again.
    rework_odds_multiplier: float = Field(gt=0.0)
    # Visiting a dark station does not make a unit more likely to fail. Held at
    # exactly one so that no evaluation number can be explained by the twin
    # having learned to fear the stations it cannot see.
    dark_visit_odds_multiplier: float = Field(default=1.0, ge=1.0, le=1.0)


class SignalParameters(Strict):
    """One process signal a tier A station reports, and how it behaves.

    The coupling is what makes a process value informative: a station running
    long shows it in its torque and its current as well as in its clock. A
    signal with zero coupling would be noise the defect model would correctly
    learn to ignore.
    """

    name: str = Field(min_length=1)
    unit: str = Field(min_length=1)
    nominal: float
    sd: float = Field(gt=0.0)
    cycle_coupling: float = Field(ge=0.0, le=1.0)


class MaterialFlow(Strict):
    """A part consumed at a station, and how its lots are numbered."""

    part: str = Field(min_length=1)
    station_id: str = Field(alias="station", min_length=1)
    lot_size: int = Field(ge=1)
    lot_prefix: str = Field(min_length=1)
    lot_start: int = Field(ge=1)


class PlantModel(Strict):
    """Everything the simulator knows and the twin does not."""

    line_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    # The simulated wall clock at time zero. Fixed, so a seeded run reproduces
    # the same timestamps as well as the same durations (NFR-07).
    epoch: datetime
    # The transport times the twin holds as nominal are not exactly reproduced.
    # This is the gap the twin's transport tolerance has to cover, and it is why
    # a derived cycle time is an interval even where one dark station sits alone
    # between two instrumented ones.
    transport_cv: float = Field(gt=0.0, le=0.5)
    station_defaults: StationDefaults
    zones: tuple[ZoneEnvironment, ...] = Field(min_length=1)
    stations: tuple[StationParameters, ...] = Field(min_length=2)
    gates: tuple[GateParameters, ...] = Field(min_length=1)
    defects: DefectModel
    signals: tuple[SignalParameters, ...] = Field(min_length=1)
    materials: tuple[MaterialFlow, ...] = ()
    operator_group_by_shift: dict[str, str]
    # How long an inspection gate takes to return a verdict. A gate result
    # carries this latency, which is why it never anchors a cycle-time interval
    # (TECHNICAL_SPEC.md Section 4.3).
    gate_latency_s: PositiveSeconds
    # How long after the work a checklist result is recorded at a dark station.
    # A person fills in a form when they get to it, which is the reason a
    # manual check cannot anchor a cycle-time interval either.
    manual_check_latency_s: PositiveSeconds
    # How often a zone reports its temperature and humidity.
    env_sample_s: PositiveSeconds
    # How many times a unit can fail a gate and go back before it is scrapped.
    max_rework_passes: int = Field(ge=0, le=5)
    # The plant's own unit identifier scheme. A vehicle identification number
    # is 17 characters, and the prefix is the part that does not change.
    unit_id_prefix: str = Field(min_length=1)
    unit_id_start: int = Field(ge=1)
    # What the plant plans to build in a day. Not the takt-limited ideal: it is
    # the figure the plant schedules against, and the gap between the two is the
    # blocking, starving and repair the line actually loses. T-020 asserts the
    # simulated output lands within 5 percent of it.
    nominal_output_per_day: int = Field(ge=1)

    def station(self, station_id: str) -> StationParameters:
        """One station's parameters by identifier."""
        for candidate in self.stations:
            if candidate.station_id == station_id:
                return candidate
        message = f"no parameters for station {station_id} on line {self.line_id}"
        raise KeyError(message)

    def zone(self, zone_id: str) -> ZoneEnvironment:
        """One zone's environment by identifier."""
        for candidate in self.zones:
            if candidate.zone_id == zone_id:
                return candidate
        message = f"no environment for zone {zone_id} on line {self.line_id}"
        raise KeyError(message)

    def gate(self, gate_id: str) -> GateParameters:
        """One gate's parameters by identifier."""
        for candidate in self.gates:
            if candidate.gate_id == gate_id:
                return candidate
        message = f"no parameters for gate {gate_id} on line {self.line_id}"
        raise KeyError(message)

    def cycle_cv_of(self, station_id: str) -> float:
        """The station's own coefficient of variation, or the default."""
        return self.station(station_id).cycle_cv or self.station_defaults.cycle_cv

    def mtbf_of(self, station_id: str) -> float:
        """The station's own mean production time between failures, or the default."""
        return self.station(station_id).mtbf_s or self.station_defaults.mtbf_s

    def mttr_median_of(self, station_id: str) -> float:
        """The station's own median repair time, or the default."""
        station = self.station(station_id)
        return station.mttr_median_s or self.station_defaults.mttr_median_s

    @model_validator(mode="after")
    def stations_are_unique(self) -> Self:
        """Two stations cannot share an identifier."""
        seen: set[str] = set()
        for station in self.stations:
            if station.station_id in seen:
                message = f"stations: {station.station_id} appears more than once"
                raise ValueError(message)
            seen.add(station.station_id)
        return self

    def validate_against(self, line: LineDefinition) -> None:
        """Check that these parameters describe that line, and say what is missing.

        Raises:
            ValueError: naming the first field that does not line up. A
                simulator running against a line it does not fully describe
                would silently invent behaviour for the stations it missed.
        """
        if self.line_id != line.line_id:
            message = f"these parameters are for {self.line_id}, not {line.line_id}"
            raise ValueError(message)

        described = {station.station_id for station in self.stations}
        missing = [
            station_id for station_id in line.station_ids if station_id not in described
        ]
        if missing:
            message = f"stations: no parameters for {', '.join(missing)}"
            raise ValueError(message)
        extra = sorted(described - set(line.station_ids))
        if extra:
            message = f"stations: {', '.join(extra)} are not on line {line.line_id}"
            raise ValueError(message)

        zones_described = {zone.zone_id for zone in self.zones}
        zones_needed = {zone.zone_id for zone in line.zones}
        if zones_described != zones_needed:
            message = (
                f"zones: parameters describe {sorted(zones_described)}, the line "
                f"has {sorted(zones_needed)}"
            )
            raise ValueError(message)

        gates_described = {gate.gate_id for gate in self.gates}
        gates_needed = {gate.gate_id for gate in line.gates}
        if gates_described != gates_needed:
            message = (
                f"gates: parameters describe {sorted(gates_described)}, the line "
                f"has {sorted(gates_needed)}"
            )
            raise ValueError(message)

        for zone in self.zones:
            if set(zone.variant_cycle_factor) != set(line.variants):
                message = (
                    f"zones.{zone.zone_id}.variant_cycle_factor: must name every "
                    f"variant. The line has {sorted(line.variants)}"
                )
                raise ValueError(message)

        shifts_needed = {shift.shift_id for shift in line.shifts}
        if set(self.operator_group_by_shift) != shifts_needed:
            message = (
                f"operator_group_by_shift: must name every shift. The line has "
                f"{sorted(shifts_needed)}"
            )
            raise ValueError(message)

        for material in self.materials:
            if material.station_id not in described:
                message = (
                    f"materials: {material.part} is consumed at "
                    f"{material.station_id}, which is not on this line"
                )
                raise ValueError(message)


def load_plant_model(path: Path | str) -> PlantModel:
    """Read and validate a set of simulator parameters."""
    return load_config(path, PlantModel, "plant model")
