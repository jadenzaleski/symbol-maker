import math
import os
import re
import shutil
import unittest
from unittest import mock

from symbolmaker.engine import weights
from symbolmaker.engine.layers import bbox, path_ds
from symbolmaker.engine.variants import run_weights
from symbolmaker.engine.weights import drop_collapsing_holes, masters_match, match_weights, to_single_weight

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INS = "2.25,0,2.25,0"
HAVE = shutil.which("swiftdraw") is not None
WEIGHTS = ("Ultralight-S", "Regular-S", "Black-S")


def raw_template(name):
    """Template as the pipeline gets it from SwiftDraw (defaults 0.5 / 1.5): the weights not yet lined up."""
    with open(f"{ROOT}/tests/fixtures/lucide/{name}.svg") as f:
        return run_weights(f.read(), 0.5, 1.5)


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


# Lucide's "contrast" icon (a ring and a D) as SwiftDraw writes the D at each weight. A path is its outer edge and
# then the edge of its hole, which SwiftDraw draws with a small spur at each corner of the D; at Black the spurs are
# large enough that the hole looks turned inside out, although it is a good D-shaped hole at every weight.
CONTRAST_D = [
    "M265,133.615 C277.49,133.615 287.615,123.49 287.615,111 C287.615,98.51 277.49,88.385 265,88.385 "
    "C264.405,88.385 263.923,88.867 263.923,89.462 L263.923,132.538 C263.923,133.133 264.405,133.615 265,133.615 Z "
    "M265,131.462 L266.077,132.538 L266.077,89.462 L265,90.538 C276.301,90.538 285.462,99.699 285.462,111 "
    "C285.462,122.301 276.301,131.462 265,131.462 Z",
    "M465,136.128 C478.878,136.128 490.128,124.878 490.128,111 C490.128,97.122 478.878,85.872 465,85.872 "
    "C463.017,85.872 461.41,87.479 461.41,89.462 L461.41,132.538 C461.41,134.521 463.017,136.128 465,136.128 Z "
    "M465,128.949 L468.59,132.538 L468.59,89.462 L465,93.051 C474.913,93.051 482.949,101.087 482.949,111 "
    "C482.949,120.913 474.913,128.949 465,128.949 Z",
    "M665,139.359 C680.662,139.359 693.359,126.662 693.359,111 C693.359,95.338 680.662,82.641 665,82.641 "
    "C661.233,82.641 658.18,85.695 658.18,89.462 L658.18,132.538 C658.18,136.305 661.233,139.359 665,139.359 Z "
    "M665,125.718 L671.821,132.538 L671.821,89.462 L665,96.282 C673.129,96.282 679.718,102.872 679.718,111 "
    "C679.718,119.129 673.129,125.718 665,125.718 Z",
]


