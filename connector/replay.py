"""The replayed source the prototype reads.

This module exists to hold a boundary that a test enforces: **nothing in
`twin/` imports the simulator.** The twin runs against a canonical event stream
and knows nothing about what produced it, which is the whole reason the same
code can be pointed at a historian. Loading a plant model, running SimPy and
throwing away what the dark stations would have said all belong on the source
side of that line, and this is the source side.

What comes back is a stream and the two facts a twin needs about it: which line
definition it describes and where its clock starts. Nothing about ground truth
crosses this boundary, and `plantsim.truth` is not imported here either. The
evaluation harness is the only thing in the repository that may read that, and
it reads it from the simulator directly rather than through anything the twin
can see.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from connector.protocol import CanonicalEvent
from plantsim.model import SimulationDetail, SimulationRequest, run_simulation
from plantsim.parameters import load_plant_model
from plantsim.scenarios import load_scenarios
from twin.config.line import LineDefinition
from twin.config.loader import load_line_definition

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ReplaySource:
    """One recorded stream, and the two facts a twin needs about it."""

    line: LineDefinition
    epoch: datetime
    events: tuple[CanonicalEvent, ...]
    description: str


def build_replay_source(
    line_name: str, scenario_id: str, seed: int, units: int
) -> ReplaySource:
    """Run the line once and hand back the events it emitted.

    The simulation runs to completion here rather than alongside the twin
    because coupling a forecast cycle's runtime to the line's pace would let a
    slow cycle slow the line it is forecasting, which is the one thing a digital
    twin must never do. The events are identical either way and the twin cannot
    tell the difference.
    """
    line = load_line_definition(REPO_ROOT / "config" / "lines" / f"{line_name}.yaml")
    plant = load_plant_model(REPO_ROOT / "config" / "plantsim" / f"{line_name}.yaml")
    catalogue = load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")
    result = run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=seed,
            units=units,
            scenario=catalogue.build(scenario_id, line.line_id),
            detail=SimulationDetail(),
        )
    )
    return ReplaySource(
        line=line,
        epoch=plant.epoch,
        events=tuple(result.events),
        description=(f"scenario {scenario_id}, seed {seed}, {units} units released"),
    )
