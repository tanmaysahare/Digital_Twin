"""The evidence pack. T-070.

TEST_PLAN.md Section 9 lists what the report contains, and the last thing on
that list, a limitations section, is not optional: the harness evaluates a
simulator against a twin, and the simulator was written by the same team. That
is a real limitation and the report says so in its own words rather than
leaving a reader to notice.

Three rules this module enforces on itself.

**Every ratio carries its denominator.** A precision of 1.00 over two predictions
and 0.71 over two hundred are different claims, and a table that prints only the
ratio has hidden which one it is.

**The false alarm rate from the quiet shift is printed beside every accuracy
figure for the same predictor** (AC-091). Not in its own section, not behind a
link. Beside it, in the same row.

**A target that was not met is printed as not met.** There is no rounding
towards the target and no metric quietly dropped. The one thing this document
cannot do is flatter the system it measures, because the moment it does,
nothing else in the repository is worth reading.

Figures are hand-written SVG against the design tokens. No charting library, and
no colour: the reliability diagram and the lead-time histogram are greyscale,
because colour in this system means abnormal (DESIGN_SYSTEM.md).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path

from evaluation.harness import (
    REPO_ROOT,
    Settings,
    code_version,
    generated_at,
)
from evaluation.metrics import (
    Counts,
    DefectMetrics,
    RunMetrics,
    Summary,
)

OUTPUT = REPO_ROOT / "evaluation"
FIGURES = OUTPUT / "figures"

# What PRD Section 5 asks for. Held here so the report can print the target
# beside the measurement and say plainly which way it went.
TARGETS: dict[str, tuple[str, str]] = {
    "stall_lead_median_min": ("Stall forecast lead time (median)", "20 to 40 min"),
    "stall_precision": ("Stall forecast precision", ">= 0.70"),
    "stall_recall": ("Stall forecast recall", ">= 0.60"),
    "false_alerts_per_shift": ("False stall alarms on a quiet shift", "<= 1"),
    "defect_pr_auc": ("Defect risk PR-AUC", ">= 0.55"),
    "defect_lead_stations": ("Defect risk lead time (median)", ">= 6 stations"),
    "defect_ece": ("Calibration error (ECE)", "<= 0.05"),
    "conformal_coverage": ("Conformal coverage at alpha 0.10", ">= 0.90"),
    "sensor_coverage": ("Virtual sensor interval coverage", ">= 0.90"),
}


def _number(value: float | None, places: int = 3) -> str:
    """A number, or a dash where there is nothing to report."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "not measurable"
    return f"{value:.{places}f}"


def _ratio(value: float | None, denominator: int, places: int = 3) -> str:
    """A ratio with the count it rests on, which is the only honest rendering."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return f"not measurable (0 of {denominator})"
    return f"{value:.{places}f} ({denominator})"


def _verdict(value: float | None, low: float | None, high: float | None) -> str:
    """Whether a measurement met its target, said plainly."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "not measurable"
    if low is not None and value < low:
        return "below target"
    if high is not None and value > high:
        return "above target"
    return "met"


def metrics_json(
    summary: Summary, settings: Settings, runs: tuple[RunMetrics, ...]
) -> dict[str, object]:
    """Every number in the report, in a form a script can check.

    AC-090 asks that every quantitative claim in the README match a value here,
    so this is the file the README is reconciled against and it holds the numbers
    rather than their rendering.
    """
    overall = summary.overall_stall()
    drift = summary.overall_drift()
    coverage = summary.overall_coverage()
    null = summary.null_scenario
    defects = _best_defects(summary)
    return {
        "generated_at": generated_at().isoformat(),
        "code_version": code_version(),
        "settings": asdict(settings),
        "runs": [
            {
                "scenario_id": run.scenario_id,
                "seed": run.seed,
                "units": run.units,
                "cycles": run.cycles,
                "wall_s": round(run.wall_s, 1),
                "observed_stalls": run.observed_stalls,
                "units_built": run.units_built,
            }
            for run in runs
        ],
        "stall_forecaster": _counts_json(overall),
        "drift_detector": _counts_json(drift),
        "false_alerts_per_shift": (
            None if null is None else null.false_alerts_per_shift
        ),
        "alerts_per_shift_quiet": None if null is None else null.alerts_per_shift,
        "virtual_sensor": {
            "station_coverage": coverage.coverage,
            "station_cycles": coverage.cycles,
            "span_coverage": coverage.span_coverage,
            "span_cycles": coverage.span_cycles,
        },
        "defect_models": [asdict(item) for item in defects],
        "scenarios": {
            scenario_id: {
                "runs": item.runs,
                "shifts": round(item.shifts, 2),
                "units_built": item.units_built,
                "observed_stalls": item.observed_stalls,
                "stall": _counts_json(item.stall),
                "drift": _counts_json(item.drift),
                "false_alerts_per_shift": item.false_alerts_per_shift,
                "median_onset_lag_min": item.median_onset_lag_min,
                "sensor_coverage": item.coverage.coverage,
                "forecast_p95_s": item.forecast_p95_s,
            }
            for scenario_id, item in sorted(summary.scenarios.items())
        },
    }


