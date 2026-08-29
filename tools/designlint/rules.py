"""The design rules from docs/quality/TEST_PLAN.md Section 7.

These implement AC-100. The stylelint and eslint configurations under `web/`
carry the rules that are natural to express in those tools; everything here is
either repository-wide or needs a check those tools cannot make.

The correct response to a failure is to fix the cause. A suppression comment on
any of these rules fails review, which is why none of them supports one.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

EM_DASH = chr(0x2014)

# Ranges that carry pictographic characters. Text punctuation and the arrows
# used in the diagrams under docs/ are deliberately outside these.
EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x1F000, 0x1FAFF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE0F, 0xFE0F),
    (0x20E3, 0x20E3),
)

WEB_SOURCE_SUFFIXES = frozenset({".css", ".ts", ".tsx", ".js", ".jsx", ".html", ".svg"})

TOKENS_FILE = "web/src/styles/tokens.css"


@dataclass(frozen=True)
class Violation:
    """One rule failure, located precisely enough to fix without searching."""

    rule: str
    path: Path
    line: int
    excerpt: str
    message: str


@dataclass(frozen=True)
class Rule:
    """A named check over the text of one file."""

    name: str
    summary: str
    applies: Callable[[Path], bool]
    check: Callable[[Path, str], Iterator[Violation]]


def _line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _line_text(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    end = len(text) if end == -1 else end
    return text[start:end].strip()[:120]


def _mask(text: str, pattern: re.Pattern[str]) -> str:
    """Blank out every match, keeping the length so line numbers stay correct."""

    def blank(match: re.Match[str]) -> str:
        return "".join(
            " " if character != "\n" else "\n" for character in match.group(0)
        )

    return pattern.sub(blank, text)


_FENCED_CODE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_INDENTED_CODE = re.compile(r"^(?: {4}|\t).*$", re.MULTILINE)
_DOUBLE_QUOTED = re.compile(r"\"[^\"\n]{0,200}\"")
_MARKDOWN_LINK = re.compile(r"\]\([^)\n]*\)")


def mask_code(text: str) -> str:
    """Blank out fenced blocks, indented blocks and inline code spans."""
    masked = _mask(text, _FENCED_CODE)
    masked = _mask(masked, _INDENTED_CODE)
    return _mask(masked, _INLINE_CODE)


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"(?<!:)//[^\n]*")


def mask_comments(text: str) -> str:
    """Blank out block and line comments in CSS and TypeScript source.

    A comment saying the product has no dark theme is not a dark theme. The
    lookbehind keeps the scheme separator of a URL out of this, because the
    external host rule still has to see it.
    """
    return _mask(_mask(text, _BLOCK_COMMENT), _LINE_COMMENT)


def mask_quoted(text: str) -> str:
    """Blank out double-quoted spans.

    Quoted material is either an example of what not to write or the title of a
    cited work. The linter does not judge either, because both have to be
    reproduced exactly to serve their purpose.
    """
    return _mask(text, _DOUBLE_QUOTED)


def check_em_dash(path: Path, text: str) -> Iterator[Violation]:
    """Fail on U+2014 anywhere. Use a comma, a colon, or two sentences."""
    for match in re.finditer(re.escape(EM_DASH), text):
        yield Violation(
            "no-em-dash",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            "Em dash. Use a comma, a colon, parentheses, or a second sentence.",
        )


def check_emoji(path: Path, text: str) -> Iterator[Violation]:
    """Fail on any pictographic character."""
    for index, character in enumerate(text):
        code = ord(character)
        if any(low <= code <= high for low, high in EMOJI_RANGES):
            yield Violation(
                "no-emoji",
                path,
                _line_number(text, index),
                _line_text(text, index),
                f"Emoji U+{code:04X}. Say it in words.",
            )


def _load_list(path: Path) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.strip() for line in lines if line.strip() and not line.startswith("#")]


def load_banned_words(lint_dir: Path) -> list[str]:
    """Read the whole-word ban list."""
    return _load_list(lint_dir / "banned-words.txt")


def load_banned_phrases(lint_dir: Path) -> list[str]:
    """Read the context-scoped ban list, each entry a regular expression."""
    return _load_list(lint_dir / "banned-phrases.txt")


def load_exempt_files(lint_dir: Path) -> dict[str, str]:
    """Read the file exemptions and their stated reasons."""
    exempt: dict[str, str] = {}
    for line in _load_list(lint_dir / "banned-words-exempt.txt"):
        name, _, reason = line.partition(" ")
        exempt[name.strip()] = reason.strip()
    return exempt


def banned_word_rule(lint_dir: Path, root: Path) -> Rule:
    """Build the banned vocabulary rule from the lists in `.lint/`."""
    words = load_banned_words(lint_dir)
    phrases = load_banned_phrases(lint_dir)
    exempt = load_exempt_files(lint_dir)

    word_pattern = (
        re.compile(
            r"(?<![\w-])("
            + "|".join(re.escape(word) for word in words)
            + r")(?![\w-])",
            re.IGNORECASE,
        )
        if words
        else None
    )
    phrase_patterns = [re.compile(phrase, re.IGNORECASE) for phrase in phrases]

    def applies(path: Path) -> bool:
        relative = _relative(path, root)
        if relative.startswith(".lint/") or relative in exempt:
            return False
        return path.suffix in {".md", ".ts", ".tsx", ".py"}

    def check(path: Path, text: str) -> Iterator[Violation]:
        searchable = mask_quoted(mask_code(text))
        if word_pattern is not None:
            for match in word_pattern.finditer(searchable):
                yield Violation(
                    "no-banned-words",
                    path,
                    _line_number(text, match.start()),
                    _line_text(text, match.start()),
                    f"Marketing vocabulary: {match.group(0)}. State what it does and "
                    f"how often it has been right.",
                )
        for pattern in phrase_patterns:
            for match in pattern.finditer(searchable):
                yield Violation(
                    "no-banned-words",
                    path,
                    _line_number(text, match.start()),
                    _line_text(text, match.start()),
                    f"Marketing sense of: {match.group(0).strip()}.",
                )

    return Rule(
        "no-banned-words",
        "Marketing vocabulary from HUMAN_DESIGN_GUIDELINES.md rule 21",
        applies,
        check,
    )


_JSX_TEXT = re.compile(r">([^<>{}\n]{2,})<")
_JS_STRING = re.compile(r"'([^'\n]{0,200})'|\"([^\"\n]{0,200})\"")


def check_exclamation(path: Path, text: str) -> Iterator[Violation]:
    """Fail on an exclamation mark in any string a reader will see."""
    spans: list[tuple[int, str]] = []
    if path.suffix == ".md":
        searchable = mask_quoted(_mask(mask_code(text), _MARKDOWN_LINK))
        searchable = searchable.replace("![", "  ")
        spans = [
            (match.start(), _line_text(text, match.start()))
            for match in re.finditer(r"!", searchable)
        ]
    else:
        for match in _JS_STRING.finditer(text):
            body = next(group for group in match.groups() if group is not None)
            if "!" in body:
                spans.append((match.start(), match.group(0)))
        for match in _JSX_TEXT.finditer(text):
            if "!" in match.group(1):
                spans.append((match.start(), match.group(1)))
    for index, excerpt in spans:
        yield Violation(
            "no-exclamation-mark",
            path,
            _line_number(text, index),
            excerpt.strip()[:120],
            "Exclamation mark. State the fact instead.",
        )


_PLACEHOLDERS = re.compile(
    r"\b(lorem\s+ipsum|lorem|John\s+Doe|Jane\s+Doe|Item\s+\d+|Foo\s+Bar|foobar"
    r"|placeholder\s+text|your\s+company\s+here)\b|\bexample\.com\b",
    re.IGNORECASE,
)


def check_placeholder(path: Path, text: str) -> Iterator[Violation]:
    """Fail on synthetic placeholder content. Use a plausible plant value."""
    for match in _PLACEHOLDERS.finditer(text):
        yield Violation(
            "no-placeholder-content",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            f"Placeholder content: {match.group(0)}. Use a plausible plant value, "
            f"for example station S20 or VIN 3C4PDCBG7JT.",
        )


_GRADIENT = re.compile(
    r"\b(linear|radial|conic|repeating-linear|repeating-radial|repeating-conic)"
    r"-gradient\b|\bbg-gradient-to-",
)
_BLUR = re.compile(
    r"backdrop-filter|backdrop-blur|filter:\s*blur\(|\bblur-(sm|md|lg|xl)\b",
)
# The lookahead sits immediately after the colon and consumes the whitespace
# itself. With a separate \s* before it the engine backtracks to zero spaces and
# the lookahead then compares against a leading space, which lets an allowed
# value through.
_LARGE_RADIUS = re.compile(
    r"border-radius:(?!\s*(?:0|2px|var\(--radius))[^;]*"
    r"|\brounded-(sm|md|lg|xl|2xl|3xl|full)\b"
    r"|\brounded-\[(?!0\]|2px\])[^\]]+\]",
)
_DARK_THEME = re.compile(r"prefers-color-scheme|(?<![\w-])dark:")
_RAW_COLOUR = re.compile(
    r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{1,5})?\b|\b(rgb|rgba|hsl|hsla)\s*\(",
)


def _relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _finder(
    name: str, pattern: re.Pattern[str], message: str
) -> Callable[[Path, str], Iterator[Violation]]:
    def check(path: Path, text: str) -> Iterator[Violation]:
        for match in pattern.finditer(mask_comments(text)):
            yield Violation(
                name,
                path,
                _line_number(text, match.start()),
                _line_text(text, match.start()),
                message,
            )

    return check


def check_raw_colour(path: Path, text: str) -> Iterator[Violation]:
    """Fail on a colour literal outside the token file."""
    for match in _RAW_COLOUR.finditer(mask_comments(text)):
        yield Violation(
            "no-raw-colour",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            f"Raw colour {match.group(0)}. Reference a token from tokens.css.",
        )


# The NumPy branch requires a call. `np.random.Generator` as a type
# annotation is how a function says it takes a seeded generator, and is not
# itself a draw. The legacy call surface still matches.
_UNSEEDED_RANDOM = re.compile(
    r"^\s*(?:import\s+random\b|from\s+random\s+import\b)"
    r"|(?<![\w.])random\.(?:random|randint|randrange|choice|choices|shuffle|sample"
    r"|uniform|gauss|normalvariate|expovariate|seed)\s*\("
    r"|(?<![\w.])(?:np|numpy)\.random\.(?!default_rng\s*\()[a-zA-Z_]+\s*\("
    r"|default_rng\s*\(\s*\)",
    re.MULTILINE,
)


def check_unseeded_random(path: Path, text: str) -> Iterator[Violation]:
    """Fail on a draw that does not come from a seeded generator."""
    for match in _UNSEEDED_RANDOM.finditer(text):
        yield Violation(
            "no-unseeded-random",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            "Unseeded random draw. Every draw comes from a generator seeded on "
            "(cycle_id, replication). See CODING_STANDARDS.md Section 1.4.",
        )


_EXTERNAL_URL = re.compile(r"https?://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)[\w.-]+")


def check_external_host(path: Path, text: str) -> Iterator[Violation]:
    """Fail on a reference to a host outside the deployment."""
    for match in _EXTERNAL_URL.finditer(text):
        yield Violation(
            "no-external-host",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            f"External host {match.group(0)}. The application runs with no network "
            f"connection (NFR-06). Fonts and assets are self-hosted.",
        )


_BARE_TODO = re.compile(r"\bTODO\b(?!\(T-\d{3}\))")
_COMMENT_MARKER = re.compile(r"#|//|/\*")


def _in_comment(text: str, index: int) -> bool:
    line_start = text.rfind("\n", 0, index) + 1
    return _COMMENT_MARKER.search(text, line_start, index) is not None


def check_todo(path: Path, text: str) -> Iterator[Violation]:
    """Fail on a TODO with no owning task. CODING_STANDARDS.md Section 4."""
    for match in _BARE_TODO.finditer(text):
        if not _in_comment(text, match.start()):
            continue
        yield Violation(
            "no-untracked-todo",
            path,
            _line_number(text, match.start()),
            _line_text(text, match.start()),
            "TODO without a task identifier. Write TODO(T-nnn) or open the task.",
        )


def build_rules(root: Path, lint_dir: Path | None = None) -> list[Rule]:
    """Assemble every design rule.

    Args:
        root: the tree the rules apply to. Path scoping is relative to it.
        lint_dir: where the word lists live. Defaults to `root/.lint`. The
            fixture tests point it at the repository's lists while scoping the
            rules to a temporary tree.
    """
    lint_dir = lint_dir if lint_dir is not None else root / ".lint"

    def anywhere(_path: Path) -> bool:
        return True

    def web_source(path: Path) -> bool:
        relative = _relative(path, root)
        return relative.startswith("web/") and path.suffix in WEB_SOURCE_SUFFIXES

    def web_source_outside_tokens(path: Path) -> bool:
        return web_source(path) and _relative(path, root) != TOKENS_FILE

    def copy_source(path: Path) -> bool:
        return path.suffix in {".md", ".ts", ".tsx"}

    def product_surface(path: Path) -> bool:
        """Where placeholder content would reach a reader.

        The specification documents that define the rule necessarily name the
        placeholders they ban, so the scan covers the product itself: the web
        application, the configuration, the simulator and the twin, plus the
        wireframes, whose mock content is held to the same standard as a
        rendered screen (HUMAN_DESIGN_GUIDELINES.md rule 24).
        """
        relative = _relative(path, root)
        if relative.startswith("docs/design/WIREFRAMES/"):
            return True
        product = ("web/", "config/", "plantsim/", "twin/", "connector/", "evaluation/")
        return relative.startswith(product) and path.suffix in {
            ".ts",
            ".tsx",
            ".css",
            ".py",
            ".yaml",
            ".yml",
            ".md",
        }

    def python_source(path: Path) -> bool:
        return path.suffix == ".py"

    def commented_source(path: Path) -> bool:
        return path.suffix in {".py", ".ts", ".tsx", ".css"}

    return [
        Rule(
            "no-em-dash", "U+2014 anywhere in the repository", anywhere, check_em_dash
        ),
        Rule("no-emoji", "Pictographic characters anywhere", anywhere, check_emoji),
        banned_word_rule(lint_dir, root),
        Rule(
            "no-exclamation-mark",
            "Exclamation marks in copy",
            copy_source,
            check_exclamation,
        ),
        Rule(
            "no-placeholder-content",
            "Synthetic placeholder content",
            product_surface,
            check_placeholder,
        ),
        Rule(
            "no-gradient",
            "Gradients in web source",
            web_source,
            _finder("no-gradient", _GRADIENT, "Gradient. Flat fills only."),
        ),
        Rule(
            "no-blur",
            "Backdrop blur and glass effects in web source",
            web_source,
            _finder(
                "no-blur",
                _BLUR,
                "Blur. Elevation is a 1px border and a background step.",
            ),
        ),
        Rule(
            "no-large-radius",
            "Border radius above 2px in web source",
            web_source,
            _finder(
                "no-large-radius",
                _LARGE_RADIUS,
                "Border radius above 2px. Use var(--radius) or 0.",
            ),
        ),
        Rule(
            "no-dark-theme",
            "Dark theme blocks and variants in web source",
            web_source,
            _finder(
                "no-dark-theme",
                _DARK_THEME,
                "Dark theme. The product ships light only and has no theme toggle.",
            ),
        ),
        Rule(
            "no-raw-colour",
            "Colour literals outside tokens.css",
            web_source_outside_tokens,
            check_raw_colour,
        ),
        Rule(
            "no-unseeded-random",
            "Draws from a global or unseeded generator",
            python_source,
            check_unseeded_random,
        ),
        Rule(
            "no-external-host",
            "References to hosts outside the deployment",
            web_source,
            check_external_host,
        ),
        Rule(
            "no-untracked-todo",
            "TODO comments with no owning task",
            commented_source,
            check_todo,
        ),
    ]
