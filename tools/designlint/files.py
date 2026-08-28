"""Which files the design rules run over.

Tracked files are the scope, because a rule that only runs over a hand-written
list is a rule that misses the file somebody added at 2 am. Where git is
available the list comes from git; otherwise the tree is walked with the same
exclusions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "node_modules",
        "out",
        "venv",
    }
)

# Extensions the rules can read as text. Anything else is skipped rather than
# guessed at, so that a font file or a screenshot never produces a violation.
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".css",
        ".html",
        ".js",
        ".json",
        ".jsx",
        ".md",
        ".mjs",
        ".py",
        ".sql",
        ".svg",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".yaml",
        ".yml",
    }
)

EXTENSIONLESS_TEXT_NAMES = frozenset({"Makefile", "LICENSE", "Dockerfile"})


def is_text_file(path: Path) -> bool:
    """Report whether a rule can read this file as text."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        return True
    return path.name in EXTENSIONLESS_TEXT_NAMES or path.suffix == ".Dockerfile"


def _from_git(root: Path) -> list[Path] | None:
    try:
        result = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    names = result.stdout.decode("utf-8").split("\0")
    return [root / name for name in names if name]


def _from_walk(root: Path) -> list[Path]:
    found: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if EXCLUDED_DIRECTORIES.intersection(path.relative_to(root).parts):
            continue
        found.append(path)
    return found


def tracked_files(root: Path) -> list[Path]:
    """List every text file in the repository that the rules should read."""
    candidates = _from_git(root)
    if candidates is None:
        candidates = _from_walk(root)
    return sorted(
        path
        for path in candidates
        if path.is_file()
        and is_text_file(path)
        and not EXCLUDED_DIRECTORIES.intersection(path.relative_to(root).parts)
    )
