"""Write the narration script against the cut the build actually produces. T-142.

The video carries no narration of its own. This writes the script a person
reads over it, and it derives every timecode from `captions.json` and the build
constants rather than from a stopwatch, so the script and the video cannot
drift apart. Re-pace the recorder and re-run this, and the timings follow.

It also checks each line against the slot it has to fit in. A narrator who runs
long on beat three is still talking when beat four is on screen, and the rest of
the read is out of step from there. A line that does not fit is reported as an
overrun rather than left for the recording session to discover.

Speaking rate is 2.5 words a second. That is slower than conversation on
purpose: this is a technical walkthrough with station identifiers and decimal
figures in it, and the numbers are the part a listener needs time to take in.

Run it after the recorder, from the repository root:

    python -m tools.demo.voiceover_script

Writes docs/submission/VOICEOVER_SCRIPT.md.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.demo.build_video import (
    CARD_SECONDS,
    CLOSING_SECONDS,
    TRANSITION_SECONDS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "submission" / "demo"
OUTPUT = REPO_ROOT / "docs" / "submission" / "VOICEOVER_SCRIPT.md"

# Words a second, narrating. See the module docstring for why it is this low.
RATE = 2.5

# The narration, keyed on the beat title the recorder logs. Keeping the key the
# recorder's own title means a beat that is renamed loses its line loudly here
# rather than silently reading the wrong one over the wrong screen.
LINES: dict[str, str] = {
    "A normal shift": (
        "This is a read-only digital twin of a forty-two station vehicle "
        "assembly line. Every number is simulated, from a model we "
        "wrote, and the header says so on every frame. Right now the line is "
        "fine, and the system says nothing."
    ),
    "Six of these stations emit nothing": (
        "Six of these forty-two stations have no instrumentation. S33 through "
        "S37, and S42. They are cross-hatched, not blank and not filled in with "
        "a plausible guess. Uneven sensor coverage is the condition of a real "
        "plant, and it is the problem we set out to solve."
    ),
    "A bound, not a number": (
        "Click S34 and the twin reports a range, not a number. It knows five "
        "dark stations share the time between S32 and S38. It cannot tell you "
        "how they split it, and it says exactly that, in plain language, rather "
        "than inventing a figure."
    ),
    "The blind spot becomes a costed recommendation": (
        "Scroll down and the blind spot turns into a decision. A sixty-five "
        "dollar photo-eye at S33 would resolve it, with the install effort and "
        "the next maintenance window. The cost is our assumption, not a "
        "quotation, and the card says so. The gap becomes a line item."
    ),
    "A fixture wearing at S20": (
        "This is the failure the product was built around. A fixture wearing at "
        "S20. Cycle time drifts from fifty-eight seconds to sixty-three over "
        "ninety minutes, stays inside specification, and trips no "
        "threshold alarm. Two detectors, EWMA and CUSUM, both have to fire "
        "before the twin says anything."
    ),
    "What would help, compared against doing nothing": (
        "Press T and the sandbox opens over the line, because the line does not "
        "stop for a dialog. Every option is compared against doing nothing, on "
        "the same replications from the same state, so the comparison is fair. "
        "The footer states the replication count and the state timestamp."
    ),
    "Defect risk, before the gate that would catch it": (
        "For each unit the twin estimates the chance it fails inspection, with a "
        "calibrated probability and a conformal interval rather than a bare "
        "score. The top three factors are given in plant language. The warning "
        "arrives thirteen stations before the gate that would have caught it."
    ),
    "The stall forecaster has not cleared its gate": (
        "This is the most important part. Our stall forecaster does not work "
        "well enough. Precision is zero point two five against a target of zero "
        "point six, and median lead time is five minutes against fifteen. We "
        "show it on screen rather than quietly leaving it out."
    ),
    "Plan view": (
        "Plan view is the plant manager's screen. Where the constraint moved "
        "hour by hour, the loss Pareto under its reconciliation line, and the "
        "sensor investment queue, which exports as a CSV you can attach to a "
        "capital request."
    ),
    "Every predictor on this line is in shadow": (
        "The scorecard. Every predictor on this line is in shadow. Each is "
        "running and being scored, and not one of them reaches "
        "the floor. A model only becomes visible after it clears a precision and "
        "recall gate, station by station, and it demotes itself when it degrades."
    ),
    "Program view": (
        "Program view is the capital holder's screen. Site readiness scored from "
        "what each site actually emits, and a business case where every "
        "assumption carries its source and its uncertainty. It computes to zero "
        "here, because this line supplies no contribution margin."
    ),
    "The evidence": (
        "Every number in this video came from the running twin over HTTP while "
        "the recording was made. Nothing was staged."
    ),
}

CLOSING_LINE = (
    "Five gates passed and two missed. Nothing was tuned to make a gate pass. "
    "The code is on GitHub, and the evidence pack regenerates with one command."
)


@dataclass(frozen=True)
class Slot:
    """One passage of narration and the room it has to fit in."""

    title: str
    starts_at: float
    seconds: float
    line: str

    @property
    def words(self) -> int:
        """How many words the line is."""
        return len(self.line.split())

    @property
    def capacity(self) -> int:
        """How many words the slot holds at the narration rate."""
        return int(self.seconds * RATE)

    @property
    def overruns(self) -> bool:
        """Whether the line is longer than the slot it plays over."""
        return self.words > self.capacity


def timecode(seconds: float) -> str:
    """Seconds as m:ss, which is how a person scrubbing a video reads it."""
    minutes, remainder = divmod(round(seconds), 60)
    return f"{minutes}:{remainder:02d}"


def slots(payload: dict[str, Any]) -> list[Slot]:
    """Every passage in order, with the clock position the build gives it.

    A narrator speaks across the caption card and on into the passage behind
    it, so the slot is the card plus the segment rather than the segment alone.
    The card is a section marker, not a rest.
    """
    beats = payload["beats"]
    total_ms = int(payload["total_ms"])
    found: list[Slot] = []
    clock = 0.0
    for index, current in enumerate(beats):
        following = beats[index + 1]["at_ms"] if index + 1 < len(beats) else total_ms
        segment = max(0.5, (following - current["at_ms"]) / 1000.0)
        held = current.get("hold_ms")
        if held is not None:
            segment = min(segment, held / 1000.0 + TRANSITION_SECONDS)
        title = current["title"]
        found.append(
            Slot(
                title=title,
                starts_at=clock,
                seconds=CARD_SECONDS + segment,
                line=LINES.get(title, ""),
            )
        )
        clock += CARD_SECONDS + segment
    found.append(
        Slot(
            title="Closing card",
            starts_at=clock,
            seconds=CLOSING_SECONDS,
            line=CLOSING_LINE,
        )
    )
    return found


def _heading(runtime: float) -> list[str]:
    """The document's own front matter."""
    return [
        "# VOICEOVER_SCRIPT.md",
        "",
        "**Purpose:** the narration read over `DigitalTwin_demo.mp4`.",
        "**Generated** by `tools/demo/voiceover_script.py` from "
        "`submission/demo/captions.json`. Do not edit by hand: edit the script "
        "in the tool and regenerate, or the timings stop describing the video.",
        f"**Runtime:** {timecode(runtime)}",
        "",
        "---",
        "",
        "## 1. How to read it",
        "",
        "Start speaking as the caption card appears and carry on into the "
        "passage behind it. The card is a section marker rather than a rest, "
        "and a beat's whole slot is the card plus the footage after it.",
        "",
        f"Word counts assume {RATE} words a second, which is a deliberate, "
        "unhurried read. The station identifiers and the decimal figures are "
        "the part a listener needs time to take in.",
        "",
    ]


