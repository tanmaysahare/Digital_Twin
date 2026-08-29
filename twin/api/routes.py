"""The HTTP surface. T-080, T-081, API_SPEC.md.

Every route holds the replay's lock for the length of one response, reads what
it needs, and lets go. The shadow-mode filter, the provenance on every value and
the refusal to publish a precision for an unpromoted predictor are all enforced
here rather than left to a client, because a client is one bug away from putting
an unpromoted forecast on a wall.

Where the twin has nothing to say yet, the route says so in the plant's own
language and with the count that would change the answer. A cold start is a
normal condition of this product, not an error, and it renders as a sentence
rather than as a spinner (UX_SPEC.md Section 9).
"""

from __future__ import annotations

import csv
import io
from collections import Counter
from datetime import datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from twin.api import serialise
from twin.api.context import CONFIG_VERSION, Context, Decision, get_context
from twin.api.schemas import (
    ActionsOut,
    BufferOut,
    ContainedUnitOut,
    CounterfactualIn,
    CounterfactualOut,
    DecisionIn,
    DecisionOut,
    EstimateOut,
    EvidenceOut,
    ForecastOut,
    HypothesisOut,
    InterventionIn,
    LinesOut,
    LineStateOut,
    MarkerOut,
    NoticeOut,
    OptionResultOut,
    PredictionRowOut,
    PredictionsOut,
    RecentEventOut,
    RetroTraceOut,
    ScorecardOut,
    SensorCardOut,
    SensorRecommendationsOut,
    SeriesPointOut,
    StationDetailOut,
    UnitDetailOut,
    UnitsAtRiskOut,
    WindowOut,
)
from twin.counterfactual.engine import Intervention, Option, RunRequest
from twin.domain.state import BufferSnapshot, LineState, StationSnapshot
from twin.forecast.attribution import ConstraintAttribution
from twin.retro.trace import ContainedUnit, RetroTrace, to_csv
from twin.sensors.value import SensorRecommendation, dark_visit_share

router = APIRouter(prefix="/api/v1")

Ctx = Annotated[Context, Depends(get_context)]

# How many points a drawer chart carries. Two hundred cycles is what
# TECHNICAL_SPEC.md Section 4.2 keeps, and drawing more would be drawing the
# window rather than the station.
CHART_POINTS = 200


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


def _not_ready(context: Context) -> HTTPException:
    """The cold start, stated with the count that would change the answer."""
    status = context.twin.status()
    return HTTPException(
        status_code=409,
        detail=(
            f"Building the line state. {status.events_fed} of "
            f"{status.events_total or 'the'} events read, "
            f"{status.cycles} forecast cycles complete. Forecasts start once "
            f"every station has a baseline."
        ),
    )


# -- state ---------------------------------------------------------------


@router.get("/lines", response_model=LinesOut)
def lines(context: Ctx) -> LinesOut:
    """Every configured line."""
    return LinesOut(lines=[serialise.line_summary(context.line, CONFIG_VERSION)])


@router.get("/config/lines/{line_id}")
def line_config(context: Ctx, line_id: str) -> dict[str, object]:
    """The line definition as loaded, so an old prediction can be interpreted."""
    _line_or_404(context, line_id)
    return {
        "line_id": context.line.line_id,
        "config_version": CONFIG_VERSION,
        "definition": context.line.model_dump(mode="json"),
    }


