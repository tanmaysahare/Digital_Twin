"""The design rule checks that implement AC-100.

Run with `make lint-design`, or as part of `make lint`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tools.designlint.files import tracked_files
from tools.designlint.rules import Rule, Violation, build_rules

__all__ = ["Report", "Violation", "run", "scan_text"]


@dataclass(frozen=True)
class Report:
    """The outcome of a lint run."""

    violations: list[Violation]
    files_scanned: int
    rules_run: int

    @property
    def ok(self) -> bool:
        """Report whether every rule passed."""
        return not self.violations


def scan_text(rules: list[Rule], path: Path, text: str) -> list[Violation]:
    """Run every applicable rule over one file's text."""
    found: list[Violation] = []
    for rule in rules:
        if rule.applies(path):
            found.extend(rule.check(path, text))
    return found


def run(root: Path, paths: list[Path] | None = None) -> Report:
    """Run every design rule over the repository, or over the given paths."""
    rules = build_rules(root)
    targets = paths if paths is not None else tracked_files(root)
    violations: list[Violation] = []
    for path in targets:
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        violations.extend(scan_text(rules, path, text))
    return Report(
        violations=violations, files_scanned=len(targets), rules_run=len(rules)
    )