def _warnings(found: list[Slot]) -> list[str]:
    """What the narrator has to know before reading a word of it."""
    out: list[str] = []
    overruns = [slot for slot in found if slot.overruns]
    if overruns:
        out.append(
            "**These lines do not fit their slot.** Cut them, or lengthen the "
            "hold in `record_demo.mjs` and record again."
        )
        out.append("")
        out += [
            f"- {slot.title}: {slot.words} words in room for {slot.capacity}"
            for slot in overruns
        ]
        out.append("")
    else:
        out.append("Every line fits its slot with room to breathe.")
        out.append("")

    missing = [slot for slot in found if not slot.line]
    if missing:
        out.append(
            "**These beats have no line.** The recorder logs a title this tool "
            "has no narration for, which usually means a beat was renamed."
        )
        out.append("")
        out += [f"- {slot.title}" for slot in missing]
        out.append("")

    # The reverse case, and the one that actually happens. Several beats are
    # conditional on what the line is doing: the defect drawer needs a unit
    # above the risk threshold, and on a quiet replay there is not one. The
    # beat is absent from the recording because the line was calm, which is the
    # twin being right, so this is reported as a fact about the cut rather than
    # as a fault.
    recorded = {slot.title for slot in found}
    unused = [title for title in LINES if title not in recorded]
    if unused:
        out.append(
            "**Written but not in this cut.** The recorder skips a beat whose "
            "screen the line did not produce. Re-record when it does, or leave "
            "the beat out and say nothing about it."
        )
        out.append("")
        out += [f"- {title}" for title in unused]
        out.append("")
    return out


