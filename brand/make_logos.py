#!/usr/bin/env python3
"""Build the Lakefront logo candidates as self-contained SVG files.

Text is set in Inter 4 / Inter Display with HarfBuzz (so the font's kerning applies), tracked
tighter than the font's default, then converted to outlines: the SVGs need no font installed and
look the same everywhere. Marks are drawn on a 64-unit grid.

Needs fonttools, uharfbuzz and the Inter 4 OTF files (https://rsms.me/inter/):

    pip install fonttools uharfbuzz
    python brand/make_logos.py --fonts /path/to/inter/otf

Writes brand/candidates/, brand/type-study/, brand/sunrise/ and the preview pages
brand/preview.html and brand/sunrise/preview.html (every SVG inlined as a data URI, so each page
works on its own).
"""
from __future__ import annotations

import argparse
import base64
import html
import os
from dataclasses import dataclass
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = Path(__file__).resolve().parent
FONT_DIR = Path(os.environ.get("INTER_DIR", "/usr/share/fonts/opentype/inter"))

# Palette. Lake passes 4.5:1 on white and Lake (dark) 8:1 on Night, so either can carry text.
INK, LAKE = "#0F1E2E", "#1A75A8"
INK_DARK, LAKE_DARK = "#F2F5F8", "#62B6E8"
NIGHT = "#0B1520"  # dark background used in the preview
LIGHT = {"ink": INK, "lake": LAKE}
DARK = {"ink": INK_DARK, "lake": LAKE_DARK}
ON_TILE = {"ink": "#FFFFFF", "lake": LAKE_DARK}

# The wordmark every lockup uses (see the type study for the alternatives).
WORD = {"face": "InterDisplay-SemiBold", "tracking": -0.04, "size": 100}


def f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


# --------------------------------------------------------------------------- type


@dataclass
class Glyph:
    name: str
    d: str
    bbox: tuple[float, float, float, float]  # x0, y0, x1, y1; y grows downwards
    contours: list[tuple[str, tuple]]        # (path, bbox) of each closed contour


@dataclass
class Line:
    glyphs: list[Glyph]
    bbox: tuple[float, float, float, float]
    cap: float
    xheight: float


_fonts: dict[str, tuple] = {}


def _font(face: str):
    if face not in _fonts:
        path = FONT_DIR / f"{face}.otf"
        blob = hb.Blob.from_file_path(str(path))
        hbface = hb.Face(blob)
        tt = TTFont(path)
        _fonts[face] = (hb.Font(hbface), hbface.upem, tt, tt.getGlyphSet(), tt.getGlyphOrder())
    return _fonts[face]


def set_text(text: str, face: str, size: float, tracking: float = 0.0,
             features: dict | None = None) -> Line:
    """Shape `text` and return its outlines with the baseline at y=0 and the pen starting at x=0.

    `tracking` is in em, applied between glyphs the way CSS letter-spacing is.
    """
    font, upem, tt, glyph_set, order = _font(face)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, **(features or {})})
    scale = size / upem
    glyphs, x = [], 0.0
    infos, positions = buf.glyph_infos, buf.glyph_positions
    for i, (info, pos) in enumerate(zip(infos, positions)):
        name = order[info.codepoint]
        affine = (scale, 0, 0, -scale, x + pos.x_offset * scale, -pos.y_offset * scale)
        recording = RecordingPen()
        glyph_set[name].draw(TransformPen(recording, affine))
        d, bounds = _outline(glyph_set, recording.value)
        contours, start = [], 0
        for k, (op, _) in enumerate(recording.value):
            if op in ("closePath", "endPath"):
                contours.append(_outline(glyph_set, recording.value[start:k + 1]))
                start = k + 1
        glyphs.append(Glyph(name, d, bounds or (x, 0, x, 0), contours))
        x += pos.x_advance * scale
        if i < len(infos) - 1:
            x += tracking * size
    inked = [g.bbox for g in glyphs if g.d]
    bbox = (min(b[0] for b in inked), min(b[1] for b in inked),
            max(b[2] for b in inked), max(b[3] for b in inked))
    os2 = tt["OS/2"]
    return Line(glyphs, bbox, os2.sCapHeight * scale, os2.sxHeight * scale)


