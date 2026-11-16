"""The page's own JavaScript (layer model, zip writer) is tested with Node's built-in runner; this runs it with the
rest, and checks that a template edited the way the page edits it is still accepted by Xcode's asset compiler."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")


@unittest.skipUnless(NODE, "needs node")
class PageScriptTests(unittest.TestCase):
    def test_node_tests_pass(self):
        files = sorted(str(p) for p in (ROOT / "tests" / "js").glob("*.test.mjs"))
        r = subprocess.run([NODE or "node", "--test", *files], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


EDIT = r"""
const L = require(process.argv[1] + '/site/layers.js');
const text = require('fs').readFileSync(process.argv[1] + '/tests/fixtures/export/lucide.circle.check.svg', 'utf8');
let m = L.fromTemplate(text);
m = L.setColor(m, m.layers[1].id, 'systemRedColor');
m = L.setLevel(m, m.layers[1].id, 'tertiary');
m = L.moveLayer(m, m.layers[1].id, -1);
m = L.addLayer(m);
m = L.assign(m, 0, m.layers.at(-1).id);          // a stroke moved into a new layer
process.stdout.write(L.apply(text, m));
"""


@unittest.skipUnless(NODE and shutil.which("xcrun"), "needs node and Xcode")
class EditedTemplateTests(unittest.TestCase):
    def test_a_template_edited_like_the_page_does_compiles_with_actool(self):
        svg = subprocess.run([NODE or "node", "-e", EDIT, str(ROOT)], capture_output=True, text=True, check=True).stdout
        self.assertIn("multicolor-0:systemRedColor", svg)
        tmp = Path(tempfile.mkdtemp())
        try:
            cat = tmp / "Test.xcassets"
            cat.mkdir()
            (cat / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}))
            s = cat / "lucide.edited.symbolset"
            s.mkdir()
            (s / "lucide.edited.svg").write_text(svg)
            (s / "Contents.json").write_text(
                json.dumps(
                    {
                        "info": {"author": "xcode", "version": 1},
                        "symbols": [{"filename": "lucide.edited.svg", "idiom": "universal"}],
                    },
                    indent=2,
                )
            )
            out = tmp / "out"
            out.mkdir()
            res = subprocess.run(
                [
                    "xcrun",
                    "actool",
                    "--output-format",
                    "human-readable-text",
                    "--notices",
                    "--warnings",
                    "--errors",
                    "--platform",
                    "iphoneos",
                    "--minimum-deployment-target",
                    "17.0",
                    "--compile",
                    str(out),
                    str(cat),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
            self.assertNotIn("error:", res.stdout + res.stderr)
            self.assertTrue((out / "Assets.car").exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
