import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from symbolmaker.engine.convert import find_swiftdraw
from symbolmaker.engine.symbolset import contents_json, validate_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NameTests(unittest.TestCase):
    def test_valid_names(self):
        for n in ("lucide.arrow.up.right", "my_symbol-2", "a", "Home.fill"):
            self.assertIsNone(validate_name(n), n)

    def test_validate_name_rejects_slashes_spaces_empty_dotdot_and_more(self):
        for n in (
            "",
            " ",
            "a b",
            "a/b",
            "a\\b",
            "..",
            "a..b",
            ".hidden",
            "trailing.",
            "café",
            "x" * 101,
            "name\n",
            "../escape",
        ):
            self.assertIsNotNone(validate_name(n), repr(n))


class ContentsTests(unittest.TestCase):
    def test_contents_json_points_at_the_svg_as_a_universal_symbol(self):
        d = json.loads(contents_json("lucide.house"))
        self.assertEqual(d["symbols"], [{"filename": "lucide.house.svg", "idiom": "universal"}])
        self.assertEqual(d["info"], {"author": "xcode", "version": 1})

    def test_an_invalid_name_is_a_value_error(self):
        with self.assertRaises(ValueError):
            contents_json("../escape")


@unittest.skipUnless(find_swiftdraw() and shutil.which("xcrun"), "needs swiftdraw and Xcode")
class ActoolTests(unittest.TestCase):
    def test_a_symbolset_built_from_contents_json_compiles_with_actool(self):
        from symbolmaker.engine.pipeline import make_template

        tmp = Path(tempfile.mkdtemp())
        try:
            cat = tmp / "Test.xcassets"
            cat.mkdir()
            (cat / "Contents.json").write_text(json.dumps({"info": {"author": "xcode", "version": 1}}))
            for n in ("heart", "house", "baby"):
                r = make_template((Path(ROOT) / f"tests/fixtures/lucide/{n}.svg").read_text())
                s = cat / f"lucide.{n}.symbolset"
                s.mkdir()
                (s / f"lucide.{n}.svg").write_text(r.template)
                (s / "Contents.json").write_text(contents_json(f"lucide.{n}"))
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
