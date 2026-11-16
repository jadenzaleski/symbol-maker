import os
import re
import unittest
from unittest import mock

from symbolmaker.engine import convert
from symbolmaker.engine.convert import (
    MAX_SVG_BYTES,
    SwiftDrawError,
    check_input,
    find_swiftdraw,
    has_strokes,
    normalize_grid,
    run_swiftdraw,
    stroke_width,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE = find_swiftdraw() is not None
NS = 'xmlns="http://www.w3.org/2000/svg"'


def svg(attrs, body):
    return f"<svg {NS} {attrs}>{body}</svg>"


class InputTests(unittest.TestCase):
    def test_check_input_rejects_empty_nonsvg_and_oversize(self):
        self.assertIn("empty", check_input("   ").lower())
        self.assertIn("svg", check_input("hello world").lower())
        self.assertIn("large", check_input("<svg>" + "x" * MAX_SVG_BYTES + "</svg>").lower())
        self.assertIsNone(check_input(svg('viewBox="0 0 24 24"', "")))


class NormalizeTests(unittest.TestCase):
    def test_24_grid_is_unchanged(self):
        s = svg('width="24" height="24" viewBox="0 0 24 24"', '<circle cx="12" cy="12" r="10"/>')
        out, note = normalize_grid(s)
        self.assertEqual(out, s)
        self.assertIsNone(note)

    def test_16_grid_scales_by_1_5(self):
        out, note = normalize_grid(svg('viewBox="0 0 16 16"', '<circle cx="8" cy="8" r="4"/>'))
        self.assertIn('viewBox="0 0 24 24"', out)
        self.assertRegex(out, r"scale\(1\.5\)")
        self.assertIn("16", note)
        self.assertIn("circle", out)

    def test_no_viewbox_uses_width_height(self):
        out, note = normalize_grid(svg('width="32" height="32"', '<path d="M0 0L32 32"/>'))
        self.assertIn('viewBox="0 0 24 24"', out)
        self.assertRegex(out, r"scale\(0\.75\)")
        self.assertIsNotNone(note)

    def test_no_size_raises(self):
        with self.assertRaises(ValueError) as cm:
            normalize_grid(svg("", '<path d="M0 0L5 5"/>'))
        self.assertIn("size", str(cm.exception))

    def test_non_square_is_centered(self):
        out, _ = normalize_grid(svg('viewBox="0 0 24 12"', '<path d="M0 6H24"/>'))
        m = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", out)
        assert m is not None
        self.assertEqual((float(m.group(1)), float(m.group(2))), (0.0, 6.0))
        self.assertRegex(out, r"scale\(1(\.0)?\)")

    def test_viewbox_origin_offset_is_respected(self):
        out, _ = normalize_grid(svg('viewBox="10 10 12 12"', '<circle cx="16" cy="16" r="2"/>'))
        m = re.search(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", out)
        assert m is not None
        self.assertEqual((float(m.group(1)), float(m.group(2))), (-20.0, -20.0))  # 10*2 scale 2


class StrokeTests(unittest.TestCase):
    def test_has_strokes_detects_inherited_and_none(self):
        self.assertTrue(has_strokes(svg('stroke="currentColor"', '<path d="M0 0L5 5"/>')))
        self.assertTrue(has_strokes(svg("", '<g stroke="#000"><circle r="3"/></g>')))
        self.assertTrue(has_strokes(svg("", '<path style="stroke:#000;fill:none" d="M0 0L5 5"/>')))
        self.assertFalse(has_strokes(svg("", '<circle cx="5" cy="5" r="3" fill="black"/>')))
        self.assertFalse(has_strokes(svg('stroke="none"', '<circle r="3"/>')))
        self.assertFalse(has_strokes(svg('stroke="currentColor"', '<circle r="3" stroke="none"/>')))


class StrokeWidthTests(unittest.TestCase):
    def test_root_group_and_element_widths(self):
        self.assertEqual(stroke_width(svg('stroke="currentColor" stroke-width="2"', '<path d="M0 0L5 5"/>')), 2.0)
        self.assertEqual(stroke_width(svg('stroke="#000"', '<g stroke-width="3"><path d="M0 0L5 5"/></g>')), 3.0)
        self.assertEqual(
            stroke_width(svg('stroke="#000" stroke-width="2"', '<path stroke-width="1.5" d="M0 0L5 5"/>')), 1.5
        )
        self.assertEqual(stroke_width(svg("", '<path style="stroke:#000;stroke-width:2.5" d="M0 0L5 5"/>')), 2.5)

    def test_default_width_is_one_when_a_stroke_has_none_given(self):
        self.assertEqual(stroke_width(svg('stroke="#000"', '<path d="M0 0L5 5"/>')), 1.0)

    def test_most_common_width_wins(self):
        body = '<path d="M0 0L5 5"/><path d="M1 1L6 6"/><path stroke-width="4" d="M2 2L7 7"/>'
        self.assertEqual(stroke_width(svg('stroke="#000" stroke-width="2"', body)), 2.0)

    def test_none_without_strokes(self):
        self.assertIsNone(stroke_width(svg("", '<circle r="3" fill="black"/>')))
        self.assertIsNone(stroke_width(svg('stroke="none" stroke-width="2"', '<circle r="3"/>')))

    def test_width_follows_the_grid_rescale(self):
        out, _ = normalize_grid(
            svg('viewBox="0 0 16 16" stroke="#000" stroke-width="1.5"', '<circle cx="8" cy="8" r="6"/>')
        )
        self.assertAlmostEqual(stroke_width(out), 2.25, places=3)  # 1.5 x (24 / 16)


@unittest.skipUnless(HAVE, "swiftdraw not installed")
class SwiftDrawTests(unittest.TestCase):
    def test_run_swiftdraw_heart_returns_three_groups(self):
        with open(f"{ROOT}/tests/fixtures/lucide/heart.svg") as f:
            out = run_swiftdraw(f.read())
        for w in ("Ultralight-S", "Regular-S", "Black-S"):
            self.assertIn(f'id="{w}"', out)

    def test_stroke_multiplier_changes_black_master(self):
        with open(f"{ROOT}/tests/fixtures/lucide/heart.svg") as f:
            src = f.read()
        from symbolmaker.engine.layers import bbox, path_ds

        def width(svg):
            b = bbox(path_ds(svg, "Black-S")[0])
            return b[2] - b[0]

        self.assertGreater(width(run_swiftdraw(src, black=2.0)), width(run_swiftdraw(src, black=1.2)))

    def test_run_swiftdraw_failure_includes_message(self):
        with self.assertRaises(SwiftDrawError) as cm:
            run_swiftdraw('<svg xmlns="http://www.w3.org/2000/svg"><this is not valid')
        self.assertTrue(str(cm.exception).strip())


class MissingToolTests(unittest.TestCase):
    def test_missing_swiftdraw_raises_helpful_error(self):
        with (
            mock.patch.object(convert, "find_swiftdraw", return_value=None),
            self.assertRaises(SwiftDrawError) as cm,
        ):
            run_swiftdraw(svg('viewBox="0 0 24 24"', '<path d="M0 0L5 5"/>'))
        self.assertIn("brew install swiftdraw", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
