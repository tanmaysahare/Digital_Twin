"""Plan and Program view endpoints. T-110, T-117, T-118, T-122.

Everything here is computed from what the twin has actually recorded. The
constraint heatmap counts the cycles in which each station was named; the loss
Pareto is the same accounting the Line view shows, over a longer window and with
the same reconciliation line under it; the recommendation table's modelled
effects come from the counterfactual engine rather than from a table of
plausible numbers; and site readiness is scored from the stream rather than from
a survey.

Where a figure could not be computed the response says so in the same sentence
it would have used to report it. There is no panel here that renders a shape
with nothing behind it.
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from twin.api.context import Context, get_context
from twin.api.routes import sensor_queue
from twin.api.schemas import (
    AssumptionOut,
    BusinessCaseIn,
    BusinessCaseOut,
    ConstraintCellOut,
    ConstraintMigrationOut,
    EstimateOut,
    InterventionIn,
    LossParetoOut,
    OptionIn,
    ParetoRowOut,
    ReadinessComponentOut,
    RealisedOut,
    RealisedRowOut,
    RecommendationOut,
    RecommendationsOut,
    SensitivityRowOut,
    SiteReadinessOut,
    SitesOut,
    TopologyDraftOut,
    TopologyFieldOut,
)
from twin.config.loader import load_line_definition
from twin.counterfactual.engine import Intervention, Option, RunRequest
from twin.forecast.attribution import ConstraintAttribution
from twin.ledger.store import STALL_FORECASTER
from twin.program import business_case
from twin.program.readiness import SiteReadiness, StreamReading, measure, score
from twin.sensors.value import SensorRecommendation
from twin.state.losses import CAUSES
from twin.topology.discover import InferredField, TopologyDiscoverer

plan_router = APIRouter(prefix="/api/v1")

Ctx = Annotated[Context, Depends(get_context)]

REPO_ROOT = Path(__file__).resolve().parents[2]
LINES_DIR = REPO_ROOT / "config" / "lines"

# How the constraint heatmap divides the range. Hours rather than weeks, because
# a prototype replaying one day of production has no weeks in it and a column
# per week would be one column. The period label says which it is.
PERIOD_MIN = 60

# The share above which a heatmap cell carries a direct numeric label (AC-060).
LABEL_ABOVE = 0.20

# How many events the topology draft reads before it answers. The draft is a
# read over a stream rather than a live view, and reading the whole of a long
# one on every request would make the endpoint the slowest in the API.
TOPOLOGY_EVENTS = 40000


def _line_or_404(context: Context, line_id: str) -> None:
    """Fail with a sentence a person can act on, not a code."""
    if line_id != context.line.line_id:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No line called {line_id} is configured. This deployment runs "
                f"{context.line.line_id}."
            ),
        )


# -- Plan view -----------------------------------------------------------


@plan_router.get(
    "/lines/{line_id}/plan/constraint-migration",
    response_model=ConstraintMigrationOut,
)
def constraint_migration(context: Ctx, line_id: str) -> ConstraintMigrationOut:
    """Which station has been holding the line back, over time. AC-060."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        cycles = twin.pipeline.cycles
        epoch = twin.calendar.epoch
    if not cycles:
        return ConstraintMigrationOut(
            line_id=line_id,
            periods=[],
            stations=[],
            cells=[],
            current_constraint=None,
            note=(
                "No forecast cycle has run yet, so no station has been named "
                "the constraint."
            ),
        )
    counts: Counter[tuple[str, str]] = Counter()
    totals: Counter[str] = Counter()
    for cycle in cycles:
        named = cycle.attribution.by_active_period
        period = _period(cycle.at, epoch)
        totals[period] += 1
        if named:
            counts[(named, period)] += 1
    periods = sorted(totals)
    stations = sorted({station for station, _ in counts})
    cells = [
        ConstraintCellOut(
            station_id=station,
            period=period,
            share=round(counts[(station, period)] / totals[period], 3),
        )
        for station in stations
        for period in periods
        if totals[period] and counts[(station, period)]
    ]
    return ConstraintMigrationOut(
        line_id=line_id,
        periods=periods,
        stations=stations,
        cells=cells,
        current_constraint=cycles[-1].attribution.by_active_period,
        note=(
            f"Share of the forecast cycles in each hour in which the station was "
            f"named the constraint by average active period. Cells above "
            f"{LABEL_ABOVE:.0%} carry their number."
        ),
    )