def _outline(glyph_set, commands):
    """SVG path and bounding box of recorded pen commands."""
    svg_pen, bounds_pen = SVGPathPen(glyph_set, ntos=f), BoundsPen(glyph_set)
    for op, args in commands:
        getattr(svg_pen, op)(*args)
        getattr(bounds_pen, op)(*args)
    return svg_pen.getCommands(), bounds_pen.bounds


# --------------------------------------------------------------------------- drawing helpers


def rect(x, y, w, h) -> str:
    return f"M{f(x)} {f(y)}h{f(w)}v{f(h)}h{f(-w)}z"


def wave(x0: float, x1: float, y: float, amp: float, halves: int):
    """Quadratic segments of a sine-like wave from (x0, y) to (x1, y), first hump upwards."""
    step = (x1 - x0) / halves
    segs = []
    for k in range(halves):
        sign = -1 if k % 2 == 0 else 1
        xa = x0 + k * step
        segs.append(((xa + step / 2, y + sign * 2 * amp), (xa + step, y)))
    return segs


def seg_d(segs) -> str:
    return "".join(f"Q{f(c[0])} {f(c[1])} {f(e[0])} {f(e[1])}" for c, e in segs)


def reverse(start, segs):
    pts = [start] + [e for _, e in segs]
    return [(segs[i][0], pts[i]) for i in range(len(segs) - 1, -1, -1)]


def wave_band(x0, x1, y_top, y_bottom, amp, halves) -> str:
    """Area between two parallel waves (or a wave and the frame's top/bottom edge)."""
    top = wave(x0, x1, y_top, amp, halves)
    bottom = wave(x0, x1, y_bottom, amp, halves)
    return (f"M{f(x0)} {f(y_top)}{seg_d(top)}L{f(x1)} {f(y_bottom)}"
            f"{seg_d(reverse((x0, y_bottom), bottom))}Z")


# --------------------------------------------------------------------------- marks (64 x 64)
# Each returns (defs, body). `uid` keeps clip-path ids unique inside one file.


def mark_reflection(c, uid):
    """Four bars (a chart, a skyline) and their reflection in the lake."""
    width, gap, x0, horizon = 11, 4, 4, 37
    heights = [16, 32, 24, 20]
    ink, lake = [], []
    for i, h in enumerate(heights):
        x = x0 + i * (width + gap)
        ink.append(rect(x, horizon - h, width, h))
        for k in range(max(1, round(h * 0.6 / 5))):
            inset = k * 1.25
            lake.append(rect(x + inset, horizon + 4 + k * 5, width - 2 * inset, 3))
    return "", (f'<path fill="{c["ink"]}" d="{"".join(ink)}"/>'
                f'<path fill="{c["lake"]}" d="{"".join(lake)}"/>')


def mark_corner(c, uid):
    """An L that holds the water in its corner: Chicago at the south-west corner of Lake Michigan."""
    el = "M6 6H20V44H58V58H6Z"
    waves = "".join(f"M28 {y}{seg_d(wave(28, 54, y, 2.5, 4))}" for y in (12, 23, 34))
    return "", (f'<path fill="{c["ink"]}" d="{el}"/>'
                f'<path fill="none" stroke="{c["lake"]}" stroke-width="5" stroke-linecap="round" '
                f'stroke-linejoin="round" d="{waves}"/>')


def rounded_polygon(points, r) -> str:
    """Closed polygon with every corner rounded (a quadratic through the vertex)."""
    n, d = len(points), []
    for i, (x, y) in enumerate(points):
        (px, py), (nx, ny) = points[i - 1], points[(i + 1) % n]
        a = (x + (px - x) * r / max(abs(px - x), abs(py - y)),
             y + (py - y) * r / max(abs(px - x), abs(py - y)))
        b = (x + (nx - x) * r / max(abs(nx - x), abs(ny - y)),
             y + (ny - y) * r / max(abs(nx - x), abs(ny - y)))
        d.append(f"{'M' if i == 0 else 'L'}{f(a[0])} {f(a[1])}Q{f(x)} {f(y)} {f(b[0])} {f(b[1])}")
    return "".join(d) + "Z"