def _script(found: list[Slot]) -> list[str]:
    """The table of cues, then each passage in full."""
    out = ["---", "", "## 2. The script", ""]
    out.append("| In at | Beat | Words | Room for |")
    out.append("|---|---|---|---|")
    out += [
        f"| {timecode(slot.starts_at)} | {slot.title} | "
        f"{slot.words} | {slot.capacity} |"
        for slot in found
    ]
    out.append("")
    for slot in found:
        out.append(f"### {timecode(slot.starts_at)}  {slot.title}")
        out.append("")
        out.append(f"> {slot.line}" if slot.line else "> No line written.")
        out.append("")
        out.append(
            f"*{slot.seconds:.1f} s of video. {slot.words} words, "
            f"room for {slot.capacity}.*"
        )
        out.append("")
    return out


def _rules() -> list[str]:
    """The four ways a read of this script can undo the product."""
    return [
        "---",
        "",
        "## 3. What the narration must not do",
        "",
        "- **Do not call a bound a measurement.** S34 has a range. Saying it "
        "takes a hundred and thirty seconds undoes the thing the beat exists "
        "to show.",
        "- **Do not soften the stall forecaster.** It misses its gate. The "
        "line says so in the same tone as the rest, without apology and "
        "without a recovery clause after it.",
        "- **Do not say the data is real.** The first beat states it is "
        "simulated, inside the first thirty seconds, which is what "
        "DEFINITION_OF_DONE.md Section 3 asks for.",
        "- **Do not read the caption cards aloud.** They are already on screen "
        "and the narration says something different from them on purpose.",
        "",
    ]


def render(found: list[Slot]) -> str:
    """The script, as a document a person reads from."""
    runtime = sum(slot.seconds for slot in found)
    parts = _heading(runtime) + _warnings(found) + _script(found) + _rules()
    return "\n".join(parts)


def main() -> int:
    """Write the script, or say what is missing."""
    captions = DEFAULT_DIR / "captions.json"
    if not captions.exists():
        print(f"no captions at {captions}. Run tools/demo/record_demo.mjs first.")
        return 1
    payload = json.loads(captions.read_text(encoding="utf-8"))
    found = slots(payload)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(found), encoding="utf-8")
    runtime = sum(slot.seconds for slot in found)
    overruns = sum(1 for slot in found if slot.overruns)
    print(f"wrote {OUTPUT}")
    print(f"{timecode(runtime)} runtime, {len(found)} passages, {overruns} overrunning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
