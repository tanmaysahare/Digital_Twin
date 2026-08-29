"""The evaluation harness. T-069, T-071.

TEST_PLAN.md Section 9. Not a test. A deliverable. It produces the evidence pack
that makes every claim in the README checkable, and the reason it exists in Phase
2 rather than Phase 5 is that a harness written on the last day evaluates
whatever was built rather than what was intended.

**What it does.** For each scenario and each seed it runs the simulator to
completion, runs the whole twin pipeline against the emitted stream, and then
joins the ledger against the simulator's ground truth. The twin's own outcome
join runs first and knows nothing about the truth; the truth is read afterwards,
by this module, connecting as the role that can see it. That order is what makes
the numbers mean anything.

**What it deliberately does not do.** It does not feed ground truth back into the
twin, tune a threshold to make a number look better, or drop a scenario whose
result is inconvenient. The null scenario is run and reported beside every
accuracy figure, because a system that predicts stalls on a quiet shift is the
system the problem statement warns about.

**Determinism.** Every run is keyed on `(scenario, seed)` and every draw inside it
on that key, so two runs on the same commit produce identical metrics (AC-103,
T-071). `verify_determinism` asserts it rather than assuming it.
"""

from __future__ import annotations

import os
import subprocess
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from plantsim.model import (
    SimulationDetail,
    SimulationRequest,
    SimulationResult,
    run_simulation,
)
from plantsim.parameters import PlantModel, load_plant_model
from plantsim.scenarios import ScenarioCatalogue, load_scenarios
from plantsim.truth import GroundTruth
from twin.config import LineDefinition, load_line_definition
from twin.domain.shifts import ProductionCalendar
from twin.ledger.store import LedgerStore
from twin.pipeline import TwinPipeline

if TYPE_CHECKING:  # pragma: no cover - import cycle: metrics reads a RunResult
    from evaluation.metrics import RunMetrics

REPO_ROOT = Path(__file__).resolve().parent.parent

# The scenarios the evidence pack covers, in the order PRD Section 6 lists them.
# SC-07 is a data-health scenario whose injection the connector handles rather
# than the predictors, and SC-02 and SC-04 are defect scenarios; all of them are
# run, because a pack that reported only the scenarios that flatter the twin
# would not be evidence.
SCENARIOS = ("SC-01", "SC-02", "SC-03", "SC-04", "SC-05", "SC-06", "SC-07", "SC-08")


@dataclass(frozen=True)
class Settings:
    """What one evaluation covers, and how hard it works at it.

    The defaults are the configuration `make evaluate` runs, and they are stated
    in the report rather than left implicit. The full 8 scenarios by 20 seeds in
    TEST_PLAN.md Section 9 is T-130 in Phase 5; this is the same harness at a
    smaller replication count, and the report says which it was.
    """

    line_name: str = "line2"
    scenarios: tuple[str, ...] = SCENARIOS
    seeds: tuple[int, ...] = (20260302, 20260303, 20260304)
    units: int = 620
    replications: int = 40
    cadence_s: float = 300.0
    horizon_min: int = 120
    # A separate, longer baseline run whose only job is to train the defect
    # models. A gate that fails one unit in seventy needs thousands of units
    # before it has enough failures to learn from, and asking each evaluation run
    # to train its own model on its own few hundred would mean no model at all.
    # This mirrors what a plant does: models are fitted ahead and shipped as
    # artefacts (NFR-05).
    training_units: int = 2400
    training_seed: int = 20260301
    workers: int | None = None

    @property
    def run_count(self) -> int:
        """How many scenario runs this evaluation covers."""
        return len(self.scenarios) * len(self.seeds)


@dataclass
class RunResult:
    """One scenario at one seed: what the twin claimed, and what happened."""

    scenario_id: str
    seed: int
    line_id: str
    units: int
    store: LedgerStore
    truth: GroundTruth
    pipeline: TwinPipeline
    result: SimulationResult
    cycles: int
    forecast_runtime_s: tuple[float, ...]
    wall_s: float
    training_report: dict[str, str] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """A stable name for this run, used in the report and in file names."""
        return f"{self.scenario_id}-{self.seed}"


def _paths(line_name: str) -> tuple[Path, Path, Path]:
    return (
        REPO_ROOT / "config" / "lines" / f"{line_name}.yaml",
        REPO_ROOT / "config" / "plantsim" / f"{line_name}.yaml",
        REPO_ROOT / "config" / "plantsim" / "scenarios.yaml",
    )


def load(line_name: str) -> tuple[LineDefinition, PlantModel, ScenarioCatalogue]:
    """Everything one line's evaluation needs, from configuration alone."""
    line_path, plant_path, scenario_path = _paths(line_name)
    return (
        load_line_definition(line_path),
        load_plant_model(plant_path),
        load_scenarios(scenario_path),
    )


def simulate(
    line: LineDefinition,
    plant: PlantModel,
    catalogue: ScenarioCatalogue,
    scenario_id: str,
    seed: int,
    units: int,
    *,
    detail: SimulationDetail | None = None,
) -> SimulationResult:
    """Run the plant once."""
    return run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=seed,
            units=units,
            scenario=catalogue.build(scenario_id, line.line_id),
            detail=detail or SimulationDetail(),
        )
    )


def train_defect_models(settings: Settings) -> TwinPipeline:
    """Fit the defect models on a long baseline run, once.

    The pipeline that comes back carries fitted models for every gate that had
    enough failures to fit one. Every scenario run then adopts them rather than
    training its own, which is both what a plant does and the only way a gate
    with a two percent failure rate has enough labels to learn from.
    """
    line, plant, catalogue = load(settings.line_name)
    result = simulate(
        line,
        plant,
        catalogue,
        "SC-06",
        settings.training_seed,
        settings.training_units,
    )
    calendar = ProductionCalendar(line, plant.epoch)
    pipeline = TwinPipeline(
        line=line,
        calendar=calendar,
        replications=1,
        cadence_s=1800.0,
        horizon_min=30,
    )
    pipeline.feed(result.events)
    pipeline.defect.train(result.truth.epoch)
    return pipeline