def mark_grid(c, uid):
    """City blocks on a street grid (or the cells of a table) against one unbroken lake. The
    shoreline steps south-east, as Chicago's does."""
    size, gap, x0, rx = 12, 4, 2, 2.5
    pitch = size + gap
    land_per_row = [1, 2, 2, 3]
    # The lake is one shape whose edge follows the blocks, a street's width away from them.
    pts = _lake_outline(land_per_row, x0, size, gap)
    land = "".join(_round_rect(x0 + col * pitch, x0 + row * pitch, size, rx)
                   for row, n in enumerate(land_per_row) for col in range(n))
    return "", (f'<path fill="{c["ink"]}" d="{land}"/>'
                f'<path fill="{c["lake"]}" d="{rounded_polygon(pts, rx)}"/>')


def _round_rect(x, y, s, r) -> str:
    return rounded_polygon([(x, y), (x + s, y), (x + s, y + s), (x, y + s)], r)


def _lake_outline(land_per_row, x0, size, gap):
    """Staircase outline of the lake, clockwise from its top-left corner."""
    pitch = size + gap
    edge = x0 + len(land_per_row) * pitch - gap
    left = [x0 + n * pitch for n in land_per_row]
    pts = [(left[0], x0), (edge, x0), (edge, edge)]
    for row in range(len(land_per_row) - 1, -1, -1):
        bottom = edge if row == len(land_per_row) - 1 else x0 + row * pitch + size
        if row < len(land_per_row) - 1 and left[row] != left[row + 1]:
            pts += [(left[row + 1], bottom), (left[row], bottom)]
        elif row == len(land_per_row) - 1:
            pts.append((left[row], bottom))
    return pts


SUN_BANDS = [(35, 41), (44, 49), (52, 56)]


def mark_sunrise(c, uid, cx=32, cy=32, r=28):
    """A sun on the horizon: the upper half solid, the lower half its reflection in bands."""
    s = r / 28  # bands are designed for r=28 centred at 32
    clip = f"{uid}-sun"
    defs = f'<clipPath id="{clip}"><circle cx="{f(cx)}" cy="{f(cy)}" r="{f(r)}"/></clipPath>'
    top = rect(cx - r, cy - r, 2 * r, r)
    bands = "".join(rect(cx - r, cy + (a - 32) * s, 2 * r, (b - a) * s) for a, b in SUN_BANDS)
    return defs, (f'<g clip-path="url(#{clip})"><path fill="{c["ink"]}" d="{top}"/>'
                  f'<path fill="{c["lake"]}" d="{bands}"/></g>')


def mark_shield(c, uid):
    """An insurer's shield over a wave-cut horizon."""
    shield = ("M12 6H52Q56 6 56 10V29C56 45 45.5 54.5 32 60C18.5 54.5 8 45 8 29V10Q8 6 12 6Z")
    clip = f"{uid}-shield"
    defs = f'<clipPath id="{clip}"><path d="{shield}"/></clipPath>'
    sky = f"M0 0H64V30{seg_d(reverse((0, 30), wave(0, 64, 30, 2.5, 4)))}Z"
    band = wave_band(0, 64, 34.5, 41, 2.5, 4)
    deep = f"M0 44.5{seg_d(wave(0, 64, 44.5, 2.5, 4))}V64H0Z"
    return defs, (f'<g clip-path="url(#{clip})"><path fill="{c["ink"]}" d="{sky}"/>'
                  f'<path fill="{c["lake"]}" d="{band}{deep}"/></g>')


def mark_letter(c, uid):
    """For the wordmark-only candidate: the L of the wordmark on its own."""
    line = set_text("L", "InterDisplay-Bold", 56)
    x0, y0, x1, y1 = line.bbox
    dx, dy = 32 - (x0 + x1) / 2, 32 - (y0 + y1) / 2
    return "", f'<path fill="{c["ink"]}" transform="translate({f(dx)} {f(dy)})" d="{line.glyphs[0].d}"/>'


# --------------------------------------------------------------------------- documents


