"""The three weight masters of an icon, from SwiftDraw, whether or not it is willing to write them itself.

SwiftDraw makes the Ultralight and Black masters by drawing the strokes thinner and thicker, repairs the differences in
structure it can, and since 0.30 refuses to write the template if any are left (they would crash SF Symbols when drawn).
Our own aligner (weights.py) exists to repair those leftovers, so it needs them written out.

`run_weights` therefore asks SwiftDraw for all three at once, as always, and only if it refuses makes the weights one at
a time: SwiftDraw is run on the SVG with its strokes scaled to each weight, which it has no reason to refuse (a template
with a single weight has nothing to disagree with), and the three outlines are put together here. The result is what
older SwiftDraw versions wrote. Both ways give the same shapes in the same places.
"""

import re

from .convert import DEFAULT_INSETS, SwiftDrawError, VariantsNotInterpolatable, run_swiftdraw, scale_strokes
from .guides import parse_template
from .weights import shift_d, weight_group

__all__ = ["SwiftDrawError", "assemble", "run_per_weight", "run_weights"]

_D = re.compile(r'(\sd=")([^"]+)(")')


def assemble(ultralight, regular, black):
    """A template made of three single-weight runs.

    It is `regular` as it is, with the Regular group of `ultralight` moved into its Ultralight slot and that of `black`
    into its Black slot. The slots are as far apart as the template's guides say.
    """
    guides = parse_template(regular)
    here = guides["regular"]["origin"][0]
    out = regular
    for key, group, source in (("ultralight", "Ultralight-S", ultralight), ("black", "Black-S", black)):
        dx = guides[key]["origin"][0] - here
        body = _D.sub(
            lambda m, dx=dx: m.group(1) + shift_d(m.group(2), dx, 0) + m.group(3),
            weight_group(source, "Regular-S").group(2),
        )
        slot = weight_group(out, group)
        out = out.replace(slot.group(0), slot.group(1) + body + slot.group(3), 1)
    return out


def run_per_weight(svg_text, ultra, black, insets=DEFAULT_INSETS):
    """Make the template one weight at a time: a SwiftDraw run on the SVG with its strokes scaled to each weight."""
    runs = [run_swiftdraw(scale_strokes(svg_text, factor), None, None, insets) for factor in (ultra, 1.0, black)]
    return assemble(*runs)


def run_weights(svg_text, ultra=0.5, black=1.5, insets=DEFAULT_INSETS):
    """A three-master template for the SVG, with Ultralight and Black strokes `ultra` and `black` times the Regular one.

    One SwiftDraw run, unless it refuses (see the module text), and then one run per weight."""
    try:
        return run_swiftdraw(svg_text, ultra, black, insets)
    except VariantsNotInterpolatable:
        return run_per_weight(svg_text, ultra, black, insets)
