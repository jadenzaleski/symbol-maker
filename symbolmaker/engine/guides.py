"""Read the drawing guides of an SF Symbols template (ours from SwiftDraw, or one exported by Apple's `sfsymbols`).

Both have the same structure: a `Guides` group with `Baseline-S`, `Capline-S` and `left-/right-margin-<Weight>-S`, and a
`<Weight>-S` group per weight holding the paths. They differ in how they are written (lines vs paths, a matrix vs a
translate) and in where the symbol sits, so this reduces both to one form per weight:

    {'paths': [d, ...], 'origin': [x, y], 'width': w, 'cap': c}

`origin` is the point, in the paths' own coordinates, that is the left margin on the baseline; `width` is the distance
between the margins (the symbol's advance); `cap` is the cap height (baseline to capline) that text sits in.
"""

import re
import xml.etree.ElementTree as ET

WEIGHTS = {"ultralight": "Ultralight", "regular": "Regular", "black": "Black"}
NUM = r"-?\d*\.?\d+(?:e-?\d+)?"


def _tag(e):
    return e.tag.split("}")[-1]


def _start(e):
    """(x, y) of a guide written as <line x1 y1 ...> or <path d="M x,y ...">."""
    if _tag(e) == "line":
        return float(e.get("x1")), float(e.get("y1"))
    n = re.findall(NUM, e.get("d", ""))
    if len(n) < 2:
        raise ValueError(f"unreadable guide {e.get('id')!r}")
    return float(n[0]), float(n[1])


def _translation(e):
    t = (e.get("transform") or "").strip()
    if not t:
        return 0.0, 0.0
    m = re.fullmatch(rf"matrix\(\s*1[\s,]+0[\s,]+0[\s,]+1[\s,]+({NUM})[\s,]+({NUM})\s*\)", t) or re.fullmatch(
        rf"translate\(\s*({NUM})(?:[\s,]+({NUM}))?\s*\)", t
    )
    if not m:
        raise ValueError(f"unsupported group transform {t!r}")
    return float(m.group(1)), float(m.group(2) or 0)


def parse_template(svg_text):
    try:
        root = ET.fromstring(svg_text)
    except ET.ParseError as e:
        raise ValueError(f"Could not parse the template: {e}") from e
    by_id = {}
    for e in root.iter():
        if e.get("id"):
            by_id.setdefault(e.get("id"), e)

    def guide(name):
        if name not in by_id:
            raise ValueError(f"The template has no {name} guide.")
        return _start(by_id[name])

    baseline, capline = guide("Baseline-S")[1], guide("Capline-S")[1]
    out = {}
    for key, label in WEIGHTS.items():
        group = by_id.get(f"{label}-S")
        if group is None:
            raise ValueError(f"The template has no {label}-S group.")
        left, right = guide(f"left-margin-{label}-S")[0], guide(f"right-margin-{label}-S")[0]
        tx, ty = _translation(group)
        paths = [p.get("d") for p in group.iter() if _tag(p) == "path" and p.get("d")]
        out[key] = {
            "paths": paths,
            "origin": [left - tx, baseline - ty],
            "width": right - left,
            "cap": baseline - capline,
        }
    return out