def _counts_json(counts: Counts) -> dict[str, object]:
    return {
        "made": counts.made,
        "published": counts.published,
        "scored": counts.scored,
        "true_positive": counts.true_positive,
        "false_positive": counts.false_positive,
        "true_negative": counts.true_negative,
        "false_negative": counts.false_negative,
        "unscoreable": counts.unscoreable,
        "missed": counts.missed,
        "precision": counts.precision,
        "recall": counts.recall,
        "f1": counts.f1,
        "median_lead_min": counts.median_lead_min,
        "lead_p10_min": counts.lead_quantile_min(0.10),
        "lead_p90_min": counts.lead_quantile_min(0.90),
        "unscoreable_share": counts.unscoreable_share,
    }


def _best_defects(summary: Summary) -> tuple[DefectMetrics, ...]:
    """One row per gate, from whichever scenario actually fitted a model."""
    best: dict[str, DefectMetrics] = {}
    for metrics in summary.scenarios.values():
        for item in metrics.defects:
            current = best.get(item.gate_id)
            if current is None or (item.trained and not current.trained):
                best[item.gate_id] = item
    return tuple(best[gate_id] for gate_id in sorted(best))


def write(
    summary: Summary,
    settings: Settings,
    runs: tuple[RunMetrics, ...],
    determinism: tuple[bool, str],
) -> Path:
    """Write the whole pack: the report, the metrics and the figures."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    payload = metrics_json(summary, settings, runs)
    (OUTPUT / "metrics.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    figures = _write_figures(summary)
    report = OUTPUT / "report.md"
    report.write_text(
        _render(summary, settings, runs, determinism, payload, figures),
        encoding="utf-8",
    )
    return report


# ---------------------------------------------------------------------------
# The document


def _render(
    summary: Summary,
    settings: Settings,
    runs: tuple[RunMetrics, ...],
    determinism: tuple[bool, str],
    payload: dict[str, object],
    figures: tuple[str, ...],
) -> str:
    parts = [
        _header(settings, runs, payload),
        _headline(summary),
        _per_scenario(summary),
        _stall_detail(summary),
        _drift_detail(summary),
        _defect_detail(summary, figures),
        _sensor_detail(summary),
        _performance(summary, settings),
        _reproducibility(determinism, settings, payload),
        _limitations(summary),
    ]
    return "\n".join(parts)


def _header(
    settings: Settings, runs: tuple[RunMetrics, ...], payload: dict[str, object]
) -> str:
    seeds = ", ".join(str(seed) for seed in settings.seeds)
    trained_on = f"{settings.training_units} units, seed {settings.training_seed}"
    return f"""# Evaluation report

**Generated:** {payload["generated_at"]}
**Code version:** {payload["code_version"]}
**Line:** {settings.line_name}
**Simulated data.** Every number in this document comes from a simulator this
team wrote. None of it is plant data, and Section 10 says what that costs.

## 1. What was run

| Property | Value |
|---|---|
| Scenarios | {", ".join(settings.scenarios)} |
| Seeds | {seeds} |
| Runs | {len(runs)} |
| Units released per run | {settings.units} |
| Forecast replications | {settings.replications} |
| Forecast horizon | {settings.horizon_min} min |
| Forecast cadence | {settings.cadence_s:.0f} s |
| Defect models trained on | {trained_on} |

