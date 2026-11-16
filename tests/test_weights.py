import math
import os
import re
import shutil
import unittest
from unittest import mock

from symbolmaker.engine import weights
from symbolmaker.engine.convert import run_swiftdraw
from symbolmaker.engine.layers import bbox, path_ds
from symbolmaker.engine.weights import drop_collapsing_holes, masters_match, match_weights, to_single_weight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INS = "2.25,0,2.25,0"
HAVE = shutil.which("swiftdraw") is not None
WEIGHTS = ("Ultralight-S", "Regular-S", "Black-S")


def raw_template(name):
    """Template as the pipeline gets it from SwiftDraw (defaults 0.5 / 1.5): the weights not yet lined up."""
    with open(f"{ROOT}/tests/fixtures/lucide/{name}.svg") as f:
        return run_swiftdraw(f.read(), 0.5, 1.5)


def norm_ds(svg, weight):
    """Path data of one weight, translated so the group's bbox center is the origin (the groups sit side by side)."""
    ds = path_ds(svg, weight)
    boxes = [bbox(d) for d in ds]
    cx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2
    cy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2
    out = []
    for d in ds:
        nums = [float(x) for x in re.findall(r"-?\d*\.?\d+(?:e-?\d+)?", d)]
        out.append([round(v - (cx if i % 2 == 0 else cy), 2) for i, v in enumerate(nums)])
    return out


def assert_close(tc, a, b, msg="", delta=0.02):
    tc.assertEqual(len(a), len(b), msg)
    for pa, pb in zip(a, b, strict=True):
        tc.assertEqual(len(pa), len(pb), msg)
        for x, y in zip(pa, pb, strict=True):
            tc.assertAlmostEqual(x, y, delta=delta, msg=msg)


def tiny_template(u, r, b):
    def g(w, d):
        return f'<g id="{w}" transform="translate(0,0)"><path d="{d}" /></g>'

    return '<svg><g id="Symbols">' + g("Ultralight-S", u) + g("Regular-S", r) + g("Black-S", b) + "</g></svg>"


@unittest.skipUnless(HAVE, "swiftdraw not installed")
class WeightEngineTests(unittest.TestCase):
    def test_baby_raw_does_not_match_then_matches(self):
        raw = raw_template("baby")
        self.assertFalse(masters_match(raw))
        fixed, err = match_weights(raw)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))

    def test_matched_shapes_unchanged(self):
        raw = raw_template("baby")
        fixed, _ = match_weights(raw)
        for w in WEIGHTS:
            a = [bbox(d) for d in path_ds(raw, w)]
            b = [bbox(d) for d in path_ds(fixed, w)]
            for x, y in zip(a, b, strict=True):
                for p, q in zip(x, y, strict=True):
                    self.assertAlmostEqual(p, q, delta=0.05, msg=w)

    def test_reproduces_the_exported_baby(self):
        fixed, _ = match_weights(raw_template("baby"))
        with open(f"{ROOT}/tests/fixtures/export/lucide.baby.svg") as f:
            exported = f.read()
        for w in WEIGHTS:
            assert_close(self, norm_ds(fixed, w), norm_ds(exported, w), w)

    def test_single_weight_masters_identical_and_match(self):
        single = to_single_weight(raw_template("baby"))
        self.assertTrue(masters_match(single))
        assert_close(self, norm_ds(single, "Ultralight-S"), norm_ds(single, "Regular-S"))
        assert_close(self, norm_ds(single, "Black-S"), norm_ds(single, "Regular-S"))

    def test_single_weight_keeps_regular_position(self):
        raw = raw_template("heart")
        single = to_single_weight(raw)
        self.assertEqual(path_ds(single, "Regular-S"), path_ds(raw, "Regular-S"))


