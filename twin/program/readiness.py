"""Site readiness, computed from what a site emits. T-117, AC-070.

UX_SPEC.md Section 4.1. Meera's first question about a new site is not "is it a
good site", it is "can this thing work there at all, and if not, what is
missing". A survey answers that badly: a plant that says it has unit-level
traceability often has it in three systems that disagree, and a plant that says
it has none often has a scan point nobody counted. So readiness is computed from
the site's own event stream where there is one, and where there is not, the
components that cannot be measured are named as not measured rather than
guessed.

**The six components**, each scored in [0, 1] and each with a stated weight:

- unit-level traceability: can a unit be followed end to end
- cycle event coverage: what share of stations emit their own cycle
- dark station share: how much of the line nothing watches, inverted
- historian available: is there a source of history to fit baselines on
- inspection results available: are there labels for the defect models
- clock quality: how far apart the sources' clocks sit

**Bands are words, not a number out of ten.** `READY`, `READY WITH
INSTRUMENTATION`, `NOT READY`. A score of 6.8 invites an argument about whether
6.8 is good. "Ready with instrumentation, and here is the list" does not.

**A NOT READY site expands to exactly what is missing**, drawn from that site's
own sensor queue, with the cost attached. That is the whole point: a site that
cannot run this today is a site with a costed list of what would change that.
"""

from __future__ import annotations

from dataclasses import dataclass

from twin.config.line import LineDefinition

# What each component is worth. Traceability and inspection results carry the
# most because without either of them a whole capability is absent rather than
# degraded: no traceability means no process signature, and no inspection
# results means no labels and therefore no defect model at all.
WEIGHTS = {
    "traceability": 0.25,
    "cycle_coverage": 0.20,
    "dark_share": 0.15,
    "historian": 0.15,
    "inspection_results": 0.20,
    "clock_quality": 0.05,
}

# Where the bands sit. A site above `READY_AT` runs today. A site above
# `INSTRUMENTABLE_AT` runs once the queue in its own sensor recommendations is
# fitted. Below that, the gap is structural rather than a matter of sensors.
READY_AT = 0.80
INSTRUMENTABLE_AT = 0.55

# How far apart two sources' clocks can sit before the component scores zero.
# Beyond this a derived cycle time at a hand-off is the skew rather than the
# station, which is the failure the whole bound rests on not having.
SKEW_LIMIT_S = 5.0

# Where each component stops being worth naming as missing. A site that can
# follow nine units in ten end to end has traceability; one that can follow
# six does not, and the difference is what a rollout plan turns on.
TRACEABILITY_ENOUGH = 0.90
CYCLE_COVERAGE_ENOUGH = 0.85
DARK_SHARE_ACCEPTABLE = 0.15
CLOCK_ACCEPTABLE = 0.50


@dataclass(frozen=True)
class Component:
    """One scored part of a site's readiness, and what is missing from it."""

    name: str
    value: str
    score: float
    weight: float
    missing: str


@dataclass(frozen=True)
class SiteReadiness:
    """One site, its band, and exactly what would move it."""

    site_id: str
    name: str
    band: str
    score: float
    components: tuple[Component, ...]
    missing: tuple[str, ...]
    instrumentation_cost_usd: float
    note: str


@dataclass(frozen=True)
class Measured:
    """What a site's own stream said, or what could not be read from it."""

    stations: int
    stations_emitting_cycles: int
    dark_stations: int
    units_with_full_signature: int
    units_seen: int
    inspection_results: int
    max_skew_s: float | None
    events_seen: int
    is_live: bool


@dataclass(frozen=True)
class StreamReading:
    """What one site's stream said. Every field is counted, none is surveyed."""

    stations_emitting: int = 0
    units_with_full_signature: int = 0
    units_seen: int = 0
    inspection_results: int = 0
    max_skew_s: float | None = None
    events_seen: int = 0


def measure(line: LineDefinition, reading: StreamReading) -> Measured:
    """Everything readiness needs, taken from one site's stream."""
    return Measured(
        stations=len(line.stations),
        stations_emitting_cycles=reading.stations_emitting,
        dark_stations=sum(1 for item in line.stations if item.tier == "C"),
        units_with_full_signature=reading.units_with_full_signature,
        units_seen=reading.units_seen,
        inspection_results=reading.inspection_results,
        max_skew_s=reading.max_skew_s,
        events_seen=reading.events_seen,
        is_live=reading.events_seen > 0,
    )


def score(
    line: LineDefinition, measured: Measured, instrumentation_cost_usd: float
) -> SiteReadiness:
    """Score one site and band it, naming what a component could not measure."""
    components = (
        _traceability(measured),
        _cycle_coverage(measured),
        _dark_share(measured),
        _historian(measured),
        _inspection(measured),
        _clock(measured),
    )
    total = sum(item.score * item.weight for item in components)
    missing = tuple(item.missing for item in components if item.missing)
    band = _band(total, instrumentation_cost_usd, components)
    return SiteReadiness(
        site_id=line.line_id,
        name=line.name,
        band=band,
        score=round(total, 3),
        components=components,
        missing=missing,
        instrumentation_cost_usd=instrumentation_cost_usd,
        note=_note(band, measured),
    )


