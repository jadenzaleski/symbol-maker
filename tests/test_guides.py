import os
import unittest

from symbolmaker.engine.guides import parse_template
from symbolmaker.engine.layers import bbox

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEIGHTS = {"ultralight", "regular", "black"}


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class OurTemplateTests(unittest.TestCase):
    def setUp(self):
        self.g = parse_template(read(f"{ROOT}/tests/fixtures/export/lucide.house.svg"))

    def test_three_weights_each_with_paths(self):
        self.assertEqual(set(self.g), WEIGHTS)
        self.assertEqual([len(self.g[w]["paths"]) for w in sorted(self.g)], [2, 2, 2])

    def test_guides_come_from_the_template(self):
        r = self.g["regular"]
        self.assertAlmostEqual(r["cap"], 70.0, places=2)  # Capline-S 76 -> Baseline-S 146
        self.assertAlmostEqual(r["width"], 508.077 - 421.923, places=2)  # right-margin - left-margin
        self.assertAlmostEqual(r["origin"][0], 421.923, places=2)  # left margin, in the paths' own coordinates
        self.assertAlmostEqual(r["origin"][1], 146.0, places=2)  # baseline

    def test_the_symbol_sits_between_the_margins_and_on_the_baseline(self):
        for w in WEIGHTS:
            g = self.g[w]
            x0 = min(bbox(d)[0] for d in g["paths"]) - g["origin"][0]
            x1 = max(bbox(d)[2] for d in g["paths"]) - g["origin"][0]
            y1 = max(bbox(d)[3] for d in g["paths"]) - g["origin"][1]
            self.assertGreaterEqual(x0, -1)
            self.assertLessEqual(x1, g["width"] + 1)
            self.assertAlmostEqual(
                y1, 0, delta=4
            )  # a house stands on the baseline (the Black stroke overhangs a little)


class AppleTemplateTests(unittest.TestCase):
    def setUp(self):
        self.g = parse_template(read(f"{ROOT}/tests/fixtures/apple-circle.svg"))

    def test_apple_template_reads_the_same_way(self):
        self.assertEqual(set(self.g), WEIGHTS)
        r = self.g["regular"]
        self.assertAlmostEqual(r["cap"], 696 - 625.541, places=2)
        self.assertAlmostEqual(r["width"], 1496.11 - 1403.58, places=2)  # right-margin - left-margin of this circle
        self.assertEqual(r["origin"], [0.0, 0.0])  # paths are already relative to margin + baseline

    def test_a_template_without_guides_is_a_value_error(self):
        with self.assertRaises(ValueError):
            parse_template('<svg xmlns="http://www.w3.org/2000/svg"><g id="Regular-S"><path d="M0,0"/></g></svg>')
        with self.assertRaises(ValueError):
            parse_template("not svg")


if __name__ == "__main__":
    unittest.main()
