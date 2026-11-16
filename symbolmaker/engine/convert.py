"""SVG input handling and the SwiftDraw call.

SwiftDraw (https://github.com/swhitty/SwiftDraw, `brew install swiftdraw`) expands strokes to outlines and writes an
SF Symbols template with three weight masters. We scale the strokes of the Ultralight/Black masters via its
`--ultralight-stroke-width` / `--black-stroke-width` options.
"""

import os
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

MAX_SVG_BYTES = 262144
SVG_NS = "http://www.w3.org/2000/svg"
SHAPES = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse"}
INSTALL_HINT = "swiftdraw is not installed. Install it with: brew install swiftdraw"

ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")


class SwiftDrawError(RuntimeError):
    """swiftdraw is missing or rejected the SVG; the message is safe to show to the user."""


def find_swiftdraw():
    return shutil.which("swiftdraw")


def check_input(svg_text):
    """Error message for unusable input, else None."""
    if not svg_text or not svg_text.strip():
        return "The SVG is empty. Paste some SVG code first."
    if len(svg_text.encode("utf-8", "ignore")) > MAX_SVG_BYTES:
        return f"The SVG is too large (limit {MAX_SVG_BYTES // 1024} KB)."
    if "<svg" not in svg_text.lower():
        return "That doesn't look like SVG (no <svg> element found)."
    return None


def _num(s):
    m = re.match(r"\s*(-?\d*\.?\d+(?:e-?\d+)?)", s or "")
    return float(m.group(1)) if m else None


def _fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def _parse(svg_text):
    try:
        return ET.fromstring(svg_text)
    except ET.ParseError as e:
        raise ValueError(f"Could not parse the SVG: {e}") from e


def normalize_grid(svg_text, grid=24):
    """-> (svg, note). SVG on a `grid`-unit viewBox (content scaled uniformly, centered); note says what changed."""
    root = _parse(svg_text)
    vb = root.get("viewBox")
    if vb:
        nums = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", vb)]
        if len(nums) != 4 or nums[2] <= 0 or nums[3] <= 0:
            raise ValueError("The SVG has an unusable viewBox (no usable size).")
        vx, vy, vw, vh = nums
    else:
        w, h = _num(root.get("width")), _num(root.get("height"))
        if not w or not h or w <= 0 or h <= 0:
            raise ValueError("The SVG has no usable size: add a viewBox or width/height.")
        vx, vy, vw, vh = 0.0, 0.0, w, h
    if (vx, vy, vw, vh) == (0, 0, grid, grid):
        return svg_text, None
    s = grid / max(vw, vh)
    tx = (grid - vw * s) / 2 - vx * s
    ty = (grid - vh * s) / 2 - vy * s
    new = ET.Element(root.tag, {k: v for k, v in root.attrib.items() if k not in ("viewBox", "width", "height")})
    new.set("viewBox", f"0 0 {grid} {grid}")
    new.set("width", str(grid))
    new.set("height", str(grid))
    g = ET.SubElement(new, f"{{{SVG_NS}}}g", {"transform": f"translate({_fmt(tx)} {_fmt(ty)}) scale({_fmt(s)})"})
    for child in list(root):
        g.append(child)
    note = f"Rescaled from {vw:g}×{vh:g} to the {grid}-unit grid."
    return ET.tostring(new, encoding="unicode"), note


def _own_stroke(el):
    v = el.get("stroke")
    if v is not None:
        return v.strip()
    m = re.search(r"(?:^|;)\s*stroke\s*:\s*([^;]+)", el.get("style", ""))
    return m.group(1).strip() if m else None


def has_strokes(svg_text):
    """True if any shape has a visible stroke (own or inherited from a group / the root)."""
    root = _parse(svg_text)

    def walk(el, inherited):
        own = _own_stroke(el)
        eff = own if own is not None else inherited
        tag = el.tag.split("}")[-1]
        if tag in SHAPES and eff not in (None, "", "none"):
            return True
        return any(walk(c, eff) for c in el)

    return walk(root, None)


def _own_width(el):
    v = el.get("stroke-width")
    if v is None:
        m = re.search(r"(?:^|;)\s*stroke-width\s*:\s*([^;]+)", el.get("style", ""))
        v = m.group(1) if m else None
    return _num(v) if v is not None else None


def _own_scale(el):
    m = re.search(r"scale\(\s*(-?\d*\.?\d+)", el.get("transform", ""))
    return abs(float(m.group(1))) if m else 1.0


def stroke_width(svg_text):
    """The Regular stroke width in the SVG's own units (24-grid units once normalised), or None without strokes.
    Honours inheritance (root / groups), style attributes and uniform scale() transforms; when shapes disagree the
    most common width wins (ties: the larger)."""
    root = _parse(svg_text)
    found = []

    def walk(el, stroke, width, scale):
        own = _own_stroke(el)
        stroke = own if own is not None else stroke
        w = _own_width(el)
        width = w if w is not None else width
        scale *= _own_scale(el)
        if el.tag.split("}")[-1] in SHAPES and stroke not in (None, "", "none"):
            found.append(round((width if width is not None else 1.0) * scale, 4))
        for c in el:
            walk(c, stroke, width, scale)

    walk(root, None, None, 1.0)
    if not found:
        return None
    return max(set(found), key=lambda v: (found.count(v), v))


def run_swiftdraw(svg_text, ultra=0.5, black=1.5, insets="2.25,0,2.25,0"):
    """Convert to a three-master SF Symbols template (text). The SVG is passed as a file argument, never via a shell."""
    exe = find_swiftdraw()
    if not exe:
        raise SwiftDrawError(INSTALL_HINT)
    with tempfile.TemporaryDirectory() as tmp:
        src, out = os.path.join(tmp, "in.svg"), os.path.join(tmp, "out.svg")
        with open(src, "w", encoding="utf-8") as f:
            f.write(svg_text)
        cmd = [
            exe,
            src,
            "--format",
            "sfsymbol",
            "--insets",
            insets,
            "--ultralight-stroke-width",
            str(ultra),
            "--ultralight-insets",
            insets,
            "--black-stroke-width",
            str(black),
            "--black-insets",
            insets,
            "--output",
            out,
        ]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise SwiftDrawError("swiftdraw took too long on this SVG (60 s).") from None
        if r.returncode != 0 or not os.path.exists(out):
            msg = (r.stderr or r.stdout or "").strip()
            raise SwiftDrawError(msg or "swiftdraw could not convert this SVG.")
        with open(out, encoding="utf-8") as f:
            return f.read()
