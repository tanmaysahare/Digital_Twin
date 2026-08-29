"""Turning the twin's own types into the wire shapes. API_SPEC.md.

This layer exists so that the domain types never grow a `to_json`. A
`StationSnapshot` knows what a station is doing; it should not know that an
interface exists. Everything that knows about both lives here.

Two rules are enforced in this file rather than trusted to a caller.

**Nothing leaves without a provenance.** `EstimateOut.of` is the only path from
an `Estimate` to a response, and it carries the provenance and the basis with
it. There is no branch here that turns an interval into a midpoint.

**A shadow prediction never becomes an action.** `actions_of` reads
`prediction.published`, which the pipeline set from the ledger's gate decision at
the moment the prediction was made. The filter is here, at the boundary, and not
in the client.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

from connector.protocol import SourceHealth
from twin.api.schemas import (
    ActionOut,
    ActionsOut,
    AttributionRowOut,
    BucketOut,
    BufferForecastOut,
    BufferOut,
    CauseOut,
    DataHealthOut,
    EstimateOut,
    EvidenceOut,
    FactorOut,
    ForecastOut,
    GateOut,
    GateResultOut,
    HighestBelowOut,
    LineStateOut,
    LineSummaryOut,
    LossOut,
    MarkerOut,
    PredictorRecordOut,
    RangeOut,
    ReplayOut,
    ScorecardOut,
    ScorecardRowOut,
    SeriesPointOut,
    ShiftOut,
    StationForecastOut,
    StationOut,
    StationVisitOut,
    UnitAtRiskOut,
    UnitDetailOut,
    UnitsAtRiskOut,
    UnresolvedOut,
    WindowOut,
    ZoneOut,
)
from twin.config.line import LineDefinition
from twin.defect.risk import UnitRisk
from twin.domain.estimate import Estimate, Interval
from twin.domain.signature import ProcessSignature
from twin.domain.state import BufferSnapshot, LineState
from twin.forecast.aggregate import ForecastSummary
from twin.forecast.attribution import ConstraintAttribution
from twin.forecast.drift import DriftEstimate
from twin.forecast.stall import StallForecast
from twin.ledger.scorecard import Scorecard, ScorecardRow
from twin.ledger.store import Prediction
from twin.live import LiveStatus
from twin.state.losses import LossSplit

# The risk above which a unit appears in the at-risk table. Not a plant value:
# it is the threshold the interface uses to decide what is worth a supervisor's
# attention, and the response carries it so the client never invents its own.
RISK_THRESHOLD = 0.45

# How many at-risk rows the table shows before it states how many more (EC-48).
MAX_AT_RISK_ROWS = 8


def line_summary(line: LineDefinition, config_version: str) -> LineSummaryOut:
    """One line's shape, as `/lines` lists it."""
    tiers = Counter(station.tier for station in line.stations)
    return LineSummaryOut(
        line_id=line.line_id,
        name=line.name,
        takt_s=line.takt_s,
        stations=len(line.stations),
        tiers={tier: tiers.get(tier, 0) for tier in ("A", "B", "C")},
        config_version=config_version,
        zones=[
            ZoneOut(
                zone_id=zone.zone_id,
                name=zone.name,
                from_station_id=zone.span[0],
                to_station_id=zone.span[1],
            )
            for zone in line.zones
        ],
        gates=[
            GateOut(gate_id=gate.gate_id, name=gate.name, after_station_id=gate.after)
            for gate in line.gates
        ],
    )


def zone_of(line: LineDefinition) -> dict[str, str]:
    """Which zone each station sits in."""
    order = line.station_ids
    found: dict[str, str] = {}
    for zone in line.zones:
        start = order.index(zone.span[0])
        end = order.index(zone.span[1])
        for station_id in order[start : end + 1]:
            found[station_id] = zone.zone_id
    return found