@router.get("/lines/{line_id}/state", response_model=LineStateOut)
def line_state(context: Ctx, line_id: str) -> LineStateOut:
    """The complete live state. The single call that fills Line view."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        if not twin.ready:
            raise _not_ready(context)
        pipeline = twin.pipeline
        state = pipeline.estimator.state()
        status = twin.status()
        shift_started, shift_id = _shift_window(context, state.at)
        drifting = frozenset(item.station_id for item in pipeline.drift.drifting())
        return serialise.line_state_out(
            context.line,
            state,
            shift=serialise.shift_out(
                context.line,
                shift_id,
                shift_started,
                pipeline.completed_since(shift_started)
                if shift_started is not None
                else pipeline.completed_units,
                state.at,
            ),
            losses=pipeline.losses.split(
                shift_started or state.at - timedelta(hours=8), state.at
            ),
            health=serialise.health_out(
                twin.source_health(),
                state,
                context.line,
                tuple(
                    f"{gap.adapter} was quiet from {gap.started_at:%H:%M:%S} "
                    f"and {gap.events_lost_estimate} events were lost with it."
                    for gap in twin.normaliser.sources.gaps()
                    if gap.is_open
                ),
            ),
            replay=serialise.replay_out(status),
            normals=context.normal_ranges(),
            drifting=drifting,
            age_s=status.behind_s,
        )


def _shift_window(context: Context, at: datetime) -> tuple[datetime | None, str | None]:
    """When the current shift started, and which one it is."""
    calendar = context.twin.calendar
    seconds = (at - calendar.epoch).total_seconds()
    window = calendar.window_at(seconds)
    if window is None:
        return None, None
    return calendar.at(window.start_s), window.shift_id


@router.get("/lines/{line_id}/forecast", response_model=ForecastOut)
def forecast(context: Ctx, line_id: str) -> ForecastOut:
    """The whole forecast. What the strip and the charts read."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        cycle = twin.pipeline.cycles[-1] if twin.pipeline.cycles else None
        if cycle is None:
            raise _not_ready(context)
        return serialise.forecast_out(cycle.summary, twin.calendar.epoch)


# -- predictions ---------------------------------------------------------


@router.get("/lines/{line_id}/actions", response_model=ActionsOut)
def actions(context: Ctx, line_id: str) -> ActionsOut:
    """The ranked action list. Published predictions only. AC-041."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        pipeline = twin.pipeline
        cycle = pipeline.cycles[-1] if pipeline.cycles else None
        if cycle is None:
            raise _not_ready(context)
        state = pipeline.estimator.state()
        return serialise.actions_of(
            context.line,
            cycle.recorded,
            cycle.forecasts,
            cycle.attribution,
            pipeline.scorecard(cycle.at),
            cycle.at,
            shadow_count=cycle.shadow_count,
            stations_running=state.running(),
            learning_note=cycle.summary.learning_note(),
        )


@router.get("/lines/{line_id}/units-at-risk", response_model=UnitsAtRiskOut)
def units_at_risk(context: Ctx, line_id: str) -> UnitsAtRiskOut:
    """The at-risk table, with a measurement where there is nothing to show."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        cycle = twin.pipeline.cycles[-1] if twin.pipeline.cycles else None
        if cycle is None:
            raise _not_ready(context)
        return serialise.units_at_risk_out(cycle.risks, cycle.at)


@router.get("/predictions/{prediction_id}/evidence", response_model=EvidenceOut)
def evidence(context: Ctx, prediction_id: UUID) -> EvidenceOut:
    """Everything behind one prediction, including its inputs hash."""
    with context.reading() as twin:
        pipeline = twin.pipeline
        try:
            prediction = pipeline.store.prediction(prediction_id)
        except KeyError as failure:
            raise HTTPException(
                status_code=404,
                detail=f"No prediction {prediction_id} is in the ledger.",
            ) from failure
        cycle = pipeline.cycles[-1] if pipeline.cycles else None
        cause = str(prediction.evidence.get("cause_station_id") or "") or (
            prediction.station_id or ""
        )
        series = pipeline.cycle_series(cause)[-CHART_POINTS:]
        markers: list[MarkerOut] = []
        drift = pipeline.drift.active(cause)
        if drift is not None:
            markers.append(serialise.drift_marker(drift))
        buffer_id, buffer_series = _buffer_series(context, cause)
        required = context.line.gates_policy.promotion.min_predictions
        record = serialise.predictor_record(
            pipeline.scorecard(prediction.made_at).row(
                prediction.predictor, prediction.station_id
            ),
            required,
        )
        notes: list[str] = []
        if not prediction.published:
            notes.append(
                "Held in shadow. This forecast was recorded and will be scored, "
                "and it was not raised to the floor."
            )
        if cycle is not None and cycle.summary.degraded:
            notes.append(
                f"Run with {cycle.summary.replications} replications rather than "
                f"the configured count."
            )
        return serialise.evidence_out(
            prediction,
            cycle_series=[
                SeriesPointOut(at=at, value=round(value, 2)) for at, value in series
            ],
            normal=context.normal_ranges().get(cause),
            markers=markers,
            buffer_series=buffer_series,
            buffer_id=buffer_id,
            attribution=(
                cycle.attribution if cycle is not None else _empty_attribution(context)
            ),
            record=record,
            notes=notes,
        )


