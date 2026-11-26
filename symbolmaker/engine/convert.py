"""SVG input handling and the SwiftDraw call.

SwiftDraw (https://github.com/swhitty/SwiftDraw, `brew install swiftdraw`) expands strokes to outlines and writes an
SF Symbols template with three weight masters. We scale the strokes of the Ultralight/Black masters via its
`--ultralight-stroke-width` / `--black-stroke-width` options.
"""

import copy
import math
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


DEFAULT_INSETS = "2.25,0,2.25,0"


class SwiftDrawError(RuntimeError):
    """swiftdraw is missing or rejected the SVG; the message is safe to show to the user."""


class VariantsNotInterpolatable(SwiftDrawError):
    """swiftdraw (0.30 and later) would not write the template because its three weights differ in structure.

    Older versions wrote it anyway; `variants.run_weights` copes with both by making the weights one at a time.
    """


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


_STYLE_WIDTH = re.compile(r"((?:^|;)\s*stroke-width\s*:\s*)([^;]+)")


def _scaled_width(value, factor):
    n = _num(value)
    if n is None:
        raise ValueError(f"Cannot scale the stroke width {value!r}.")
    return _fmt(n * factor)


def scale_strokes(svg_text, factor):
    """The SVG with every stroke width multiplied by `factor` (the same way swiftdraw scales one for a weight).

    Widths on the root, on groups, on shapes and in `style` attributes are scaled; an SVG that never says how wide its
    strokes are gets the default width (1) scaled. A width it cannot read, or a style sheet (which it does not read),
    raises ValueError rather than being left at the wrong weight.
    """
    root = _parse(svg_text)
    if any(el.tag.split("}")[-1] == "style" for el in root.iter()):
        raise ValueError("Cannot scale the strokes of an SVG that has a style sheet.")
    for el in root.iter():
        if el.get("stroke-width") is not None:
            el.set("stroke-width", _scaled_width(el.get("stroke-width"), factor))
        style = el.get("style")
        if style and _STYLE_WIDTH.search(style):
            el.set("style", _STYLE_WIDTH.sub(lambda m: m.group(1) + _scaled_width(m.group(2), factor), style))
    if root.get("stroke-width") is None and not _STYLE_WIDTH.search(root.get("style", "")):
        root.set("stroke-width", _fmt(factor))
    return ET.tostring(root, encoding="unicode")


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


def run_swiftdraw(svg_text, ultra=0.5, black=1.5, insets=DEFAULT_INSETS):
    """Convert to a three-master SF Symbols template (text). The SVG is passed as a file argument, never via a shell.

    `ultra` and `black` are the stroke widths of those masters as multiples of the SVG's own (None: do not ask for that
    master, and swiftdraw copies Regular into it). Raises VariantsNotInterpolatable when swiftdraw refuses the result.
    """
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
        ]
        for flag, factor in (("--ultralight", ultra), ("--black", black)):
            if factor is not None:
                cmd += [f"{flag}-stroke-width", str(factor), f"{flag}-insets", insets]
        cmd += ["--output", out]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise SwiftDrawError("swiftdraw took too long on this SVG (60 s).") from None
        if r.returncode != 0 or not os.path.exists(out):
            msg = (r.stderr or r.stdout or "").strip()
            if "not interpolatable" in msg:
                raise VariantsNotInterpolatable(msg)
            raise SwiftDrawError(msg or "swiftdraw could not convert this SVG.")
        with open(out, encoding="utf-8") as f:
            return f.read()


# --- Shapes that have both a fill and a stroke --------------------------------------------------------------------
#
# SwiftDraw writes only the fill of a shape that is both filled and stroked (as of 0.30; its PNG output draws both, a
# browser does too), so the stroke goes missing: Lucide's palette gets dots 1 unit wide instead of 3, and the dots of
# many Tabler and Iconoir icons are lost the same way. `split_fills_from_strokes` gives SwiftDraw shapes that have only
# one of the two, so it draws what the browser draws. If a later SwiftDraw keeps the stroke itself, this step does no
# harm (nothing it writes has both) and can be deleted along with its call in pipeline.make_template.

_PATH_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGUMENTS = {"m": 2, "l": 2, "h": 1, "v": 1, "c": 6, "s": 4, "q": 4, "t": 2, "a": 7}
_UNDRAWN = {"defs", "clipPath", "mask", "pattern", "marker", "symbol", "style"}
_NO_PAINT = {"none", "transparent"}
_FILLED_SHAPES = {"path", "circle", "rect", "polyline", "polygon", "ellipse"}  # a <line> encloses nothing to fill


