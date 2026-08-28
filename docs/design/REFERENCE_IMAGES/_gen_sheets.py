"""Generate the reference sheets from the design tokens.

The tokens are read from web/src/styles/tokens.css, which is the single source
of truth for them, so a sheet cannot drift from the implementation. Run with
`make reference-sheets`.
"""

import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
TOKENS_CSS = HERE.parent.parent.parent / "web" / "src" / "styles" / "tokens.css"

_COLOUR_TOKEN = re.compile(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{3,8})\s*;")

TOKENS = {
    name: value.upper()
    for name, value in _COLOUR_TOKEN.findall(TOKENS_CSS.read_text(encoding="utf-8"))
}

SANS = "Inter, 'IBM Plex Sans', system-ui, sans-serif"
MONO = "'IBM Plex Mono', 'JetBrains Mono', ui-monospace, monospace"


def lum(hexcolor):
    c = hexcolor.lstrip("#")
    rgb = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    rgb = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def ratio(a, b):
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def header(w, h, title, sub):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" font-family="{SANS}">'
        f'<rect width="{w}" height="{h}" fill="{TOKENS["paper"]}"/>'
        f'<text x="32" y="40" font-size="20" font-weight="600" '
        f'fill="{TOKENS["ink"]}">{title}</text>'
        f'<text x="32" y="60" font-size="12" fill="{TOKENS["ink-3"]}">{sub}</text>'
        f'<line x1="32" y1="76" x2="{w - 32}" y2="76" stroke="{TOKENS["rule-strong"]}" '
        f'stroke-width="1"/>'
    )


# ---------------------------------------------------------------- palette.svg
def palette():
    groups = [
        ("Base", ["paper", "paper-sunk", "paper-raised", "ink", "ink-2", "ink-3",
                  "ink-4", "rule", "rule-strong"]),
        ("State (the only saturated colour in the product)",
         ["state-drift", "state-blocked", "state-down", "state-dark"]),
        ("Accent", ["accent", "accent-quiet"]),
        ("Charts", ["series-1", "series-2", "series-3", "band", "baseline"]),
    ]
    w, y = 980, 108
    rows = []
    for name, keys in groups:
        rows.append(f'<text x="32" y="{y}" font-size="13" font-weight="600" '
                    f'fill="{TOKENS["ink-2"]}">{name}</text>')
        y += 16
        for k in keys:
            v = TOKENS[k]
            r = ratio(v, TOKENS["paper"])
            note = "on paper" if k not in ("paper", "paper-raised") else ""
            rows.append(
                f'<rect x="32" y="{y}" width="120" height="34" fill="{v}" '
                f'stroke="{TOKENS["rule"]}" stroke-width="1" rx="2"/>'
                f'<text x="168" y="{y + 15}" font-size="12" font-family="{MONO}" '
                f'fill="{TOKENS["ink"]}">--{k}</text>'
                f'<text x="168" y="{y + 29}" font-size="11" font-family="{MONO}" '
                f'fill="{TOKENS["ink-3"]}">{v}</text>'
                f'<text x="330" y="{y + 22}" font-size="11" font-family="{MONO}" '
                f'fill="{TOKENS["ink-3"]}">contrast {r:.1f}:1 {note}</text>')
            y += 40
        y += 12
    h = y + 24
    body = "".join(rows)
    return (header(w, h, "Palette", "DigitalTwin.ai design tokens. No gradients. "
                                    "No dark variants. Colour means abnormal.")
            + body + "</svg>")


# --------------------------------------------------------- state-patterns.svg
def defs_patterns(suffix="", mono=False):
    def col(k):
        if not mono:
            return TOKENS[k]
        v = TOKENS[k]
        c = v.lstrip("#")
        g = int(0.299 * int(c[0:2], 16) + 0.587 * int(c[2:4], 16)
                + 0.114 * int(c[4:6], 16))
        return "#%02x%02x%02x" % (g, g, g)

    return (
        f'<defs>'
        f'<pattern id="p-drift{suffix}" width="8" height="8" '
        f'patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        f'<rect width="8" height="8" fill="{col("state-drift")}"/>'
        f'<rect width="3" height="8" fill="{col("ink")}" opacity="0.22"/></pattern>'
        f'<pattern id="p-blocked{suffix}" width="8" height="8" '
        f'patternUnits="userSpaceOnUse">'
        f'<rect width="8" height="8" fill="{col("state-blocked")}"/>'
        f'<rect width="3" height="8" fill="{col("ink")}" opacity="0.22"/></pattern>'
        f'<pattern id="p-starved{suffix}" width="8" height="8" '
        f'patternUnits="userSpaceOnUse">'
        f'<rect width="8" height="8" fill="{col("state-starved")}"/>'
        f'<rect width="8" height="3" fill="{col("ink")}" opacity="0.22"/></pattern>'
        f'<pattern id="p-dark{suffix}" width="7" height="7" '
        f'patternUnits="userSpaceOnUse">'
        f'<rect width="7" height="7" fill="{col("paper-sunk")}"/>'
        f'<path d="M0,7 L7,0 M-1,1 L1,-1 M6,8 L8,6" stroke="{col("state-dark")}" '
        f'stroke-width="1"/></pattern>'
        f'</defs>')