def _empty_attribution(context: Context) -> ConstraintAttribution:
    """An attribution with nothing in it, for a prediction with no cycle behind it."""
    return ConstraintAttribution(
        at=context.twin.calendar.epoch,
        by_active_period=None,
        by_buffer_trend=None,
        agreement=True,
        ranked=(),
        unattributable=(),
        basis="no forecast cycle has run since this prediction was made",
    )


def _buffer_series(
    context: Context, station_id: str
) -> tuple[str | None, list[SeriesPointOut]]:
    """The buffer feeding a station, and its recent occupancy."""
    with context.twin.lock:
        state = context.twin.pipeline.estimator.state()
    order = context.line.station_ids
    if station_id not in order:
        return None, []
    index = order.index(station_id)
    upstream = order[index - 1] if index > 0 else None
    for buffer in state.buffers:
        if buffer.after_station_id == upstream:
            return buffer.buffer_id, [
                SeriesPointOut(at=state.at, value=buffer.occupancy.sort_key())
            ]
    return None, []


# -- drawers -------------------------------------------------------------


@router.get("/lines/{line_id}/stations/{station_id}", response_model=StationDetailOut)
def station_detail(context: Ctx, line_id: str, station_id: str) -> StationDetailOut:
    """The station drawer. UX_SPEC.md Section 6."""
    _line_or_404(context, line_id)
    if station_id not in context.line.station_ids:
        raise HTTPException(
            status_code=404,
            detail=f"{station_id} is not a station on {context.line.name}.",
        )
    with context.reading() as twin:
        pipeline = twin.pipeline
        state = pipeline.estimator.state()
        snapshot = state.station(station_id)
        zones = serialise.zone_of(context.line)
        normals = context.normal_ranges()
        drifting = frozenset(item.station_id for item in pipeline.drift.drifting())
        station = serialise.station_out(
            station_id, state, context.line, zones, normals.get(station_id), drifting
        )
        markers: list[MarkerOut] = []
        drift = pipeline.drift.active(station_id)
        if drift is not None:
            markers.append(serialise.drift_marker(drift))
        knows, unknowns = _knowledge(context, station_id, snapshot, state)
        upstream, downstream = _buffers_either_side(context, station_id, state)
        required = context.line.gates_policy.promotion.min_predictions
        scorecard = pipeline.scorecard(state.at)
        rows = [
            serialise.scorecard_row_out(row, required)
            for row in scorecard.rows
            if row.station_id == station_id
        ]
        return StationDetailOut(
            station=station,
            zone_name=next(
                (
                    zone.name
                    for zone in context.line.zones
                    if zone.zone_id == zones.get(station_id)
                ),
                "",
            ),
            time_in_state_s=round((state.at - snapshot.since).total_seconds(), 1),
            cycle_series=[
                SeriesPointOut(at=at, value=round(value, 2))
                for at, value in pipeline.cycle_series(station_id)[-CHART_POINTS:]
            ],
            normal_range=normals.get(station_id),
            markers=markers,
            knows=knows,
            does_not_know=unknowns,
            buffer_upstream=upstream,
            buffer_downstream=downstream,
            predictor_record=rows,
            sensor_card=_card_for(context, station_id),
            recent_events=_recent_events(context, station_id, state.at),
            cycles_recorded=snapshot.observed_cycles,
            cycles_required=context.line.state.min_cycles,
        )


def _knowledge(
    context: Context, station_id: str, snapshot: StationSnapshot, state: LineState
) -> tuple[list[str], list[str]]:
    """What the twin knows and does not know about one station, in sentences."""
    tier = snapshot.tier
    estimate = snapshot.last_cycle
    knows: list[str] = []
    unknowns: list[str] = []
    if tier == "C":
        if estimate is not None:
            knows.append(
                f"{station_id} has no machine data. Cycle time is bounded to "
                f"{estimate.lo:.0f} to {estimate.hi:.0f} s from the stations "
                f"either side."
            )
        unknowns.append(
            "Blocked, starved and slow work cannot be separated at this station."
        )
        for item in state.unresolved:
            if item.station_id == station_id:
                unknowns.append(
                    f"{item.reason} This would be resolved by {item.resolved_by}."
                )
    else:
        knows.append(
            f"{station_id} reports its own cycle start and stop, so its cycle "
            f"time is measured rather than derived."
        )
    if tier != "C" and snapshot.observed_cycles < context.line.state.min_cycles:
        remaining = context.line.state.min_cycles - snapshot.observed_cycles
        unknowns.append(
            f"No baseline yet. {remaining} more cycles before this station is "
            f"forecast from its own distribution."
        )
    return knows, unknowns


