import os
import re
import unittest
from unittest import mock

from symbolmaker.engine import convert
from symbolmaker.engine.convert import (
    MAX_SVG_BYTES,
    SwiftDrawError,
    VariantsNotInterpolatable,
    check_input,
    find_swiftdraw,
    has_strokes,
    normalize_grid,
    run_swiftdraw,
    scale_strokes,
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


class ScaleStrokesTests(unittest.TestCase):
    """The stroke widths of an SVG multiplied, which is how a weight is made when SwiftDraw is not asked to make it."""

    def scaled(self, body, factor, attrs='viewBox="0 0 24 24"'):
        return scale_strokes(svg(attrs, body), factor)

    def test_the_width_set_on_the_root_is_scaled(self):
        out = self.scaled('<path d="M2 2L20 20" stroke="black"/>', 1.9, 'viewBox="0 0 24 24" stroke-width="2"')
        self.assertAlmostEqual(stroke_width(out), 3.8)

    def test_a_width_on_an_element_a_group_and_in_a_style_are_all_scaled(self):
        cases = {
            "element": ('<path d="M2 2L9 9" stroke="black" stroke-width="2"/>', 1),
            "group": ('<g stroke-width="4"><path d="M3 3L8 9" stroke="black"/></g>', 2),
            "style": ('<path d="M4 4L7 9" stroke="black" style="stroke-width: 6; stroke-linecap: round"/>', 3),
        }
        for name, (body, expected) in cases.items():
            with self.subTest(name):
                self.assertAlmostEqual(stroke_width(self.scaled(body, 0.5)), expected)

    def test_an_svg_that_never_says_how_wide_its_strokes_are_gets_the_default_scaled(self):
        out = self.scaled('<path d="M2 2L20 20" stroke="black"/>', 1.9)
        self.assertAlmostEqual(stroke_width(out), 1.9)

    def test_a_scale_transform_still_multiplies_the_scaled_width(self):
        out = self.scaled('<g transform="scale(2)"><path d="M1 1L9 9" stroke="black" stroke-width="1"/></g>', 0.3)
        self.assertAlmostEqual(stroke_width(out), 0.6)

    def test_everything_else_in_the_svg_is_kept(self):
        body = (
            '<path d="M2 2L20 20" stroke="black" stroke-linecap="round"/>'
            '<circle cx="5" cy="5" r="2" fill="none" stroke="red"/>'
        )
        out = self.scaled(body, 2.0)
        for part in ('d="M2 2L20 20"', 'stroke-linecap="round"', 'cx="5"', 'fill="none"', 'viewBox="0 0 24 24"'):
            self.assertIn(part, out)

    def test_a_width_it_cannot_read_or_a_style_sheet_is_refused_not_ignored(self):
        with self.assertRaises(ValueError):
            self.scaled('<path d="M0 0L5 5" stroke="black" stroke-width="var(--w)"/>', 2.0)
        with self.assertRaises(ValueError):
            self.scaled('<style>path { stroke-width: 3 }</style><path d="M0 0L5 5" stroke="black"/>', 2.0)


class VariantsErrorTests(unittest.TestCase):
    """SwiftDraw 0.30 refuses to write a template whose three weights differ in structure: that gets its own error."""

    def failing(self, stderr):
        done = mock.Mock(returncode=70, stdout="", stderr=stderr)
        return mock.patch.object(convert.subprocess, "run", return_value=done)

    def test_the_refusal_is_told_apart_from_other_failures(self):
        text = "Failure: Variants are not interpolatable: path 2 has 36/45/45 segments (ultralight/regular/black)."
        with (
            mock.patch.object(convert, "find_swiftdraw", return_value="/x/swiftdraw"),
            self.failing(text),
            self.assertRaises(VariantsNotInterpolatable) as cm,
        ):
            run_swiftdraw(svg('viewBox="0 0 24 24"', '<path d="M0 0L5 5"/>'))
        self.assertIsInstance(cm.exception, SwiftDrawError)
        self.assertIn("36/45/45", str(cm.exception))

    def test_any_other_failure_is_an_ordinary_swiftdraw_error(self):
        with (
            mock.patch.object(convert, "find_swiftdraw", return_value="/x/swiftdraw"),
            self.failing("Failure: something else"),
            self.assertRaises(SwiftDrawError) as cm,
        ):
            run_swiftdraw(svg('viewBox="0 0 24 24"', '<path d="M0 0L5 5"/>'))
        self.assertNotIsInstance(cm.exception, VariantsNotInterpolatable)

    def test_no_variant_options_are_passed_when_none_are_asked_for(self):
        ok = mock.Mock(returncode=0, stdout="", stderr="")
        seen = {}

        def fake(cmd, **kw):
            seen["cmd"] = cmd
            with open(cmd[cmd.index("--output") + 1], "w") as f:
                f.write("<svg/>")
            return ok

        with (
            mock.patch.object(convert, "find_swiftdraw", return_value="/x/swiftdraw"),
            mock.patch.object(convert.subprocess, "run", side_effect=fake),
        ):
            run_swiftdraw(svg('viewBox="0 0 24 24"', '<path d="M0 0L5 5"/>'), None, None)
        self.assertNotIn("--ultralight-stroke-width", seen["cmd"])
        self.assertNotIn("--black-stroke-width", seen["cmd"])
        self.assertIn("--insets", seen["cmd"])


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