def node_offsets(svg):
    """Largest distance between corresponding nodes of Regular and each other master (groups centered).
    Corresponding nodes of adjacent masters differ by about a stroke edge (<= ~2 units; Ultralight<->Black ~4)."""
    import math

    from symbolmaker.engine.weights import group_center, node_pos, parse, shift

    ds = {w: path_ds(svg, w) for w in WEIGHTS}
    ctr = {w: group_center(ds[w]) for w in WEIGHTS}
    worst = 0.0
    for pi in range(len(ds["Regular-S"])):
        cs = {w: shift(parse(ds[w][pi]), -ctr[w][0], -ctr[w][1]) for w in WEIGHTS}
        for ci in range(len(cs["Regular-S"])):
            r = node_pos(cs["Regular-S"][ci])
            for w in ("Ultralight-S", "Black-S"):
                o = node_pos(cs[w][ci])
                if len(o) != len(r):
                    return float("inf")
                worst = max(worst, max(math.dist(x, y) for x, y in zip(r, o, strict=True)))
    return worst


@unittest.skipUnless(HAVE, "swiftdraw not installed")
class NodeCorrespondenceTests(unittest.TestCase):
    def test_heart_raw_masters_do_not_really_match(self):
        # same verb sequence, but zero-length segments sit at different places: nodes do not correspond
        self.assertFalse(masters_match(raw_template("heart")))

    def test_heart_nodes_correspond_after_matching(self):
        raw = raw_template("heart")
        self.assertGreater(node_offsets(raw), 20.0)
        fixed, err = match_weights(raw)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))
        self.assertLess(node_offsets(fixed), 6.0)


class ReasonTests(unittest.TestCase):
    def test_contour_count_mismatch_reports_reason(self):
        square = "M0,0 L10,0 L10,10 L0,10 Z"
        two = square + " M3,3 L6,3 L6,6 L3,6 Z"
        fixed, err = match_weights(tiny_template(two, square, square))
        self.assertIsNone(fixed)
        self.assertIn("contour", err)

    def test_already_matching_template_is_returned(self):
        square = "M0,0 L10,0 L10,10 L0,10 Z"
        svg = tiny_template(square, square, square)
        self.assertTrue(masters_match(svg))
        fixed, err = match_weights(svg)
        self.assertIsNone(err)
        self.assertTrue(masters_match(fixed))


K = 0.5523


def circle_d(cx, cy, r, cw=True):
    """A circle as four cubics (all one point when r == 0). cw=False runs the other way round."""
    sg = 1 if cw else -1

    def pt(k):
        return (cx + r * math.cos(sg * k * math.pi / 2), cy + r * math.sin(sg * k * math.pi / 2))

    def tn(k):
        return (-sg * math.sin(sg * k * math.pi / 2), sg * math.cos(sg * k * math.pi / 2))

    def f(v):
        return f"{v:.4f}"

    d = "M" + ",".join(map(f, pt(0)))
    for k in range(4):
        p0, p1, t0, t1 = pt(k), pt(k + 1), tn(k), tn(k + 1)
        c1 = (p0[0] + K * r * t0[0], p0[1] + K * r * t0[1])
        c2 = (p1[0] - K * r * t1[0], p1[1] - K * r * t1[1])
        d += " C" + " ".join(",".join(map(f, q)) for q in (c1, c2, p1))
    return d + " Z"


def ring(cx, cy, ro, ri, hole=True):
    """Outer circle plus an inner one: a hole (opposite way round) or, with hole=False, a same-direction inner circle
    (what a negative inner radius turns into)."""
    return circle_d(cx, cy, ro) + " " + circle_d(cx, cy, ri, cw=not hole)


def template(*rings_by_weight):
    """rings_by_weight[w] = list of path d strings for weight w."""
    groups = []
    for name, ds in zip(("Ultralight-S", "Regular-S", "Black-S"), rings_by_weight, strict=True):
        groups.append(f'<g id="{name}">' + "".join(f'<path d="{d}"/>' for d in ds) + "</g>")
    return "<svg>" + "".join(groups) + "</svg>"


def contour_counts(svg):
    return [
        [d.count("M") for d in re.findall(r'<path d="([^"]+)"', g)]
        for g in re.findall(r'<g id="[^"]+">(.*?)</g>', svg, re.S)
    ]