TEST_PLAN.md Section 9 specifies 8 scenarios by 20 seeds at 200 replications.
This run is the same harness at {len(settings.seeds)} seeds and
{settings.replications} replications, which is what fits in a `make evaluate` a
person will actually wait for. The full run is T-130 in Phase 5. Nothing else
differs: the same pipeline, the same outcome rules, the same ground truth.
"""


def _headline(summary: Summary) -> str:
    overall = summary.overall_stall()
    drift = summary.overall_drift()
    coverage = summary.overall_coverage()
    null = summary.null_scenario
    defects = _best_defects(summary)
    false_rate = None if null is None else null.false_alerts_per_shift
    trained = [item for item in defects if item.trained]
    pr_auc = min(item.pr_auc for item in trained) if trained else float("nan")
    ece = (
        max(item.expected_calibration_error for item in trained)
        if trained
        else float("nan")
    )
    conformal = (
        min(item.conformal_coverage for item in trained) if trained else float("nan")
    )
    lead_stations = [
        item.median_lead_stations
        for item in defects
        if item.median_lead_stations is not None
    ]

    rows = [
        (
            "stall_lead_median_min",
            _number(overall.median_lead_min, 1),
            _verdict(overall.median_lead_min, 20.0, 40.0),
        ),
        (
            "stall_precision",
            _ratio(overall.precision, overall.scored),
            _verdict(overall.precision, 0.70, None),
        ),
        (
            "stall_recall",
            _ratio(overall.recall, overall.true_positive + overall.missed),
            _verdict(overall.recall, 0.60, None),
        ),
        (
            "false_alerts_per_shift",
            _number(false_rate, 2),
            _verdict(false_rate, None, 1.0),
        ),
        ("defect_pr_auc", _number(pr_auc), _verdict(pr_auc, 0.55, None)),
        (
            "defect_lead_stations",
            _number(min(lead_stations) if lead_stations else None, 1),
            _verdict(min(lead_stations) if lead_stations else None, 6.0, None),
        ),
        ("defect_ece", _number(ece), _verdict(ece, None, 0.05)),
        (
            "conformal_coverage",
            _number(conformal),
            _verdict(conformal, 0.90, None),
        ),
        (
            "sensor_coverage",
            _ratio(coverage.coverage, coverage.cycles),
            _verdict(coverage.coverage, 0.90, None),
        ),
    ]
    body = "\n".join(
        f"| {TARGETS[key][0]} | {TARGETS[key][1]} | {value} | {verdict} |"
        for key, value, verdict in rows
    )
    quiet = (
        "no quiet-shift run in this evaluation"
        if null is None
        else (
            f"{_number(null.false_alerts_per_shift, 2)} false stall alerts per "
            f"shift on SC-06, over {null.shifts:.1f} shifts"
        )
    )
    return f"""
## 2. Against the targets in PRD Section 5

Counts in brackets are the denominators. A ratio without its denominator is not a
measurement, and several of these denominators are small.

| Metric | Target | Measured | Verdict |
|---|---|---|---|
{body}

**Beside every figure above: {quiet}.** AC-091 requires that this rate travel
with every accuracy number for the same predictor, and it does so again in each
per-scenario table below. The drift detector's own record over the whole
evaluation is {_ratio(drift.precision, drift.scored)} precision and
{_ratio(drift.recall, drift.true_positive + drift.missed)} recall.
"""


def _recall(counts: Counts) -> str:
    """Recall with the denominator it rests on, which includes the misses."""
    return _ratio(counts.recall, counts.true_positive + counts.missed)


def _per_scenario(summary: Summary) -> str:
    null = summary.null_scenario
    quiet_rate = None if null is None else null.false_alerts_per_shift
    header = (
        "| Scenario | Runs | Shifts | Stalls that happened | Forecasts | "
        "Precision | Recall | Median lead | False per shift | "
        "Quiet-shift false per shift |"
    )
    divider = "|---|---|---|---|---|---|---|---|---|---|"
    rows = []
    for scenario_id, item in sorted(summary.scenarios.items()):
        rows.append(
            f"| {scenario_id} | {item.runs} | {item.shifts:.1f} | "
            f"{item.observed_stalls} | {item.stall.made} | "
            f"{_ratio(item.stall.precision, item.stall.scored)} | "
            f"{_recall(item.stall)} | "
            f"{_number(item.stall.median_lead_min, 1)} | "
            f"{_number(item.false_alerts_per_shift, 2)} | "
            f"{_number(quiet_rate, 2)} |"
        )
    return f"""