def svg(w, h, body, defs="", label="Lakefront") -> str:
    defs = f"<defs>{defs}</defs>" if defs else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(w)} {f(h)}" '
            f'width="{f(w)}" height="{f(h)}" role="img" aria-label="{label}">'
            f"<title>{label}</title>{defs}{body}</svg>\n")


def wordmark_body(line: Line, colour: str, dx: float, dy: float, skip=()) -> str:
    d = "".join(g.d for g in line.glyphs if g.name not in skip)
    return f'<path fill="{colour}" transform="translate({f(dx)} {f(dy)})" d="{d}"/>'


def wordmark(face, tracking, colour, text="Lakefront", size=100, features=None, pad=0):
    line = set_text(text, face, size, tracking, features)
    x0, y0, x1, y1 = line.bbox
    w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
    return svg(w, h, wordmark_body(line, colour, pad - x0, pad - y0), label=text)


def lockup(mark_fn, c, uid):
    """Mark to the left of the wordmark, centred on the capitals."""
    line = set_text("Lakefront", WORD["face"], WORD["size"], WORD["tracking"])
    x0, y0, x1, y1 = line.bbox
    box = line.cap * 1.5          # side of the 64-unit mark box
    gap = box * 0.26
    scale = box / 64
    top = min(y0, -line.cap / 2 - box / 2)
    bottom = max(y1, -line.cap / 2 + box / 2)
    defs, body = mark_fn(c, uid)
    mark_y = -line.cap / 2 - box / 2 - top
    parts = (f'<g transform="translate(0 {f(mark_y)}) scale({f(scale)})">{body}</g>'
             + wordmark_body(line, c["ink"], box + gap - x0, -top))
    return svg(box + gap + x1 - x0, bottom - top, parts, defs)


def sunrise_wordmark(c, uid):
    """The wordmark with its o replaced by the sunrise."""
    line = set_text("Lakefront", WORD["face"], WORD["size"], WORD["tracking"])
    x0, y0, x1, y1 = line.bbox
    o = next(g for g in line.glyphs if g.name == "o")
    ox0, oy0, ox1, oy1 = o.bbox
    r = (oy1 - oy0) / 2
    defs, sun = mark_sunrise(c, uid, cx=(ox0 + ox1) / 2 - x0, cy=(oy0 + oy1) / 2 - y0, r=r)
    body = wordmark_body(line, c["ink"], -x0, -y0, skip={"o"}) + sun
    return svg(x1 - x0, y1 - y0, body, defs)


def icon(mark_fn, uid, scale=0.72):
    """App icon / favicon: the mark on an ink tile."""
    defs, body = mark_fn(ON_TILE, uid)
    off = 32 - 32 * scale
    return svg(64, 64, f'<rect width="64" height="64" rx="14" fill="{INK}"/>'
               f'<g transform="translate({f(off)} {f(off)}) scale({f(scale)})">{body}</g>', defs)


# --------------------------------------------------------------------------- sunrise o variations


@dataclass
class Sunrise:
    slug: str
    name: str
    note: str
    shape: str   # "circle": a circle as tall as the o; "oval": Inter's outline of the o.
    #              Both are solid: the o's counter is filled in.
    bands: list  # lake bands as (top, bottom) in 28ths of the o's half-height below the horizon;
    #              28 is the bottom of the o


THREE_BANDS = [(3, 10.5), (13.5, 20), (23, 28)]

SUNRISE = [
    Sunrise("a-circle-3-bands", "Circle, three bands",
            "Only the first change: the bands are rebalanced so the last one runs to the bottom of "
            "the circle, and the o sits on the baseline like the letters around it.",
            "circle", THREE_BANDS),
    Sunrise("b-oval-3-bands", "Inter's o, three bands",
            "Both changes: Inter's own outline of the o, filled in, with the same three bands. It is "
            "narrower than the circle and squarer at the shoulders, so it sits in the word like a letter.",
            "oval", THREE_BANDS),
    Sunrise("c-oval-4-bands", "Inter's o, four bands",
            "Finer ripples, getting thinner towards the bottom. Best at large sizes: below about 24 px "
            "the gaps close up.",
            "oval", [(2.5, 8), (10.5, 15), (17.5, 21.5), (24, 28)]),
    Sunrise("d-oval-2-bands", "Inter's o, two bands",
            "Two broad bands and wider gaps. The boldest version, and the one that lasts down to "
            "favicon size.",
            "oval", [(3.5, 14.5), (18, 28)]),
    Sunrise("e-oval-horizon", "Inter's o, horizon only",
            "No ripples: ink above the horizon, lake below. The quietest version, and the clearest "
            "at the smallest sizes.",
            "oval", [(3.5, 28)]),
]