def _period(at: datetime, epoch: datetime) -> str:
    """Which period one instant falls in, labelled as the plant reads a clock."""
    del epoch
    return f"{at:%d %b %H}:00"


@plan_router.get("/lines/{line_id}/plan/loss-pareto", response_model=LossParetoOut)
def loss_pareto(
    context: Ctx,
    line_id: str,
    hours: Annotated[int, Query(ge=1, le=168)] = 8,
) -> LossParetoOut:
    """Lost minutes by cause, with the reconciliation line under it. AC-061."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        at = twin.pipeline.estimator.state().at
        split = twin.pipeline.losses.split(at - timedelta(hours=hours), at)
    total = split.accounted_min or 1.0
    rows = sorted(
        (
            ParetoRowOut(
                cause=cause,
                minutes=round(split.minutes.get(cause, 0.0), 1),
                share=round(split.minutes.get(cause, 0.0) / total, 3),
            )
            for cause in CAUSES
        ),
        key=lambda row: -row.minutes,
    )
    return LossParetoOut(
        line_id=line_id,
        from_at=split.from_at,
        to_at=split.to_at,
        rows=rows,
        reconciliation=split.reconciliation(),
        unexplained_min=round(split.unexplained_min, 1),
        unexplained_share=split.unexplained_share,
    )


@plan_router.get(
    "/lines/{line_id}/plan/recommendations", response_model=RecommendationsOut
)
def recommendations(context: Ctx, line_id: str) -> RecommendationsOut:
    """Buffer and staffing changes, each modelled rather than asserted. AC-062."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        cycles = twin.pipeline.cycles
        if not cycles:
            return RecommendationsOut(
                line_id=line_id,
                as_of=twin.calendar.epoch,
                rows=[],
                note=(
                    "No forecast cycle has run yet, so nothing has been modelled "
                    "and there is nothing to recommend."
                ),
            )
        cycle = cycles[-1]
        seed = twin.pipeline.build_seed(cycle.at)
    candidates = _candidates(context, cycle.attribution)
    if not candidates:
        return RecommendationsOut(
            line_id=line_id,
            as_of=cycle.at,
            rows=[],
            note=(
                "No station has been named the constraint often enough to model "
                "a change against."
            ),
        )
    result = context.sandbox.run(
        seed,
        tuple(option for option, _ in candidates),
        RunRequest(run_id=str(uuid4())),
    )
    modelled = {item.label: item for item in result.options}
    rows: list[RecommendationOut] = []
    for option, wire in candidates:
        outcome = modelled.get(option.label)
        if outcome is None:
            continue
        rows.append(
            RecommendationOut(
                rec_id=f"{line_id}:{option.label}",
                change=option.label,
                station_id=option.interventions[0].station_id,
                buffer_id=option.interventions[0].buffer_id,
                modelled_effect=EstimateOut.of(outcome.delta, "units"),
                assumptions=list(outcome.assumptions),
                sandbox=wire,
            )
        )
    rows.sort(key=lambda row: -row.modelled_effect.hi)
    return RecommendationsOut(
        line_id=line_id,
        as_of=cycle.at,
        rows=rows,
        note=(
            f"Each row is {result.replications_used} replications against the "
            f"same replications of doing nothing, on shared seeds, from the "
            f"{cycle.at:%H:%M:%S} state."
        ),
    )


def _candidates(
    context: Context, attribution: ConstraintAttribution
) -> list[tuple[Option, OptionIn]]:
    """The changes worth modelling, chosen from what the line is actually doing."""
    named = attribution.by_active_period
    if not named:
        return []
    order = context.line.station_ids
    index = order.index(named) if named in order else 0
    upstream = order[index - 1] if index > 0 else None
    found: list[tuple[Option, OptionIn]] = []
    operator = Intervention(type="ADD_OPERATOR", station_id=named, count=1)
    found.append(
        (
            Option(label=f"Add an operator at {named}", interventions=(operator,)),
            OptionIn(
                label=f"Add an operator at {named}",
                interventions=[
                    InterventionIn(type="ADD_OPERATOR", station_id=named, count=1)
                ],
            ),
        )
    )
    buffer = next(
        (item for item in context.line.buffers if item.after == upstream), None
    )
    if buffer is not None:
        capacity = buffer.capacity + 2
        change = Intervention(
            type="CHANGE_BUFFER_TARGET", buffer_id=buffer.buffer_id, count=capacity
        )
        label = f"Raise {buffer.buffer_id} to {capacity} places"
        found.append(
            (
                Option(label=label, interventions=(change,)),
                OptionIn(
                    label=label,
                    interventions=[
                        InterventionIn(
                            type="CHANGE_BUFFER_TARGET",
                            buffer_id=buffer.buffer_id,
                            count=capacity,
                        )
                    ],
                ),
            )
        )
    slow = Intervention(type="CHANGE_TAKT", percent=-4.0)
    found.append(
        (
            Option(label="Slow takt by 4 percent", interventions=(slow,)),
            OptionIn(
                label="Slow takt by 4 percent",
                interventions=[InterventionIn(type="CHANGE_TAKT", percent=-4.0)],
            ),
        )
    )
    return found


