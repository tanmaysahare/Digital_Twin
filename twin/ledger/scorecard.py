"""The predictor scorecard. T-062.

DATABASE_SCHEMA.md Section 5 and AC-040, AC-043. What the floor reads to decide
whether this system is worth reading.

**Recall is not computable from predictions alone, and this module refuses to
pretend otherwise.** Precision comes from the outcomes joined to predictions.
Recall needs the events nothing predicted, and those live in `missed_event`. A
scorecard built from the prediction table alone can only say how often the twin
was right when it spoke, and reporting that as accuracy is exactly the behaviour
this product argues against. `recall` here is `None` where no missed-event
accounting exists for a predictor, rather than silently equal to precision.

**A shadow entry never returns a precision**, even when one could be computed.
Exposing an unpromoted hit rate invites the floor to trust something that has not
cleared its gate, and the gate is the product's argument (API_SPEC Section 6).
`ScorecardRow.published_precision` is what an interface reads;
`ScorecardRow.precision` is what the gate reads, and only the gate.

**False alerts per shift is a column, not a drill-down** (AC-043). It is the
number a supervisor uses to decide whether to keep looking at the screen, so it
sits beside the hit rate rather than behind it.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar
from twin.ledger.store import (
    STALL_FORECASTER,
    LedgerStore,
    PredictorState,
)


@dataclass(frozen=True)
class ScorecardRow:
    """One predictor's record at one station over the window."""

    predictor: str
    line_id: str
    station_id: str | None
    state: PredictorState
    made: int
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    unscoreable: int
    missed: int
    median_lead_s: float | None
    lead_times_s: tuple[float, ...]
    shifts_in_window: float
    state_changed_at: datetime | None
    state_reason: str | None

    @property
    def scored(self) -> int:
        """Predictions that count towards precision."""
        return self.true_positive + self.false_positive

    @property
    def precision(self) -> float | None:
        """Hits over scored predictions. None where nothing has been scored."""
        return self.true_positive / self.scored if self.scored else None

    @property
    def recall(self) -> float | None:
        """Hits over everything that happened.

        For a forecaster, the denominator is the hits plus the events that
        happened with nothing in scope, which is what `missed_event` records. For
        a classifier, it is the hits plus the failures it did not flag. Both come
        from rows that exist rather than from an assumption.
        """
        if self.predictor == STALL_FORECASTER:
            denominator = self.true_positive + self.missed
        else:
            denominator = self.true_positive + self.false_negative
        return self.true_positive / denominator if denominator else None

    @property
    def published_precision(self) -> float | None:
        """The precision an interface may show. None while in shadow."""
        return self.precision if self.state == "ACTIVE" else None

    @property
    def unscoreable_share(self) -> float:
        """How much of this record could not be scored either way."""
        return self.unscoreable / self.made if self.made else 0.0

    @property
    def false_per_shift(self) -> float | None:
        """False alerts a supervisor would have seen per shift. AC-043."""
        if self.shifts_in_window <= 0:
            return None
        return self.false_positive / self.shifts_in_window

    @property
    def median_lead_min(self) -> float | None:
        """The median lead time in minutes, which is what the interface prints."""
        return self.median_lead_s / 60.0 if self.median_lead_s is not None else None


@dataclass(frozen=True)
class Scorecard:
    """Every predictor at every station over one window."""

    line_id: str
    at: datetime
    window_days: int
    rows: tuple[ScorecardRow, ...]

    def row(self, predictor: str, station_id: str | None) -> ScorecardRow | None:
        """One row by predictor and station."""
        for item in self.rows:
            if item.predictor == predictor and item.station_id == station_id:
                return item
        return None

    def for_predictor(self, predictor: str) -> tuple[ScorecardRow, ...]:
        """Every station's row for one predictor."""
        return tuple(item for item in self.rows if item.predictor == predictor)

    def totals(self, predictor: str) -> ScorecardRow:
        """One predictor's record across every station, as a single row.

        Station-level rows are what the gates read, because a predictor can be
        worth reading at S20 and not at S31. This is what the evidence pack
        reports, because a per-station precision over eleven predictions is a
        number with an enormous confidence interval.
        """
        rows = self.for_predictor(predictor)
        leads = tuple(value for row in rows for value in row.lead_times_s)
        return ScorecardRow(
            predictor=predictor,
            line_id=self.line_id,
            station_id=None,
            state="ACTIVE" if any(row.state == "ACTIVE" for row in rows) else "SHADOW",
            made=sum(row.made for row in rows),
            true_positive=sum(row.true_positive for row in rows),
            false_positive=sum(row.false_positive for row in rows),
            true_negative=sum(row.true_negative for row in rows),
            false_negative=sum(row.false_negative for row in rows),
            unscoreable=sum(row.unscoreable for row in rows),
            missed=sum(row.missed for row in rows),
            median_lead_s=statistics.median(leads) if leads else None,
            lead_times_s=leads,
            shifts_in_window=max((row.shifts_in_window for row in rows), default=0.0),
            state_changed_at=None,
            state_reason=None,
        )