def station_out(
    station_id: str,
    state: LineState,
    line: LineDefinition,
    zones: dict[str, str],
    normal: RangeOut | None,
    drifting: frozenset[str],
) -> StationOut:
    """One station's live row, with its flags in the order the strip reads them."""
    snapshot = state.station(station_id)
    flags: list[str] = []
    if snapshot.tier == "C":
        flags.append("NO_MACHINE_DATA")
    if snapshot.resolution == "UNRESOLVED":
        flags.append("UNRESOLVED")
    if station_id in drifting:
        flags.append("DRIFTING")
    if snapshot.state in {"BLOCKED", "STARVED", "DOWN"}:
        flags.append(snapshot.state)
    return StationOut(
        station_id=station_id,
        seq=line.station_ids.index(station_id) + 1,
        zone_id=zones.get(station_id, ""),
        tier=snapshot.tier,
        state=snapshot.state,
        since=snapshot.since,
        current_unit_id=snapshot.current_unit_id,
        cycle_time=(
            EstimateOut.of(snapshot.last_cycle, "s")
            if snapshot.last_cycle is not None
            else None
        ),
        normal_range=normal,
        observed_cycles=snapshot.observed_cycles,
        flags=flags,
        basis=snapshot.basis,
    )


def buffer_out(buffer: BufferSnapshot) -> BufferOut:
    """One buffer's occupancy against its capacity."""
    return BufferOut(
        buffer_id=buffer.buffer_id,
        after_station_id=buffer.after_station_id,
        occupancy=EstimateOut.of(buffer.occupancy, "units"),
        capacity=buffer.capacity,
        trend=buffer.trend,
    )


def loss_out(split: LossSplit) -> LossOut:
    """The loss split with its reconciliation line attached."""
    return LossOut(
        minutes={name: round(value, 1) for name, value in split.minutes.items()},
        accounted_min=round(split.accounted_min, 1),
        implied_total_min=round(split.implied_total_min, 1),
        unexplained_min=round(split.unexplained_min, 1),
        unexplained_share=split.unexplained_share,
        reconciliation=split.reconciliation(),
    )


def replay_out(status: LiveStatus) -> ReplayOut:
    """What the replay behind the prototype is doing."""
    return ReplayOut(
        ready=status.ready,
        warming=status.warming,
        speed=status.speed,
        scenario_id=status.scenario_id,
        seed=status.seed,
        events_total=status.events_total,
        events_fed=status.events_fed,
        cycles=status.cycles,
        behind_s=round(status.behind_s, 1),
        finished=status.finished,
        note=status.note,
    )


def health_out(
    sources: tuple[SourceHealth, ...],
    state: LineState,
    line: LineDefinition,
    open_gaps: tuple[str, ...],
) -> DataHealthOut:
    """Data health, with a sentence per problem rather than a code."""
    live = sum(1 for item in sources if item.state == "LIVE")
    last = max(
        (item.last_event_at for item in sources if item.last_event_at is not None),
        default=None,
    )
    skew = max((abs(item.estimated_skew_s or 0.0) for item in sources), default=0.0)
    dark = sum(1 for station in line.stations if station.tier == "C")
    reporting = sum(
        1
        for station in state.stations
        if station.tier != "C" and station.observed_cycles > 0
    )
    notes: list[str] = []
    if live < len(sources):
        silent = [item.adapter for item in sources if item.state != "LIVE"]
        notes.append(
            f"Source {', '.join(silent)} has gone quiet. Forecasts for the "
            f"stations it covers are paused rather than estimated."
        )
    for gap in open_gaps:
        notes.append(gap)
    return DataHealthOut(
        sources_live=live,
        sources_total=len(sources),
        last_event_at=last,
        max_skew_s=round(skew, 2),
        stations_reporting=reporting,
        stations_dark_by_design=dark,
        open_gaps=list(open_gaps),
        notes=notes,
    )


def shift_out(
    line: LineDefinition,
    shift_id: str | None,
    started_at: datetime | None,
    completed: int,
    at: datetime,
) -> ShiftOut:
    """Output against target, and how far off the pace the line is."""
    target = _shift_target(line)
    if started_at is None:
        return ShiftOut(
            shift_id=shift_id,
            started_at=None,
            target_units=target,
            completed=completed,
            pace_delta_units=0,
            pace_note="pace not yet measurable",
        )
    elapsed = max(0.0, (at - started_at).total_seconds())
    expected = int(elapsed / max(1.0, line.takt_s))
    delta = completed - expected
    if delta == 0:
        note = "pace on target"
    elif delta < 0:
        note = f"pace {abs(delta)} units behind"
    else:
        note = f"pace {delta} units ahead"
    return ShiftOut(
        shift_id=shift_id,
        started_at=started_at,
        target_units=target,
        completed=completed,
        pace_delta_units=delta,
        pace_note=note,
    )


