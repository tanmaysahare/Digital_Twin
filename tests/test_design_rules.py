"""Every design rule has a fixture that fails it and a fixture that passes it.

T-006, AC-100.

The fixtures are written into a temporary tree rather than committed, because a
committed fixture for the em dash rule would be a tracked file containing an em
dash, which is the thing the rule forbids. Generating them keeps both true at
once: the rule is exercised on real files, and no tracked file violates it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.designlint import run, scan_text
from tools.designlint.rules import (
    EM_DASH,
    build_rules,
    load_banned_phrases,
    load_banned_words,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
LINT_DIR = REPO_ROOT / ".lint"

A_BANNED_WORD = load_banned_words(LINT_DIR)[0]
EMOJI = chr(0x1F600)

# Two failing fixtures are assembled from fragments so that this file does not
# itself contain the pattern its rule forbids. A literal here would make the
# linter fail on its own test suite, and exempting this file would be the
# suppression mechanism these rules deliberately lack.
UNSEEDED_DRAW = "import numpy as np\n\nvalue = np." + "random.rand()\n"
BARE_TODO = "# TO" + "DO handle the unresolvable case\n"
TRACKED_TODO = "# TO" + "DO(T-042) handle the unresolvable case\n"


def _fixture(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# rule name, relative path, failing body, passing body
CASES: list[tuple[str, str, str, str]] = [
    (
        "no-em-dash",
        "docs/note.md",
        f"The line stalled at S22{EM_DASH}eleven units were lost.\n",
        "The line stalled at S22. Eleven units were lost.\n",
    ),
    (
        "no-emoji",
        "docs/note.md",
        f"Forecast raised {EMOJI}\n",
        "Forecast raised at 09:14.\n",
    ),
    (
        "no-banned-words",
        "docs/note.md",
        f"A {A_BANNED_WORD} forecast for S20.\n",
        "The S20 forecast has been right 7 times in 10.\n",
    ),
    (
        "no-exclamation-mark",
        "web/src/app/page.tsx",
        "export const NOTICE = 'S20 has drifted!';\n",
        "export const NOTICE = 'S20 has drifted 4.1 s above normal.';\n",
    ),
    (
        "no-placeholder-content",
        "web/src/app/page.tsx",
        "export const ROWS = ['Item 1', 'Item 2'];\n",
        "export const ROWS = ['S20', 'S22'];\n",
    ),
    (
        "no-gradient",
        "web/src/styles/strip.css",
        ".strip { background: linear-gradient(var(--paper), var(--paper-sunk)); }\n",
        ".strip { background: var(--paper-sunk); }\n",
    ),
    (
        "no-blur",
        "web/src/styles/drawer.css",
        ".drawer { backdrop-filter: blur(8px); }\n",
        ".drawer { background: var(--paper-raised); border: var(--border); }\n",
    ),
    (
        "no-large-radius",
        "web/src/styles/card.css",
        ".card { border-radius: 16px; }\n",
        ".card { border-radius: var(--radius); }\n",
    ),
    (
        "no-dark-theme",
        "web/src/styles/theme.css",
        "@media (prefers-color-scheme: dark) { :root { --paper: #111111; } }\n",
        ":root { --page-gap: var(--space-6); }\n",
    ),
    (
        "no-raw-colour",
        "web/src/components/StateChip.css",
        ".chip { color: #a32020; }\n",
        ".chip { color: var(--state-down); }\n",
    ),
    (
        "no-unseeded-random",
        "twin/forecast/draw.py",
        UNSEEDED_DRAW,
        "import numpy as np\n\nvalue = np.random.default_rng(seed).random()\n",
    ),
    (
        "no-external-host",
        "web/src/lib/api.ts",
        "export const FONT = 'https://fonts.googleapis.com/css2';\n",
        "export const FONT = '/fonts/inter.woff2';\n",
    ),
    (
        "no-untracked-todo",
        "twin/state/estimator.py",
        BARE_TODO,
        TRACKED_TODO,
    ),
]


@pytest.mark.parametrize(
    ("rule_name", "relative", "failing", "passing"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_rule_fixtures(
    tmp_path: Path, rule_name: str, relative: str, failing: str, passing: str
) -> None:
    rules = build_rules(tmp_path, lint_dir=LINT_DIR)

    bad = _fixture(tmp_path, relative, failing)
    violations = scan_text(rules, bad, failing)
    assert rule_name in {violation.rule for violation in violations}, (
        f"{rule_name} did not fire on its failing fixture. "
        f"Fired: {sorted({violation.rule for violation in violations})}"
    )

    good = _fixture(tmp_path, relative, passing)
    assert scan_text(rules, good, passing) == []


def test_every_rule_has_a_fixture() -> None:
    covered = {case[0] for case in CASES}
    declared = {rule.name for rule in build_rules(REPO_ROOT)}
    assert declared == covered


def test_repository_passes_every_design_rule() -> None:
    report = run(REPO_ROOT)
    assert report.ok, "\n".join(
        f"{violation.path}:{violation.line}: {violation.rule}: {violation.message}"
        for violation in report.violations
    )


def test_banned_lists_are_readable() -> None:
    assert load_banned_words(LINT_DIR)
    assert load_banned_phrases(LINT_DIR)


def test_quoted_material_is_not_judged() -> None:
    """A document that quotes a bad example is not itself a violation."""
    rules = build_rules(REPO_ROOT)
    path = REPO_ROOT / "docs" / "quoting.md"
    text = f'Do not write "a {A_BANNED_WORD} forecast". Write the hit rate instead.\n'
    assert scan_text(rules, path, text) == []


def test_a_generator_annotation_is_not_a_draw() -> None:
    """A function that declares it takes a seeded generator is doing it right."""
    rules = build_rules(REPO_ROOT)
    path = REPO_ROOT / "twin" / "forecast" / "draw.py"
    text = (
        "import numpy as np\n\n\n"
        "def sample(rng: np." + "random.Generator) -> float:\n"
        "    return float(rng.normal())\n"
    )
    assert scan_text(rules, path, text) == []