# -- Program view --------------------------------------------------------


def _readiness(context: Context) -> tuple[SiteReadiness, ...]:
    """Every configured site, scored from its own stream where there is one."""
    found: list[SiteReadiness] = []
    running = context.line.line_id
    with context.reading() as twin:
        pipeline = twin.pipeline
        state = pipeline.estimator.state()
        signatures = pipeline.estimator.signatures()
        reading = StreamReading(
            stations_emitting=sum(
                1 for item in state.stations if item.observed_cycles > 0
            ),
            units_with_full_signature=sum(
                1
                for item in signatures
                if item.visits and item.status in {"COMPLETED", "IN_PROCESS"}
            ),
            units_seen=len(signatures),
            inspection_results=len(pipeline.gate_results),
            max_skew_s=twin.normaliser.skew.worst(),
            events_seen=twin.status().events_fed,
        )
    cost = sum(item.option.indicative_cost_usd for item in _sensor_costs(context))
    found.append(score(context.line, measure(context.line, reading), cost))
    for path in sorted(LINES_DIR.glob("*.yaml")):
        line = load_line_definition(path)
        if line.line_id == running:
            continue
        found.append(score(line, measure(line, StreamReading()), 0.0))
    return tuple(found)


def _sensor_costs(context: Context) -> tuple[SensorRecommendation, ...]:
    """The running line's sensor queue, for the instrumentation figure."""
    return sensor_queue(context)


@plan_router.get("/program/sites", response_model=SitesOut)
def sites(context: Ctx) -> SitesOut:
    """Readiness per site with every component it was scored on. AC-070."""
    return SitesOut(
        sites=[
            SiteReadinessOut(
                site_id=item.site_id,
                name=item.name,
                band=item.band,
                score=item.score,
                components=[
                    ReadinessComponentOut(
                        name=part.name,
                        value=part.value,
                        score=round(part.score, 2),
                        weight=part.weight,
                        missing=part.missing,
                    )
                    for part in item.components
                ],
                missing=list(item.missing),
                instrumentation_cost_usd=round(item.instrumentation_cost_usd, 2),
                note=item.note,
            )
            for item in _readiness(context)
        ],
        computed_from=(
            "Each component is counted from the site's own event stream. A site "
            "with no stream connected is scored on its line definition alone and "
            "says so."
        ),
    )


def _measured_precision(context: Context) -> tuple[float | None, str]:
    """The ledger's own precision for the stall forecaster, and where it came from."""
    with context.reading() as twin:
        cycles = twin.pipeline.cycles
        if not cycles:
            return None, (
                "No prediction has been scored yet, so there is no measured "
                "precision and this field is zero."
            )
        card = twin.pipeline.scorecard(cycles[-1].at)
    totals = card.totals(STALL_FORECASTER)
    if totals.precision is None:
        return None, (
            f"{totals.made} predictions recorded and none scored yet, so there "
            f"is no measured precision and this field is zero."
        )
    return totals.precision, (
        f"Measured from the ledger: {totals.true_positive} hits in "
        f"{totals.scored} scored predictions over {card.window_days} days. "
        f"Not a target."
    )


def _assumptions(context: Context) -> tuple[business_case.Assumption, ...]:
    """The default assumption set for the running line."""
    precision, basis = _measured_precision(context)
    cost = sum(item.option.indicative_cost_usd for item in _sensor_costs(context))
    return business_case.defaults(
        measured_precision=precision,
        precision_basis=basis,
        instrumentation_cost_usd=cost,
        unit_value_usd=context.line.sensors.unit_value_usd,
    )


