"""Retro-trace: the backward divergence walk and the containment list.

T-097, T-098, AC-026 to AC-029. TECHNICAL_SPEC.md Section 7.

A unit fails at a gate. The question the floor asks is not "why did this unit
fail" in the abstract, it is "what else is on the line that looks like it". This
module answers the second question well and the first one honestly.

**The walk.** Every station the unit visited, in reverse order from the gate.
For each visit, how far that visit sat from what the rest of the line was doing
at the same time: the cycle time against that station's own distribution for
that variant, the dwell against the same, and any process value against the
contemporaneous population of units that passed the same station in the same
window. The divergence is the largest of those, in sigma.

**Why contemporaneous.** A station that has drifted all shift is not evidence
about one unit. Comparing against the population that passed at the same time
removes the drift and leaves what was different about this unit, which is what a
containment list needs.

**Co-hypotheses, not a root cause.** Where two stations diverge within
`CO_HYPOTHESIS_BAND` sigma of each other, both are returned at the same strength
and neither is called the cause. The response carries a `disclaimer` field that
API_SPEC.md Section 5 makes part of the contract, and the word "cause" never
appears as an assertion (AC-029). Intermittent and multi-causal conditions are
the normal case in a plant, and a tool that names one station confidently is a
tool that sends a team to the wrong station confidently.

**Containment.** Units are included by shared attribute first (a part lot is the
strongest signal a plant has and is what a quality engineer can act on) and by
signature similarity second. Each row carries the evidence for its own
inclusion, because a containment list nobody can check is a containment list
nobody will act on. The list is split by where the unit is now, since what you
do about a unit differs completely between the line, the yard and a customer.
"""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from twin.config.line import LineDefinition
from twin.domain.signature import ProcessSignature, StationVisit

# How close two divergences have to be before both are reported at the same
# strength. Below this the evidence does not separate them and presenting a
# ranking would be presenting precision the data does not carry.
CO_HYPOTHESIS_BAND = 0.5

# How wide a window counts as contemporaneous. Long enough to hold a usable
# population on a 60 s takt, short enough that a drift that began an hour ago is
# not in it.
POPULATION_WINDOW_MIN = 45

# Below this many comparable passages there is no population to compare against
# and the visit yields no divergence rather than a large one.
MINIMUM_POPULATION = 6

# The divergence below which a visit is not worth reporting at all.
REPORTABLE_SIGMA = 1.5

# How many hypotheses the response carries. More than this is a list nobody
# reads, and the walk keeps its own ordering behind them.
MAX_HYPOTHESES = 5

# Every comparable passage, keyed by station and variant, each carrying the
# unit it belongs to.
_Population = dict[tuple[str, str], list[tuple[str, StationVisit]]]

DISCLAIMER = (
    "Ranked hypothesis, not a confirmed root cause. Intermittent and "
    "multi-causal conditions are common."
)


@dataclass(frozen=True)
class SharedAttribute:
    """Something this unit had in common with others, and what kind of thing."""

    kind: str
    value: str


@dataclass(frozen=True)
class Hypothesis:
    """One station that looked different for this unit, and by how much."""

    rank: int
    station_id: str
    window_from: datetime
    window_to: datetime
    divergence: float
    strength: str
    description: str
    shared_attribute: SharedAttribute | None
    population: int


@dataclass(frozen=True)
class ContainedUnit:
    """One unit on the containment list, with the evidence for its inclusion."""

    unit_id: str
    similarity: float
    at: str
    location: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class RetroTrace:
    """What the walk found, and what it says should be looked at."""

    unit_id: str
    line_id: str
    failed_at_gate: str
    failed_at: datetime
    hypotheses: tuple[Hypothesis, ...]
    on_line: tuple[ContainedUnit, ...]
    in_yard: tuple[ContainedUnit, ...]
    shipped: tuple[ContainedUnit, ...]
    runtime_s: float
    disclaimer: str = DISCLAIMER

    @property
    def counts(self) -> dict[str, int]:
        """How many units each part of the list holds."""
        return {
            "on_line": len(self.on_line),
            "in_yard": len(self.in_yard),
            "shipped": len(self.shipped),
        }