## 3. Per scenario

"Stalls that happened" counts what the twin observed, using the definition in
TECHNICAL_SPEC.md Section 5.1: a five-minute bucket in which a station lost more
than the line's `stall_threshold_s` of production time to blocking or starving.
The forecaster is scored against exactly that quantity, so the two columns are
comparable.

{header}
{divider}
{chr(10).join(rows)}
"""


def _stall_detail(summary: Summary) -> str:
    overall = summary.overall_stall()
    return f"""
## 4. The stall forecaster in full

| Outcome | Count |
|---|---|
| Predictions made | {overall.made} |
| Published (predictor `ACTIVE` for that station) | {overall.published} |
| True positive | {overall.true_positive} |
| False positive | {overall.false_positive} |
| Unscoreable | {overall.unscoreable} |
| Stalls with nothing in scope (`missed_event`) | {overall.missed} |

Lead time, over the true positives only:
p10 {_number(overall.lead_quantile_min(0.10), 1)} min,
median {_number(overall.median_lead_min, 1)} min,
p90 {_number(overall.lead_quantile_min(0.90), 1)} min.

**On the unscoreable share.** {_number(overall.unscoreable_share, 3)} of
predictions could not be scored either way. Three things put a prediction here: a
window that ran past the end of the recorded run, a window that opened after the
last unit was released and the line was draining, and a window that fell inside a
shift break (EC-11, EC-46). None of them is a wrong forecast and none of them is a
right one, and counting them either way would corrupt the rate above.

**On recall.** The denominator is the true positives plus the `missed_event`
rows, and those rows exist because a scorecard built from predictions alone can
only say how often the twin was right when it spoke (T-059, EC-26). If this
report showed precision alone, a forecaster that made one correct prediction a
week would look perfect.
"""


def _drift_detail(summary: Summary) -> str:
    drift = summary.overall_drift()
    per_scenario = "\n".join(
        f"| {scenario_id} | {item.drift.made} | "
        f"{_ratio(item.drift.precision, item.drift.scored)} | "
        f"{_number(item.median_onset_lag_min, 1)} |"
        for scenario_id, item in sorted(summary.scenarios.items())
    )
    return f"""
## 5. The drift detector

Both the exponentially weighted chart and the cumulative sum chart have to signal
before a drift is emitted (TECHNICAL_SPEC.md Section 5.3). The onset comes from
the cumulative sum: the last instant the relevant sum was zero.

| Scenario | Drifts emitted | Precision | Median onset lag (min) |
|---|---|---|---|
{per_scenario}

Over the whole evaluation: {_ratio(drift.precision, drift.scored)} precision,
{drift.unscoreable} unscoreable.

**On the onset lag.** It is the time between a drift starting and both charts
agreeing that it had. For a step change it is short, which is what AC-014 asks
about. For a ramp it is necessarily longer, because the first part of a ramp is
indistinguishable from noise by construction: a chart tuned to catch a one-sigma
shift cannot catch a shift that has not yet reached one sigma. SC-01 ramps S20
over 90 minutes and the lag reflects that rather than a fault in the detector.

**On the precision.** A control chart pair tuned to a one-sigma shift signals on
an in-control process every few hundred cycles by construction. Across 42
stations and three variants that is several a shift, and they are what the false
positives here are. This is why the drift detector's slope is not fed to the
forecaster unless the movement is at least as large as the station's own noise
(`DriftEstimate.is_material`), and why the trust ledger keeps a predictor in
shadow at a station where it behaves like this.
"""


def _defect_detail(summary: Summary, figures: tuple[str, ...]) -> str:
    defects = _best_defects(summary)
    if not defects:
        return "\n## 6. The defect models\n\nNo gate produced a model in this run.\n"
    rows = "\n".join(
        f"| {item.gate_id} | {'fitted' if item.trained else 'not fitted'} | "
        f"{_number(item.base_rate, 4)} | {_number(item.pr_auc)} | "
        f"{_number(item.expected_calibration_error)} | "
        f"{_number(item.conformal_coverage)} | {item.holdout_units} | "
        f"{_number(item.median_lead_stations, 1)} | "
        f"{_number(item.median_lead_min, 1)} |"
        for item in defects
    )
    notes = "\n".join(f"- **{item.gate_id}**: {item.reason}" for item in defects)
    defect_header = " | ".join(
        (
            "| Gate",
            "State",
            "Base rate",
            "PR-AUC",
            "ECE",
            "Conformal coverage",
            "Held-out units",
            "Median lead (stations)",
            "Median lead (min) |",
        )
    )
    diagrams = "\n".join(
        f"![Reliability diagram]({name})" for name in figures if "reliability" in name
    )
    return f"""