def _shift_target(line: LineDefinition) -> int:
    """How many units one shift allows for, from the shift definition itself."""
    if not line.shifts:
        return 0
    shift = line.shifts[0]
    start = shift.start.hour * 3600 + shift.start.minute * 60
    end = shift.end.hour * 3600 + shift.end.minute * 60
    span = (end - start) % (24 * 3600)
    producing = span - shift.break_min * 60 - shift.changeover_min * 60
    return int(max(0.0, producing) / max(1.0, line.takt_s))


def line_state_out(
    line: LineDefinition,
    state: LineState,
    *,
    shift: ShiftOut,
    losses: LossSplit,
    health: DataHealthOut,
    replay: ReplayOut,
    normals: dict[str, RangeOut | None],
    drifting: frozenset[str],
    age_s: float,
) -> LineStateOut:
    """The whole live state in one response."""
    zones = zone_of(line)
    return LineStateOut(
        line_id=line.line_id,
        as_of=state.at,
        age_s=round(age_s, 1),
        shift=shift,
        stations=[
            station_out(
                station.station_id,
                state,
                line,
                zones,
                normals.get(station.station_id),
                drifting,
            )
            for station in line.stations
        ],
        buffers=[buffer_out(item) for item in state.buffers],
        unresolved=[
            UnresolvedOut(
                station_id=item.station_id,
                reason=item.reason,
                resolved_by=item.resolved_by,
            )
            for item in state.unresolved
        ],
        loss_this_shift=loss_out(losses),
        data_health=health,
        replay=replay,
    )


def normal_range(median: float, scale: float) -> RangeOut:
    """A station's normal band, as the strip's range plot draws it.

    Two robust standard deviations either side of the median. Wide enough that
    an ordinary cycle sits inside it and narrow enough that a drift leaves it,
    which is what the bar has to show at a glance.
    """
    return RangeOut(lo=median - 2.0 * scale, hi=median + 2.0 * scale, unit="s")


# -- predictions ---------------------------------------------------------


def predictor_record(row: ScorecardRow | None, required: int) -> PredictorRecordOut:
    """One predictor's record, declining to give a precision while in shadow."""
    if row is None:
        return PredictorRecordOut(
            state="SHADOW",
            made=0,
            hits=None,
            precision=None,
            median_lead_min=None,
            required=required,
            note=(
                f"Learning. 0 of the {required} predictions needed before "
                f"alerts start here."
            ),
        )
    if row.state != "ACTIVE":
        return PredictorRecordOut(
            state=row.state,
            made=row.made,
            hits=None,
            precision=None,
            median_lead_min=None,
            required=required,
            note=(
                row.state_reason
                or f"Learning. {row.made} of the {required} predictions needed "
                f"before alerts start here."
            ),
        )
    lead = row.median_lead_s / 60.0 if row.median_lead_s is not None else None
    return PredictorRecordOut(
        state=row.state,
        made=row.made,
        hits=row.true_positive,
        precision=row.precision,
        median_lead_min=lead,
        required=None,
        note=(
            f"Right on {row.true_positive} of {row.scored} forecasts at "
            f"{row.station_id or 'this line'} over the last "
            f"{row.shifts_in_window:.0f} shifts."
        ),
    )