@dataclass
class RetroTracer:
    """Runs the walk and builds the containment list for one line."""

    line: LineDefinition

    def trace(
        self,
        unit_id: str,
        gate_id: str,
        failed_at: datetime,
        signatures: tuple[ProcessSignature, ...],
    ) -> RetroTrace | None:
        """Walk one failed unit backwards and rank what looked different.

        Returns None where the unit has no recorded signature, which happens
        when a gate result arrives for a unit the twin never saw enter (EC-34).
        """
        started = datetime.now(tz=failed_at.tzinfo)
        subject = next((s for s in signatures if s.unit_id == unit_id), None)
        if subject is None:
            return None
        population = self._population(signatures, failed_at)
        found: list[Hypothesis] = []
        for visit in reversed(subject.visits):
            reading = self._divergence(
                subject.unit_id, visit, subject.variant_id, population
            )
            if reading is None:
                continue
            sigma, description, count = reading
            if sigma < REPORTABLE_SIGMA:
                continue
            found.append(
                Hypothesis(
                    rank=0,
                    station_id=visit.station_id,
                    window_from=visit.arrived_at or failed_at,
                    window_to=visit.departed_at or failed_at,
                    divergence=sigma,
                    strength="leading",
                    description=description,
                    shared_attribute=(
                        SharedAttribute("PART_LOT", visit.part_lots[0])
                        if visit.part_lots
                        else None
                    ),
                    population=count,
                )
            )
        ranked = self._rank(found)
        containment = self._contain(subject, ranked, signatures)
        elapsed = (datetime.now(tz=failed_at.tzinfo) - started).total_seconds()
        return RetroTrace(
            unit_id=unit_id,
            line_id=self.line.line_id,
            failed_at_gate=gate_id,
            failed_at=failed_at,
            hypotheses=ranked,
            on_line=containment["on_line"],
            in_yard=containment["in_yard"],
            shipped=containment["shipped"],
            runtime_s=elapsed,
        )

    # -- the walk ---------------------------------------------------------

    def _population(
        self, signatures: tuple[ProcessSignature, ...], failed_at: datetime
    ) -> _Population:
        """Every comparable passage in the contemporaneous window.

        Keyed by station and variant, and each entry carries the unit it
        belongs to, because the subject's own passage has to be left out of
        the population it is being compared against.
        """
        cutoff = failed_at - timedelta(minutes=POPULATION_WINDOW_MIN)
        pool: _Population = defaultdict(list)
        for signature in signatures:
            for visit in signature.visits:
                moment = visit.departed_at or visit.arrived_at
                if moment is None or moment < cutoff or moment > failed_at:
                    continue
                key = (visit.station_id, signature.variant_id)
                pool[key].append((signature.unit_id, visit))
        return pool

    def _divergence(
        self,
        unit_id: str,
        visit: StationVisit,
        variant_id: str,
        population: _Population,
    ) -> tuple[float, str, int] | None:
        """How far this visit sat from what the line was doing at the time."""
        peers = population.get((visit.station_id, variant_id), [])
        cycles = [
            peer.cycle_time.sort_key()
            for peer_id, peer in peers
            if peer.cycle_time is not None
            and peer.cycle_time.provenance == "MEASURED"
            and peer_id != unit_id
        ]
        if len(cycles) < MINIMUM_POPULATION:
            return None
        if visit.cycle_time is None or visit.cycle_time.provenance != "MEASURED":
            return None
        centre, scale = _robust(cycles)
        if scale <= 0.0:
            return None
        value = visit.cycle_time.sort_key()
        sigma = abs(value - centre) / scale
        direction = "above" if value > centre else "below"
        best = (
            sigma,
            (
                f"cycle time ran {sigma:.1f} sigma {direction} the "
                f"contemporaneous population at {visit.station_id}"
            ),
            len(cycles),
        )
        for name, reading in visit.process_values.items():
            peer_values = [
                peer.process_values[name]
                for peer_id, peer in peers
                if name in peer.process_values and peer_id != unit_id
            ]
            if len(peer_values) < MINIMUM_POPULATION:
                continue
            peer_centre, peer_scale = _robust(peer_values)
            if peer_scale <= 0.0:
                continue
            peer_sigma = abs(reading - peer_centre) / peer_scale
            if peer_sigma > best[0]:
                where = "above" if reading > peer_centre else "below"
                best = (
                    peer_sigma,
                    (
                        f"{name.replace('_', ' ')} ran {peer_sigma:.1f} sigma "
                        f"{where} the contemporaneous population at "
                        f"{visit.station_id}"
                    ),
                    len(peer_values),
                )
        return best

    def _rank(self, found: list[Hypothesis]) -> tuple[Hypothesis, ...]:
        """Order by divergence and mark everything inside the band as equal."""
        ordered = sorted(found, key=lambda item: -item.divergence)[:MAX_HYPOTHESES]
        if not ordered:
            return ()
        leader = ordered[0].divergence
        ranked: list[Hypothesis] = []
        for index, item in enumerate(ordered, start=1):
            close = leader - item.divergence <= CO_HYPOTHESIS_BAND
            strength = "leading" if index == 1 or close else "co-hypothesis"
            if index > 1 and close:
                strength = "co-hypothesis of equal strength"
            ranked.append(
                Hypothesis(
                    rank=index,
                    station_id=item.station_id,
                    window_from=item.window_from,
                    window_to=item.window_to,
                    divergence=item.divergence,
                    strength=strength,
                    description=item.description,
                    shared_attribute=item.shared_attribute,
                    population=item.population,
                )
            )
        return tuple(ranked)

    # -- containment ------------------------------------------------------

    def _contain(
        self,
        subject: ProcessSignature,
        hypotheses: tuple[Hypothesis, ...],
        signatures: tuple[ProcessSignature, ...],
    ) -> dict[str, tuple[ContainedUnit, ...]]:
        """Every other unit that shares this one's evidence. AC-027."""
        lots = {lot for visit in subject.visits for lot in visit.part_lots}
        implicated = {item.station_id for item in hypotheses}
        buckets: dict[str, list[ContainedUnit]] = {
            "on_line": [],
            "in_yard": [],
            "shipped": [],
        }
        for signature in signatures:
            if signature.unit_id == subject.unit_id:
                continue
            evidence: list[str] = []
            shared_lots = {
                lot
                for visit in signature.visits
                for lot in visit.part_lots
                if lot in lots
            }
            evidence.extend(f"lot {lot}" for lot in sorted(shared_lots))
            passed = {
                visit.station_id
                for visit in signature.visits
                if visit.station_id in implicated
            }
            evidence.extend(f"passed {station}" for station in sorted(passed))
            if not shared_lots:
                continue
            similarity = _similarity(len(shared_lots), len(lots), len(passed))
            location, at = _where(signature, self.line)
            buckets[location].append(
                ContainedUnit(
                    unit_id=signature.unit_id,
                    similarity=similarity,
                    at=at,
                    location=location,
                    evidence=tuple(evidence),
                )
            )
        return {
            name: tuple(sorted(rows, key=lambda row: -row.similarity))
            for name, rows in buckets.items()
        }


