"""Assemble the demo video from the recording and its captions. T-142.

`record_demo.mjs` produces a screen recording of the running application and a
`captions.json` saying when each beat began. This turns the pair into one MP4:
a caption card, then the passage of the recording that the caption describes,
then the next card.

**Why cards rather than narration.** DEFINITION_OF_DONE.md Section 3 asks for
the simulated-data statement out loud in the first thirty seconds. There is no
narrator, and no synthetic voice we were willing to put a plant's name next to,
so the statement is on the first card and on every frame of the recording
through the application's own header marker. That is a deviation from the
checklist and it is recorded as one rather than ticked.

**Why the cards look like this.** The same rules as the product:
DESIGN_SYSTEM.md light palette, flat fills, no gradient, no radius beyond 2px,
no decorative motion, and colour only where something is abnormal. A demo video
that looked like a different product than the one it is showing would be its
own kind of dishonesty.

Run it after the recorder, from the repository root:

    python tools/demo/build_video.py

ffmpeg comes from PATH if it is there and from the `imageio-ffmpeg` wheel
otherwise, so the build needs no system package.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = REPO_ROOT / "submission" / "demo"

# DESIGN_SYSTEM.md Section 11, the same values tokens.css carries.
PAPER = (250, 249, 247)
INK = (26, 26, 26)
INK_2 = (74, 74, 72)
INK_3 = (111, 110, 106)
RULE = (217, 214, 208)
ACCENT = (27, 58, 92)
STATE_DOWN = (163, 32, 32)

CARD_SECONDS = 4.0
# How much of the action after a passage to keep: a drawer opening or the
# sandbox appearing reads as part of the beat. Longer than this is a route
# loading, which is not.
TRANSITION_SECONDS = 3.0
CLOSING_SECONDS = 11.0
FPS = 25

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


def find_ffmpeg() -> str:
    """The ffmpeg binary, preferring a system one over the bundled wheel."""
    return shutil.which("ffmpeg") or str(imageio_ffmpeg.get_ffmpeg_exe())


def load_font(size: int, *, bold: bool = False) -> Font:
    """A system font at a size, falling back to whatever PIL can give us."""
    candidates = (
        ["seguisb.ttf", "segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
        if bold
        else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]
    )
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def wrap(draw: ImageDraw.ImageDraw, text: str, font: Font, limit: int) -> list[str]:
    """Greedy wrap to a pixel width, because a caption is prose."""
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= limit or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _number(value: object, digits: int = 3, default: str = "not measured") -> str:
    """A metric as text, saying so plainly where there is no metric.

    A metric that is absent, or a NaN standing in for one the harness could not
    compute, reads as the default rather than as `nan` on a closing frame.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return default
    number = float(value)
    if math.isnan(number):
        return default
    return f"{number:.{digits}f}"


@dataclass(frozen=True)
class Beat:
    """One caption and the passage of recording it introduces."""

    at_ms: int
    title: str
    body: str
    hold_ms: int | None = None


def card(path: Path, width: int, height: int, title: str, body: str) -> None:
    """One caption card, in the product's own visual language."""
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)

    margin = int(width * 0.10)
    limit = width - 2 * margin

    title_font = load_font(int(height * 0.058), bold=True)
    body_font = load_font(int(height * 0.033))
    mark_font = load_font(int(height * 0.020))

    # A single hairline above the title. The product separates things with
    # rules rather than boxes, and so does this.
    y = int(height * 0.34)
    draw.line([(margin, y), (margin + int(limit * 0.10), y)], fill=ACCENT, width=3)

    y += int(height * 0.045)
    for line in wrap(draw, title, title_font, limit):
        draw.text((margin, y), line, font=title_font, fill=INK)
        y += int(height * 0.072)

    y += int(height * 0.020)
    for line in wrap(draw, body, body_font, limit):
        draw.text((margin, y), line, font=body_font, fill=INK_2)
        y += int(height * 0.048)

    # The simulated-data marker, on every card, in the words the application's
    # own header uses.
    baseline = height - int(height * 0.10)
    draw.line([(margin, baseline), (width - margin, baseline)], fill=RULE, width=1)
    draw.text(
        (margin, height - int(height * 0.078)),
        "Simulated data. DigitalTwin.ai, Team Aeronomics.",
        font=mark_font,
        fill=INK_3,
    )
    image.save(path)