# Candidate 05 as first drawn, in the same terms, for comparison.
SUNRISE_BEFORE = Sunrise("before", "Before", "", "circle", [(3, 9), (12, 17), (20, 24)])


def wordmark_o() -> tuple[Line, Glyph]:
    line = set_text("Lakefront", WORD["face"], WORD["size"], WORD["tracking"])
    return line, next(g for g in line.glyphs if g.name == "o")


def outer_outline(o: Glyph) -> str:
    """The o's outer contour alone: the letter with its counter filled in."""
    return max(o.contours, key=lambda k: (k[1][2] - k[1][0]) * (k[1][3] - k[1][1]))[0]


def sunrise_o(c, uid, o: Glyph, v: Sunrise):
    """The o as a sun on the horizon, drawn in the o's own coordinates."""
    x0, y0, x1, y1 = o.bbox
    cx, cy, half = (x0 + x1) / 2, (y0 + y1) / 2, (y1 - y0) / 2
    clip = f"{uid}-o"
    if v.shape == "circle":
        shape = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(half)}"/>'
        left, right = cx - half, cx + half
    else:
        shape = f'<path d="{outer_outline(o)}"/>'
        left, right = x0, x1
    width, unit = right - left + 2, half / 28
    sky = rect(left - 1, y0 - 1, width, cy - y0 + 1)
    lake = "".join(rect(left - 1, cy + a * unit, width, (b + (1 if b >= 28 else 0) - a) * unit)
                   for a, b in v.bands)
    return (f'<clipPath id="{clip}">{shape}</clipPath>',
            f'<g clip-path="url(#{clip})"><path fill="{c["ink"]}" d="{sky}"/>'
            f'<path fill="{c["lake"]}" d="{lake}"/></g>')


def sunrise_lockup(v: Sunrise, c, uid):
    line, o = wordmark_o()
    x0, y0, x1, y1 = line.bbox
    defs, sun = sunrise_o(c, uid, o, v)
    body = (wordmark_body(line, c["ink"], -x0, -y0, skip={"o"})
            + f'<g transform="translate({f(-x0)} {f(-y0)})">{sun}</g>')
    return svg(x1 - x0, y1 - y0, body, defs)


def sunrise_mark(v: Sunrise, c, uid, height=56, overlay=False):
    """The o alone, centred in the 64-unit box. `overlay` traces the outline of Inter's o over it
    (preview only)."""
    _, o = wordmark_o()
    x0, y0, x1, y1 = o.bbox
    s = height / (y1 - y0)
    defs, body = sunrise_o(c, uid, o, v)
    if overlay:
        body += (f'<path fill="none" stroke="{OVERLAY}" stroke-width="1.5" '
                 f'vector-effect="non-scaling-stroke" d="{outer_outline(o)}"/>')
    move = f"translate({f(32 - (x0 + x1) / 2 * s)} {f(32 - (y0 + y1) / 2 * s)}) scale({f(s)})"
    return defs, f'<g transform="{move}">{body}</g>'


OVERLAY = "#E5484D"


# --------------------------------------------------------------------------- the candidates