def actions_of(
    line: LineDefinition,
    predictions: tuple[Prediction, ...],
    forecasts: tuple[StallForecast, ...],
    attribution: ConstraintAttribution,
    scorecard: Scorecard,
    at: datetime,
    *,
    shadow_count: int,
    stations_running: int,
    learning_note: str,
) -> ActionsOut:
    """The ranked action list. Published predictions only. AC-041."""
    by_station = {item.station_id: item for item in forecasts}
    required = line.gates_policy.promotion.min_predictions
    rows: list[ActionOut] = []
    for prediction in predictions:
        if not prediction.published:
            continue
        kind = str(prediction.claim.get("kind", ""))
        if kind == "DRIFT":
            rows.append(_drift_action(prediction, scorecard, required))
            continue
        if kind != "STALL_FORECAST":
            continue
        station_id = prediction.station_id or ""
        forecast = by_station.get(station_id)
        if forecast is None:
            continue
        record = predictor_record(
            scorecard.row(prediction.predictor, station_id), required
        )
        rows.append(
            ActionOut(
                prediction_id=str(prediction.prediction_id),
                predictor=prediction.predictor,
                kind="STALL_FORECAST",
                station_id=station_id,
                window=WindowOut(
                    from_at=prediction.made_at
                    + timedelta(seconds=forecast.lead_time_s),
                    to_at=prediction.horizon_end,
                ),
                probability=forecast.probability,
                lead_time_min=round(forecast.lead_time_min, 1),
                cause=CauseOut(
                    station_id=forecast.cause.station_id,
                    description=forecast.cause.description,
                    attribution=list(forecast.cause.methods),
                    agreement=forecast.cause.agreement,
                ),
                expected_unit_loss=EstimateOut.of(forecast.expected_unit_loss, "units"),
                evidence_url=f"/api/v1/predictions/{prediction.prediction_id}/evidence",
                predictor_record=record,
                degraded=forecast.degraded,
            )
        )
    rows.sort(key=lambda item: (-item.expected_unit_loss.hi, item.kind == "DRIFT"))
    return ActionsOut(
        as_of=at,
        actions=rows,
        shadow_count=shadow_count,
        stations_running=stations_running,
        calm_note=_calm_note(stations_running, shadow_count, at, attribution),
        learning_note=learning_note,
    )


def _drift_action(
    prediction: Prediction, scorecard: Scorecard, required: int
) -> ActionOut:
    """A promoted drift signal, as the second card in WIREFRAMES/01.

    A drift is not a stall forecast and the card does not pretend it is. It
    carries no window and no probability of a stop, because the detector makes
    no claim about one: what it says is that a station has moved and by how
    much, which is enough for a supervisor to go and look.
    """
    station_id = prediction.station_id or ""
    magnitude = _number(prediction.claim.get("magnitude_s", 0.0))
    onset = prediction.claim.get("onset")
    return ActionOut(
        prediction_id=str(prediction.prediction_id),
        predictor=prediction.predictor,
        kind="DRIFT",
        station_id=station_id,
        window=WindowOut(from_at=prediction.made_at, to_at=prediction.horizon_end),
        probability=prediction.confidence,
        lead_time_min=0.0,
        cause=CauseOut(
            station_id=station_id,
            description=(
                f"cycle time has moved {magnitude:+.1f} s against its baseline "
                f"since {str(onset)[11:16]}"
            ),
            attribution=["EWMA", "CUSUM"],
            agreement=True,
        ),
        expected_unit_loss=EstimateOut.of(
            Estimate.derived(
                Interval(0.0, 0.0),
                basis=(
                    "the drift detector makes no claim about units lost. It "
                    "says the station has moved"
                ),
                confidence=prediction.confidence,
            ),
            "units",
        ),
        evidence_url=f"/api/v1/predictions/{prediction.prediction_id}/evidence",
        predictor_record=predictor_record(
            scorecard.row(prediction.predictor, station_id), required
        ),
        degraded=False,
    )


def _number(value: object) -> float:
    """Read a quantity out of a claim, which the ledger stores untyped."""
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return 0.0


def _calm_note(
    running: int, shadow: int, at: datetime, attribution: ConstraintAttribution
) -> str:
    """The second line of the calm state. A fact, not a reassurance."""
    constraint = attribution.by_active_period or attribution.by_buffer_trend
    tail = f" · slowest station {constraint}" if constraint else ""
    return (
        f"{running} stations running · {shadow} forecasts in shadow · "
        f"last check {at:%H:%M:%S}{tail}"
    )


def units_at_risk_out(
    risks: tuple[UnitRisk, ...],
    at: datetime,
    threshold: float = RISK_THRESHOLD,
) -> UnitsAtRiskOut:
    """The at-risk table, with a measurement where there is nothing to show."""
    rows = sorted(
        (item for item in risks if _risk_point(item) >= threshold),
        key=lambda item: item.minutes_remaining,
    )
    below = [item for item in risks if _risk_point(item) < threshold]
    highest = max(below, key=_risk_point, default=None)
    return UnitsAtRiskOut(
        as_of=at,
        units=[_unit_at_risk(item) for item in rows[:MAX_AT_RISK_ROWS]],
        threshold=threshold,
        total=len(rows),
        highest_below_threshold=(
            HighestBelowOut(
                unit_id=highest.unit_id,
                current_station_id=highest.current_station_id,
                gate_id=highest.gate_id,
                risk_point=round(_risk_point(highest), 2),
            )
            if highest is not None
            else None
        ),
        note=(
            f"{len(rows) - MAX_AT_RISK_ROWS} more above the threshold."
            if len(rows) > MAX_AT_RISK_ROWS
            else ""
        ),
    )


