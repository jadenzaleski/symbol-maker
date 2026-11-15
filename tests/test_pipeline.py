import os
import re
import shutil
import unittest
from unittest import mock

from symbolmaker.engine import pipeline
from symbolmaker.engine.convert import SwiftDrawError, find_swiftdraw
from symbolmaker.engine.layers import LayerAssignment, bbox, path_ds, read_assignments
from symbolmaker.engine.pipeline import make_template
from symbolmaker.engine.weights import masters_match

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE = find_swiftdraw() is not None
NS = 'xmlns="http://www.w3.org/2000/svg"'


def lucide(name):
    with open(f'{ROOT}/tests/fixtures/lucide/{name}.svg') as f:
        return f.read()


def master_width(r, key):
    boxes = [bbox(d) for d in r.masters[key]]
    return max(b[2] for b in boxes) - min(b[0] for b in boxes)


@unittest.skipUnless(HAVE, 'swiftdraw not installed')
class PipelineTests(unittest.TestCase):
    def test_heart_is_variable_one_layer(self):
        r = make_template(lucide('heart'))
        self.assertEqual(r.status, 'variable')
        self.assertEqual(len(r.assignments), 1)
        self.assertEqual(r.assignments[0].level, 'primary')

    def test_house_two_layers_container_secondary(self):
        r = make_template(lucide('house'))
        self.assertEqual(sorted(a.level for a in r.assignments), ['primary', 'secondary'])
        self.assertEqual(read_assignments(r.template), r.assignments)

    def test_baby_variable_after_matching(self):
        r = make_template(lucide('baby'))
        self.assertEqual(r.status, 'variable')
        self.assertTrue(masters_match(r.template))

    def test_fill_only_svg_is_identical_masters_with_note(self):
        r = make_template(f'<svg {NS} viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="black"/></svg>')
        self.assertEqual(r.status, 'identical-masters')
        self.assertTrue(any('bolder' in n for n in r.notes))
        self.assertTrue(masters_match(r.template))

    def test_16_grid_svg_is_rescaled_and_converts(self):
        svg = (f'<svg {NS} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">'
               '<circle cx="8" cy="8" r="6"/></svg>')
        r = make_template(svg)
        self.assertEqual(r.status, 'variable')
        self.assertTrue(any('Rescaled' in n for n in r.notes))

    def test_unmatchable_falls_back_to_single_weight(self):
        # baby's raw masters have different verbs, so with matching unavailable only single-weight is valid
        with mock.patch.object(pipeline, 'match_weights', return_value=(None, 'x went wrong')):
            r = make_template(lucide('baby'))
        self.assertEqual(r.status, 'single-weight')
        note = ' '.join(r.notes)
        self.assertIn('single-weight', note)
        self.assertIn('bold text', note)
        self.assertNotIn('Error', note)                     # no Python error text on the page
        self.assertNotIn('x went wrong', note)
        self.assertTrue(masters_match(r.template))

    def test_regular_stroke_is_reported_in_grid_units(self):
        self.assertEqual(make_template(lucide('heart')).stroke, 2.0)
        svg = (f'<svg {NS} viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5">'
               '<circle cx="8" cy="8" r="6"/></svg>')
        self.assertAlmostEqual(make_template(svg).stroke, 2.25, places=3)

    def test_fill_only_svg_has_no_regular_stroke(self):
        r = make_template(f'<svg {NS} viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="black"/></svg>')
        self.assertIsNone(r.stroke)

    def test_a_dot_icon_is_variable_with_no_warning(self):
        for name in ('dot', 'skull'):
            r = make_template(lucide(name), 0.30, 1.90)
            self.assertEqual((name, r.status, r.notes), (name, 'variable', []))

    def test_black_is_lightened_only_as_far_as_needed_to_line_the_weights_up(self):
        # donut's tight curves close up at Apple's Black (1.9x), which makes SwiftDraw's outline a different shape
        r = make_template(lucide('donut'), 0.30, 1.90)
        self.assertEqual(r.status, 'variable')
        self.assertTrue(masters_match(r.template))
        note = ' '.join(r.notes)
        self.assertIn('Black', note)
        self.assertIn('1.9', note)                                 # says what was asked for
        self.assertNotIn('uneven', note)

    def test_an_icon_that_lines_up_at_the_requested_weights_gets_no_note(self):
        self.assertEqual(make_template(lucide('heart'), 0.30, 1.90).notes, [])

    def test_the_fallback_never_makes_black_heavier_than_requested(self):
        r = make_template(lucide('panda'), 0.30, 1.55)
        self.assertEqual(r.status, 'variable')
        self.assertNotIn('1.6', ' '.join(r.notes))

    def test_unalignable_icon_stays_variable_but_warns_and_is_a_problem(self):
        # the weights have the same segments but their nodes cannot be lined up by the matcher
        with mock.patch.object(pipeline, 'match_weights', return_value=(None, 'x')), \
                mock.patch.object(pipeline, 'signature_ok', return_value=True):
            r = make_template(lucide('heart'))
        self.assertEqual(r.status, 'variable')
        self.assertTrue(any('uneven' in n for n in r.notes), r.notes)
        self.assertNotIn('node-for-node', ' '.join(r.notes))
        self.assertTrue(r.problem)

    def test_single_weight_is_a_problem(self):
        with mock.patch.object(pipeline, 'match_weights', return_value=(None, 'x went wrong')):
            r = make_template(lucide('baby'))
        self.assertEqual(r.status, 'single-weight')
        self.assertTrue(r.problem)

    def test_a_clean_icon_and_a_lightened_black_are_not_problems(self):
        self.assertFalse(make_template(lucide('heart'), 0.30, 1.90).problem)
        r = make_template(lucide('donut'), 0.30, 1.90)
        self.assertTrue(r.notes)
        self.assertFalse(r.problem)

    def test_a_fill_only_icon_is_a_problem_because_it_will_not_follow_weight(self):
        r = make_template(f'<svg {NS} viewBox="0 0 24 24"><circle cx="12" cy="12" r="8" fill="black"/></svg>')
        self.assertEqual(r.status, 'identical-masters')
        self.assertTrue(r.problem)

    def test_aligned_icon_has_no_unevenness_warning(self):
        r = make_template(lucide('heart'))
        self.assertFalse(any('uneven' in n for n in r.notes), r.notes)

    def test_stroke_multipliers_change_master_widths(self):
        thin = make_template(lucide('circle'), ultra=0.35)
        base = make_template(lucide('circle'), ultra=0.5)
        self.assertLess(master_width(thin, 'ultralight'), master_width(base, 'ultralight'))
        heavy = make_template(lucide('circle'), black=1.8)
        self.assertGreater(master_width(heavy, 'black'), master_width(base, 'black'))

    def test_preview_masters_centered_at_origin(self):
        r = make_template(lucide('house'))
        for key in ('ultralight', 'regular', 'black'):
            boxes = [bbox(d) for d in r.masters[key]]
            cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
            cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
            self.assertAlmostEqual(cx, 0, delta=0.05)
            self.assertAlmostEqual(cy, 0, delta=0.05)
            x, y, w, h = r.box[key]
            self.assertAlmostEqual(x + w / 2, 0, delta=0.05)


class InputErrorTests(unittest.TestCase):
    def test_bad_input_raises_value_error(self):
        for bad in ('', '   ', 'hello', '<svg>' + 'x' * 300000 + '</svg>'):
            with self.assertRaises(ValueError):
                make_template(bad)

    def test_missing_swiftdraw_is_reported(self):
        with mock.patch('symbolmaker.engine.convert.find_swiftdraw', return_value=None):
            with self.assertRaises(SwiftDrawError):
                make_template(f'<svg {NS} viewBox="0 0 24 24"><path d="M2 2L20 20" stroke="black"/></svg>')


if __name__ == '__main__':
    unittest.main()
