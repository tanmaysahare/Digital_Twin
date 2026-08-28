"""Command line entry point for the design rule checks."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.designlint import run

ROOT = Path(__file__).resolve().parent.parent.parent


def main(argv: list[str] | None = None) -> int:
    """Run the design rules and print any violation with its location."""
    parser = argparse.ArgumentParser(
        prog="designlint",
        description="The design rule checks in docs/quality/TEST_PLAN.md Section 7.",
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files to check. Defaults to every tracked text file.",
    )
    arguments = parser.parse_args(argv)

    report = run(ROOT, [path.resolve() for path in arguments.paths] or None)

    for violation in report.violations:
        try:
            location = violation.path.relative_to(ROOT).as_posix()
        except ValueError:
            location = violation.path.as_posix()
        print(f"{location}:{violation.line}: {violation.rule}: {violation.message}")
        if violation.excerpt:
            print(f"    {violation.excerpt}")

    if report.ok:
        print(
            f"Design rules passed. {report.rules_run} rules over "
            f"{report.files_scanned} files."
        )
        return 0
    print(
        f"\n{len(report.violations)} design rule violations over "
        f"{report.files_scanned} files. Fix the cause; these rules carry no "
        f"suppression mechanism."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