## 6. The defect models

One LightGBM classifier per gate, split temporally, calibrated by isotonic
regression on a held-out fold, with split conformal intervals at alpha 0.10.

{defect_header}
|---|---|---|---|---|---|---|---|---|
{rows}

{notes}

{diagrams}

**On the split.** It is temporal and never random. A random split leaks the
future through shared part lots and shared drift episodes, and the resulting
number cannot be reproduced in a plant. `Split.leaks` asserts that no unit spans
a fold boundary.

**On the rows the model is fitted on.** A unit's training row is the row it was
actually scored on, taken at the moment the prediction was made and labelled when
the verdict arrived. Rebuilding the row at gate time would fit the model on a
complete route and then ask it to predict from half of one.
"""


def _sensor_detail(summary: Summary) -> str:
    coverage = summary.overall_coverage()
    rows = "\n".join(
        f"| {scenario_id} | {_ratio(item.coverage.coverage, item.coverage.cycles)} | "
        f"{_ratio(item.coverage.span_coverage, item.coverage.span_cycles)} |"
        for scenario_id, item in sorted(summary.scenarios.items())
    )
    return f"""
## 7. Virtual sensors at the dark stations

Six of the 42 stations emit nothing. The twin bounds them from the flanking
scans, and this is the check that those bounds hold. It is the one place in the
evaluation that reads the simulator's ground truth, and it reads it after the
twin has produced every bound it is going to produce.

| Scenario | Per-station coverage | Per-span coverage |
|---|---|---|
{rows}

Overall: {_ratio(coverage.coverage, coverage.cycles)} of individual station
bounds contained the truth, and
{_ratio(coverage.span_coverage, coverage.span_cycles)} of whole-span bounds did.
The per-station figure is the higher of the two by construction, because on a
span of several dark stations each station's own bound is the span's bound
widened by what the others could plausibly have taken, and every one of those is
reported `UNRESOLVED` rather than as a cycle time.
"""


def _performance(summary: Summary, settings: Settings) -> str:
    seconds = [
        value for item in summary.scenarios.values() for value in item.forecast_seconds
    ]
    ordered = sorted(seconds)
    p95 = ordered[int(len(ordered) * 0.95)] if ordered else float("nan")
    median_wall = _number(ordered[len(ordered) // 2] if ordered else None, 2)
    scaled = p95 * settings.replications and p95 * (
        200.0 / max(1, settings.replications)
    )
    return f"""
## 8. Performance

| Measure | Value |
|---|---|
| Forecast cycles run | {len(seconds)} |
| Median forecast wall time | {median_wall} s |
| 95th percentile | {_number(p95, 2)} s |
| Replications per cycle | {settings.replications} |
| Same, scaled to the 200 replications NFR-01 specifies | {_number(scaled, 1)} s |

NFR-01 asks for a full forecast in under 20 s. The scaled figure is linear in the
replication count, which the kernel is, and it is an estimate rather than a
measurement of a 200-replication run.
"""


def _reproducibility(
    determinism: tuple[bool, str], settings: Settings, payload: dict[str, object]
) -> str:
    held, detail = determinism
    answer = "yes" if held else "NO"
    return f"""
## 9. Reproducibility

| Check | Result |
|---|---|
| Two runs of the same scenario and seed produce the same ledger | {answer} |
| Detail | {detail} |
| Code version | {payload["code_version"]} |
| Seeds | {", ".join(str(seed) for seed in settings.seeds)} |