CANDIDATES = [
    {
        "slug": "01-wordmark",
        "name": "Wordmark",
        "concept": "Type only: Inter Display SemiBold at -0.04em. Nothing to explain, works at any "
                   "size, and you can set it as live text in HTML. The icon is its L.",
        "mark": mark_letter,
        "lockup": lambda c, uid: wordmark(WORD["face"], WORD["tracking"], c["ink"]),
    },
    {
        "slug": "02-reflection",
        "name": "Reflection",
        "concept": "Four bars read as a chart and as a skyline, mirrored in the lake below. "
                   "Synthetic data as a reflection of a real city.",
        "mark": mark_reflection,
    },
    {
        "slug": "03-corner",
        "name": "South-west corner",
        "concept": "An L that holds the water in its corner. Chicago sits at the south-west corner "
                   "of Lake Michigan, so the shape is also the map.",
        "mark": mark_corner,
    },
    {
        "slug": "04-shoreline-grid",
        "name": "Shoreline grid",
        "concept": "City blocks on a street grid (or the cells of a table) against one unbroken "
                   "lake. The shore steps south-east the way Chicago's does.",
        "mark": mark_grid,
    },
    {
        "slug": "05-sunrise",
        "name": "Sunrise o",
        "concept": "The o becomes the sun rising over the lake (sunrise is over the water in "
                   "Chicago), its lower half reflected in bands. The mark lives inside the word.",
        "mark": mark_sunrise,
        "lockup": sunrise_wordmark,
    },
    {
        "slug": "06-shield",
        "name": "Shield",
        "concept": "The insurer's shield with a wave-cut horizon. The most literal of the six: "
                   "it says insurance first and lake second.",
        "mark": mark_shield,
    },
]

TYPE_STUDY = [
    ("Inter SemiBold", "Inter-SemiBold", -0.02, "Lakefront", None,
     "Inter's recommended spacing for large text, for reference"),
    ("Inter SemiBold", "Inter-SemiBold", -0.04, "Lakefront", None, ""),
    ("Inter Display SemiBold", "InterDisplay-SemiBold", -0.04, "Lakefront", None,
     "Used in the lockups"),
    ("Inter Display Bold", "InterDisplay-Bold", -0.05, "Lakefront", None, ""),
    ("Inter Display ExtraBold", "InterDisplay-ExtraBold", -0.06, "Lakefront", None, ""),
    ("Inter Display Medium, cv05", "InterDisplay-Medium", -0.04, "lakefront", {"cv05": True},
     "Lower case, with Inter's tailed l"),
]


def build(out: Path) -> dict:
    cand_dir, type_dir = out / "candidates", out / "type-study"
    cand_dir.mkdir(parents=True, exist_ok=True)
    type_dir.mkdir(parents=True, exist_ok=True)
    files = {}

    def write(path: Path, text: str):
        path.write_text(text)
        files[path.relative_to(out).as_posix()] = text

    for cand in CANDIDATES:
        slug, mark_fn = cand["slug"], cand["mark"]
        make_lockup = cand.get("lockup") or (lambda c, uid, m=mark_fn: lockup(m, c, uid))
        write(cand_dir / f"{slug}-lockup.svg", make_lockup(LIGHT, slug))
        write(cand_dir / f"{slug}-lockup-dark.svg", make_lockup(DARK, slug))
        defs, body = mark_fn(LIGHT, slug)
        write(cand_dir / f"{slug}-mark.svg", svg(64, 64, body, defs))
        write(cand_dir / f"{slug}-icon.svg", icon(mark_fn, slug))

    for i, (label, face, tracking, text, feats, _note) in enumerate(TYPE_STUDY, 1):
        name = f"{i:02d}-{face.lower()}{'-cv05' if feats else ''}-{abs(tracking):.3f}em".replace(".", "_")
        write(type_dir / f"{name}.svg", wordmark(face, tracking, INK, text=text, features=feats))

    sun_dir = out / "sunrise"
    sun_dir.mkdir(parents=True, exist_ok=True)
    for v in SUNRISE:
        write(sun_dir / f"{v.slug}-lockup.svg", sunrise_lockup(v, LIGHT, v.slug))
        write(sun_dir / f"{v.slug}-lockup-dark.svg", sunrise_lockup(v, DARK, v.slug))
        defs, body = sunrise_mark(v, LIGHT, v.slug)
        write(sun_dir / f"{v.slug}-mark.svg", svg(64, 64, body, defs))
        write(sun_dir / f"{v.slug}-icon.svg", icon(lambda c, uid, v=v: sunrise_mark(v, c, uid), v.slug))
    return files


# --------------------------------------------------------------------------- preview page


def data_uri(svg_text: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg_text.encode()).decode()