def _buffers_either_side(
    context: Context, station_id: str, state: LineState
) -> tuple[BufferOut | None, BufferOut | None]:
    """The buffers immediately upstream and downstream of one station."""
    order = context.line.station_ids
    index = order.index(station_id)
    upstream_of = order[index - 1] if index > 0 else None
    found_up: BufferOut | None = None
    found_down: BufferOut | None = None
    buffers: tuple[BufferSnapshot, ...] = state.buffers
    for buffer in buffers:
        if buffer.after_station_id == upstream_of:
            found_up = serialise.buffer_out(buffer)
        if buffer.after_station_id == station_id:
            found_down = serialise.buffer_out(buffer)
    return found_up, found_down


def _recent_events(
    context: Context, station_id: str, at: datetime
) -> list[RecentEventOut]:
    """The tail of what has happened at one station."""
    found: list[RecentEventOut] = []
    with context.twin.lock:
        drift = context.twin.pipeline.drift.active(station_id)
        episodes = context.twin.pipeline.observed.episodes()
    if drift is not None:
        found.append(
            RecentEventOut(
                at=drift.detected_at,
                kind="drift",
                detail=(
                    f"Cycle time {drift.magnitude_s:+.1f} s against baseline, "
                    f"running since {drift.onset_at:%H:%M}"
                ),
            )
        )
    for episode in episodes[-6:]:
        if episode.station_id != station_id:
            continue
        found.append(
            RecentEventOut(
                at=episode.started_at,
                kind=episode.dominant.lower(),
                detail=(
                    f"Lost {episode.lost_s:.0f} s in the five minutes from "
                    f"{episode.started_at:%H:%M}"
                ),
            )
        )
    del at
    return sorted(found, key=lambda item: item.at, reverse=True)[:8]


@router.get("/lines/{line_id}/units/{unit_id}", response_model=UnitDetailOut)
def unit_detail(context: Ctx, line_id: str, unit_id: str) -> UnitDetailOut:
    """The unit drawer, with the process signature as its spine."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        pipeline = twin.pipeline
        signature = pipeline.estimator.signature(unit_id)
        if signature is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"The twin has no record of unit {unit_id}. It may not have "
                    f"been released onto the line yet."
                ),
            )
        cycle = pipeline.cycles[-1] if pipeline.cycles else None
        risks = tuple(
            item for item in (cycle.risks if cycle else ()) if item.unit_id == unit_id
        )
        gates = tuple(
            (item.gate_id, item.at, item.passed)
            for item in pipeline.gate_results
            if item.unit_id == unit_id
        )
        return serialise.unit_detail_out(
            signature,
            context.line,
            normals=context.normal_ranges(),
            risks=risks,
            gates=gates,
        )


# -- the ledger ----------------------------------------------------------


@router.get("/lines/{line_id}/scorecard", response_model=ScorecardOut)
def scorecard(context: Ctx, line_id: str) -> ScorecardOut:
    """Every predictor's record. A shadow row never carries a precision."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        pipeline = twin.pipeline
        if not pipeline.cycles:
            raise _not_ready(context)
        at = pipeline.cycles[-1].at
        card = pipeline.scorecard(at)
        predictors = tuple(sorted({row.predictor for row in card.rows}))
        return serialise.scorecard_out(card, context.line, predictors)


