"""Getting the three weights out of SwiftDraw, including for icons it refuses to write itself (0.30 and later)."""

import glob
import os
import re
import unittest
from unittest import mock

from symbolmaker.engine import variants
from symbolmaker.engine.convert import VariantsNotInterpolatable, find_swiftdraw, run_swiftdraw, stroke_width
from symbolmaker.engine.guides import parse_template
from symbolmaker.engine.layers import bbox, path_ds

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE = find_swiftdraw() is not None
NS = 'xmlns="http://www.w3.org/2000/svg"'
MARGINS = {"Ultralight-S": 221.923, "Regular-S": 421.923, "Black-S": 621.923}
NUM = r"-?\d*\.?\d+"


def template(bodies):
    """A minimal SwiftDraw-style template: the guides (margins 200 apart) and one group of paths per weight."""
    guides = '<path id="Baseline-S" d="M18,146 l800,0"/><path id="Capline-S" d="M18,76 l800,0"/>'
    for name, x in MARGINS.items():
        guides += f'<path id="left-margin-{name}" d="M{x},56 l0,110"/>'
        guides += f'<path id="right-margin-{name}" d="M{x + 86.154},56 l0,110"/>'
    groups = "".join(f'<g id="{w}" transform="translate(0,0)">{bodies[w]}</g>' for w in MARGINS)
    return f'<svg {NS}><g id="Guides">{guides}</g><g id="Symbols">{groups}</g></svg>'


def paths(*ds):
    return "".join(f'<path d="{d}"/>' for d in ds)


def numbers(d):
    return [float(x) for x in re.findall(NUM, d)]


class AssembleTests(unittest.TestCase):
    """The Regular group of the thin run goes into the Ultralight slot, that of the heavy run into the Black slot."""

    def setUp(self):
        slot = {w: i for i, w in enumerate(MARGINS)}
        # each run, like SwiftDraw's output when it is given no variants, holds the same outline in every slot
        self.thin = template(
            {w: paths(f"M{230.5 + 200 * slot[w]},100 L{240.5 + 200 * slot[w]},100 L240,110 Z") for w in MARGINS}
        )
        self.regular = template(
            {
                w: paths(f"M{232 + 200 * slot[w]},100 L{242 + 200 * slot[w]},100 L242,110 Z", "M300,1 L301,2 Z")
                for w in MARGINS
            }
        )
        self.heavy = template(
            {w: paths(f"M{229 + 200 * slot[w]},100 L{244 + 200 * slot[w]},100 L244,110 Z") for w in MARGINS}
        )
        self.out = variants.assemble(self.thin, self.regular, self.heavy)

    def test_the_regular_group_and_the_guides_are_the_regular_runs(self):
        self.assertEqual(path_ds(self.out, "Regular-S"), path_ds(self.regular, "Regular-S"))
        self.assertEqual(
            parse_template(self.out)["regular"]["origin"], parse_template(self.regular)["regular"]["origin"]
        )

    def test_the_thin_run_lands_in_the_ultralight_slot_and_the_heavy_run_in_the_black_slot(self):
        # the thin run drew its outline at x = 430.5 in its Regular slot: 230.5 in the Ultralight slot, 200 to the left
        self.assertEqual(numbers(path_ds(self.out, "Ultralight-S")[0])[:2], [230.5, 100])
        # the heavy run drew its outline at x = 429 in its Regular slot, which is 629 in the Black slot
        self.assertEqual(numbers(path_ds(self.out, "Black-S")[0])[:2], [629, 100])

    def test_weights_may_have_a_different_number_of_paths(self):
        self.assertEqual([len(path_ds(self.out, w)) for w in MARGINS], [1, 2, 1])

    def test_a_template_without_a_group_is_refused_with_a_message(self):
        broken = self.thin.replace('id="Regular-S"', 'id="Other"')
        with self.assertRaisesRegex(ValueError, "Regular-S"):
            variants.assemble(broken, self.regular, self.heavy)