def _own(el, name):
    """The value this element gives the property: its style attribute wins over its own attribute."""
    m = re.search(rf"(?:^|;)\s*{re.escape(name)}\s*:\s*([^;]+)", el.get("style", ""))
    if m:
        return m.group(1).strip()
    v = el.get(name)
    return v.strip() if v is not None else None


def _put(el, name, value):
    """Set the property on this element, in its style attribute too if that is where it was set."""
    el.set(name, value)
    style = el.get("style")
    if style and re.search(rf"(?:^|;)\s*{re.escape(name)}\s*:", style):
        el.set("style", re.sub(rf"((?:^|;)\s*{re.escape(name)}\s*:)[^;]*", rf"\g<1>{value}", style))


def _arc_points(x1, y1, rx, ry, rotation, large, sweep, x2, y2):
    """Points along an elliptical arc (SVG implementation notes F.6.5), the end point included."""
    rx, ry = abs(rx), abs(ry)
    if (x1, y1) == (x2, y2):
        return []
    if rx == 0 or ry == 0:
        return [(x2, y2)]
    cos_p, sin_p = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p, y1p = cos_p * dx + sin_p * dy, -sin_p * dx + cos_p * dy
    grow = (x1p / rx) ** 2 + (y1p / ry) ** 2
    if grow > 1:
        rx, ry = rx * math.sqrt(grow), ry * math.sqrt(grow)
    side = (rx * ry) ** 2 - (rx * y1p) ** 2 - (ry * x1p) ** 2
    coef = math.sqrt(max(0.0, side / ((rx * y1p) ** 2 + (ry * x1p) ** 2))) * (-1 if large == sweep else 1)
    cxp, cyp = coef * rx * y1p / ry, -coef * ry * x1p / rx
    cx, cy = cos_p * cxp - sin_p * cyp + (x1 + x2) / 2, sin_p * cxp + cos_p * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    start = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    span = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and span > 0:
        span -= 2 * math.pi
    elif sweep and span < 0:
        span += 2 * math.pi
    steps = 16
    pts = []
    for k in range(1, steps + 1):
        a = start + span * k / steps
        ex, ey = rx * math.cos(a), ry * math.sin(a)
        pts.append((cos_p * ex - sin_p * ey + cx, sin_p * ex + cos_p * ey + cy))
    return pts


def _path_points(d):
    """Points along the path data (curves sampled), enough to tell how big the shape is. ValueError if unreadable."""
    n, i = len(d), 0

    def blank():
        nonlocal i
        while i < n and d[i] in " ,\t\r\n":
            i += 1

    def number(flag=False):
        nonlocal i
        blank()
        if flag:  # arc flags may run into the next number: "a1 1 0 011 1"
            if i < n and d[i] in "01":
                i += 1
                return float(d[i - 1])
            raise ValueError("bad arc flag")
        m = _PATH_NUMBER.match(d, i)
        if not m:
            raise ValueError("bad number")
        i = m.end()
        return float(m.group())

    pts, cmd = [], None
    x = y = sx = sy = 0.0
    ctrl = None  # the last control point, for the smooth curve commands
    while True:
        blank()
        if i >= n:
            return pts
        if d[i].isalpha():
            cmd = d[i]
            i += 1
            if cmd not in "MmLlHhVvCcSsQqTtAaZz":
                raise ValueError("unknown command")
            if cmd in "Zz":
                x, y, ctrl = sx, sy, None
                continue
        elif cmd is None or cmd in "Zz":
            raise ValueError("numbers without a command")
        c, rel = cmd.lower(), cmd.islower()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        reflected = (2 * x - ctrl[0], 2 * y - ctrl[1]) if ctrl else (x, y)  # the first control point of s and t
        if c in "ml":
            x, y = number() + ox, number() + oy
            if c == "m":
                sx, sy, cmd = x, y, ("l" if rel else "L")
            pts.append((x, y))
            ctrl = None
        elif c == "h":
            x = number() + ox
            pts.append((x, y))
            ctrl = None
        elif c == "v":
            y = number() + oy
            pts.append((x, y))
            ctrl = None
        elif c in "cs":
            p1 = (number() + ox, number() + oy) if c == "c" else reflected
            p2 = (number() + ox, number() + oy)
            p3 = (number() + ox, number() + oy)
            for k in range(1, 9):
                u = k / 8
                a, b, e, f = (1 - u) ** 3, 3 * (1 - u) ** 2 * u, 3 * (1 - u) * u**2, u**3
                pts.append((a * x + b * p1[0] + e * p2[0] + f * p3[0], a * y + b * p1[1] + e * p2[1] + f * p3[1]))
            (x, y), ctrl = p3, p2
        elif c in "qt":
            p1 = (number() + ox, number() + oy) if c == "q" else reflected
            p2 = (number() + ox, number() + oy)
            for k in range(1, 9):
                u = k / 8
                a, b, e = (1 - u) ** 2, 2 * (1 - u) * u, u**2
                pts.append((a * x + b * p1[0] + e * p2[0], a * y + b * p1[1] + e * p2[1]))
            (x, y), ctrl = p2, p1
        else:  # a
            rx, ry, rotation = number(), number(), number()
            large, sweep = number(flag=True), number(flag=True)
            ex, ey = number() + ox, number() + oy
            pts += _arc_points(x, y, rx, ry, rotation, large, sweep, ex, ey) or [(ex, ey)]
            x, y, ctrl = ex, ey, None
    return pts


