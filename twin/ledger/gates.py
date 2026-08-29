"""Promotion and demotion gates. T-061.

TECHNICAL_SPEC.md Section 9.3, AC-041, AC-042, EC-44. Per predictor per station.

**Every predictor starts in shadow.** It emits predictions, the ledger records
them in full, and none of them reaches an interface. It leaves shadow only by
clearing its gate on that station's own evidence. A predictor that is excellent
at S20 and useless at S31 is promoted at S20 and stays in shadow at S31, because
a supervisor's trust is not a line-wide quantity: they learn to ignore the screen
one station at a time.

**Hysteresis, and a cooling period.** Promotion needs 0.70 precision and demotion
happens at 0.55, so a predictor sitting at 0.62 does not oscillate. After a
demotion it cannot be promoted again for the cooling period, whatever its numbers
do. A predictor that flickers on and off is worse for trust than one that stays
off, and a floor that has seen a withdrawn alert come back the same afternoon has
learned that the withdrawal meant nothing (EC-44).

**Both directions write a record with the numbers that caused them.** That record
is what the interface reads when it tells the floor a predictor was withdrawn and
why (AC-042). A state change with no metrics attached would be an announcement
rather than an explanation.

**The gate thresholds are configuration, and their history is auditable.** They
live in `config/lines/*.yaml`. Loosening a gate to promote a failing predictor is
a configuration change with a version, visible to anyone reading the history
(EC-45).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from twin.config.line import LineDefinition
from twin.ledger.scorecard import Scorecard, ScorecardRow
from twin.ledger.store import LedgerStore, StateChange


@dataclass(frozen=True)
class GateDecision:
    """One gate evaluation, whether or not it changed anything."""

    predictor: str
    station_id: str | None
    was: str
    now: str
    changed: bool
    reason: str
    metrics: dict[str, object]


def evaluate_gates(
    store: LedgerStore,
    line: LineDefinition,
    scorecard: Scorecard,
    at: datetime,
) -> tuple[GateDecision, ...]:
    """Promote, demote or leave every predictor where it is.

    Args:
        store: the ledger, which holds the state history and receives the change.
        line: the line, for its own promotion and demotion policy.
        scorecard: the record every decision is made from.
        at: the instant the evaluation runs.

    Returns:
        One decision per row assessed, changed or not. The unchanged ones are
        returned as well because the interface shows a predictor's distance from
        its gate, which is what tells a supervisor that a station is learning
        rather than broken (API_SPEC Section 6).
    """
    policy = line.gates_policy
    decisions: list[GateDecision] = []
    for row in scorecard.rows:
        state = row.state
        if state == "UNAVAILABLE":
            continue
        decision = (
            _consider_demotion(row, line, at)
            if state == "ACTIVE"
            else _consider_promotion(row, line, store, at)
        )
        decisions.append(decision)
        if decision.changed:
            store.change_state(
                StateChange(
                    predictor=row.predictor,
                    line_id=line.line_id,
                    station_id=row.station_id,
                    state=decision.now,  # type: ignore[arg-type]
                    changed_at=at,
                    reason=decision.reason,
                    metrics=decision.metrics,
                )
            )
    del policy
    return tuple(decisions)


def _metrics(row: ScorecardRow) -> dict[str, object]:
    """The numbers a state change is recorded with."""
    return {
        "made": row.made,
        "scored": row.scored,
        "true_positive": row.true_positive,
        "false_positive": row.false_positive,
        "unscoreable": row.unscoreable,
        "missed": row.missed,
        "precision": None if row.precision is None else round(row.precision, 4),
        "recall": None if row.recall is None else round(row.recall, 4),
        "median_lead_min": (
            None if row.median_lead_min is None else round(row.median_lead_min, 1)
        ),
        "false_per_shift": (
            None if row.false_per_shift is None else round(row.false_per_shift, 3)
        ),
    }


def _consider_promotion(
    row: ScorecardRow, line: LineDefinition, store: LedgerStore, at: datetime
) -> GateDecision:
    policy = line.gates_policy
    gate = policy.promotion
    metrics = _metrics(row)
    cooling = _cooling_until(store, row, line, policy.cooling_period_days)
    if cooling is not None and at < cooling:
        withdrawn = cooling - timedelta(days=policy.cooling_period_days)
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="SHADOW",
            now="SHADOW",
            changed=False,
            reason=(
                f"Withdrawn on {withdrawn:%d %b}. Cannot return to the floor "
                f"before {cooling:%d %b}, whatever the numbers do in the meantime"
            ),
            metrics=metrics,
        )
    if row.scored < gate.min_predictions:
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="SHADOW",
            now="SHADOW",
            changed=False,
            reason=(
                f"Learning. {row.scored} of the {gate.min_predictions} scored "
                f"predictions needed before alerts start here"
            ),
            metrics=metrics,
        )
    precision = row.precision or 0.0
    recall = row.recall
    if precision < gate.min_precision:
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="SHADOW",
            now="SHADOW",
            changed=False,
            reason=(
                f"Precision {precision:.2f} over {row.scored} scored predictions, "
                f"below the {gate.min_precision:.2f} this line asks for"
            ),
            metrics=metrics,
        )
    if recall is None or recall < gate.min_recall:
        shown = "not measurable yet" if recall is None else f"{recall:.2f}"
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="SHADOW",
            now="SHADOW",
            changed=False,
            reason=(
                f"Precision {precision:.2f} clears its gate, recall is {shown} "
                f"against the {gate.min_recall:.2f} this line asks for. A "
                f"predictor that is right when it speaks and silent most of the "
                f"time has not earned the floor"
            ),
            metrics=metrics,
        )
    return GateDecision(
        predictor=row.predictor,
        station_id=row.station_id,
        was="SHADOW",
        now="ACTIVE",
        changed=True,
        reason=(
            f"Promoted: {precision:.2f} precision and {recall:.2f} recall over "
            f"{row.scored} scored predictions at this station"
        ),
        metrics=metrics,
    )


def _consider_demotion(
    row: ScorecardRow, line: LineDefinition, at: datetime
) -> GateDecision:
    gate = line.gates_policy.demotion
    metrics = _metrics(row)
    precision = row.precision
    if row.scored < gate.min_predictions or precision is None:
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="ACTIVE",
            now="ACTIVE",
            changed=False,
            reason=(
                f"On the floor. {row.scored} scored predictions in the window, "
                f"below the {gate.min_predictions} a withdrawal needs"
            ),
            metrics=metrics,
        )
    if precision > gate.max_precision:
        return GateDecision(
            predictor=row.predictor,
            station_id=row.station_id,
            was="ACTIVE",
            now="ACTIVE",
            changed=False,
            reason=(
                f"On the floor: {precision:.2f} precision over {row.scored} scored "
                f"predictions"
            ),
            metrics=metrics,
        )
    del at
    return GateDecision(
        predictor=row.predictor,
        station_id=row.station_id,
        was="ACTIVE",
        now="SHADOW",
        changed=True,
        reason=(
            f"Withdrawn: precision fell to {precision:.2f} over {row.scored} scored "
            f"predictions, below the {gate.max_precision:.2f} this line withdraws at"
        ),
        metrics=metrics,
    )


def _cooling_until(
    store: LedgerStore, row: ScorecardRow, line: LineDefinition, days: int
) -> datetime | None:
    """When a demoted predictor may be considered again, or None if never demoted."""
    if days <= 0:
        return None
    change = store.last_change(row.predictor, line.line_id, row.station_id)
    if change is None or change.state != "SHADOW":
        return None
    if not change.reason.startswith("Withdrawn"):
        return None
    return change.changed_at + timedelta(days=days)
