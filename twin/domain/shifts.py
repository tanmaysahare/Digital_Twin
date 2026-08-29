"""The production calendar: when the line is running and when it is not.

Derived entirely from the shift pattern in the `LineDefinition`, so the
simulator and the twin agree about it without either telling the other. That
agreement matters in three places:

- A shift break is not a stall (EC-11). Scoring a forecast across one would
  count every lunch break as a line stop.
- A dark station's derived cycle time has to have the non-production part of
  the span subtracted from it, or the twin would read a break as slow work
  (TECHNICAL_SPEC.md Section 4.3).
- The average active period accumulator resets at shift boundaries rather than
  spanning them, because the continuous-operation assumption in Roser et al.
  does not hold across a two-shift changeover (Section 5.2).

Times are seconds from a run epoch, which is how the simulator counts, and
convert to wall clock only at the boundary where an event is emitted.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from twin.config.line import LineDefinition

DAY_S = 24 * 60 * 60

MarkerKind = Literal["START", "END", "BREAK_START", "BREAK_END", "CHANGEOVER"]


@dataclass(frozen=True)
class ProductionWindow:
    """A run of seconds during which the line produces, and whose shift it is."""

    start_s: float
    end_s: float
    shift_id: str

    @property
    def duration_s(self) -> float:
        """How long the window lasts."""
        return self.end_s - self.start_s


@dataclass(frozen=True)
class ShiftMarkerTime:
    """A boundary the line publishes as a `SHIFT_MARKER` event."""

    at_s: float
    shift_id: str
    marker: MarkerKind


class ProductionCalendar:
    """When the line runs, built from the shift pattern and nothing else."""

    def __init__(self, line: LineDefinition, epoch: datetime) -> None:
        """Build the calendar for one line.

        Args:
            line: the line whose shifts, breaks and changeovers apply.
            epoch: the wall clock at second zero. Shift times are read in this
                instant's own zone, because a shift pattern is written in the
                plant's local time and never in UTC.
        """
        self._line = line
        self._epoch = epoch
        self._windows: list[ProductionWindow] = []
        self._markers: list[ShiftMarkerTime] = []
        self._starts: list[float] = []
        self._days_built = 0
        self._build_to(0)

    @property
    def epoch(self) -> datetime:
        """The wall clock at second zero."""
        return self._epoch

    def at(self, seconds: float) -> datetime:
        """The wall clock at a given number of seconds from the epoch."""
        return self._epoch + timedelta(seconds=seconds)

    def _build_to(self, day_index: int) -> None:
        """Extend the calendar so that it covers the given day."""
        while self._days_built <= day_index:
            self._build_day(self._days_built)
            self._days_built += 1
            # A shift that runs past midnight can produce a window that starts
            # before one built earlier in the same pass, and the lookup is a
            # binary search over the start times.
            self._windows.sort(key=lambda window: window.start_s)
            self._starts = [window.start_s for window in self._windows]

    def _build_day(self, day_index: int) -> None:
        day_start = day_index * DAY_S
        # The epoch's own time of day, so that a run starting at 06:00 does not
        # produce a spurious partial window before it.
        epoch_offset_s = (
            self._epoch.hour * 3600 + self._epoch.minute * 60 + self._epoch.second
        )
        for shift in self._line.shifts:
            start_of_day = shift.start.hour * 3600 + shift.start.minute * 60
            end_of_day = shift.end.hour * 3600 + shift.end.minute * 60
            if end_of_day <= start_of_day:
                # A shift that runs past midnight ends on the following day.
                end_of_day += DAY_S
            start_s = day_start + start_of_day - epoch_offset_s
            end_s = day_start + end_of_day - epoch_offset_s

            changeover_s = shift.changeover_min * 60
            if changeover_s > 0:
                self._markers.append(
                    ShiftMarkerTime(start_s, shift.shift_id, "CHANGEOVER")
                )
            open_s = start_s + changeover_s
            if open_s >= end_s:
                continue
            self._markers.append(ShiftMarkerTime(open_s, shift.shift_id, "START"))

            break_s = shift.break_min * 60
            if break_s <= 0:
                self._add_window(ProductionWindow(open_s, end_s, shift.shift_id))
            else:
                # The break sits in the middle of the running part of the shift.
                # Where it sits is a plant decision; the middle is the neutral
                # choice and it is what the shift comparison in Plan view
                # assumes when it splits a shift into halves.
                midpoint = (open_s + end_s) / 2.0
                break_start = midpoint - break_s / 2.0
                break_end = break_start + break_s
                self._add_window(ProductionWindow(open_s, break_start, shift.shift_id))
                self._markers.append(
                    ShiftMarkerTime(break_start, shift.shift_id, "BREAK_START")
                )
                self._markers.append(
                    ShiftMarkerTime(break_end, shift.shift_id, "BREAK_END")
                )
                self._add_window(ProductionWindow(break_end, end_s, shift.shift_id))
            self._markers.append(ShiftMarkerTime(end_s, shift.shift_id, "END"))

    def _add_window(self, window: ProductionWindow) -> None:
        if window.duration_s <= 0:
            return
        self._windows.append(window)

    def _ensure(self, seconds: float) -> None:
        self._build_to(int(seconds // DAY_S) + 1)

    def _index_at_or_before(self, seconds: float) -> int:
        return bisect_right(self._starts, seconds) - 1

    def window_at(self, seconds: float) -> ProductionWindow | None:
        """The window containing this instant, or None if the line is stopped."""
        self._ensure(seconds)
        index = self._index_at_or_before(seconds)
        if index < 0:
            return None
        window = self._windows[index]
        return window if seconds < window.end_s else None

    def is_producing(self, seconds: float) -> bool:
        """Whether the line is running at this instant."""
        return self.window_at(seconds) is not None

    def shift_started_at(self, seconds: float) -> float | None:
        """When the shift containing this instant began.

        `window_at` answers with the production window, which is the stretch
        since the last break. That is the right answer for arithmetic about
        production time and the wrong one for a shift's output: a supervisor
        judged on 460 units a shift is not judged on the units built since the
        last tea break.
        """
        self._ensure(seconds)
        index = self._index_at_or_before(seconds)
        if index < 0:
            return None
        window = self._windows[index]
        if seconds >= window.end_s:
            return None
        shift_id = window.shift_id
        while index > 0 and self._windows[index - 1].shift_id == shift_id:
            index -= 1
        return self._windows[index].start_s

    def shift_at(self, seconds: float) -> str | None:
        """Which shift is running at this instant, or None if the line is stopped."""
        window = self.window_at(seconds)
        return window.shift_id if window is not None else None

    def next_open(self, seconds: float) -> float:
        """The next instant at or after this one when the line is running."""
        self._ensure(seconds)
        index = self._index_at_or_before(seconds)
        if index >= 0 and seconds < self._windows[index].end_s:
            return seconds
        candidate = index + 1
        while candidate >= len(self._windows):
            self._build_to(self._days_built)
        return self._windows[candidate].start_s

    def advance(self, seconds: float, production_s: float) -> float:
        """The instant at which a given amount of production time has elapsed.

        Work paused by a break resumes after it, so a station's processing time
        counts production seconds and its dwell counts wall seconds. That
        difference is exactly what the twin has to subtract before it can read a
        span as work.
        """
        if production_s < 0:
            message = f"production_s must not be negative, got {production_s}"
            raise ValueError(message)
        now = self.next_open(seconds)
        remaining = production_s
        while remaining > 0:
            window = self.window_at(now)
            if window is None:
                now = self.next_open(now)
                continue
            available = window.end_s - now
            if remaining <= available:
                return now + remaining
            remaining -= available
            now = self.next_open(window.end_s)
        return now

    def production_between(self, start_s: float, end_s: float) -> float:
        """How many production seconds lie between two instants."""
        if end_s <= start_s:
            return 0.0
        self._ensure(end_s)
        total = 0.0
        index = max(0, self._index_at_or_before(start_s))
        while index < len(self._windows):
            window = self._windows[index]
            if window.start_s >= end_s:
                break
            overlap = min(window.end_s, end_s) - max(window.start_s, start_s)
            if overlap > 0:
                total += overlap
            index += 1
        return total

    def stopped_between(self, start_s: float, end_s: float) -> float:
        """How many non-production seconds lie between two instants."""
        if end_s <= start_s:
            return 0.0
        return (end_s - start_s) - self.production_between(start_s, end_s)

    def markers_until(self, end_s: float) -> tuple[ShiftMarkerTime, ...]:
        """Every shift boundary up to an instant, in time order."""
        self._ensure(end_s)
        return tuple(
            sorted(
                (marker for marker in self._markers if marker.at_s <= end_s),
                key=lambda marker: (marker.at_s, marker.marker),
            )
        )

    def windows_until(self, end_s: float) -> tuple[ProductionWindow, ...]:
        """Every production window that starts before an instant, in time order."""
        self._ensure(end_s)
        return tuple(window for window in self._windows if window.start_s < end_s)