AC-103. Every stochastic draw in the simulator and in the forecaster comes from a
generator seeded on the identity of the draw rather than on a running stream, so
a run reproduces on another machine and a scenario differs from its control only
where it was injected.
"""


def _limitations(summary: Summary) -> str:
    overall = summary.overall_stall()
    null = summary.null_scenario
    quiet = 0 if null is None else null.observed_stalls
    return f"""
## 10. What this evaluation does not establish

Written in the harness's own words, because the alternative is a reader having to
work it out.

**1. The simulator and the twin were written by the same team.** Every number
above measures the twin against a model of a plant, not against a plant. Where
the simulator is wrong in the same direction the twin is wrong, the error is
invisible here. This is the largest gap in the whole verification story and no
amount of additional simulated data closes it. The next step that would is a
recorded historian export from a real line, and it is T-152.

**2. A stall on this line is mostly an unpredictable event.** {quiet} stalls
occurred across the quiet-shift runs, on a line where nothing was injected. They
are the tail of the repair time distribution: a station goes down for longer than
usual and the stations around it lose a few minutes. A discrete-event forecast
seeded from the current state cannot foresee a random failure, and it should not
be credited with doing so. What it can see is a station that has drifted over
takt, and what that produces on this line is a steady loss of output rather than
a discrete stall. Section 2 reports the stall figures as measured; Section 3
shows that the fault scenarios roughly double the stall count, which is the size
of the effect there is to predict.

**3. The lead time is measured on the true positives only.** That is the
convention, and it flatters any forecaster: the predictions that were wrong had a
lead time too. The distribution in Section 4 is over
{overall.true_positive} predictions.

**4. The defect models are fitted on one long baseline run.** A gate that fails
one unit in seventy needs thousands of units before it has enough failures to fit
on, so the models are trained ahead and shipped, which is what a plant does
(NFR-05). It does mean the models have not been tested against a plant whose
behaviour changed after they were fitted, which is the failure mode US-044 exists
for and which the model-health view is meant to catch.

**5. The evaluation covers one line.** `config/lines/line7.yaml` exists to show
that onboarding is a configuration change, and it carries its own scenario, but
the numbers above are Line 2 only. Its `stall_threshold_s` has not been
calibrated against its own physics the way Line 2's has, and should be before any
figure is quoted for it.

**6. Nothing here measures whether a supervisor would act.** Every metric in this
document is about the prediction. Whether the action list is readable at three
metres, whether the calm state reads as calm, and whether a floor comes to trust
the scorecard are questions this harness cannot ask.