def build_scorecard(
    store: LedgerStore,
    line: LineDefinition,
    calendar: ProductionCalendar,
    at: datetime,
    window_days: int | None = None,
) -> Scorecard:
    """Aggregate the ledger into the record the floor reads.

    Args:
        store: the ledger.
        line: the line, for its own gate window.
        calendar: the production calendar, for counting shifts in the window.
        at: the instant the scorecard is as of.
        window_days: the rolling window. Defaults to the line's own policy.
    """
    days = window_days or line.gates_policy.window_days
    since = at - timedelta(days=days)
    shifts = _shifts_between(calendar, since, at)

    counters: dict[tuple[str, str | None], dict[str, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    leads: dict[tuple[str, str | None], list[float]] = defaultdict(list)
    keys: set[tuple[str, str | None]] = set()

    for prediction in store.predictions:
        if prediction.made_at < since or prediction.made_at > at:
            continue
        key = (prediction.predictor, prediction.station_id)
        keys.add(key)
        counters[key]["made"] += 1
        outcome = store.outcome_of(prediction.prediction_id)
        if outcome is None:
            continue
        counters[key][outcome.result.lower()] += 1
        if outcome.result == "TRUE_POSITIVE" and outcome.lead_time_s is not None:
            leads[key].append(outcome.lead_time_s)

    for event in store.missed:
        if event.occurred_at < since or event.occurred_at > at:
            continue
        key = (event.predictor, event.station_id)
        keys.add(key)
        counters[key]["missed"] += 1

    rows: list[ScorecardRow] = []
    for predictor, station_id in sorted(keys, key=lambda key: (key[0], key[1] or "")):
        key = (predictor, station_id)
        counts = counters[key]
        change = store.last_change(predictor, line.line_id, station_id)
        ordered = sorted(leads[key])
        rows.append(
            ScorecardRow(
                predictor=predictor,
                line_id=line.line_id,
                station_id=station_id,
                state=store.state_of(predictor, line.line_id, station_id, at),
                made=counts["made"],
                true_positive=counts["true_positive"],
                false_positive=counts["false_positive"],
                true_negative=counts["true_negative"],
                false_negative=counts["false_negative"],
                unscoreable=counts["unscoreable"],
                missed=counts["missed"],
                median_lead_s=statistics.median(ordered) if ordered else None,
                lead_times_s=tuple(ordered),
                shifts_in_window=shifts,
                state_changed_at=change.changed_at if change is not None else None,
                state_reason=change.reason if change is not None else None,
            )
        )
    return Scorecard(line_id=line.line_id, at=at, window_days=days, rows=tuple(rows))


def _shifts_between(
    calendar: ProductionCalendar, start: datetime, end: datetime
) -> float:
    """How many shifts the window holds, from the production calendar.

    Counted as production windows rather than as elapsed days, because a
    supervisor sees false alerts per shift they worked and not per calendar day
    the plant existed.
    """
    epoch = calendar.epoch
    start_s = (start - epoch).total_seconds()
    end_s = (end - epoch).total_seconds()
    windows = [
        window
        for window in calendar.windows_until(end_s)
        if window.end_s > start_s and window.start_s < end_s
    ]
    if not windows:
        return 0.0
    # Two production windows either side of a break are one shift, so the count
    # is the production time over the length of one shift's production time.
    per_shift = statistics.median(
        [window.duration_s for window in calendar.windows_until(end_s)] or [1.0]
    )
    covered = sum(
        min(window.end_s, end_s) - max(window.start_s, start_s) for window in windows
    )
    return covered / (per_shift * 2.0) if per_shift > 0 else 0.0