STATES = [
    ("Running", "none", "greyscale, no fill", "62.1 s"),
    ("Drifting", "p-drift", "diagonal stripe", "62.1 s  +4.1"),
    ("Blocked", "p-blocked", "vertical stripe", "held 41 s"),
    ("Starved", "p-starved", "horizontal stripe", "waiting 18 s"),
    ("Down", "solid-down", "solid, white text", "stopped 6 min"),
    ("Forecast", "outline", "2px outline, no fill", "09:52 to 10:04"),
    ("No machine data", "p-dark", "cross-hatch", "54 to 71 s"),
]


def grey(hexcolor):
    c = hexcolor.lstrip("#")
    g = int(0.299 * int(c[0:2], 16) + 0.587 * int(c[2:4], 16)
            + 0.114 * int(c[4:6], 16))
    return "#%02x%02x%02x" % (g, g, g)


def state_row(x, y, fill_id, label, pattern_note, value, suffix=""):
    mono = suffix == "-g"
    tk = (lambda k: grey(TOKENS[k])) if mono else (lambda k: TOKENS[k])
    if fill_id == "none":
        rect = (f'<rect x="{x}" y="{y}" width="150" height="52" '
                f'fill="{tk("paper-raised")}" stroke="{tk("rule")}"/>')
        tcol = tk("ink")
    elif fill_id == "solid-down":
        rect = (f'<rect x="{x}" y="{y}" width="150" height="52" '
                f'fill="{tk("state-down")}"/>')
        tcol = "#FFFFFF"
    elif fill_id == "outline":
        rect = (f'<rect x="{x}" y="{y}" width="150" height="52" '
                f'fill="{tk("paper-raised")}" '
                f'stroke="{tk("state-forecast")}" stroke-width="2" '
                f'stroke-dasharray="0"/>')
        tcol = tk("ink")
    else:
        rect = (f'<rect x="{x}" y="{y}" width="150" height="52" '
                f'fill="url(#{fill_id}{suffix})" stroke="{tk("rule")}"/>')
        tcol = tk("ink")
    return (rect
            + f'<text x="{x + 8}" y="{y + 18}" font-size="11" font-weight="600" '
              f'fill="{tcol}">{label}</text>'
            + f'<text x="{x + 8}" y="{y + 34}" font-size="11" font-family="{MONO}" '
              f'fill="{tcol}">{value}</text>'
            + f'<text x="{x + 8}" y="{y + 47}" font-size="9" fill="{tcol}" '
              f'opacity="0.75">{pattern_note}</text>')


def state_patterns():
    w, h = 1180, 300
    parts = [header(w, h, "Station states",
                    "Every state carries colour, pattern and text. "
                    "Colour is never the only signal.")]
    parts.append(defs_patterns())
    parts.append(defs_patterns("-g", mono=True))
    parts.append(f'<text x="32" y="104" font-size="12" font-weight="600" '
                 f'fill="{TOKENS["ink-2"]}">Colour</text>')
    x = 32
    for label, fid, note, val in STATES:
        parts.append(state_row(x, 114, fid, label, note, val))
        x += 158
    parts.append(f'<text x="32" y="196" font-size="12" font-weight="600" '
                 f'fill="{TOKENS["ink-2"]}">Same sheet in greyscale. Every state '
                 f'stays distinguishable.</text>')
    x = 32
    for label, fid, note, val in STATES:
        fid_g = fid if fid in ("none", "outline", "solid-down") else fid
        parts.append(state_row(x, 206, fid_g, label, note, val, suffix="-g"))
        x += 158
    return "".join(parts) + "</svg>"


# -------------------------------------------------------- line-strip-study.svg
ZONES = [("Body construction", 1, 16), ("Paint", 17, 26),
         ("Final assembly", 27, 42)]
DARK = {33, 34, 35, 36, 37, 42}
TIER_B = {7, 13, 14, 15, 16, 23, 24, 25, 26, 32, 40, 41}