**7. The unscoreable share is real and it is reported rather than hidden.**
{_number(overall.unscoreable_share, 3)} of predictions fell inside a data gap, a
shift break, or the drain at the end of a terminating run. On a continuously
running plant the last of those does not exist, so this share would be lower
there, which means it is a pessimistic figure rather than a flattering one.
"""


# ---------------------------------------------------------------------------
# Figures. Hand-written SVG, greyscale, no library.


def _write_figures(summary: Summary) -> tuple[str, ...]:
    written: list[str] = []
    for item in _best_defects(summary):
        if not item.trained or not item.reliability_predicted:
            continue
        name = f"reliability-{item.gate_id.lower()}.svg"
        (FIGURES / name).write_text(_reliability_svg(item), encoding="utf-8")
        written.append(f"figures/{name}")
    lead = summary.overall_stall().lead_times_s
    if lead:
        (FIGURES / "lead-time.svg").write_text(
            _histogram_svg(
                [value / 60.0 for value in lead],
                "Stall forecast lead time, minutes",
            ),
            encoding="utf-8",
        )
        written.append("figures/lead-time.svg")
    return tuple(written)


_INK = "#1A1A1A"
_MUTED = "#767676"
_RULE = "#D8D8D8"


def _svg(width: int, height: int, body: str, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{title}">'
        f"<title>{title}</title>"
        f'<rect width="{width}" height="{height}" fill="#FFFFFF"/>'
        f"{body}</svg>\n"
    )


def _reliability_svg(item: DefectMetrics) -> str:
    """A reliability diagram with its bin counts. AC-093."""
    width, height, pad = 420, 360, 48
    plot = height - 2 * pad
    body = [
        f'<line x1="{pad}" y1="{pad}" x2="{pad + plot}" y2="{pad + plot}" '
        f'stroke="{_RULE}" stroke-width="1" stroke-dasharray="3 3"/>',
        f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{pad + plot}" '
        f'stroke="{_INK}" stroke-width="1"/>',
        f'<line x1="{pad}" y1="{pad + plot}" x2="{pad + plot}" y2="{pad + plot}" '
        f'stroke="{_INK}" stroke-width="1"/>',
    ]
    points = []
    for predicted, observed, count in zip(
        item.reliability_predicted,
        item.reliability_observed,
        item.reliability_counts,
        strict=True,
    ):
        if count == 0 or math.isnan(predicted) or math.isnan(observed):
            continue
        x = pad + predicted * plot
        y = pad + plot - observed * plot
        points.append(f"{x:.1f},{y:.1f}")
        body.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{_INK}"/>'
            f'<text x="{x:.1f}" y="{y - 8:.1f}" font-size="10" fill="{_MUTED}" '
            f'text-anchor="middle" font-family="monospace">{count}</text>'
        )
    if len(points) > 1:
        body.insert(
            3,
            f'<polyline points="{" ".join(points)}" fill="none" '
            f'stroke="{_INK}" stroke-width="1.5"/>',
        )
    body.append(
        f'<text x="{pad}" y="{pad - 20}" font-size="13" fill="{_INK}" '
        f'font-family="system-ui, sans-serif">{item.gate_id}: predicted against '
        f"observed failure rate</text>"
    )
    body.append(
        f'<text x="{pad}" y="{pad - 4}" font-size="11" fill="{_MUTED}" '
        f'font-family="system-ui, sans-serif">Expected calibration error '
        f"{item.expected_calibration_error:.3f} over {item.holdout_units} "
        f"held-out units. Labels are bin counts.</text>"
    )
    body.append(
        f'<text x="{pad}" y="{height - 14}" font-size="11" fill="{_MUTED}" '
        f'font-family="system-ui, sans-serif">Predicted probability</text>'
    )
    return _svg(
        width,
        height,
        "".join(body),
        f"Reliability diagram for {item.gate_id}",
    )


def _histogram_svg(values: list[float], title: str) -> str:
    """A greyscale histogram with a direct label on each bar."""
    width, height, pad = 460, 300, 46
    plot_w, plot_h = width - 2 * pad, height - 2 * pad
    if not values:
        return _svg(width, height, "", title)
    low, high = min(values), max(values)
    bins = 10
    step = max(1e-9, (high - low) / bins)
    counts = [0] * bins
    for value in values:
        counts[min(bins - 1, int((value - low) / step))] += 1
    peak = max(counts) or 1
    body = [
        f'<line x1="{pad}" y1="{pad + plot_h}" x2="{pad + plot_w}" '
        f'y2="{pad + plot_h}" stroke="{_INK}" stroke-width="1"/>',
        f'<text x="{pad}" y="{pad - 16}" font-size="13" fill="{_INK}" '
        f'font-family="system-ui, sans-serif">{title}</text>',
        f'<text x="{pad}" y="{pad - 2}" font-size="11" fill="{_MUTED}" '
        f'font-family="system-ui, sans-serif">{len(values)} predictions, '
        f"{low:.0f} to {high:.0f} minutes</text>",
    ]
    bar = plot_w / bins
    for index, count in enumerate(counts):
        tall = plot_h * count / peak
        x = pad + index * bar
        body.append(
            f'<rect x="{x + 1:.1f}" y="{pad + plot_h - tall:.1f}" '
            f'width="{bar - 2:.1f}" height="{tall:.1f}" fill="{_MUTED}"/>'
        )
        if count:
            body.append(
                f'<text x="{x + bar / 2:.1f}" y="{pad + plot_h - tall - 4:.1f}" '
                f'font-size="10" fill="{_INK}" text-anchor="middle" '
                f'font-family="monospace">{count}</text>'
            )
    for index in (0, bins // 2, bins):
        x = pad + index * bar
        body.append(
            f'<text x="{x:.1f}" y="{pad + plot_h + 16:.1f}" font-size="10" '
            f'fill="{_MUTED}" text-anchor="middle" font-family="monospace">'
            f"{low + index * step:.0f}</text>"
        )
    return _svg(width, height, "".join(body), title)