class MendedHoleTests(unittest.TestCase):
    """A hole whose edge SwiftDraw drew with loops at the corners is not a collapsing hole: with the loops cut off it is
    a sound hole at every weight, and the symbol keeps it."""

    def d_template(self):
        return template([CONTRAST_D[0]], [CONTRAST_D[1]], [CONTRAST_D[2]])

    def test_the_hole_of_the_d_is_kept_in_all_three_weights(self):
        out = drop_collapsing_holes(self.d_template())
        self.assertEqual(contour_counts(out), [[2], [2], [2]])

    def test_the_kept_hole_is_the_hole_the_icon_has(self):
        from symbolmaker.engine.loops import signed_area
        from symbolmaker.engine.weights import parse

        out = drop_collapsing_holes(self.d_template())
        areas = []
        for g in re.findall(r'<g id="[^"]+">(.*?)</g>', out, re.S):
            (d,) = re.findall(r'<path d="([^"]+)"', g)
            areas.append(signed_area(parse(d, 0)[1]))
        # the hole is the part of the inside of the D beyond its straight side: 1 / 4 as big again at Ultralight as at
        # Regular, and smaller again at Black; and no weight has it turned inside out
        self.assertTrue(all(a > 0 for a in areas), areas)
        self.assertGreater(areas[0], areas[1])
        self.assertGreater(areas[1], areas[2])

    def test_the_weights_with_the_hole_still_line_up(self):
        matched, why = match_weights(drop_collapsing_holes(self.d_template()))
        self.assertIsNotNone(matched, why)
        self.assertTrue(masters_match(matched))
        self.assertEqual(contour_counts(matched), [[2], [2], [2]])

    def test_mending_can_be_turned_off_to_get_the_old_result(self):
        out = drop_collapsing_holes(self.d_template(), mend=False)
        self.assertEqual(contour_counts(out), [[1], [1], [1]], "the hole is dropped from every weight")

    @unittest.skipUnless(HAVE, "swiftdraw not installed")
    def test_an_icon_that_cannot_be_lined_up_with_its_hole_is_converted_the_old_way_not_given_up_on(self):
        from symbolmaker.engine.pipeline import make_template

        # With its holes kept, the weights of this icon do not line up at any Black weight; with them dropped they do.
        with open(f"{ROOT}/tests/fixtures/iconoir/media-video-folder.svg") as f:
            r = make_template(f.read(), 0.30, 1.90)
        self.assertEqual(r.status, "variable", r.notes)
        self.assertTrue(masters_match(r.template))

    def test_a_dot_whose_hole_really_closes_is_still_made_solid(self):
        dot = template([ring(10, 10, 1.3, 0.7)], [ring(10, 10, 2.0, 0.0)], [ring(10, 10, 2.9, 0.9, hole=False)])
        self.assertEqual(contour_counts(drop_collapsing_holes(dot)), [[1], [1], [1]])

    @unittest.skipUnless(HAVE, "swiftdraw not installed")
    def test_the_real_contrast_icon_keeps_the_hole_of_its_d(self):
        from symbolmaker.engine.pipeline import make_template

        with open(f"{ROOT}/tests/fixtures/lucide/contrast.svg") as f:
            r = make_template(f.read(), 0.30, 1.90)
        self.assertEqual((r.status, r.notes), ("variable", []))
        self.assertTrue(masters_match(r.template))
        counts = [[d.count("M") for d in path_ds(r.template, w)] for w in WEIGHTS]
        self.assertEqual(counts, [[2, 2]] * 3, "the ring and the D: each is an edge and a hole")


class EqualizeEffortTests(unittest.TestCase):
    """Lining up a contour must not redo the same arc-length sums for every node it adds: for a 150-segment icon that
    took minutes (SwiftDraw 0.30 hands over the weights unrepaired, so there is more to add than there used to be)."""

    def circle(self):
        ((start, segs),) = weights.parse(circle_d(0, 0, 10))
        return start, segs

    def test_a_point_asked_for_with_the_fractions_already_known_is_the_same_point(self):
        contour = self.circle()
        fracs = weights.nodes_fracs(*contour)[0]
        for frac in (0.0, 0.1, 0.37, 0.5, 0.99, 1.0):
            self.assertEqual(weights.point_at(contour, frac, fracs), weights.point_at(contour, frac))

    def test_arc_lengths_are_summed_once_per_weight_not_once_per_candidate_position(self):
        start, segs = self.circle()
        eight = weights.insert_nodes(
            start, segs, [0.125, 0.375, 0.625, 0.875]
        )  # Regular has four nodes the others lack
        with mock.patch.object(weights, "nodes_fracs", wraps=weights.nodes_fracs) as spy:
            lined_up = weights.equalize([(start, segs), (start, eight), (start, segs)])
        self.assertEqual(len({len(r) for r in lined_up}), 1, "the three weights now have the same structure")
        self.assertLess(spy.call_count, 20, f"nodes_fracs ran {spy.call_count} times")


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
