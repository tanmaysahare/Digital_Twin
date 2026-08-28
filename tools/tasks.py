"""The task runner behind the Makefile.

Every command in the Makefile delegates here so that Windows, macOS and Linux
run byte-identical steps. `make` is not present on a stock Windows machine and
the team develops on all three platforms (T-136), so a Makefile that carried the
command lines itself would need a second, drifting copy in a batch file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


@dataclass(frozen=True)
class Step:
    """One command in a task, run from `cwd` relative to the repository root."""

    argv: list[str]
    cwd: Path = ROOT
    skip_if_missing: str | None = None


@dataclass(frozen=True)
class Pending:
    """A command named in CLAUDE.md whose implementation is not written yet."""

    task_id: str
    what: str


@dataclass(frozen=True)
class Task:
    """A named command, its summary, and the steps it runs."""

    summary: str
    steps: list[Step | Pending]


def _python(*args: str) -> Step:
    return Step([sys.executable, *args])


def _npm(*args: str) -> Step:
    return Step(["npm", *args], cwd=WEB, skip_if_missing="npm")


TASKS: dict[str, Task] = {
    "install": Task(
        "Install Python and Node development dependencies",
        [
            _python("-m", "pip", "install", "--upgrade", "pip"),
            _python("-m", "pip", "install", "-e", ".[dev]"),
            _npm("install"),
        ],
    ),
    "lint": Task(
        "Design rules, ruff, mypy strict, eslint, stylelint",
        [
            _python("-m", "tools.designlint"),
            _python("-m", "ruff", "check", "."),
            _python("-m", "ruff", "format", "--check", "."),
            _python("-m", "mypy"),
            _npm("run", "lint"),
            _npm("run", "lint:css"),
        ],
    ),
    "lint-design": Task(
        "The design rule checks only (TEST_PLAN.md Section 7)",
        [_python("-m", "tools.designlint")],
    ),
    "format": Task(
        "Rewrite Python and web sources in the project style",
        [
            _python("-m", "ruff", "format", "."),
            _python("-m", "ruff", "check", "--fix", "."),
            _npm("run", "format"),
        ],
    ),
    "test": Task(
        "Full test suite: pytest and the web unit tests",
        [
            _python("-m", "pytest"),
            _npm("run", "test"),
        ],
    ),
    "test-python": Task("pytest only", [_python("-m", "pytest")]),
    "up": Task(
        "Start the seeded demo stack",
        [Step(["docker", "compose", "up", "-d"], skip_if_missing="docker")],
    ),
    "down": Task(
        "Stop the stack and remove its containers",
        [Step(["docker", "compose", "down"], skip_if_missing="docker")],
    ),
    "db": Task(
        "Start the database alone, for the non-Docker development path",
        [Step(["docker", "compose", "up", "-d", "db"], skip_if_missing="docker")],
    ),
    "migrate": Task(
        "Apply database migrations to the configured database",
        [_python("-m", "alembic", "upgrade", "head")],
    ),
    "seed": Task(
        "Rebuild the seeded demo database",
        [Pending("T-024", "the simulator and its ground truth channel")],
    ),
    "evaluate": Task(
        "Regenerate the evidence pack at evaluation/report.md",
        [Pending("T-069", "the evaluation harness")],
    ),
    "reference-sheets": Task(
        "Regenerate docs/design/REFERENCE_IMAGES/*.svg from the design tokens",
        [_python("docs/design/REFERENCE_IMAGES/_gen_sheets.py")],
    ),
}


def print_help() -> None:
    """Print every task and what it does."""
    print("DigitalTwin.ai. Run one of:\n")
    width = max(len(name) for name in TASKS)
    for name, task in TASKS.items():
        print(f"  make {name.ljust(width)}  {task.summary}")
    print("")
    print(r"On Windows without make installed, use: .\make.cmd <task>")


def run(name: str) -> int:
    """Run one task by name. Returns the exit code of the first failing step."""
    task = TASKS.get(name)
    if task is None:
        print(f"No task named {name}. Run without arguments to see the list.")
        return 2

    for step in task.steps:
        if isinstance(step, Pending):
            print(
                f"'{name}' is not built yet. {step.task_id} builds {step.what}. "
                f"See docs/ai/TASKS.md."
            )
            return 1
        if step.skip_if_missing and shutil.which(step.skip_if_missing) is None:
            missing = step.skip_if_missing
            print(f"Skipping '{' '.join(step.argv)}': {missing} not found.")
            continue
        print(f"$ {' '.join(step.argv)}")
        # Windows needs the resolved path: npm is npm.cmd, and CreateProcess
        # does not consult PATHEXT the way a shell does.
        resolved = shutil.which(step.argv[0]) or step.argv[0]
        result = subprocess.run([resolved, *step.argv[1:]], cwd=step.cwd, check=False)
        if result.returncode != 0:
            return result.returncode
    return 0


def main(argv: list[str]) -> int:
    """Dispatch to one task, or print the list."""
    if not argv or argv[0] in {"help", "-h", "--help"}:
        print_help()
        return 0
    return run(argv[0])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