class CollapsingHoleTests(unittest.TestCase):
    """A stroked dot: its inner ring is a real hole at Ultralight, a single point at Regular and turned inside out at
    Black, so the weights cannot be interpolated. The hole is dropped from every weight (the dot is solid)."""

    def dot(self):
        return template([ring(10, 10, 1.3, 0.7)], [ring(10, 10, 2.0, 0.0)], [ring(10, 10, 2.9, 0.9, hole=False)])

    def test_the_hole_is_removed_from_all_three_weights(self):
        out = drop_collapsing_holes(self.dot())
        self.assertEqual(contour_counts(out), [[1], [1], [1]])
        self.assertTrue(masters_match(out))

    def test_a_healthy_ring_is_left_alone(self):
        svg = template([ring(10, 10, 6, 5)], [ring(10, 10, 7, 5)], [ring(10, 10, 8, 4)])
        self.assertEqual(drop_collapsing_holes(svg), svg)

    def test_only_the_collapsing_path_changes(self):
        svg = template(
            [ring(10, 10, 1.3, 0.7), ring(30, 10, 6, 5)],
            [ring(10, 10, 2.0, 0.0), ring(30, 10, 7, 5)],
            [ring(10, 10, 2.9, 0.9, hole=False), ring(30, 10, 8, 4)],
        )
        out = drop_collapsing_holes(svg)
        self.assertEqual(contour_counts(out), [[1, 2], [1, 2], [1, 2]])

    def test_a_template_with_one_contour_per_path_is_unchanged(self):
        svg = template([circle_d(10, 10, 2)], [circle_d(10, 10, 3)], [circle_d(10, 10, 4)])
        self.assertEqual(drop_collapsing_holes(svg), svg)

    def test_never_removes_every_contour_of_a_path(self):
        svg = template([circle_d(10, 10, 0)], [circle_d(10, 10, 0)], [circle_d(10, 10, 0)])
        self.assertEqual(contour_counts(drop_collapsing_holes(svg)), [[1], [1], [1]])

    @unittest.skipUnless(HAVE, "swiftdraw not installed")
    def test_the_real_dot_and_skull_become_valid_variable_symbols(self):
        from symbolmaker.engine.pipeline import make_template

        for name in ("dot", "skull"):
            with open(f"{ROOT}/tests/fixtures/lucide/{name}.svg") as f:
                r = make_template(f.read(), 0.30, 1.90)
            self.assertEqual((name, r.status, r.notes), (name, "variable", []))
            self.assertTrue(masters_match(r.template))


class MatchEffortTests(unittest.TestCase):
    """match_weights tries several alignment tolerances; it must not burn time on ones that cannot help."""

    def patched(self, process_effect, sig=True):
        return (
            mock.patch.object(weights, "masters_match", return_value=False),
            mock.patch.object(weights, "process", side_effect=process_effect),
            mock.patch.object(weights, "signature_ok", return_value=sig),
        )

    def run_match(self, process_effect, sig=True, **kw):
        p1, p2, p3 = self.patched(process_effect, sig)
        with p1, p2 as proc, p3:
            result = match_weights("<svg/>", **kw)
        return result, proc.call_count

    def test_gives_up_after_three_identical_failures(self):
        (svg, why), calls = self.run_match(ValueError("node counts [41, 43, 44] vs clusters 45"))
        self.assertIsNone(svg)
        self.assertEqual(calls, 3)
        self.assertIn("node counts", why)

    def test_keeps_trying_while_the_failures_differ(self):
        effects = [ValueError("a"), ValueError("b"), ValueError("c"), ValueError("d"), ("<svg ok/>", None)]
        (svg, why), calls = self.run_match(effects)
        self.assertEqual((svg, why, calls), ("<svg ok/>", None, 5))

    def test_the_tolerances_to_try_can_be_limited(self):
        (svg, _), calls = self.run_match(ValueError("x"), tries=(10,))
        self.assertIsNone(svg)
        self.assertEqual(calls, 1)

    def test_a_result_whose_verbs_differ_counts_as_a_failure_and_the_next_tolerance_is_tried(self):
        p1, p2, _p3 = self.patched([("<svg bad/>", None), ("<svg ok/>", None)])
        sig = mock.patch.object(weights, "signature_ok", side_effect=[False, True])
        with p1, p2 as proc, sig:
            svg, _why = match_weights("<svg/>")
        self.assertEqual((svg, proc.call_count), ("<svg ok/>", 2))


if __name__ == "__main__":
    unittest.main()