def closing_card(path: Path, width: int, height: int, metrics: dict[str, Any]) -> None:
    """The evidence card. Passed and missed gates on the same frame."""
    image = Image.new("RGB", (width, height), PAPER)
    draw = ImageDraw.Draw(image)
    margin = int(width * 0.08)

    title_font = load_font(int(height * 0.046), bold=True)
    row_font = load_font(int(height * 0.029))
    small_font = load_font(int(height * 0.020))

    y = int(height * 0.10)
    draw.line([(margin, y), (margin + int(width * 0.06), y)], fill=ACCENT, width=3)
    y += int(height * 0.038)
    draw.text(
        (margin, y), "Measured, in evaluation/metrics.json", font=title_font, fill=INK
    )
    y += int(height * 0.085)

    virtual = metrics.get("virtual_sensor", {})
    stall = metrics.get("stall_forecaster", {})
    defects = {d.get("gate_id"): d for d in metrics.get("defect_models", [])}
    g1 = defects.get("G1", {})

    rows: list[tuple[str, str, bool]] = [
        (
            "Dark-station interval coverage, per station",
            _number(virtual.get("station_coverage")),
            True,
        ),
        ("Dark-span interval coverage", _number(virtual.get("span_coverage")), True),
        (
            "False stall alerts per quiet shift",
            _number(metrics.get("false_alerts_per_shift"), 2),
            True,
        ),
        (
            "Defect calibration error, G1",
            _number(g1.get("expected_calibration_error")),
            True,
        ),
        (
            "Conformal coverage at alpha 0.10, G1",
            _number(g1.get("conformal_coverage")),
            True,
        ),
        (
            "Stall forecast precision, target 0.60",
            _number(stall.get("precision")),
            False,
        ),
        (
            "Stall forecast median lead, target 15 min",
            f"{_number(stall.get('median_lead_min'), 0)} min",
            False,
        ),
    ]

    step = int(height * 0.062)
    for label, value, passed in rows:
        colour = INK_2 if passed else STATE_DOWN
        draw.text((margin, y), label, font=row_font, fill=colour)
        draw.text(
            (width - margin - draw.textlength(value, font=row_font), y),
            value,
            font=row_font,
            fill=colour,
        )
        y += int(step * 0.62)
        draw.line([(margin, y), (width - margin, y)], fill=RULE, width=1)
        y += int(step * 0.38)

    y += int(height * 0.020)
    closing = (
        "The stall forecaster misses its gate, so the ledger keeps it in shadow "
        "and the floor sees nothing from it. Nothing was tuned to make a gate pass."
    )
    for line in wrap(draw, closing, row_font, width - 2 * margin):
        draw.text((margin, y), line, font=row_font, fill=INK)
        y += int(height * 0.042)

    draw.text(
        (margin, height - int(height * 0.062)),
        "Simulated data. github.com/tanmaysahare/Digital_Twin",
        font=small_font,
        fill=INK_3,
    )
    image.save(path)


def run(ffmpeg: str, args: list[str]) -> None:
    """One ffmpeg invocation, quiet unless it fails."""
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        message = f"ffmpeg failed:\n{result.stderr[-3000:]}"
        raise SystemExit(message)


def encode_common(width: int, height: int) -> list[str]:
    """One encoder setting for every piece, so the concat is safe."""
    return [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-vf",
        f"scale={width}:{height},setsar=1",
        "-an",
    ]


def main() -> int:
    """Build the video, or say precisely what is missing."""
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_DIR
    captions_path = out_dir / "captions.json"
    if not captions_path.exists():
        print(f"no captions at {captions_path}. Run tools/demo/record_demo.mjs first.")
        return 1

    payload = json.loads(captions_path.read_text(encoding="utf-8"))
    width = int(payload["width"])
    height = int(payload["height"])
    beats = [
        Beat(
            at_ms=b["at_ms"],
            title=b["title"],
            body=b["body"],
            hold_ms=b.get("hold_ms"),
        )
        for b in payload["beats"]
    ]
    recording = Path(payload["video"]) if payload.get("video") else None
    if recording is None or not recording.exists():
        print("the recording named in captions.json is not there.")
        return 1

    metrics = json.loads(
        (REPO_ROOT / "evaluation" / "metrics.json").read_text(encoding="utf-8")
    )

    ffmpeg = find_ffmpeg()
    work = out_dir / "_build"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    pieces: list[Path] = []
    total_ms = int(payload["total_ms"])

    for index, current in enumerate(beats):
        card_png = work / f"card{index:02d}.png"
        card(card_png, width, height, current.title, current.body)
        card_mp4 = work / f"card{index:02d}.mp4"
        run(
            ffmpeg,
            [
                "-loop",
                "1",
                "-t",
                str(CARD_SECONDS),
                "-i",
                str(card_png),
                *encode_common(width, height),
                str(card_mp4),
            ],
        )
        pieces.append(card_mp4)

        start = current.at_ms / 1000.0
        following = beats[index + 1].at_ms if index + 1 < len(beats) else total_ms
        duration = max(0.5, following / 1000.0 - start)
        # Cut to the passage the narrator speaks over, plus enough of what
        # follows to keep a drawer opening or a sandbox appearing. What this
        # drops is the wait for a slow route, which is dead air in a narrated
        # video and was never part of any sentence.
        if current.hold_ms is not None:
            duration = min(duration, current.hold_ms / 1000.0 + TRANSITION_SECONDS)
        segment = work / f"seg{index:02d}.mp4"
        run(
            ffmpeg,
            [
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(recording),
                *encode_common(width, height),
                str(segment),
            ],
        )
        pieces.append(segment)

    closing_png = work / "closing.png"
    closing_card(closing_png, width, height, metrics)
    closing_mp4 = work / "closing.mp4"
    run(
        ffmpeg,
        [
            "-loop",
            "1",
            "-t",
            str(CLOSING_SECONDS),
            "-i",
            str(closing_png),
            *encode_common(width, height),
            str(closing_mp4),
        ],
    )
    pieces.append(closing_mp4)

    listing = work / "pieces.txt"
    listing.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in pieces), encoding="utf-8"
    )
    final = out_dir / "DigitalTwin_demo.mp4"
    run(
        ffmpeg,
        ["-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(final)],
    )

    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(final)],
        capture_output=True,
        text=True,
        check=False,
    )
    duration_line = next(
        (line.strip() for line in probe.stderr.splitlines() if "Duration:" in line), ""
    )
    shutil.rmtree(work)
    print(f"wrote {final}")
    print(
        f"{duration_line}  {final.stat().st_size / (1024 * 1024):.1f} MB  "
        f"{len(beats)} beats"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
