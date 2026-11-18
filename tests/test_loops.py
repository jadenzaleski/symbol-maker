"""SwiftDraw draws the inner edge of a stroked closed shape with small loops at its sharp corners (the edge crosses
itself and runs backwards for a moment). Cutting those loops off gives the hole the shape it really has."""

import math
import unittest

from symbolmaker.engine.loops import intersections, remove_loops, signed_area, split_loops
from symbolmaker.engine.weights import cub, parse

# The inner edge of Lucide's "contrast" D (the half disc of `M12 18a6 6 0 0 0 0-12v12z`) at the Regular weight, as
# SwiftDraw writes it: the straight side (x = 468.59) overshoots the arc at both ends and two spurs bring it back.
D_REGULAR = (
    "M465,128.949 L468.59,132.538 L468.59,89.462 L465,93.051 "
    "C474.913,93.051 482.949,101.087 482.949,111 C482.949,120.913 474.913,128.949 465,128.949 Z"
)


def contour(d):
    return parse(d, 0)[0]


def disc_segment_area(r, d):
    """Area of the part of a disc of radius r on the far side of a chord d from the center."""
    return r * r * math.acos(d / r) - d * math.sqrt(r * r - d * d)


# The hole of Lucide's "ad" at Regular: a rounded box (7.18 wide, 14.36 high, round on the right) whose two left corners
# have small spurs. Its curves meet at nodes all round, which must not be taken for crossings.
AD_HOLE = (
    "M475.769,119.974 L475.769,102.026 C475.769,102.502 475.58,102.958 475.244,103.295 "
    "C474.907,103.631 474.45,103.821 473.974,103.821 L477.564,103.821 "
    "C478.992,103.821 480.362,104.388 481.372,105.398 C482.381,106.407 482.949,107.777 482.949,109.205 "
    "L482.949,112.795 C482.949,114.223 482.381,115.593 481.372,116.602 "
    "C480.362,117.612 478.992,118.179 477.564,118.179 L473.974,118.179 "
    "C474.45,118.179 474.907,118.369 475.243,118.705 C475.58,119.042 475.769,119.498 475.769,119.974 Z"
)


class AreaTests(unittest.TestCase):
    def test_a_square_has_the_area_it_is_and_a_sign_for_the_way_it_goes_round(self):
        a = contour("M0,0 L10,0 L10,10 L0,10 Z")
        self.assertAlmostEqual(signed_area(a), 100)
        self.assertAlmostEqual(signed_area(contour("M0,0 L0,10 L10,10 L10,0 Z")), -100)

    def test_a_curve_counts_with_its_bulge(self):
        # a half disc of radius 10: a cubic approximation of the arc plus the straight side
        k = 0.5522847498 * 10
        half = contour(f"M0,-10 C{k},-10 10,{-k} 10,0 C10,{k} {k},10 0,10 Z")
        self.assertAlmostEqual(signed_area(half), math.pi * 100 / 2, delta=0.3)


class IntersectionTests(unittest.TestCase):
    def test_two_lines(self):
        (hit,) = intersections((0, 0), ("L", (10, 10)), (0, 10), ("L", (10, 0)))
        self.assertAlmostEqual(hit[0], 0.5)
        self.assertAlmostEqual(hit[1], 0.5)

    def test_lines_that_stop_short_do_not_cross(self):
        self.assertEqual(intersections((0, 0), ("L", (4, 4)), (0, 10), ("L", (10, 0))), [])

    def test_a_line_through_a_curve(self):
        # a quarter circle of radius 10 about the origin, crossed by the line x = 6 (at y = -8, so 0.6 of the way up it)
        k = 0.5522847498 * 10
        arc = ("C", (10, -k), (k, -10), (0, -10))
        (hit,) = intersections((10, 0), arc, (6, -20), ("L", (6, 0)))
        self.assertAlmostEqual(hit[1], 0.6, delta=2e-3)
        x, y = cub((10, 0), *arc[1:], hit[0])
        self.assertAlmostEqual(x, 6, delta=1e-3)
        self.assertAlmostEqual(y, -8, delta=3e-3)
        (back,) = intersections((6, -20), ("L", (6, 0)), (10, 0), arc)  # and the same the other way round
        self.assertAlmostEqual(back[0], hit[1], places=3)
        self.assertAlmostEqual(back[1], hit[0], places=3)

    def test_two_curves(self):
        k = 0.5522847498 * 10
        arc = ("C", (10, -k), (k, -10), (0, -10))  # quarter circle about the origin
        upright = ("C", (3, -8), (3, -4), (3, 0))  # from (3, -12) straight up: a vertical line written as a curve
        (hit,) = intersections((10, 0), arc, (3, -12), upright)
        self.assertAlmostEqual(hit[1], (12 - math.sqrt(91)) / 12, delta=1e-3)  # the circle is at y = -sqrt(91) there
        x, _y = cub((10, 0), *arc[1:], hit[0])
        self.assertAlmostEqual(x, 3, delta=2e-3)

    def test_curves_that_do_not_meet(self):
        arc = ("C", (10, -5), (5, -10), (0, -10))
        self.assertEqual(intersections((10, 0), arc, (20, 0), ("C", (20, -5), (15, -10), (12, -10))), [])


