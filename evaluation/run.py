"""`make evaluate`. T-069, T-070.

Runs every scenario at every seed, joins the ledger against ground truth, and
writes `evaluation/report.md`, `evaluation/metrics.json` and
`evaluation/figures/*.svg`.

The defaults are what a person will wait for on a laptop. `--full` is the 8
scenarios by 20 seeds at 200 replications that TEST_PLAN.md Section 9 specifies,
which is T-130 and takes an evening. Whichever ran is stated at the top of the
report, because a number without the configuration that produced it is not
reproducible.
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import replace

from evaluation import metrics as metrics_module
from evaluation import report as report_module
from evaluation.harness import Settings, run_all, verify_determinism


def build_settings(arguments: argparse.Namespace) -> Settings:
    """Turn the command line into the settings the harness runs on."""
    settings = Settings()
    if arguments.full:
        settings = replace(
            settings,
            seeds=tuple(20260302 + offset for offset in range(20)),
            replications=200,
            units=920,
            cadence_s=120.0,
        )
    if arguments.quick:
        settings = replace(
            settings, seeds=(20260302,), replications=20, units=400, cadence_s=600.0
        )
    if arguments.scenarios:
        settings = replace(settings, scenarios=tuple(arguments.scenarios))
    if arguments.seeds:
        settings = replace(settings, seeds=tuple(arguments.seeds))
    if arguments.replications:
        settings = replace(settings, replications=arguments.replications)
    if arguments.units:
        settings = replace(settings, units=arguments.units)
    if arguments.workers:
        settings = replace(settings, workers=arguments.workers)
    return settings


def main(argv: list[str] | None = None) -> int:
    """Regenerate the evidence pack."""
    parser = argparse.ArgumentParser(
        prog="evaluate", description="Regenerate the evidence pack."
    )
    parser.add_argument("--full", action="store_true", help="the T-130 configuration")
    parser.add_argument("--quick", action="store_true", help="one seed, for a check")
    parser.add_argument("--scenarios", nargs="*", help="scenario identifiers")
    parser.add_argument("--seeds", nargs="*", type=int, help="seeds")
    parser.add_argument("--replications", type=int, help="replications per cycle")
    parser.add_argument("--units", type=int, help="units released per run")
    parser.add_argument("--workers", type=int, help="processes to run across")
    parser.add_argument(
        "--skip-determinism",
        action="store_true",
        help="skip the two-run determinism check, which doubles one scenario",
    )
    arguments = parser.parse_args(argv)
    settings = build_settings(arguments)

    print(
        f"Evaluating {len(settings.scenarios)} scenarios at "
        f"{len(settings.seeds)} seeds, {settings.replications} replications, "
        f"{settings.units} units per run."
    )
    started = time.monotonic()
    runs = run_all(settings, progress=True)
    print(f"{len(runs)} runs in {time.monotonic() - started:.0f} s.")

    summary = metrics_module.summarise(runs)
    determinism = (
        (True, "skipped at the caller's request")
        if arguments.skip_determinism
        else verify_determinism(settings)
    )
    path = report_module.write(summary, settings, runs, determinism)

    overall = summary.overall_stall()
    null = summary.null_scenario
    coverage = summary.overall_coverage()
    print("")
    print(f"Wrote {path.relative_to(path.parent.parent)}")
    print(
        f"  stall forecaster: {overall.made} made, "
        f"{overall.true_positive} true positive, "
        f"{overall.false_positive} false positive, "
        f"{overall.unscoreable} unscoreable, {overall.missed} missed"
    )
    print(
        f"  precision {_show(overall.precision)}  recall {_show(overall.recall)}  "
        f"median lead {_show(overall.median_lead_min, 1)} min"
    )
    if null is not None:
        print(
            f"  quiet shift: {_show(null.false_alerts_per_shift, 2)} false alerts "
            f"per shift over {null.shifts:.1f} shifts"
        )
    print(f"  virtual sensor coverage {_show(coverage.coverage)}")
    return 0


def _show(value: float | None, places: int = 3) -> str:
    if value is None:
        return "not measurable"
    return f"{value:.{places}f}"


if __name__ == "__main__":
    sys.exit(main())
