"""Releases: the zips attached to a GitHub release, the notes that describe them, and the files that wire up
release-please and keep GitHub Pages tied to releases."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
import zipfile
from pathlib import Path
from typing import ClassVar

from symbolmaker import release_assets, sitebuild
from tests.test_sitebuild import LUCIDE, TABLER, fake_convert, release

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_site(tmp):
    out = Path(tmp) / "site"
    sitebuild.build(
        out,
        [
            (LUCIDE, release()),
            (TABLER, release(["home", "star"], version="3.52.0", license_name="MIT", license_text="MIT License")),
        ],
        convert=fake_convert,
        swiftdraw="0.29.0",
        commit={"sha": "a" * 40, "dirty": False},
        version="1.2.3",
    )
    return out


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.site = make_site(self.tmp)
        self.out = Path(self.tmp) / "assets"
        self.files = release_assets.build_assets(self.site, self.out)

    def names(self):
        return sorted(p.name for p in self.files)

    def test_each_set_gets_exactly_one_zip_with_a_stable_name(self):
        self.assertEqual(self.names(), sorted(["SHA256SUMS.txt", "build-info.json", "lucide.zip", "tabler.zip"]))
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), self.names(), "nothing else is left in the folder")

    def test_the_zip_holds_every_template_unchanged_and_the_license(self):
        z = zipfile.ZipFile(self.out / "lucide.zip")
        self.assertIsNone(z.testzip())
        published = sorted((self.site / "lucide/templates").glob("*.svg"))
        self.assertEqual(len(published), 3)
        in_templates = sorted(n for n in z.namelist() if n.startswith("lucide/templates/"))
        self.assertEqual(in_templates, sorted(f"lucide/templates/{p.name}" for p in published))
        for p in published:
            self.assertEqual(z.read(f"lucide/templates/{p.name}"), p.read_bytes())
        self.assertEqual(z.read("lucide/LICENSE-lucide.txt").decode(), "ISC License\nCopyright (c) Lucide")

    def test_the_same_zip_also_holds_an_asset_catalog_with_one_symbolset_per_symbol(self):
        z = zipfile.ZipFile(self.out / "tabler.zip")
        names = set(z.namelist())
        self.assertEqual(
            json.loads(z.read("tabler/tabler.xcassets/Contents.json")), {"info": {"author": "xcode", "version": 1}}
        )
        for sym in ("tabler.home", "tabler.star"):
            self.assertEqual(
                json.loads(z.read(f"tabler/tabler.xcassets/{sym}.symbolset/Contents.json"))["symbols"],
                [{"filename": f"{sym}.svg", "idiom": "universal"}],
            )
            self.assertEqual(
                z.read(f"tabler/tabler.xcassets/{sym}.symbolset/{sym}.svg"),
                (self.site / f"tabler/templates/{sym}.svg").read_bytes(),
            )
        # nothing else: the templates folder, the catalog, and the license
        self.assertEqual(len(names), 2 + 1 + (1 + 2 * 2) + 0, sorted(names))

    def test_checksums_cover_every_other_file_in_the_shasum_format(self):
        lines = (self.out / "SHA256SUMS.txt").read_text().splitlines()
        listed = {}
        for line in lines:
            digest, name = line.split("  ")
            listed[name] = digest
        self.assertEqual(sorted(listed), sorted(n for n in self.names() if n != "SHA256SUMS.txt"))
        for name, digest in listed.items():
            self.assertEqual(hashlib.sha256((self.out / name).read_bytes()).hexdigest(), digest, name)

    def test_build_info_is_the_sites_own_description_of_the_build(self):
        self.assertEqual(
            json.loads((self.out / "build-info.json").read_text()), json.loads((self.site / "sources.json").read_text())
        )

    def test_the_same_site_gives_the_same_bytes(self):
        again = Path(self.tmp) / "again"
        release_assets.build_assets(self.site, again)
        for p in self.files:
            self.assertEqual((again / p.name).read_bytes(), p.read_bytes(), p.name)

    def test_a_missing_or_empty_site_is_an_error_with_a_message(self):
        with self.assertRaisesRegex(ValueError, "sources.json"):
            release_assets.build_assets(Path(self.tmp) / "nope", Path(self.tmp) / "o2")
        shutil.rmtree(self.site / "tabler/templates")
        (self.site / "tabler/templates").mkdir()
        with self.assertRaisesRegex(ValueError, "tabler"):
            release_assets.build_assets(self.site, Path(self.tmp) / "o3")

    @unittest.skipUnless(shutil.which("xcrun"), "needs Xcode")
    def test_the_catalog_zip_compiles_with_actool(self):
        work = Path(self.tmp) / "x"
        zipfile.ZipFile(self.out / "lucide.zip").extractall(work)
        (work / "out").mkdir()
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
                str(work / "out"),
                str(work / "lucide/lucide.xcassets"),
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertNotIn("error:", res.stdout + res.stderr)
        self.assertTrue((work / "out/Assets.car").exists())


class NotesTests(unittest.TestCase):
    META: ClassVar[dict] = {
        "built": "2026-11-16T10:00:00+00:00",
        "swiftdraw": "0.29.0",
        "engine": "5b4aa5dc",
        "commit": "f" * 40,
        "dirty": False,
        "version": "1.2.3",
        "weights": {"ultralight": 0.30, "black": 1.90},
        "sources": [
            {"id": "lucide", "title": "Lucide", "version": "1.73.0", "license": "ISC", "count": 2055, "failed": 0},
            {
                "id": "tabler",
                "title": "Tabler Icons",
                "version": "3.52.0",
                "license": "MIT",
                "count": 5503,
                "failed": 0,
            },
        ],
    }

    def test_the_block_lists_each_set_with_its_version_count_and_license(self):
        b = release_assets.notes_block(self.META, "o/r")
        self.assertTrue(b.startswith(release_assets.START) and b.rstrip().endswith(release_assets.END))
        self.assertIn("| Lucide | 1.73.0 | 2,055 | ISC |", b)
        self.assertIn("| Tabler Icons | 3.52.0 | 5,503 | MIT |", b)
        self.assertIn("SwiftDraw 0.29.0", b)
        self.assertIn("`lucide.zip`", b)
        self.assertIn("`tabler.zip`", b)
        self.assertNotIn("-templates.zip", b)
        self.assertNotIn("-xcassets.zip", b)

    def test_the_commit_is_linked_when_it_is_exact_and_left_out_when_it_is_not(self):
        self.assertIn("https://github.com/o/r/commit/" + "f" * 40, release_assets.notes_block(self.META, "o/r"))
        self.assertNotIn("/commit/", release_assets.notes_block({**self.META, "dirty": True}, "o/r"))
        no = dict(self.META)
        del no["commit"]
        self.assertNotIn("/commit/", release_assets.notes_block(no, "o/r"))

    def test_merging_appends_to_the_release_notes_and_replaces_its_own_block_when_run_again(self):
        block = release_assets.notes_block(self.META, "o/r")
        body = "## 1.2.3\n\n### Features\n\n* a thing\n"
        once = release_assets.merge_notes(body, block)
        self.assertTrue(once.startswith(body.rstrip()))
        self.assertEqual(once.count(release_assets.START), 1)
        newer = release_assets.notes_block({**self.META, "swiftdraw": "0.30.0"}, "o/r")
        twice = release_assets.merge_notes(once, newer)
        self.assertEqual(twice.count(release_assets.START), 1)
        self.assertIn("SwiftDraw 0.30.0", twice)
        self.assertNotIn("SwiftDraw 0.29.0", twice)
        self.assertTrue(twice.startswith(body.rstrip()), "the changelog text is untouched")
        self.assertEqual(release_assets.merge_notes(once, block), once, "merging the same block again changes nothing")

    def test_empty_notes_are_fine(self):
        self.assertTrue(
            release_assets.merge_notes("", release_assets.notes_block(self.META, "o/r")).startswith(
                release_assets.START
            )
        )


class VersionTests(unittest.TestCase):
    def test_the_version_is_read_from_pyproject(self):
        self.assertEqual(
            sitebuild.project_version(ROOT / "pyproject.toml"),
            tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        )

    def test_an_unreadable_pyproject_gives_unknown_not_a_crash(self):
        self.assertEqual(sitebuild.project_version(Path("/nonexistent/pyproject.toml")), "unknown")

    def test_the_version_is_recorded_in_sources_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = json.loads((make_site(tmp) / "sources.json").read_text())
        self.assertEqual(d["version"], "1.2.3")


class ReleaseSetupTests(unittest.TestCase):
    """The rules that keep releases working, checked so that editing one file cannot quietly break another."""

    def read(self, rel):
        return (ROOT / rel).read_text()

    def test_release_please_starts_from_the_version_in_pyproject(self):
        manifest = json.loads(self.read(".release-please-manifest.json"))
        self.assertEqual(
            manifest,
            {".": tomllib.loads(self.read("pyproject.toml"))["project"]["version"]},
            "the manifest is the last released version; pyproject must say the same until the first release",
        )

    def test_release_please_is_configured_for_this_python_project(self):
        cfg = json.loads(self.read("release-please-config.json"))
        pkg = cfg["packages"]["."]
        self.assertEqual(pkg["release-type"], "python")
        self.assertTrue(pkg["bump-minor-pre-major"], "while below 1.0 a feature is a minor bump, not a major one")
        self.assertTrue(pkg["include-v-in-tag"], "tags look like v0.1.0")
        self.assertIs(pkg["include-component-in-tag"], False, "not symbol-maker-v0.1.0, which release.yml refuses")
        self.assertRegex(cfg["bootstrap-sha"], r"^[0-9a-f]{40}$")

    def test_pages_is_deployed_only_from_the_release_workflow(self):
        self.assertFalse(
            (ROOT / ".github/workflows/pages.yml").exists(), "the old deploy-on-every-push workflow is gone"
        )
        self.assertIn("deploy-pages", self.read(".github/workflows/release.yml"))

    def test_a_manual_run_still_deploys_even_though_release_please_is_skipped_in_it(self):
        # `needs: build` alone also requires build's own dependency (release-please) not to be skipped, which it is
        # whenever the workflow is run by hand to publish a tag again.
        text = self.read(".github/workflows/release.yml")
        deploy = text[text.index("\n  deploy:") :]
        self.assertRegex(deploy, r"if: \$\{\{ !cancelled\(\) && needs\.build\.result == 'success' \}\}")
        for f in sorted((ROOT / ".github/workflows").glob("*.yml")) + sorted((ROOT / ".github/actions").rglob("*.yml")):
            if f.name != "release.yml":
                self.assertNotIn("deploy-pages", f.read_text(), f"{f.name} must not publish the site")
                self.assertNotIn("pages: write", f.read_text(), f"{f.name} must not be able to publish the site")

    def test_the_site_is_built_and_published_only_after_a_release_exists(self):
        wf = self.read(".github/workflows/release.yml")
        self.assertIn("googleapis/release-please-action", wf)
        self.assertIn("release_created == 'true'", wf)
        self.assertIn("needs: release-please", wf)
        self.assertIn("gh release upload", wf)
        self.assertLess(
            wf.index("gh release upload"),
            wf.index("upload-pages-artifact"),
            "assets are attached before Pages is touched",
        )

    def test_everything_that_builds_shares_one_definition_of_how(self):
        for f in ("ci.yml", "release.yml"):
            self.assertIn("./.github/actions/build-site", self.read(f".github/workflows/{f}"))
        self.assertIn("./ci.sh", self.read(".github/actions/build-site/action.yml"))

    def test_dependabot_also_watches_the_shared_action(self):
        self.assertIn("/.github/actions/build-site", self.read(".github/dependabot.yml"))


if __name__ == "__main__":
    unittest.main()