@router.get("/lines/{line_id}/predictions", response_model=PredictionsOut)
def predictions(
    context: Ctx,
    line_id: str,
    predictor: Annotated[str | None, Query()] = None,
    station_id: Annotated[str | None, Query()] = None,
    published: Annotated[bool | None, Query()] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> PredictionsOut:
    """A page of the ledger. What the evaluation harness and Plan view read."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        store = twin.pipeline.store
        rows = [
            item
            for item in store.predictions
            if (predictor is None or item.predictor == predictor)
            and (station_id is None or item.station_id == station_id)
            and (published is None or item.published == published)
        ]
        rows.sort(key=lambda item: item.made_at, reverse=True)
        page = rows[offset : offset + limit]
        return PredictionsOut(
            line_id=line_id,
            rows=[
                PredictionRowOut(
                    prediction_id=str(item.prediction_id),
                    predictor=item.predictor,
                    station_id=item.station_id,
                    unit_id=item.unit_id,
                    made_at=item.made_at,
                    horizon_end=item.horizon_end,
                    published=item.published,
                    confidence=item.confidence,
                    claim=dict(item.claim),
                    result=(
                        outcome.result
                        if (outcome := store.outcome_of(item.prediction_id))
                        else None
                    ),
                    resolved_at=(
                        outcome.resolved_at
                        if (outcome := store.outcome_of(item.prediction_id))
                        else None
                    ),
                )
                for item in page
            ],
            total=len(rows),
            offset=offset,
            limit=limit,
        )


# -- the sandbox ---------------------------------------------------------


@router.post("/lines/{line_id}/counterfactual", response_model=CounterfactualOut)
def counterfactual(
    context: Ctx, line_id: str, request: CounterfactualIn
) -> CounterfactualOut:
    """Compare doing nothing against up to three options. Nothing is applied."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        pipeline = twin.pipeline
        if not pipeline.cycles:
            raise _not_ready(context)
        at = pipeline.cycles[-1].at
        seed = pipeline.build_seed(at)
    options = tuple(
        Option(
            label=item.label,
            interventions=tuple(_intervention(entry) for entry in item.interventions),
        )
        for item in request.options
    )
    run_id = str(uuid4())
    try:
        result = context.sandbox.run(
            seed,
            options,
            RunRequest(
                run_id=run_id,
                replications=request.replications,
                budget_s=(request.budget_ms / 1000.0) if request.budget_ms else None,
            ),
        )
    except ValueError as failure:
        raise HTTPException(status_code=422, detail=str(failure)) from failure
    epoch = context.twin.calendar.epoch
    seed_at = epoch + timedelta(seconds=result.seed_state_at_s)
    footer = (
        f"Ran {result.replications_used} replications in "
        f"{result.runtime_ms / 1000:.1f} s from the {seed_at:%H:%M:%S} state."
    )
    if result.degraded:
        footer = f"{footer} {result.degraded_note}"
    return CounterfactualOut(
        run_id=result.run_id,
        line_id=result.line_id,
        seed_state_at=seed_at,
        horizon_min=context.line.forecast.horizon_min,
        replications_used=result.replications_used,
        replications_requested=result.replications_requested,
        runtime_ms=result.runtime_ms,
        degraded=result.degraded,
        degraded_note=result.degraded_note,
        baseline_units=EstimateOut.of(result.baseline_units, "units"),
        baseline_stall_probability={
            key: round(value, 3)
            for key, value in result.baseline_stall_probability.items()
        },
        options=[
            OptionResultOut(
                label=item.label,
                units=EstimateOut.of(item.units, "units"),
                delta=EstimateOut.of(item.delta, "units"),
                stall_probability={
                    key: round(value, 3)
                    for key, value in item.stall_probability.items()
                },
                assumptions=list(item.assumptions),
                rank=item.rank,
            )
            for item in result.options
        ],
        footer=footer,
    )


def _intervention(entry: InterventionIn) -> Intervention:
    """One wire intervention as the engine's own type."""
    return Intervention(
        type=entry.type,
        station_id=entry.station_id,
        buffer_id=entry.buffer_id,
        count=entry.count,
        percent=entry.percent,
        minutes=entry.minutes,
        variant_order=tuple(entry.variant_order),
    )


@router.post("/counterfactual/{run_id}/mark-executed", response_model=DecisionOut)
def mark_executed(context: Ctx, run_id: str, request: DecisionIn) -> DecisionOut:
    """Record that an option was chosen. It changes nothing on the line."""
    with context.reading() as twin:
        at = twin.pipeline.estimator.state().at
    decision = Decision(
        run_id=run_id, label=request.label, recorded_at=at, note=request.note
    )
    context.record_decision(decision)
    return DecisionOut(
        run_id=run_id,
        label=request.label,
        recorded_at=at,
        note=request.note,
    )


# -- retro-trace ---------------------------------------------------------


def _trace_or_404(context: Context, unit_id: str) -> RetroTrace:
    """Run the walk for one unit, or say plainly why there is nothing to walk."""
    with context.reading() as twin:
        pipeline = twin.pipeline
        failures = [
            item
            for item in pipeline.gate_results
            if item.unit_id == unit_id and not item.passed
        ]
        if not failures:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Unit {unit_id} has not failed a gate, so there is nothing "
                    f"to trace back from."
                ),
            )
        last = failures[-1]
        signatures = pipeline.estimator.signatures()
    trace = context.tracer.trace(unit_id, last.gate_id, last.at, signatures)
    if trace is None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"The twin has no process signature for {unit_id}, so its "
                f"passage cannot be walked back."
            ),
        )
    context.traces[unit_id] = trace
    return trace