def _shape_box(el):
    """(x0, y0, x1, y1) of a shape in its own units, or None when it cannot be worked out."""
    tag = el.tag.split("}")[-1]
    try:
        if tag in ("circle", "ellipse"):
            rx = _num(el.get("rx" if tag == "ellipse" else "r"))
            ry = _num(el.get("ry")) if tag == "ellipse" else rx
            cx, cy = _num(el.get("cx")) or 0.0, _num(el.get("cy")) or 0.0
            if rx is None or ry is None:
                return None
            return cx - rx, cy - ry, cx + rx, cy + ry
        if tag == "rect":
            x, y = _num(el.get("x")) or 0.0, _num(el.get("y")) or 0.0
            w, h = _num(el.get("width")), _num(el.get("height"))
            return None if w is None or h is None else (x, y, x + w, y + h)
        if tag in ("polyline", "polygon"):
            nums = [float(v) for v in _PATH_NUMBER.findall(el.get("points", ""))]
            pts = list(zip(nums[0::2], nums[1::2], strict=False))
        else:
            pts = _path_points(el.get("d", ""))
    except ValueError:
        return None
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _stroked_and_filled(el, fill, stroke, width):
    """Stroke width if the shape has a fill and a stroke of its own, else None. A fill nobody gave is not guessed at."""
    if fill is None or fill in _NO_PAINT or stroke is None or stroke in _NO_PAINT:
        return None
    if width is None:
        return 1.0
    w = None if width.endswith("%") else _num(width)
    return w if w and w > 0 else None


def _split_shape(el, stroke, w):
    """The shapes that draw what `el` draws: a point with round caps if it is a dot, else its fill and its stroke."""
    box = _shape_box(el)
    if box and max(box[2] - box[0], box[3] - box[1]) < w:
        # SwiftDraw draws the stroke of a closed shape smaller than the stroke as a ring with a hole in it, which shows
        # at the heavier weights. A point with round caps is a solid dot that grows with the weight, and a dot as wide
        # as the shape with its stroke is what the browser draws.
        x, y = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        tag = el.tag[: el.tag.rfind("}") + 1]
        dot = ET.Element(
            f"{tag}path",
            {
                "d": f"M{_fmt(x)} {_fmt(y)}h.01",
                "fill": "none",
                "stroke": stroke,
                "stroke-width": _fmt(max(box[2] - box[0], box[3] - box[1]) + w),
                "stroke-linecap": "round",
            },
        )
        for keep in ("transform", "id"):
            if el.get(keep) is not None:
                dot.set(keep, el.get(keep))
        return [dot]
    fill_only, stroke_only = copy.deepcopy(el), copy.deepcopy(el)
    _put(fill_only, "stroke", "none")
    _put(stroke_only, "fill", "none")
    if "id" in fill_only.attrib:
        del fill_only.attrib["id"]
    return [fill_only, stroke_only]


def _split_children(parent, fill, stroke, width):
    changed = False
    for child in list(parent):
        tag = child.tag.split("}")[-1]
        if tag in _UNDRAWN:
            continue
        f = _own(child, "fill") or fill
        s = _own(child, "stroke") or stroke
        w = _own(child, "stroke-width") or width
        sw = _stroked_and_filled(child, f, s, w) if tag in _FILLED_SHAPES else None
        if sw is not None:
            at = list(parent).index(child)
            parent.remove(child)
            for k, new in enumerate(_split_shape(child, s, sw)):
                parent.insert(at + k, new)
            changed = True
        else:
            changed |= _split_children(child, f, s, w)
    return changed


def split_fills_from_strokes(svg_text):
    """The SVG with every shape that has both a fill and a stroke replaced by shapes that draw the same with only one.

    Dots (shapes smaller than their own stroke) become a round-capped point as wide as the dot with its stroke;
    other shapes become one copy that is only filled and one that is only stroked. An SVG without such shapes comes
    back exactly as it was."""
    root = _parse(svg_text)
    if not _split_children(root, *(_own(root, name) for name in ("fill", "stroke", "stroke-width"))):
        return svg_text
    return ET.tostring(root, encoding="unicode")
