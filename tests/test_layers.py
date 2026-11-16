import os
import re
import unittest

from symbolmaker.engine.layers import LayerAssignment, annotate, path_ds, plan_layers, read_assignments

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE = [
    "lucide.house",
    "lucide.file.check",
    "lucide.layers.arrow.down",
    "lucide.calendar",
    "lucide.circle.check",
    "lucide.bell",
    "lucide.heart",
    "lucide.arrow.down.narrow.wide",
]


def load(name):
    with open(f"{ROOT}/tests/fixtures/export/{name}.svg") as f:
        return f.read()


class LayerEngineTests(unittest.TestCase):
    def test_house_has_container_secondary_and_door_primary(self):
        plan = plan_layers(path_ds(load("lucide.house")))
        levels = {a.layer: a.level for a in plan}
        self.assertEqual(levels[0], "secondary")
        self.assertEqual(sorted(a.level for a in plan), ["primary", "secondary"])

    def test_arrow_shaft_and_head_share_a_layer(self):
        plan = plan_layers(path_ds(load("lucide.layers.arrow.down")))
        self.assertEqual(len({a.layer for a in plan}), 4)
        self.assertEqual(len(plan), 5)  # 5 paths, 4 layers: shaft and head share one
        shared = [n for n in {a.layer for a in plan} if sum(1 for a in plan if a.layer == n) == 2]
        self.assertEqual(len(shared), 1)

    def test_cap_is_respected(self):
        for cap in (2, 3, 4):
            for name in SAMPLE:
                plan = plan_layers(path_ds(load(name)), cap=cap)
                self.assertLessEqual(len({a.layer for a in plan}), cap, f"{name} cap={cap}")

    def test_annotate_roundtrip_and_all_weights_carry_classes(self):
        svg = load("lucide.house")
        new = [LayerAssignment(0, "primary"), LayerAssignment(1, "tertiary")]
        out = annotate(svg, new)
        self.assertEqual(read_assignments(out), new)
        for w in ("Ultralight-S", "Regular-S", "Black-S"):
            found = re.search(rf'<g id="{w}"[^>]*>(.*?)</g>', out, re.S)
            assert found is not None
            group = found.group(1)
            self.assertEqual(re.findall(r"hierarchical-(\d):(\w+)", group), [("0", "primary"), ("1", "tertiary")])

    def test_annotate_rejects_conflicting_levels(self):
        svg = load("lucide.house")
        with self.assertRaises(ValueError):
            annotate(svg, [LayerAssignment(0, "primary"), LayerAssignment(0, "secondary")])

    def test_annotate_rejects_wrong_count(self):
        with self.assertRaises(ValueError):
            annotate(load("lucide.house"), [LayerAssignment(0, "primary")])

    def test_parity_with_existing_export(self):
        for name in SAMPLE:
            svg = load(name)
            self.assertEqual(plan_layers(path_ds(svg)), read_assignments(svg), name)


if __name__ == "__main__":
    unittest.main()