def _risk_point(item: UnitRisk) -> float:
    """The calibrated probability on one risk row."""
    return item.risk.point


def _unit_at_risk(item: UnitRisk) -> UnitAtRiskOut:
    """One row of the at-risk table."""
    risk = item.risk
    return UnitAtRiskOut(
        unit_id=item.unit_id,
        current_station_id=item.current_station_id,
        gate_id=item.gate_id,
        risk=EstimateOut.of(
            Estimate.derived(
                Interval(risk.lo, risk.hi),
                basis=item.basis,
                confidence=min(1.0, max(0.0, risk.point)),
            )
        ),
        stations_remaining=item.stations_remaining,
        minutes_remaining=round(item.minutes_remaining, 1),
        dark_visits=item.dark_visits,
        factors=[
            FactorOut(
                label=factor.label,
                detail=factor.detail,
                contribution=round(factor.contribution, 3),
            )
            for factor in item.factors
        ],
        published=item.flagged,
    )


def forecast_out(summary: ForecastSummary, epoch: datetime) -> ForecastOut:
    """The whole forecast, with every bucket carrying a real timestamp."""
    return ForecastOut(
        line_id=summary.line_id,
        as_of=epoch + timedelta(seconds=summary.at_s),
        horizon_min=summary.horizon_s / 60.0,
        replications=summary.replications,
        degraded=summary.degraded,
        buckets=[
            BucketOut(
                index=bucket.index,
                start_at=epoch + timedelta(seconds=bucket.start_s),
                end_at=epoch + timedelta(seconds=bucket.end_s),
            )
            for bucket in summary.buckets
        ],
        stations=[
            StationForecastOut(
                station_id=item.station_id,
                stall_probability=[round(v, 3) for v in item.stall_probability],
                blocked_probability=[round(v, 3) for v in item.blocked_probability],
                starved_probability=[round(v, 3) for v in item.starved_probability],
                mean_lost_s=[round(v, 1) for v in item.mean_lost_s],
            )
            for item in summary.stations
        ],
        buffers=[
            BufferForecastOut(
                buffer_id=item.buffer_id,
                after_station_id=item.after_station_id,
                capacity=item.capacity,
                low=[round(v, 2) for v in item.low],
                high=[round(v, 2) for v in item.high],
                mean=[round(v, 2) for v in item.mean],
            )
            for item in summary.buffers
        ],
        line_stall_probability=[round(v, 3) for v in summary.line_stall_probability],
        output=EstimateOut.of(summary.output, "units"),
        expected_unit_loss=EstimateOut.of(summary.expected_unit_loss, "units"),
        fallback_stations=list(summary.fallback_stations),
        learning_stations=list(summary.learning_stations),
        drifting_stations=list(summary.drifting_stations),
        learning_note=summary.learning_note(),
        runtime_s=round(summary.runtime_s, 2),
    )


def evidence_out(
    prediction: Prediction,
    *,
    cycle_series: list[SeriesPointOut],
    normal: RangeOut | None,
    markers: list[MarkerOut],
    buffer_series: list[SeriesPointOut],
    buffer_id: str | None,
    attribution: ConstraintAttribution,
    record: PredictorRecordOut,
    notes: list[str],
) -> EvidenceOut:
    """Everything behind one prediction, including its inputs hash."""
    constraint = attribution.by_active_period
    return EvidenceOut(
        prediction_id=str(prediction.prediction_id),
        predictor=prediction.predictor,
        model_version=prediction.model_version,
        made_at=prediction.made_at,
        horizon_end=prediction.horizon_end,
        published=prediction.published,
        inputs_hash=prediction.inputs_hash,
        claim=dict(prediction.claim),
        cause_station_id=str(prediction.evidence.get("cause_station_id") or "")
        or prediction.station_id,
        cycle_series=cycle_series,
        normal_range=normal,
        markers=markers,
        buffer_series=buffer_series,
        buffer_id=buffer_id,
        attribution=[
            AttributionRowOut(
                station_id=item.station_id,
                average_active_s=round(item.average_active_s, 1),
                is_constraint=item.station_id == constraint,
            )
            for item in attribution.ranked[:8]
        ],
        predictor_record=record,
        notes=notes,
    )