@router.get("/units/{unit_id}/retro-trace", response_model=RetroTraceOut)
def retro_trace(context: Ctx, unit_id: str) -> RetroTraceOut:
    """Ranked hypotheses and the containment list. AC-026 to AC-029."""
    trace = _trace_or_404(context, unit_id)
    return RetroTraceOut(
        unit_id=trace.unit_id,
        line_id=trace.line_id,
        failed_at_gate=trace.failed_at_gate,
        failed_at=trace.failed_at,
        hypotheses=[
            HypothesisOut(
                rank=item.rank,
                station_id=item.station_id,
                window=WindowOut(from_at=item.window_from, to_at=item.window_to),
                divergence=round(item.divergence, 2),
                strength=item.strength,
                description=item.description,
                shared_attribute=(
                    {
                        "type": item.shared_attribute.kind,
                        "value": item.shared_attribute.value,
                    }
                    if item.shared_attribute is not None
                    else None
                ),
                population=item.population,
            )
            for item in trace.hypotheses
        ],
        on_line=[_contained(item) for item in trace.on_line],
        in_yard=[_contained(item) for item in trace.in_yard],
        shipped=[_contained(item) for item in trace.shipped],
        counts=trace.counts,
        runtime_s=round(trace.runtime_s, 3),
        disclaimer=trace.disclaimer,
    )


def _contained(item: ContainedUnit) -> ContainedUnitOut:
    """One containment row."""
    return ContainedUnitOut(
        unit_id=item.unit_id,
        similarity=round(item.similarity, 2),
        at=item.at,
        evidence=list(item.evidence),
    )


@router.get("/units/{unit_id}/retro-trace/export")
def retro_trace_export(context: Ctx, unit_id: str) -> Response:
    """The containment list as a CSV a quality engineer can work from. AC-028."""
    trace = _trace_or_404(context, unit_id)
    return Response(
        content=to_csv(trace),
        media_type="text/csv",
        headers={
            "Content-Disposition": (f'attachment; filename="containment-{unit_id}.csv"')
        },
    )


# -- sensor value --------------------------------------------------------


def sensor_queue(context: Context) -> tuple[SensorRecommendation, ...]:
    """Every card the observability and criticality gate lets through.

    Public because Plan view's instrumentation cost is this queue's total,
    and a second implementation of it would be a second answer to the same
    question.
    """
    with context.reading() as twin:
        pipeline = twin.pipeline
        state = pipeline.estimator.state()
        cycles = pipeline.cycles
        counts: dict[str, int] = {}
        for cycle in cycles:
            named = cycle.attribution.by_active_period
            if named:
                counts[named] = counts.get(named, 0) + 1
        signatures = pipeline.estimator.signatures()
        loss = cycles[-1].summary.expected_unit_loss.sort_key() if cycles else 0.0
        sensors = pipeline.estimator.sensors
        observability = context.sensors.observability(state, sensors)
        criticality = context.sensors.criticality(
            Counter(counts), len(cycles), dark_visit_share(signatures)
        )
        return context.sensors.recommend(
            observability, criticality, expected_unit_loss=loss, at=state.at
        )