def run_one(
    scenario_id: str,
    seed: int,
    settings: Settings,
    trained: TwinPipeline | None = None,
) -> RunResult:
    """One scenario at one seed, end to end."""
    started = time.monotonic()
    line, plant, catalogue = load(settings.line_name)
    result = simulate(line, plant, catalogue, scenario_id, seed, settings.units)
    calendar = ProductionCalendar(line, plant.epoch)
    pipeline = TwinPipeline(
        line=line,
        calendar=calendar,
        replications=settings.replications,
        cadence_s=settings.cadence_s,
        horizon_min=settings.horizon_min,
    )
    if trained is not None:
        pipeline.defect.adopt(trained.defect)
    pipeline.feed(result.events)
    return RunResult(
        scenario_id=scenario_id,
        seed=seed,
        line_id=line.line_id,
        units=settings.units,
        store=pipeline.store,
        truth=result.truth,
        pipeline=pipeline,
        result=result,
        cycles=len(pipeline.cycles),
        forecast_runtime_s=tuple(cycle.summary.runtime_s for cycle in pipeline.cycles),
        wall_s=time.monotonic() - started,
        training_report=pipeline.training_report,
    )


def _worker(payload: tuple[str, int, Settings]) -> RunMetrics:
    """One run, measured in the worker and returned as numbers.

    A `RunResult` holds the whole pipeline, which is large and holds closures
    that do not cross a process boundary. Measuring here and shipping the tally
    keeps the pool usable and means the expensive part of the evaluation, which
    is the run, is the part that is parallelised.
    """
    from evaluation.metrics import measure

    scenario_id, seed, settings = payload
    trained = _shared_models()
    return measure(run_one(scenario_id, seed, settings, trained))


_TRAINED: TwinPipeline | None = None
_TRAINED_SETTINGS: Settings | None = None


def _shared_models() -> TwinPipeline | None:
    """The trained models, fitted once per process and then reused."""
    global _TRAINED
    if _TRAINED is None and _TRAINED_SETTINGS is not None:
        _TRAINED = train_defect_models(_TRAINED_SETTINGS)
    return _TRAINED


def _initialise(settings: Settings) -> None:
    global _TRAINED_SETTINGS
    _TRAINED_SETTINGS = settings


def run_all(
    settings: Settings | None = None,
    *,
    progress: bool = False,
) -> tuple[RunMetrics, ...]:
    """Every scenario at every seed.

    Runs are independent, so they go across a process pool. A single run is a
    simulator pass and a few dozen forecast cycles, and on a laptop the whole
    evaluation is minutes rather than an afternoon.
    """
    options = settings or Settings()
    jobs = [
        (scenario_id, seed, options)
        for scenario_id in options.scenarios
        for seed in options.seeds
    ]
    workers = options.workers or min(len(jobs), max(1, (os.cpu_count() or 2) - 1))
    if workers <= 1:
        _initialise(options)
        found: list[RunMetrics] = []
        for index, job in enumerate(jobs, start=1):
            item = _worker(job)
            if progress:
                print(f"  {index}/{len(jobs)} {item.key} in {item.wall_s:.0f} s")
            found.append(item)
        return tuple(found)
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_initialise, initargs=(options,)
    ) as pool:
        found = []
        for index, item in enumerate(pool.map(_worker, jobs), start=1):
            if progress:
                print(f"  {index}/{len(jobs)} {item.key} in {item.wall_s:.0f} s")
            found.append(item)
        return tuple(found)


def verify_determinism(settings: Settings | None = None) -> tuple[bool, str]:
    """Run one scenario twice and check that nothing moved. T-071, AC-103.

    Compares the ledger rather than a summary metric, because two runs could
    agree on a rounded precision while disagreeing on which predictions were
    made, and the evidence pack's claim is that any number in it can be
    reproduced exactly.
    """
    options = replace(
        settings or Settings(), scenarios=("SC-01",), seeds=(20260302,), workers=1
    )
    first = run_one("SC-01", 20260302, options)
    second = run_one("SC-01", 20260302, options)
    return _same_ledger(first.store, second.store)


def _same_ledger(first: LedgerStore, second: LedgerStore) -> tuple[bool, str]:
    if len(first.predictions) != len(second.predictions):
        return False, (
            f"{len(first.predictions)} predictions against "
            f"{len(second.predictions)} on the second run"
        )
    for left, right in zip(first.predictions, second.predictions, strict=True):
        if left.prediction_id != right.prediction_id:
            return False, f"prediction identifiers diverge at {left.made_at}"
        if left.claim != right.claim:
            return False, f"claim differs for {left.prediction_id}"
        if left.inputs_hash != right.inputs_hash:
            return False, f"inputs hash differs for {left.prediction_id}"
    for prediction_id, outcome in first.outcomes.items():
        other = second.outcomes.get(prediction_id)
        if other is None or other.result != outcome.result:
            return False, f"outcome differs for {prediction_id}"
    if len(first.missed) != len(second.missed):
        return False, (
            f"{len(first.missed)} missed events against {len(second.missed)}"
        )
    return True, (
        f"{len(first.predictions)} predictions, {len(first.outcomes)} outcomes and "
        f"{len(first.missed)} missed events identical across two runs"
    )


def code_version() -> str:
    """The commit the evidence pack was produced from, or a marker if unknown."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def generated_at() -> datetime:
    """When this pack was produced, in the plant's own clock."""
    return datetime.now().astimezone()