def drift_marker(estimate: DriftEstimate) -> MarkerOut:
    """The drift onset, which is the marker the evidence chart exists to show."""
    return MarkerOut(
        at=estimate.onset_at,
        label=(
            f"drift onset, {estimate.magnitude_s:+.1f} s over "
            f"{estimate.cycles_since_onset} cycles"
        ),
    )


# -- units ---------------------------------------------------------------


def unit_detail_out(
    signature: ProcessSignature,
    line: LineDefinition,
    *,
    normals: dict[str, RangeOut | None],
    risks: tuple[UnitRisk, ...],
    gates: tuple[tuple[str, datetime, bool], ...],
) -> UnitDetailOut:
    """The unit drawer, with the process signature as its spine."""
    order = line.station_ids
    visits: list[StationVisitOut] = []
    lots: list[str] = []
    for visit in signature.visits:
        normal = normals.get(visit.station_id)
        outside = False
        if normal is not None and visit.cycle_time is not None:
            value = visit.cycle_time
            outside = value.hi < normal.lo or value.lo > normal.hi
        lots.extend(visit.part_lots)
        visits.append(
            StationVisitOut(
                station_id=visit.station_id,
                seq=order.index(visit.station_id) + 1
                if visit.station_id in order
                else visit.seq,
                arrived_at=visit.arrived_at,
                departed_at=visit.departed_at,
                dwell_s=round(visit.dwell_s, 1) if visit.dwell_s is not None else None,
                cycle_time=(
                    EstimateOut.of(visit.cycle_time, "s")
                    if visit.cycle_time is not None
                    else None
                ),
                normal_range=normal,
                state_during=visit.state_during,
                outside_normal=outside,
                part_lots=list(visit.part_lots),
                process_values={
                    name: round(value, 3)
                    for name, value in visit.process_values.items()
                },
            )
        )
    return UnitDetailOut(
        unit_id=signature.unit_id,
        line_id=signature.line_id,
        variant_id=signature.variant_id,
        entered_at=signature.entered_at,
        exited_at=signature.exited_at,
        status=signature.status,
        current_station_id=(
            signature.visits[-1].station_id if signature.visits else None
        ),
        visits=visits,
        gates=[
            GateResultOut(gate_id=gate_id, at=at, passed=passed)
            for gate_id, at, passed in gates
        ],
        risks=[_unit_at_risk(item) for item in risks],
        part_lots=sorted(set(lots)),
        has_retro_trace=any(not passed for _, _, passed in gates),
    )


# -- the ledger ----------------------------------------------------------


def scorecard_row_out(row: ScorecardRow, required: int) -> ScorecardRowOut:
    """One scorecard row. A shadow row returns no precision, by construction."""
    active = row.state == "ACTIVE"
    return ScorecardRowOut(
        predictor=row.predictor,
        station_id=row.station_id,
        state=row.state,
        made=row.made,
        true_positive=row.true_positive,
        false_positive=row.false_positive,
        unscoreable=row.unscoreable,
        missed=row.missed,
        precision=row.precision if active else None,
        recall=row.recall if active else None,
        median_lead_min=(
            row.median_lead_s / 60.0
            if active and row.median_lead_s is not None
            else None
        ),
        false_per_shift=(
            row.false_positive / row.shifts_in_window
            if active and row.shifts_in_window > 0
            else None
        ),
        required=None if active else required,
        state_changed_at=row.state_changed_at,
        state_reason=row.state_reason,
    )


def scorecard_out(
    scorecard: Scorecard, line: LineDefinition, predictors: tuple[str, ...]
) -> ScorecardOut:
    """Every predictor's record, plus one aggregate row per predictor."""
    required = line.gates_policy.promotion.min_predictions
    return ScorecardOut(
        line_id=scorecard.line_id,
        as_of=scorecard.at,
        window_days=scorecard.window_days,
        rows=[scorecard_row_out(row, required) for row in scorecard.rows],
        totals=[
            scorecard_row_out(scorecard.totals(predictor), required)
            for predictor in predictors
        ],
    )