class RunWeightsTests(unittest.TestCase):
    """SwiftDraw's own combined run is used whenever it works; only when it refuses are the weights made one by one."""

    SRC = f'<svg {NS} viewBox="0 0 24 24" stroke-width="2"><path d="M2 2L20 20" stroke="black"/></svg>'

    def fake(self, refuse):
        calls = []

        def run(svg_text, ultra=0.5, black=1.5, insets="2.25,0,2.25,0"):
            calls.append((ultra, black, stroke_width(svg_text)))
            if ultra is not None and refuse:
                raise VariantsNotInterpolatable("Variants are not interpolatable: path 0 has 1/2/3 segments")
            w = stroke_width(svg_text)
            return template({name: paths(f"M{232 + 200 * i + w},100 L10,10 Z") for i, name in enumerate(MARGINS)})

        return calls, mock.patch.object(variants, "run_swiftdraw", side_effect=run)

    def test_when_swiftdraw_is_happy_one_run_is_all_it_takes(self):
        calls, patch = self.fake(refuse=False)
        with patch:
            variants.run_weights(self.SRC, 0.3, 1.9)
        self.assertEqual(calls, [(0.3, 1.9, 2.0)])

    def test_when_it_refuses_each_weight_is_run_on_an_svg_with_its_strokes_scaled(self):
        calls, patch = self.fake(refuse=True)
        with patch:
            out = variants.run_weights(self.SRC, 0.3, 1.9)
        self.assertEqual(calls[0], (0.3, 1.9, 2.0))
        asked = sorted(round(w, 3) for _, _, w in calls[1:])
        self.assertEqual(asked, [0.6, 2.0, 3.8])
        self.assertTrue(all(ultra is None and black is None for ultra, black, _ in calls[1:]))
        # the thin run (strokes 0.6) drew x = 432.6 in its Regular slot: 232.6 in the Ultralight slot;
        # the heavy run (strokes 3.8) drew 435.8, which is 635.8 in the Black slot
        self.assertAlmostEqual(numbers(path_ds(out, "Ultralight-S")[0])[0], 232.6, places=3)
        self.assertAlmostEqual(numbers(path_ds(out, "Black-S")[0])[0], 635.8, places=3)

    def test_other_errors_are_not_swallowed(self):
        with (
            mock.patch.object(variants, "run_swiftdraw", side_effect=variants.SwiftDrawError("boom")),
            self.assertRaisesRegex(variants.SwiftDrawError, "boom"),
        ):
            variants.run_weights(self.SRC, 0.3, 1.9)


@unittest.skipUnless(HAVE, "swiftdraw not installed")
class RealSwiftDrawTests(unittest.TestCase):
    def heart(self):
        with open(f"{ROOT}/tests/fixtures/lucide/heart.svg") as f:
            return f.read()

    def box(self, svg_text, weight):
        boxes = [bbox(d) for d in path_ds(svg_text, weight)]
        return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]

    def test_weights_made_one_by_one_are_where_and_as_big_as_swiftdraws_own(self):
        combined = run_swiftdraw(self.heart(), 0.3, 1.9)
        one_by_one = variants.run_per_weight(self.heart(), 0.3, 1.9)
        for weight in ("Ultralight-S", "Regular-S", "Black-S"):
            for ours, theirs in zip(self.box(one_by_one, weight), self.box(combined, weight), strict=True):
                self.assertAlmostEqual(ours, theirs, delta=0.01, msg=weight)

    def test_every_fixture_comes_out_with_three_weights_whatever_the_swiftdraw_version(self):
        files = sorted(glob.glob(f"{ROOT}/tests/fixtures/lucide/*.svg"))
        self.assertGreater(len(files), 5)
        for f in files:
            with open(f) as fh:
                out = variants.run_weights(fh.read(), 0.3, 1.9)
            for weight in ("Ultralight-S", "Regular-S", "Black-S"):
                self.assertTrue(path_ds(out, weight), f"{os.path.basename(f)}: {weight}")


if __name__ == "__main__":
    unittest.main()