class LoopTests(unittest.TestCase):
    def test_a_contour_that_does_not_cross_itself_is_one_loop_and_comes_back_unchanged(self):
        c = contour("M0,0 L10,0 L10,10 L0,10 Z")
        self.assertEqual(split_loops(c), [c])
        self.assertIs(remove_loops(c, +1), c)

    def test_the_hole_of_the_d_loses_its_two_spurs_and_keeps_the_shape_it_really_has(self):
        c = contour(D_REGULAR)
        hole = remove_loops(c, +1)
        self.assertIsNotNone(hole)
        # exactly the part of the inner disc (radius 17.949 about (465, 111)) beyond the straight side at x = 468.59
        self.assertAlmostEqual(signed_area(hole), disc_segment_area(17.949, 3.59), delta=0.5)
        self.assertEqual(sorted(s[0] for s in hole[1]), ["C", "C", "L"], "two arcs and the straight side")
        self.assertEqual(hole[1][-1][-1], hole[0], "closed")
        xs = [p[0] for s in hole[1] for p in s[1:]]
        self.assertGreaterEqual(min(xs), 465 - 1e-6)
        self.assertTrue(all(abs(p[0] - 468.59) < 1e-3 for p in (hole[1][-1][-1], hole[0])), "ends on the straight side")

    def test_the_spurs_are_loops_of_their_own_that_run_the_other_way(self):
        loops = split_loops(contour(D_REGULAR))
        areas = sorted(signed_area(c) for c in loops)
        self.assertEqual(len(loops), 3)
        self.assertLess(areas[0], 0)
        self.assertLess(areas[1], 0)
        self.assertGreater(areas[2], 300)

    def test_a_hole_made_of_many_curves_meeting_at_nodes_is_not_mistaken_for_a_tangle(self):
        hole = remove_loops(contour(AD_HOLE), +1)
        self.assertIsNotNone(hole)
        # a 7.18 x 14.36 box with two round corners of radius 5.385 on its right
        self.assertAlmostEqual(signed_area(hole), 7.18 * 14.358 - 2 * 5.385**2 * (1 - math.pi / 4), delta=0.6)
        self.assertEqual(len(split_loops(hole)), 1)

    def test_cutting_is_idempotent(self):
        hole = remove_loops(contour(D_REGULAR), +1)
        again = remove_loops(hole, +1)
        self.assertEqual(len(split_loops(hole)), 1)
        self.assertEqual(len(again[1]), len(hole[1]))

    def test_a_bow_tie_gives_the_loop_that_goes_the_way_asked_for(self):
        bow = contour("M0,0 L10,10 L10,0 L0,10 Z")
        plus = remove_loops(bow, +1)
        minus = remove_loops(bow, -1)
        self.assertGreater(signed_area(plus), 0)
        self.assertLess(signed_area(minus), 0)
        self.assertAlmostEqual(abs(signed_area(plus)), 25, delta=0.01)

    def test_a_contour_that_goes_the_wrong_way_altogether_has_nothing_to_keep(self):
        # the hole of a dot at the heaviest weight: turned inside out
        self.assertIsNone(remove_loops(contour("M0,0 L0,3 L3,3 L3,0 Z"), +1))


if __name__ == "__main__":
    unittest.main()
