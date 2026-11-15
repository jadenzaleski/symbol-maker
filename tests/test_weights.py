import os
import re
import shutil
import subprocess
import tempfile
import unittest

from symbolmaker.engine.layers import bbox, path_ds
from symbolmaker.engine.weights import masters_match, match_weights, to_single_weight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INS = '2.25,0,2.25,0'
HAVE = shutil.which('swiftdraw') is not None
WEIGHTS = ('Ultralight-S', 'Regular-S', 'Black-S')


def raw_template(name):
    """Template exactly as the pipeline would get it from SwiftDraw (defaults 0.5 / 1.5)."""
    out = tempfile.mktemp(suffix='.svg')
    subprocess.run(['swiftdraw', f'{ROOT}/tests/fixtures/lucide/{name}.svg', '--format', 'sfsymbol', '--insets', INS,
                    '--ultralight-stroke-width', '0.5', '--ultralight-insets', INS,
                    '--black-stroke-width', '1.5', '--black-insets', INS, '--output', out],
                   check=True, capture_output=True)
    with open(out) as f:
        return f.read()


def norm_ds(svg, weight):
    """Path data of one weight, translated so the group's bbox center is the origin (the groups sit side by side)."""
    ds = path_ds(svg, weight)
    boxes = [bbox(d) for d in ds]
    cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
    cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
    out = []
    for d in ds:
        nums = [float(x) for x in re.findall(r'-?\d*\.?\d+(?:e-?\d+)?', d)]
        out.append([round(v - (cx if i % 2 == 0 else cy), 2) for i, v in enumerate(nums)])
    return out


def assert_close(tc, a, b, msg='', delta=0.02):
    tc.assertEqual(len(a), len(b), msg)
    for pa, pb in zip(a, b):
        tc.assertEqual(len(pa), len(pb), msg)
        for x, y in zip(pa, pb):
            tc.assertAlmostEqual(x, y, delta=delta, msg=msg)


def tiny_template(u, r, b):
    def g(w, d):
        return f'<g id="{w}" transform="translate(0,0)"><path d="{d}" /></g>'
    return ('<svg><g id="Symbols">' + g('Ultralight-S', u) + g('Regular-S', r) + g('Black-S', b) + '</g></svg>')


@unittest.skipUnless(HAVE, 'swiftdraw not installed')
class WeightEngineTests(unittest.TestCase):
    def test_baby_raw_does_not_match_then_matches(self):
        raw = raw_template('baby')
        self.assertFalse(masters_match(raw))
        fixed, err = match_weights(raw)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))

    def test_matched_shapes_unchanged(self):
        raw = raw_template('baby')
        fixed, _ = match_weights(raw)
        for w in WEIGHTS:
            a = [bbox(d) for d in path_ds(raw, w)]
            b = [bbox(d) for d in path_ds(fixed, w)]
            for x, y in zip(a, b):
                for p, q in zip(x, y):
                    self.assertAlmostEqual(p, q, delta=0.05, msg=w)

    def test_reproduces_the_exported_baby(self):
        fixed, _ = match_weights(raw_template('baby'))
        with open(f'{ROOT}/tests/fixtures/export/lucide.baby.svg') as f:
            exported = f.read()
        for w in WEIGHTS:
            assert_close(self, norm_ds(fixed, w), norm_ds(exported, w), w)

    def test_single_weight_masters_identical_and_match(self):
        single = to_single_weight(raw_template('baby'))
        self.assertTrue(masters_match(single))
        assert_close(self, norm_ds(single, 'Ultralight-S'), norm_ds(single, 'Regular-S'))
        assert_close(self, norm_ds(single, 'Black-S'), norm_ds(single, 'Regular-S'))

    def test_single_weight_keeps_regular_position(self):
        raw = raw_template('heart')
        single = to_single_weight(raw)
        self.assertEqual(path_ds(single, 'Regular-S'), path_ds(raw, 'Regular-S'))


def node_offsets(svg):
    """Largest distance between corresponding nodes of Regular and each other master (groups centered).
    Corresponding nodes of adjacent masters differ by about a stroke edge (<= ~2 units; Ultralight<->Black ~4)."""
    import math
    from symbolmaker.engine.weights import group_center, node_pos, parse, shift
    ds = {w: path_ds(svg, w) for w in WEIGHTS}
    ctr = {w: group_center(ds[w]) for w in WEIGHTS}
    worst = 0.0
    for pi in range(len(ds['Regular-S'])):
        cs = {w: shift(parse(ds[w][pi]), -ctr[w][0], -ctr[w][1]) for w in WEIGHTS}
        for ci in range(len(cs['Regular-S'])):
            r = node_pos(cs['Regular-S'][ci])
            for w in ('Ultralight-S', 'Black-S'):
                o = node_pos(cs[w][ci])
                if len(o) != len(r):
                    return float('inf')
                worst = max(worst, max(math.dist(x, y) for x, y in zip(r, o)))
    return worst


@unittest.skipUnless(HAVE, 'swiftdraw not installed')
class NodeCorrespondenceTests(unittest.TestCase):
    def test_heart_raw_masters_do_not_really_match(self):
        # same verb sequence, but zero-length segments sit at different places: nodes do not correspond
        self.assertFalse(masters_match(raw_template('heart')))

    def test_heart_nodes_correspond_after_matching(self):
        raw = raw_template('heart')
        self.assertGreater(node_offsets(raw), 20.0)
        fixed, err = match_weights(raw)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))
        self.assertLess(node_offsets(fixed), 6.0)


class ReasonTests(unittest.TestCase):
    def test_contour_count_mismatch_reports_reason(self):
        square = 'M0,0 L10,0 L10,10 L0,10 Z'
        two = square + ' M3,3 L6,3 L6,6 L3,6 Z'
        fixed, err = match_weights(tiny_template(two, square, square))
        self.assertIsNone(fixed)
        self.assertIn('contour', err)

    def test_already_matching_template_is_returned(self):
        square = 'M0,0 L10,0 L10,10 L0,10 Z'
        svg = tiny_template(square, square, square)
        self.assertTrue(masters_match(svg))
        fixed, err = match_weights(svg)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))


if __name__ == '__main__':
    unittest.main()