def img(svg_text: str, height: int, alt="Lakefront") -> str:
    return f'<img src="{data_uri(svg_text)}" alt="{html.escape(alt)}" style="height:{height}px">'


def section(num, name, concept, light, dark, icon_svg) -> str:
    icons = "".join(img(icon_svg, px) for px in (64, 32, 16))
    return f"""
<section class="cand">
  <header><span class="num">{num}</span><h2>{name}</h2><p>{concept}</p></header>
  <div class="tiles">
    <div class="tile light">{img(light, 56)}</div>
    <div class="tile dark">{img(dark, 56)}</div>
    <div class="tile icons">{icons}</div>
  </div>
  <div class="small">
    <span class="light">{img(light, 22)}</span>
    <span class="dark">{img(dark, 22)}</span>
    <span class="note">header size</span>
  </div>
</section>"""


def page(title: str, lede: str, body: str) -> str:
    swatches = "".join(
        f'<span class="sw"><i style="background:{hexv}"></i>{name} <code>{hexv}</code></span>'
        for name, hexv in [("Ink", INK), ("Lake", LAKE), ("Ink on dark", INK_DARK),
                           ("Lake on dark", LAKE_DARK), ("Night", NIGHT)])
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --ink: {INK}; --lake: {LAKE}; --night: {NIGHT}; --line: #E3E8EE; --muted: #5B6B7C; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; color: var(--ink); background: #F6F8FA; }}
  main {{ max-width: 1180px; margin: 0 auto; padding: 40px 28px 64px; }}
  h1 {{ font-size: 28px; letter-spacing: -0.02em; margin: 0 0 6px; }}
  h2 {{ font-size: 17px; margin: 0; }}
  h3 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .08em; color: var(--muted); margin: 40px 0 14px; }}
  p.lede {{ color: var(--muted); margin: 0 0 18px; max-width: 760px; }}
  .swatches {{ display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 13px; color: var(--muted); }}
  .sw {{ display: inline-flex; align-items: center; gap: 6px; }}
  .sw i {{ width: 16px; height: 16px; border-radius: 4px; box-shadow: inset 0 0 0 1px rgba(0,0,0,.12); }}
  code {{ font: 12px ui-monospace, SFMono-Regular, Menlo, monospace; }}
  .types {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }}
  figure.type {{ margin: 0; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 26px 22px 16px; }}
  figure.type img {{ display: block; margin-bottom: 18px; }}
  figcaption {{ font-size: 13px; display: flex; flex-wrap: wrap; gap: 2px 10px; color: var(--muted); }}
  figcaption b {{ color: var(--ink); font-weight: 600; }}
  figcaption em {{ flex-basis: 100%; font-style: normal; }}
  .glance {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px; }}
  figure.o {{ margin: 0; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 16px 10px 10px; text-align: center; }}
  figure.o img {{ display: block; margin: 0 auto 10px; }}
  figure.o figcaption {{ display: block; font-size: 12px; line-height: 1.35; }}
  figure.o.before {{ background: #F1F4F7; }}
  .key {{ font-size: 13px; color: var(--muted); margin: 10px 0 0; }}
  .key i {{ display: inline-block; width: 18px; height: 0; border-top: 2px solid {OVERLAY}; vertical-align: middle; margin-right: 6px; }}
  section.cand {{ background: #fff; border: 1px solid var(--line); border-radius: 14px; padding: 20px; margin-bottom: 14px; }}
  section.cand header {{ display: grid; grid-template-columns: 34px 1fr; column-gap: 8px; margin-bottom: 14px; }}
  section.cand header p {{ grid-column: 2; margin: 2px 0 0; color: var(--muted); max-width: 760px; }}
  .num {{ font: 600 13px ui-monospace, Menlo, monospace; color: var(--lake); padding-top: 2px; }}
  .tiles {{ display: grid; grid-template-columns: 1fr 1fr 200px; gap: 10px; }}
  .tile {{ border-radius: 10px; min-height: 150px; display: flex; align-items: center; justify-content: center; padding: 24px; }}
  .tile.light {{ background: #fff; box-shadow: inset 0 0 0 1px var(--line); }}
  .tile.dark {{ background: var(--night); }}
  .tile.icons {{ background: #F1F4F7; gap: 18px; }}
  .small {{ display: flex; align-items: center; gap: 10px; margin-top: 10px; }}
  .small > span {{ display: inline-flex; align-items: center; height: 46px; padding: 0 16px; border-radius: 8px; }}
  .small .light {{ box-shadow: inset 0 0 0 1px var(--line); }}
  .small .dark {{ background: var(--night); }}
  .small .note {{ font-size: 12px; color: var(--muted); padding: 0; }}
  img {{ max-width: 100%; }}
  @media (max-width: 760px) {{ .tiles {{ grid-template-columns: 1fr; }} .glance {{ grid-template-columns: repeat(3, 1fr); }} }}
</style></head>
<body><main>
  <h1>{title}</h1>
  <p class="lede">{lede}</p>
  <div class="swatches">{swatches}</div>
  {body}
</main></body></html>
"""


def preview(files: dict) -> str:
    type_rows = []
    keys = sorted(k for k in files if k.startswith("type-study/"))
    for key, (label, face, tracking, text, feats, note) in zip(keys, TYPE_STUDY):
        type_rows.append(
            f'<figure class="type">{img(files[key], 48)}<figcaption><b>{label}</b>'
            f"<span>letter-spacing {tracking:.2f}em</span>"
            f'{f"<em>{note}</em>" if note else ""}</figcaption></figure>')
    cands = "".join(
        section(c["slug"][:2], c["name"], c["concept"], files[f"candidates/{c['slug']}-lockup.svg"],
                files[f"candidates/{c['slug']}-lockup-dark.svg"],
                files[f"candidates/{c['slug']}-icon.svg"])
        for c in CANDIDATES)
    return page(
        "Lakefront: logo candidates",
        "Every wordmark is Inter 4 converted to outlines, so the SVG files need no font. Lockups use "
        "Inter Display SemiBold at -0.04em. Icons are shown at 64, 32 and 16 px.",
        f"""<h3>Type study: Inter with tightened spacing</h3>
  <div class="types">{''.join(type_rows)}</div>
  <h3>Candidates</h3>
  {cands}""")


def sunrise_preview(files: dict) -> str:
    glance = []
    for v in [SUNRISE_BEFORE] + SUNRISE:
        defs, body = sunrise_mark(v, LIGHT, v.slug, overlay=True)
        label = "Before" if v is SUNRISE_BEFORE else f"{v.slug[0].upper()}. {v.name}"
        cls = "o before" if v is SUNRISE_BEFORE else "o"
        glance.append(f'<figure class="{cls}">{img(svg(64, 64, body, defs), 112)}'
                      f"<figcaption>{label}</figcaption></figure>")
    rows = "".join(
        section(v.slug[0].upper(), v.name, v.note, files[f"sunrise/{v.slug}-lockup.svg"],
                files[f"sunrise/{v.slug}-lockup-dark.svg"], files[f"sunrise/{v.slug}-icon.svg"])
        for v in SUNRISE)
    return page(
        "Lakefront: sunrise o variations",
        "Candidate 05, refined in two ways: the lake bands now run to the bottom of the o, so it sits "
        "on the baseline, and B to E follow the outline of Inter's own o instead of a circle. Every o is solid. Icons at 64, 32 and 16 px.",
        f"""<h3>The o, close up</h3>
  <div class="glance">{''.join(glance)}</div>
  <p class="key"><i></i>The outline of Inter Display SemiBold's own o, traced over each version</p>
  <h3>Variations</h3>
  {rows}""")


def main():
    global FONT_DIR
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--fonts", type=Path, default=FONT_DIR, help="folder with Inter's .otf files")
    ap.add_argument("--out", type=Path, default=HERE)
    args = ap.parse_args()
    FONT_DIR = args.fonts
    files = build(args.out)
    (args.out / "preview.html").write_text(preview(files))
    (args.out / "sunrise" / "preview.html").write_text(sunrise_preview(files))
    print(f"wrote {len(files)} SVG files, preview.html and sunrise/preview.html to {args.out}")


if __name__ == "__main__":
    main()