def _band(
    total: float, instrumentation_cost_usd: float, components: tuple[Component, ...]
) -> str:
    """Which band a score falls into, in words."""
    if total >= READY_AT:
        return "READY"
    structural = any(
        item.score == 0.0 and item.name in {"traceability", "inspection_results"}
        for item in components
    )
    if total >= INSTRUMENTABLE_AT and not structural:
        del instrumentation_cost_usd
        return "READY WITH INSTRUMENTATION"
    return "NOT READY"


def _note(band: str, measured: Measured) -> str:
    """One sentence a person can act on."""
    if not measured.is_live:
        return (
            "Scored from the line definition alone. No event stream has been "
            "read from this site, so four of the six components could not be "
            "measured and are scored at zero rather than assumed."
        )
    if band == "READY":
        return (
            f"{measured.stations_emitting_cycles} of {measured.stations} stations "
            f"emit their own cycle and the twin runs against this site today."
        )
    if band == "READY WITH INSTRUMENTATION":
        return (
            "The twin runs here once the sensor queue below is fitted. Nothing "
            "in the gap is structural."
        )
    return (
        "A capability is absent rather than degraded. The list below says which "
        "one and what it would take."
    )


def _traceability(measured: Measured) -> Component:
    """Whether a unit can be followed end to end."""
    if measured.units_seen == 0:
        return Component(
            name="traceability",
            value="not measured",
            score=0.0,
            weight=WEIGHTS["traceability"],
            missing=(
                "No unit has been followed through this site. A scan at the "
                "release point and at each gate is what makes a process "
                "signature possible."
            ),
        )
    share = measured.units_with_full_signature / measured.units_seen
    return Component(
        name="traceability",
        value=f"{measured.units_with_full_signature} of {measured.units_seen} units",
        score=min(1.0, share),
        weight=WEIGHTS["traceability"],
        missing=(
            ""
            if share >= TRACEABILITY_ENOUGH
            else (
                f"{(1 - share) * 100:.0f} percent of units cannot be followed "
                f"end to end."
            )
        ),
    )


def _cycle_coverage(measured: Measured) -> Component:
    """What share of stations emit their own cycle."""
    share = (
        measured.stations_emitting_cycles / measured.stations
        if measured.stations
        else 0.0
    )
    return Component(
        name="cycle_coverage",
        value=f"{measured.stations_emitting_cycles} of {measured.stations} stations",
        score=min(1.0, share),
        weight=WEIGHTS["cycle_coverage"],
        missing=(
            ""
            if share >= CYCLE_COVERAGE_ENOUGH
            else (
                f"{measured.stations - measured.stations_emitting_cycles} stations "
                f"emit no cycle of their own."
            )
        ),
    )


def _dark_share(measured: Measured) -> Component:
    """How much of the line nothing watches, inverted so more is better."""
    share = measured.dark_stations / measured.stations if measured.stations else 1.0
    return Component(
        name="dark_share",
        value=f"{measured.dark_stations} of {measured.stations} dark",
        score=max(0.0, 1.0 - share * 2.0),
        weight=WEIGHTS["dark_share"],
        missing=(
            ""
            if share <= DARK_SHARE_ACCEPTABLE
            else f"{share * 100:.0f} percent of the line emits no machine data."
        ),
    )


def _historian(measured: Measured) -> Component:
    """Whether there is enough history to fit a baseline on."""
    return Component(
        name="historian",
        value=f"{measured.events_seen:,} events read",
        score=1.0 if measured.events_seen > 0 else 0.0,
        weight=WEIGHTS["historian"],
        missing=(
            ""
            if measured.events_seen > 0
            else "No historian or live stream has been connected."
        ),
    )


def _inspection(measured: Measured) -> Component:
    """Whether there are labels for a defect model to learn from."""
    return Component(
        name="inspection_results",
        value=f"{measured.inspection_results:,} verdicts read",
        score=1.0 if measured.inspection_results > 0 else 0.0,
        weight=WEIGHTS["inspection_results"],
        missing=(
            ""
            if measured.inspection_results > 0
            else (
                "No inspection verdicts reach the twin, so there are no labels "
                "and no defect model can be fitted."
            )
        ),
    )


def _clock(measured: Measured) -> Component:
    """How far apart the sources' clocks sit."""
    if measured.max_skew_s is None:
        return Component(
            name="clock_quality",
            value="not measured",
            score=0.0,
            weight=WEIGHTS["clock_quality"],
            missing="Clock skew between sources has not been measured here.",
        )
    score_value = max(0.0, 1.0 - measured.max_skew_s / SKEW_LIMIT_S)
    return Component(
        name="clock_quality",
        value=f"max {measured.max_skew_s:.1f} s between sources",
        score=score_value,
        weight=WEIGHTS["clock_quality"],
        missing=(
            ""
            if score_value > CLOCK_ACCEPTABLE
            else (
                f"Sources are {measured.max_skew_s:.1f} s apart, which is wider "
                f"than a hand-off, so a derived cycle time would be the skew "
                f"rather than the station."
            )
        ),
    )