def line_strip():
    w, h = 1440, 400
    left, right = 32, 1408
    n = 42
    seg_w = (right - left) / n
    parts = [header(w, h, "Line strip study",
                    "42 stations, Line 2. One drifting (S20), one down (S22), "
                    "six with no machine data. Simulated data.")]
    parts.append(defs_patterns())

    # forecast track
    ftop = 100
    parts.append(f'<text x="32" y="{ftop - 6}" font-size="11" '
                 f'fill="{TOKENS["ink-3"]}">Next 120 min</text>')
    parts.append(f'<line x1="{left}" y1="{ftop + 34}" x2="{right}" y2="{ftop + 34}" '
                 f'stroke="{TOKENS["rule"]}"/>')
    for i in range(9):
        tx = left + (right - left) * i / 8
        parts.append(f'<line x1="{tx}" y1="{ftop + 30}" x2="{tx}" y2="{ftop + 34}" '
                     f'stroke="{TOKENS["rule-strong"]}"/>')
        parts.append(f'<text x="{tx}" y="{ftop + 46}" font-size="9" '
                     f'font-family="{MONO}" fill="{TOKENS["ink-4"]}" '
                     f'text-anchor="middle">+{i * 15}</text>')
    # one forecast marker at ~ +20 to +32 min
    fx0 = left + (right - left) * 20 / 120
    fx1 = left + (right - left) * 32 / 120
    parts.append(f'<line x1="{fx0}" y1="{ftop + 14}" x2="{fx1}" y2="{ftop + 14}" '
                 f'stroke="{TOKENS["state-forecast"]}" stroke-width="2"/>')
    for fx in (fx0, fx1):
        parts.append(f'<line x1="{fx}" y1="{ftop + 8}" x2="{fx}" y2="{ftop + 20}" '
                     f'stroke="{TOKENS["state-forecast"]}" stroke-width="2"/>')
    parts.append(f'<text x="{fx1 + 8}" y="{ftop + 18}" font-size="11" '
                 f'font-family="{MONO}" fill="{TOKENS["ink"]}">'
                 f'S22 stop  p 0.71  09:52 to 10:04</text>')

    # station row
    stop, sh = 164, 90
    for i in range(1, n + 1):
        x = left + seg_w * (i - 1)
        sid = f"S{i:02d}"
        if i == 22:
            fill, tcol, val = TOKENS["state-down"], "#FFFFFF", "stopped"
        elif i == 20:
            fill, tcol, val = "url(#p-drift)", TOKENS["ink"], "62.1"
        elif i in DARK:
            fill, tcol, val = "url(#p-dark)", TOKENS["ink-2"], "54-71"
        else:
            fill, tcol, val = TOKENS["paper-raised"], TOKENS["ink"], "%.1f" % (
                57.4 + (i * 37 % 21) / 10)
        parts.append(f'<rect x="{x + 0.5}" y="{stop}" width="{seg_w - 1}" '
                     f'height="{sh}" fill="{fill}" stroke="{TOKENS["rule"]}"/>')
        parts.append(f'<text x="{x + 3}" y="{stop + 12}" font-size="8" '
                     f'font-family="{MONO}" fill="{tcol}">{sid}</text>')
        # range plot
        ry, rh = stop + 22, 44
        parts.append(f'<line x1="{x + seg_w / 2}" y1="{ry}" x2="{x + seg_w / 2}" '
                     f'y2="{ry + rh}" stroke="{TOKENS["rule-strong"]}"/>')
        if i in DARK:
            parts.append(f'<rect x="{x + seg_w / 2 - 3}" y="{ry + 6}" width="6" '
                         f'height="26" fill="{TOKENS["state-dark"]}" opacity="0.5"/>')
        elif i == 22:
            pass
        else:
            mark = ry + rh - 10 if i == 20 else ry + rh / 2 + ((i * 13 % 9) - 4)
            parts.append(f'<line x1="{x + seg_w / 2 - 5}" y1="{mark}" '
                         f'x2="{x + seg_w / 2 + 5}" y2="{mark}" stroke="{tcol}" '
                         f'stroke-width="2"/>')
        parts.append(f'<text x="{x + seg_w / 2}" y="{stop + sh - 4}" font-size="7.5" '
                     f'font-family="{MONO}" fill="{tcol}" '
                     f'text-anchor="middle">{val}</text>')

    # buffer row
    btop = stop + sh + 6
    buffers = [(4, 3, 6), (8, 5, 8), (12, 8, 8), (16, 2, 6), (20, 11, 12),
               (24, 1, 6), (28, 4, 8), (34, 6, 8), (39, 5, 6)]
    for pos, occ, cap in buffers:
        x = left + seg_w * pos - 10
        parts.append(f'<rect x="{x}" y="{btop}" width="20" height="26" '
                     f'fill="{TOKENS["paper-sunk"]}" stroke="{TOKENS["rule"]}"/>')
        fh = 26 * occ / cap
        parts.append(f'<rect x="{x}" y="{btop + 26 - fh}" width="20" height="{fh}" '
                     f'fill="{TOKENS["ink-3"]}" opacity="0.55"/>')
        parts.append(f'<text x="{x + 10}" y="{btop + 40}" font-size="8" '
                     f'font-family="{MONO}" fill="{TOKENS["ink-3"]}" '
                     f'text-anchor="middle">{occ}/{cap}</text>')

    # zone rule
    ztop = btop + 52
    parts.append(f'<line x1="{left}" y1="{ztop}" x2="{right}" y2="{ztop}" '
                 f'stroke="{TOKENS["rule-strong"]}"/>')
    for name, a, b in ZONES:
        x0 = left + seg_w * (a - 1)
        x1 = left + seg_w * b
        parts.append(f'<line x1="{x0}" y1="{ztop}" x2="{x0}" y2="{ztop + 6}" '
                     f'stroke="{TOKENS["rule-strong"]}"/>')
        parts.append(f'<text x="{(x0 + x1) / 2}" y="{ztop + 18}" font-size="11" '
                     f'fill="{TOKENS["ink-2"]}" text-anchor="middle">{name} '
                     f'S{a:02d}-S{b:02d}</text>')
    for gate, pos in (("G1", 16), ("G2", 26), ("G3", 42)):
        x = left + seg_w * pos
        parts.append(f'<text x="{x - 4}" y="{ztop + 32}" font-size="10" '
                     f'font-family="{MONO}" fill="{TOKENS["ink"]}" '
                     f'text-anchor="middle">{gate}</text>')

    parts.append(f'<text x="32" y="{h - 16}" font-size="11" '
                 f'fill="{TOKENS["ink-3"]}">A normal line is 42 grey blocks. '
                 f'The drifting station is the only saturated thing on screen, '
                 f'which is the point.</text>')
    return "".join(parts) + "</svg>"