def _case_out(result: business_case.CaseResult) -> BusinessCaseOut:
    """One computed case on the wire."""
    return BusinessCaseOut(
        scenario_id=result.scenario_id,
        assumptions=[
            AssumptionOut(
                key=item.key,
                label=item.label,
                value=item.value,
                unit=item.unit,
                source=item.source,
                uncertainty=item.uncertainty,
                editable=item.editable,
            )
            for item in result.assumptions
        ],
        annual_benefit=EstimateOut.of(result.annual_benefit, "USD"),
        payback_months=result.payback_months,
        sensitivity=[
            SensitivityRowOut(
                key=row.key,
                label=row.label,
                low_result=row.low_result,
                high_result=row.high_result,
                swing=round(row.swing, 2),
            )
            for row in result.sensitivity
        ],
        notes=list(result.notes),
    )


@plan_router.get("/program/business-case", response_model=BusinessCaseOut)
def business_case_get(context: Ctx) -> BusinessCaseOut:
    """The case as it stands, with the ledger's own precision in it."""
    return _case_out(business_case.evaluate(_assumptions(context)))


@plan_router.post("/program/business-case", response_model=BusinessCaseOut)
def business_case_post(context: Ctx, request: BusinessCaseIn) -> BusinessCaseOut:
    """Recalculate against edited assumptions. Nothing is persisted globally."""
    edited = business_case.apply(_assumptions(context), request.values)
    return _case_out(business_case.evaluate(edited, scenario_id=str(uuid4())))


@plan_router.get("/program/realised", response_model=RealisedOut)
def realised(context: Ctx) -> RealisedOut:
    """Modelled against realised, which reads correctly with a negative gap."""
    result = business_case.evaluate(_assumptions(context))
    with context.reading() as twin:
        decisions = len(context.decisions)
        interventions = len(context.interventions)
        cycles = twin.pipeline.cycles
    rows = [
        RealisedRowOut(
            site_id=context.line.line_id,
            measure="Annual benefit",
            modelled=round(result.annual_benefit.sort_key(), 2),
            realised=None,
            gap=None,
            unit="USD",
            evidence=(
                f"{decisions} decisions and {interventions} carried-out "
                f"interventions are recorded against this line. A realised "
                f"figure needs an intervention whose effect has been scored, "
                f"and none has closed yet."
            ),
        ),
        RealisedRowOut(
            site_id=context.line.line_id,
            measure="Forecast cycles run",
            modelled=float(len(cycles)),
            realised=float(len(cycles)),
            gap=0.0,
            unit="cycles",
            evidence="Counted from the ledger.",
        ),
    ]
    return RealisedOut(
        rows=rows,
        note=(
            "A realised figure appears here only once an intervention recorded "
            "in the sandbox has been carried out and its window has closed. "
            "Until then the column is empty rather than optimistic."
        ),
    )


@plan_router.get("/lines/{line_id}/topology-draft", response_model=TopologyDraftOut)
def topology_draft(context: Ctx, line_id: str) -> TopologyDraftOut:
    """A line definition drafted from the stream. Blanks are marked. AC-081."""
    _line_or_404(context, line_id)
    discoverer = TopologyDiscoverer()
    with context.reading() as twin:
        events = twin.events_seen(TOPOLOGY_EVENTS)
    for event in events:
        discoverer.observe(event)
    draft = discoverer.draft()
    return TopologyDraftOut(
        line_id=draft.line_id,
        observed_events=draft.observed_events,
        fields=[_field(item) for item in draft.fields],
        stations=[_field(item) for item in draft.stations],
        not_inferable=list(draft.not_inferable),
        note=draft.note,
    )


def _field(item: InferredField) -> TopologyFieldOut:
    """One inferred field on the wire."""
    return TopologyFieldOut(
        field=item.field,
        value=item.value,
        confidence=item.confidence,
        inferred_from=item.inferred_from,
        note=item.note,
    )


@plan_router.get("/lines/{line_id}/plan/loss-pareto/export")
def loss_pareto_export(
    context: Ctx,
    line_id: str,
    hours: Annotated[int, Query(ge=1, le=168)] = 8,
) -> Response:
    """The loss split as a CSV, with the reconciliation line in it."""
    result = loss_pareto(context, line_id, hours)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["cause", "minutes", "share of accounted"])
    for row in result.rows:
        writer.writerow([row.cause, f"{row.minutes:.1f}", f"{row.share:.3f}"])
    writer.writerow([])
    writer.writerow(["reconciliation", result.reconciliation])
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="loss-{line_id}.csv"'},
    )