# Every file that leaves the product says where its numbers came from. A CSV
# that leaves without this is a CSV that can end up in a capital request looking
# like plant data.
SIMULATED = (
    "Simulated data. Produced by the DigitalTwin.ai prototype against a "
    "simulated line, not measured in a plant."
)


def to_csv(trace: RetroTrace) -> str:
    """The containment list as a CSV a quality engineer can work from. AC-028."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([SIMULATED])
    writer.writerow(
        [
            "unit_id",
            "location",
            "at",
            "similarity",
            "evidence",
            "traced_from_unit",
            "failed_gate",
            "failed_at",
            "note",
        ]
    )
    for group in (trace.on_line, trace.in_yard, trace.shipped):
        for row in group:
            writer.writerow(
                [
                    row.unit_id,
                    row.location,
                    row.at,
                    f"{row.similarity:.2f}",
                    "; ".join(row.evidence),
                    trace.unit_id,
                    trace.failed_at_gate,
                    trace.failed_at.isoformat(),
                    trace.disclaimer,
                ]
            )
    return buffer.getvalue()


def _robust(values: list[float]) -> tuple[float, float]:
    """The median and a scale that one outlier cannot move."""
    ordered = sorted(values)
    middle = len(ordered) // 2
    centre = (
        ordered[middle]
        if len(ordered) % 2
        else (ordered[middle - 1] + ordered[middle]) / 2.0
    )
    deviations = sorted(abs(value - centre) for value in ordered)
    mid = len(deviations) // 2
    mad = (
        deviations[mid]
        if len(deviations) % 2
        else (deviations[mid - 1] + deviations[mid]) / 2.0
    )
    return centre, mad * 1.4826


def _similarity(shared_lots: int, total_lots: int, stations: int) -> float:
    """How much of the subject's evidence this unit carries too."""
    lot_term = shared_lots / total_lots if total_lots else 0.0
    station_term = min(1.0, stations / 3.0)
    value = 0.7 * lot_term + 0.3 * station_term
    return 0.0 if not math.isfinite(value) else min(1.0, value)


def _where(signature: ProcessSignature, line: LineDefinition) -> tuple[str, str]:
    """Where a unit is now, and the station or state to print beside it."""
    if signature.status == "IN_PROCESS" and signature.visits:
        return "on_line", signature.visits[-1].station_id
    if signature.status == "SCRAPPED":
        return "in_yard", "scrapped"
    if signature.exited_at is None:
        return "on_line", line.station_ids[0]
    return "in_yard", "built, not despatched"
