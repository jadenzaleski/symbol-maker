"""SVG text in, annotated three-master template + preview data out."""

from dataclasses import dataclass, field

from .convert import check_input, has_strokes, normalize_grid, stroke_width
from .layers import annotate, bbox, path_ds, plan_layers
from .variants import run_weights
from .weights import drop_collapsing_holes, masters_match, match_weights, shift_d, signature_ok, to_single_weight

PREVIEW_KEYS = {"ultralight": "Ultralight-S", "regular": "Regular-S", "black": "Black-S"}


@dataclass
class MakeResult:
    template: str
    status: str  # 'variable' | 'single-weight' | 'identical-masters'
    notes: list = field(default_factory=list)
    assignments: list = field(default_factory=list)  # list[LayerAssignment], one per path
    masters: dict = field(default_factory=dict)  # 'ultralight'|'regular'|'black' -> path data centered on the origin
    box: dict = field(default_factory=dict)  # same keys -> (x, y, w, h) of that master (centered on the origin)
    stroke: float | None = None  # Regular stroke width in 24-grid units (None: no strokes); set by make_template only
    problem: bool = False  # the symbol will not follow weight properly (single weight, or uneven in between)


def _preview(template):
    masters, box = {}, {}
    for key, weight in PREVIEW_KEYS.items():
        ds = path_ds(template, weight)
        boxes = [bbox(d) for d in ds]
        x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
        x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        masters[key] = [shift_d(d, -cx, -cy) for d in ds]
        box[key] = (-(x1 - x0) / 2, -(y1 - y0) / 2, x1 - x0, y1 - y0)
    return masters, box


def _result(template, status, notes, assignments):
    masters, box = _preview(template)
    return MakeResult(template, status, list(notes), list(assignments), masters, box)


LADDER_TRIES = (10, 6)  # alignment tolerances for the retries (kept few: each is slow)
BLACK_LADDER = (1.75, 1.6, 1.5, 1.4, 1.3, 1.2)  # lighter Black strokes to try when the requested one does not line up


def _line_up(raw, **kw):
    """Line up the three weights of `raw`: with the holes SwiftDraw drew loops on mended and kept if that works, and
    otherwise with every collapsing hole dropped, as it used to be. -> (matched template or None, reason or None)."""
    mended = drop_collapsing_holes(raw)
    matched, why = match_weights(mended, **kw)
    if matched is None:
        plain = drop_collapsing_holes(raw, mend=False)
        if plain != mended:
            return match_weights(plain, **kw)
    return matched, why


def _with_lighter_black(svg, ultra, black):
    """Retry the conversion with a lighter Black stroke, as little lighter as works. -> (matched template, black used)
    or (None, None). Never heavier than requested."""
    for b in (x for x in BLACK_LADDER if x < black):
        matched, _ = _line_up(run_weights(svg, ultra, b), tries=LADDER_TRIES)
        if matched is not None:
            return matched, b
    return None, None


def make_template(svg_text, ultra=0.5, black=1.5):
    """Convert one SVG. Raises ValueError for unusable input and SwiftDrawError when swiftdraw fails."""
    err = check_input(svg_text)
    if err:
        raise ValueError(err)
    svg, note = normalize_grid(svg_text)
    notes = [note] if note else []
    problem = False
    raw = run_weights(svg, ultra, black)
    if not has_strokes(svg):
        template = raw if masters_match(raw) else to_single_weight(raw)
        status, problem = "identical-masters", True
        notes.append(
            "This SVG has no strokes, so all three weights are identical: the symbol will convert and "
            "export, but it will not get bolder with bold text."
        )
    else:
        matched, _why = _line_up(raw)
        lighter = None
        if matched is None:
            matched, lighter = _with_lighter_black(svg, ultra, black)
        raw = drop_collapsing_holes(raw, mend=False)  # what the fallbacks below start from, as they always have
        if lighter is not None:
            notes.append(
                f"Black is {lighter:g}x the Regular stroke for this icon instead of {black:g}x: at the "
                "heavier weight its curves close up into a different shape, so the three weights could "
                "not line up."
            )
        if matched is not None:
            template, status = matched, "variable"
        elif signature_ok(raw):
            # the masters have the same segments but their nodes could not be aligned: still a valid variable
            # symbol (exact weights look right), but intermediate weights may look slightly uneven
            template, status, problem = raw, "variable", True
            notes.append(
                "The three weights line up as Ultralight, Regular and Black, but this icon may look slightly "
                "uneven at weights in between: its outlines could not be matched point for point."
            )
        else:
            template, status, problem = to_single_weight(raw), "single-weight", True
            notes.append(
                "The three weights of this icon could not be lined up, so it is a single-weight symbol: "
                "it will not follow bold text."
            )
    assignments = plan_layers(path_ds(template))
    res = _result(annotate(template, assignments), status, notes, assignments)
    res.stroke = stroke_width(svg)
    res.problem = problem
    return res
