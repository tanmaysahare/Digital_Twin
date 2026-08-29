"""The business case, and the sensitivity table that makes it interrogable.

T-118, AC-071. UX_SPEC.md Section 4.2.

Three design rules govern this module and each of them is there because of a way
business cases usually go wrong.

**Every assumption carries its source and its uncertainty.** An assumption
without a stated source is a number nobody can defend, and the one thing Meera's
job consists of is defending numbers. The `source` field is not optional and the
model refuses to compute without one.

**Forecast precision defaults to the measured value from the ledger, not to an
aspiration.** The twin knows how often it has been right. Letting the case be
built on a hoped-for precision would make the case a wish, and the ledger exists
precisely so that it does not have to be.

**The sensitivity table is mandatory.** A case that does not show what it is
sensitive to cannot be argued with, and a case that cannot be argued with does
not survive its first meeting. Each assumption is moved to each end of its own
stated uncertainty with the others held still, and the swing is reported. The
ranking is what a reader should look at first, so it is what the table sorts on.

**Where a number is zero, it is zero on purpose.** `unit_value_usd` defaults to
zero in `config/lines/*.yaml`, so a site that has not supplied its own
contribution margin sees a modelled benefit of zero rather than one built on an
industry figure that does not apply to it. The note says so.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from twin.domain.estimate import Estimate, Interval

# How many shifts a year the recovered minutes are spread over. Two shifts a day
# over the working year the sensor value model already uses, so the two agree.
SHIFTS_PER_YEAR = 480

# How wide the modelled benefit's interval is, as a share either side of the
# central figure. It is the precision's own uncertainty carried through: a
# precision measured over tens of predictions rather than thousands does not
# support a tighter claim than this.
BENEFIT_SPREAD = 0.35


@dataclass(frozen=True)
class Assumption:
    """One input to the case, with where it came from and how sure it is."""

    key: str
    label: str
    value: float
    unit: str
    source: str
    uncertainty: str
    # How far the sensitivity pass moves this assumption, as a share of itself.
    swing_share: float = 0.25
    editable: bool = True

    def __post_init__(self) -> None:
        """Refuse an assumption with no stated source.

        Raises:
            ValueError: if `source` is empty. A number nobody can trace is a
                number nobody can defend, and this model exists to be defended.
        """
        if not self.source.strip():
            message = (
                f"assumption {self.key} has no source. An assumption without a "
                f"stated source cannot be reviewed and does not belong in a case"
            )
            raise ValueError(message)


@dataclass(frozen=True)
class SensitivityRow:
    """How far the result moves when one assumption moves to its own limits."""

    key: str
    label: str
    low_result: float
    high_result: float

    @property
    def swing(self) -> float:
        """The size of the move. What the table ranks on."""
        return abs(self.high_result - self.low_result)


@dataclass(frozen=True)
class CaseResult:
    """The modelled case, its payback, and what it is most sensitive to."""

    scenario_id: str
    assumptions: tuple[Assumption, ...]
    annual_benefit: Estimate
    payback_months: float | None
    sensitivity: tuple[SensitivityRow, ...]
    notes: tuple[str, ...]


def defaults(
    *,
    measured_precision: float | None,
    precision_basis: str,
    instrumentation_cost_usd: float,
    unit_value_usd: float,
) -> tuple[Assumption, ...]:
    """The assumption set, with the ledger's own precision already in it."""
    precision = measured_precision if measured_precision is not None else 0.0
    return (
        Assumption(
            key="baseline_stop_min_per_month",
            label="Unplanned stop minutes per line per month",
            value=0.0,
            unit="min",
            source=(
                "Site-measured. No default is supplied: a published industry "
                "figure would not describe this line and the case would rest on "
                "it."
            ),
            uncertainty="Enter the site's own shift-report total for one month.",
        ),
        Assumption(
            key="recoverable_share",
            label="Share of those minutes a 20 minute warning could recover",
            value=0.15,
            unit="share",
            source=(
                "Our assumption. It is the share of stops that a supervisor "
                "with a floater and twenty minutes can prevent or shorten, and "
                "it is the assumption the whole case is most sensitive to."
            ),
            uncertainty="Plus or minus half of itself until a pilot measures it.",
            swing_share=0.5,
        ),
        Assumption(
            key="forecast_precision",
            label="Forecast precision",
            value=round(precision, 3),
            unit="share",
            source=precision_basis,
            uncertainty=(
                "Measured over the predictions in the ledger. It moves as the "
                "ledger fills and it is not a target."
            ),
            editable=False,
        ),
        Assumption(
            key="unit_value_usd",
            label="Contribution margin per unit",
            value=unit_value_usd,
            unit="USD",
            source=(
                "Site-specific. Zero until the plant supplies its own figure, "
                "so that a modelled benefit reads as zero rather than as a "
                "number the twin invented."
            ),
            uncertainty="Enter the plant's own contribution margin.",
        ),
        Assumption(
            key="units_per_stop_minute",
            label="Units lost per minute of line stop",
            value=1.0,
            unit="units",
            source=(
                "Derived from takt. A 60 s takt loses one unit a minute while "
                "the line is stopped, before any catch-up."
            ),
            uncertainty="Catch-up recovers some of it, so this is an upper figure.",
        ),
        Assumption(
            key="implementation_cost_usd",
            label="Implementation cost per site",
            value=0.0,
            unit="USD",
            source=(
                "Site-specific. Integration effort against that site's own "
                "historian and quality system."
            ),
            uncertainty="Enter the quoted integration cost.",
        ),
        Assumption(
            key="instrumentation_cost_usd",
            label="Instrumentation cost per site",
            value=round(instrumentation_cost_usd, 2),
            unit="USD",
            source=(
                "Pulled from this site's own sensor queue, at the indicative "
                "costs in config/catalogue/sensors.yaml. Those are our "
                "assumptions rather than quotations and the queue says so."
            ),
            uncertainty="Replace with site quotations before a capital request.",
            editable=False,
        ),
    )