# ------------------------------------------------------- typography-scale.svg
def typography():
    w, h = 980, 580
    scale = [("--text-display", 28, 600, "27", "lead time, once per screen"),
             ("--text-title", 20, 600, "Line 2", "page title"),
             ("--text-section", 15, 600, "At-risk units", "section heading"),
             ("--text-body", 14, 400, "S20 cycle time has drifted 4.1 s "
                                      "above its normal range.", "body"),
             ("--text-label", 13, 500, "Lead time", "labels, table headers"),
             ("--text-small", 12, 400, "14:32:06 · 38 s ago", "units, timestamps"),
             ("--text-micro", 11, 500, "S20", "station IDs, axis ticks")]
    parts = [header(w, h, "Type scale",
                    "Inter for prose. IBM Plex Mono, tabular figures, for every "
                    "number that will be compared.")]
    y = 112
    for token, size, weight, sample, use in scale:
        parts.append(f'<text x="32" y="{y}" font-size="11" font-family="{MONO}" '
                     f'fill="{TOKENS["ink-3"]}">{token}  {size}px/{weight}</text>')
        parts.append(f'<text x="230" y="{y}" font-size="{size}" '
                     f'font-weight="{weight}" fill="{TOKENS["ink"]}">{sample}</text>')
        parts.append(f'<text x="760" y="{y}" font-size="11" '
                     f'fill="{TOKENS["ink-4"]}">{use}</text>')
        y += max(size + 20, 34)
    y += 16
    parts.append(f'<line x1="32" y1="{y}" x2="948" y2="{y}" '
                 f'stroke="{TOKENS["rule"]}"/>')
    y += 26
    parts.append(f'<text x="32" y="{y}" font-size="13" font-weight="600" '
                 f'fill="{TOKENS["ink-2"]}">Numerals align, because they are '
                 f'compared</text>')
    y += 24
    for label, val in (("S18", "58.4 s"), ("S19", "57.9 s"), ("S20", "62.1 s"),
                       ("S21", "58.2 s"), ("S34", "54 to 71 s")):
        parts.append(f'<text x="32" y="{y}" font-size="13" font-family="{MONO}" '
                     f'fill="{TOKENS["ink"]}">{label}</text>')
        parts.append(f'<text x="180" y="{y}" font-size="13" font-family="{MONO}" '
                     f'fill="{TOKENS["ink"]}" text-anchor="end">{val}</text>')
        y += 20
    parts.append(f'<text x="300" y="{y - 20}" font-size="11" '
                 f'fill="{TOKENS["ink-3"]}">an interval, because that is what '
                 f'is known about S34</text>')
    return "".join(parts) + "</svg>"


for name, fn in (("palette.svg", palette), ("state-patterns.svg", state_patterns),
                 ("line-strip-study.svg", line_strip),
                 ("typography-scale.svg", typography)):
    (HERE / name).write_text(fn(), encoding="utf-8")
    print("wrote", name)