def _card(item: SensorRecommendation) -> SensorCardOut:
    """One Sensor Value Card on the wire."""
    return SensorCardOut(
        rec_id=item.rec_id,
        station_id=item.station_id,
        unknown=item.unknown,
        option_id=item.option.option_id,
        option_name=item.option.name,
        signal_provided=item.option.signal_provided,
        indicative_cost_usd=item.option.indicative_cost_usd,
        cost_source=item.cost_source,
        install_hours=item.option.install_hours,
        requires_window=item.option.requires_window,
        next_window=item.next_window,
        confidence_now=round(item.confidence_now, 2),
        confidence_projected=round(item.confidence_projected, 2),
        confidence_projected_lo=round(item.confidence_projected_lo, 2),
        confidence_projected_hi=round(item.confidence_projected_hi, 2),
        resolves=item.resolves,
        criticality=round(item.criticality.score, 2),
        criticality_basis=item.criticality.basis,
        modelled_annual_value=EstimateOut.of(item.modelled_annual_value, "USD"),
        status=item.status,
    )


def _card_for(context: Context, station_id: str) -> SensorCardOut | None:
    """The card for one station, if the gate generated one."""
    for item in sensor_queue(context):
        if item.station_id == station_id:
            return _card(item)
    return None


@router.get(
    "/lines/{line_id}/sensor-recommendations",
    response_model=SensorRecommendationsOut,
)
def sensor_recommendations(context: Ctx, line_id: str) -> SensorRecommendationsOut:
    """The sensor investment queue, ranked by modelled value. AC-052."""
    _line_or_404(context, line_id)
    with context.reading() as twin:
        at = twin.pipeline.estimator.state().at
    return SensorRecommendationsOut(
        line_id=line_id,
        as_of=at,
        recommendations=[_card(item) for item in sensor_queue(context)],
        currency=context.catalogue.currency,
        note=context.catalogue.note,
    )


@router.get("/lines/{line_id}/sensor-recommendations/export")
def sensor_recommendations_export(context: Ctx, line_id: str) -> Response:
    """The queue as a CSV suitable for a capital request."""
    _line_or_404(context, line_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "station",
            "what is unknown",
            "proposed sensor",
            "signal",
            "confidence now",
            "confidence projected",
            "indicative cost",
            "cost basis",
            "install hours",
            "next window",
            "modelled annual value low",
            "modelled annual value high",
            "value basis",
        ]
    )
    for item in sensor_queue(context):
        writer.writerow(
            [
                item.station_id,
                item.unknown,
                item.option.name,
                item.option.signal_provided,
                f"{item.confidence_now:.2f}",
                f"{item.confidence_projected:.2f}",
                f"{item.option.indicative_cost_usd:.0f}",
                item.cost_source,
                f"{item.option.install_hours:.1f}",
                item.next_window,
                f"{item.modelled_annual_value.lo:.0f}",
                f"{item.modelled_annual_value.hi:.0f}",
                item.modelled_annual_value.basis,
            ]
        )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="sensor-queue-{line_id}.csv"'
            )
        },
    )


# -- notices -------------------------------------------------------------


@router.get("/lines/{line_id}/notices", response_model=list[NoticeOut])
def notices(context: Ctx, line_id: str) -> list[NoticeOut]:
    """Everything the interface has to say and keep saying. UX_SPEC.md Section 9."""
    _line_or_404(context, line_id)
    found: list[NoticeOut] = []
    with context.reading() as twin:
        status = twin.status()
        pipeline = twin.pipeline
        cycle = pipeline.cycles[-1] if pipeline.cycles else None
        if status.warming:
            found.append(
                NoticeOut(
                    tone="neutral",
                    text="Building the line state.",
                    detail=(
                        f"{status.events_fed} events read. Forecasts start once "
                        f"every station has a baseline."
                    ),
                )
            )
        if status.finished:
            found.append(
                NoticeOut(
                    tone="neutral",
                    text="The replayed run has finished.",
                    detail=status.note,
                )
            )
        if cycle is not None:
            for decision in cycle.decisions:
                if not decision.changed:
                    continue
                found.append(
                    NoticeOut(
                        tone=("attention" if decision.now != "ACTIVE" else "neutral"),
                        text=(
                            f"{decision.predictor} at "
                            f"{decision.station_id or context.line.line_id} moved to "
                            f"{decision.now.lower()}."
                        ),
                        detail=decision.reason,
                    )
                )
            if cycle.summary.learning_stations:
                found.append(
                    NoticeOut(
                        tone="neutral",
                        text="No stall forecast yet.",
                        detail=cycle.summary.learning_note(),
                    )
                )
    return found