def evaluate(
    assumptions: tuple[Assumption, ...], scenario_id: str = "default"
) -> CaseResult:
    """Compute the case and the sensitivity ranking beside it."""
    values = {item.key: item.value for item in assumptions}
    centre = _benefit(values)
    notes = list(_notes(values))
    cost = values.get("implementation_cost_usd", 0.0) + values.get(
        "instrumentation_cost_usd", 0.0
    )
    payback = (cost / (centre / 12.0)) if centre > 0.0 else None
    return CaseResult(
        scenario_id=scenario_id,
        assumptions=assumptions,
        annual_benefit=Estimate.derived(
            Interval(
                max(0.0, centre * (1.0 - BENEFIT_SPREAD)),
                centre * (1.0 + BENEFIT_SPREAD),
            ),
            basis=(
                "recoverable stop minutes times forecast precision times units "
                "per stop minute times contribution margin, over a year"
            ),
            confidence=0.4,
        ),
        payback_months=round(payback, 1) if payback is not None else None,
        sensitivity=_sensitivity(assumptions, values),
        notes=tuple(notes),
    )


def apply(
    assumptions: tuple[Assumption, ...], edits: dict[str, float]
) -> tuple[Assumption, ...]:
    """The assumption set with the caller's edits applied to editable fields."""
    return tuple(
        replace(item, value=edits[item.key])
        if item.editable and item.key in edits
        else item
        for item in assumptions
    )


def _benefit(values: dict[str, float]) -> float:
    """The central modelled annual benefit."""
    monthly_minutes = values.get("baseline_stop_min_per_month", 0.0)
    recoverable = values.get("recoverable_share", 0.0)
    precision = values.get("forecast_precision", 0.0)
    units_per_min = values.get("units_per_stop_minute", 0.0)
    unit_value = values.get("unit_value_usd", 0.0)
    return monthly_minutes * 12.0 * recoverable * precision * units_per_min * unit_value


def _sensitivity(
    assumptions: tuple[Assumption, ...], values: dict[str, float]
) -> tuple[SensitivityRow, ...]:
    """Move each assumption to its own limits with the others held still."""
    rows: list[SensitivityRow] = []
    for item in assumptions:
        if item.key in {"implementation_cost_usd", "instrumentation_cost_usd"}:
            continue
        low = dict(values)
        high = dict(values)
        low[item.key] = item.value * (1.0 - item.swing_share)
        high[item.key] = item.value * (1.0 + item.swing_share)
        rows.append(
            SensitivityRow(
                key=item.key,
                label=item.label,
                low_result=round(_benefit(low), 2),
                high_result=round(_benefit(high), 2),
            )
        )
    return tuple(sorted(rows, key=lambda row: -row.swing))


def _notes(values: dict[str, float]) -> tuple[str, ...]:
    """What a reader has to know before they read the number."""
    found: list[str] = []
    if values.get("unit_value_usd", 0.0) <= 0.0:
        found.append(
            "Contribution margin per unit is zero, so the modelled benefit is "
            "zero. Enter the plant's own figure to see a result. Nothing here "
            "supplies an industry average in its place."
        )
    if values.get("baseline_stop_min_per_month", 0.0) <= 0.0:
        found.append(
            "Unplanned stop minutes per month has not been entered. It comes "
            "from the site's own shift reporting."
        )
    if values.get("forecast_precision", 0.0) <= 0.0:
        found.append(
            "No predictor has been promoted yet, so measured precision is zero "
            "and the case computes to zero. That is the ledger reporting where "
            "the product actually is."
        )
    return tuple(found)
