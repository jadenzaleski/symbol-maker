import io
import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from symbolmaker import sitebuild
from symbolmaker.engine.convert import find_swiftdraw
from symbolmaker.engine.layers import LayerAssignment, read_assignments
from symbolmaker.engine.pipeline import MakeResult
from symbolmaker.sources import SOURCES

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOUSE = (ROOT / "tests/fixtures/export/lucide.house.svg").read_text()
LUCIDE, TABLER = SOURCES["lucide"], SOURCES["tabler"]


def release(
    names=("a-arrow-down", "heart", "house"),
    version="9.9.9",
    license_name="ISC",
    license_text="ISC License\nCopyright (c) Lucide",
):
    return {
        "version": version,
        "license": license_text,
        "license_name": license_name,
        "names": list(names),
        "svgs": {n: f'<svg class="icon-{n}"/>' for n in names},
    }


def fake_convert(svg):
    return MakeResult(HOUSE, "variable", ["a note"], [LayerAssignment(0, "secondary"), LayerAssignment(1, "primary")])


class StampTests(unittest.TestCase):
    def test_the_license_comment_is_added_and_the_template_still_reads(self):
        out = sitebuild.stamp(HOUSE, LUCIDE, "house", "9.9.9", "ISC")
        head = out.split("<svg", 1)[0]
        self.assertIn("Lucide", head)
        self.assertIn("ISC", head)
        self.assertIn("LICENSE-lucide.txt", head)
        self.assertTrue(out.startswith("<?xml"))
        ET.fromstring(out)  # still well-formed XML
        self.assertEqual(read_assignments(out), read_assignments(HOUSE))

    def test_the_comment_never_contains_a_double_hyphen(self):
        head = sitebuild.stamp(HOUSE, TABLER, "a-arrow-down", "1.2.3", "MIT").split("<svg", 1)[0]
        self.assertNotIn("--", head.split("<!--", 1)[1].rsplit("-->", 1)[0])
        evil = sitebuild.stamp(HOUSE, TABLER, "x", "1.0.0", "A--B").split("<svg", 1)[0]
        self.assertNotIn("--", evil.split("<!--", 1)[1].rsplit("-->", 1)[0])


class ZipTests(unittest.TestCase):
    def test_the_zip_holds_a_symbolset_folder_and_the_license_beside_it(self):
        z = zipfile.ZipFile(io.BytesIO(sitebuild.symbolset_zip("tabler.home", HOUSE, "MIT text", "LICENSE-tabler.txt")))
        self.assertEqual(
            sorted(z.namelist()),
            ["LICENSE-tabler.txt", "tabler.home.symbolset/Contents.json", "tabler.home.symbolset/tabler.home.svg"],
        )
        self.assertEqual(z.read("tabler.home.symbolset/tabler.home.svg").decode(), HOUSE)
        self.assertEqual(
            json.loads(z.read("tabler.home.symbolset/Contents.json"))["symbols"][0]["filename"], "tabler.home.svg"
        )
        self.assertEqual(z.read("LICENSE-tabler.txt").decode(), "MIT text")

    def test_the_same_input_gives_the_same_bytes(self):
        a = sitebuild.symbolset_zip("lucide.house", HOUSE, "x", "LICENSE-lucide.txt")
        self.assertEqual(a, sitebuild.symbolset_zip("lucide.house", HOUSE, "x", "LICENSE-lucide.txt"))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "dist"
        self.addCleanup(shutil.rmtree, self.out.parent, True)

    def build(self, items=None, **kw):
        kw.setdefault("convert", fake_convert)
        return sitebuild.build(self.out, items or [(LUCIDE, release())], swiftdraw="0.29.0", **kw)

    def test_writes_every_artifact_for_every_icon_in_a_folder_per_source(self):
        self.build()
        for sym, icon in (
            ("lucide.house", "house"),
            ("lucide.heart", "heart"),
            ("lucide.a.arrow.down", "a-arrow-down"),
        ):
            self.assertTrue((self.out / "lucide/templates" / f"{sym}.svg").read_text().startswith("<?xml"))
            self.assertEqual(
                set(json.loads((self.out / "lucide/guides" / f"{sym}.json").read_text())),
                {"ultralight", "regular", "black"},
            )
            self.assertTrue(zipfile.is_zipfile(self.out / "lucide/zips" / f"{sym}.symbolset.zip"))
            self.assertIn(f"icon-{icon}", (self.out / "lucide/icons" / f"{icon}.svg").read_text())
        self.assertEqual((self.out / "lucide/LICENSE.txt").read_text(), "ISC License\nCopyright (c) Lucide")
        self.assertTrue((self.out / ".nojekyll").exists())

    def test_sources_json_lists_the_sources_and_the_build(self):
        self.build(
            [
                (LUCIDE, release()),
                (TABLER, release(["home", "star"], version="3.52.0", license_name="MIT", license_text="MIT License")),
            ]
        )
        d = json.loads((self.out / "sources.json").read_text())
        self.assertEqual((d["swiftdraw"], d["weights"]), ("0.29.0", {"ultralight": 0.30, "black": 1.90}))
        self.assertEqual([s["id"] for s in d["sources"]], ["lucide", "tabler"])
        tabler = d["sources"][1]
        self.assertEqual(
            (tabler["title"], tabler["version"], tabler["license"], tabler["count"], tabler["homepage"]),
            ("Tabler Icons", "3.52.0", "MIT", 2, "https://tabler.io/icons"),
        )
        self.assertTrue((self.out / "tabler/templates/tabler.home.svg").exists())
        self.assertTrue((self.out / "tabler/LICENSE.txt").read_text().startswith("MIT"))

    def test_each_source_index_describes_its_icons(self):
        self.build()
        d = json.loads((self.out / "lucide/index.json").read_text())
        self.assertEqual([i["name"] for i in d["icons"]], ["a-arrow-down", "heart", "house"])
        first = d["icons"][0]
        self.assertEqual(
            (first["symbol"], first["status"], first["layers"], first["notes"]),
            ("lucide.a.arrow.down", "variable", 2, ["a note"]),
        )
        self.assertEqual(d["failed"], [])

    def test_the_site_files_are_copied_in(self):
        site = self.out.parent / "site"
        site.mkdir()
        (site / "index.html").write_text("<html>")
        self.build(site_dir=site)
        self.assertEqual((self.out / "index.html").read_text(), "<html>")

    def test_icons_are_flagged_as_problem_or_note_in_the_index(self):
        def convert(svg):
            r = fake_convert(svg)
            if "icon-heart" in svg:
                r.problem = True  # will not follow weight properly
            elif "icon-house" in svg:
                r.notes = []  # nothing to say
            return r

        self.build(convert=convert)
        icons = {i["name"]: i for i in json.loads((self.out / "lucide/index.json").read_text())["icons"]}
        self.assertEqual(icons["heart"]["flag"], "problem")
        self.assertEqual(icons["a-arrow-down"]["flag"], "note")  # it has a note (fake_convert says 'a note')
        self.assertNotIn("flag", icons["house"])

    def test_the_page_assets_in_subfolders_are_copied_too(self):
        site = self.out.parent / "site"
        (site / "ui").mkdir(parents=True)
        (site / "index.html").write_text("<html>")
        (site / "ui" / "download.svg").write_text("<svg/>")
        self.build(site_dir=site)
        self.assertEqual((self.out / "ui" / "download.svg").read_text(), "<svg/>")

    def test_one_failing_icon_is_recorded_and_skipped(self):
        def convert(svg):
            if "icon-heart" in svg:
                raise ValueError("cannot convert")
            return fake_convert(svg)

        s = self.build(convert=convert, max_failed=0.5)
        d = json.loads((self.out / "lucide/index.json").read_text())
        self.assertEqual(d["failed"], [{"name": "heart", "error": "cannot convert"}])
        self.assertEqual([i["name"] for i in d["icons"]], ["a-arrow-down", "house"])
        self.assertFalse((self.out / "lucide/templates/lucide.heart.svg").exists())
        self.assertEqual(
            {k: s["lucide"][k] for k in ("icons", "failed", "cached")}, {"icons": 2, "failed": 1, "cached": 0}
        )

    def test_too_many_failures_in_one_source_stop_the_build_before_anything_is_published(self):
        def convert(svg):
            raise ValueError("nope")

        with self.assertRaises(sitebuild.BuildError) as cm:
            self.build(convert=convert, max_failed=0.02)
        self.assertIn("lucide", str(cm.exception))
        self.assertFalse(self.out.exists())

    def test_an_existing_output_folder_is_replaced_not_merged(self):
        self.out.mkdir(parents=True)
        (self.out / "stale.txt").write_text("old")
        self.build()
        self.assertFalse((self.out / "stale.txt").exists())

    def test_limit_applies_to_each_source(self):
        self.build([(LUCIDE, release()), (TABLER, release(["home", "star", "x"]))], limit=2)
        self.assertEqual(len(json.loads((self.out / "lucide/index.json").read_text())["icons"]), 2)
        self.assertEqual(len(json.loads((self.out / "tabler/index.json").read_text())["icons"]), 2)


class CacheTests(unittest.TestCase):
    """Icons whose SVG, engine code, SwiftDraw version and weights are unchanged are not converted again."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.out, self.cache_dir = tmp / "dist", tmp / "cache"
        self.converted = []

    def convert(self, svg):
        self.converted.append(svg)
        return fake_convert(svg)

    def build(self, rel, fingerprint="fp1", **kw):
        cache = sitebuild.ConvertCache(self.cache_dir, fingerprint)
        return sitebuild.build(self.out, [(LUCIDE, rel)], convert=self.convert, cache=cache, **kw)

    def templates(self):
        return {p.name: p.read_text() for p in sorted((self.out / "lucide/templates").iterdir())}

    def test_the_second_build_converts_nothing(self):
        rel = release()
        first = self.build(rel)
        first_templates = self.templates()
        self.assertEqual((len(self.converted), first["lucide"]["cached"]), (3, 0))
        self.converted.clear()
        second = self.build(rel)
        self.assertEqual((self.converted, second["lucide"]["cached"]), ([], 3))
        self.assertEqual(self.templates(), first_templates)  # same output either way

    def test_only_a_changed_icon_is_converted_again(self):
        rel = release()
        self.build(rel)
        self.converted.clear()
        rel["svgs"]["heart"] = '<svg class="icon-heart" data-edited="1"/>'
        s = self.build(rel)
        self.assertEqual(self.converted, [rel["svgs"]["heart"]])
        self.assertEqual(s["lucide"]["cached"], 2)

    def test_a_new_engine_or_swiftdraw_or_weights_fingerprint_converts_everything(self):
        rel = release()
        self.build(rel, fingerprint="fp1")
        self.converted.clear()
        self.build(rel, fingerprint="fp2")
        self.assertEqual(len(self.converted), 3)

    def test_icons_that_left_the_set_are_dropped_from_the_cache(self):
        self.build(release())
        self.converted.clear()
        self.build(release(["house"]))
        self.converted.clear()
        self.build(release())  # heart and a-arrow-down come back: reconverted
        self.assertEqual(len(self.converted), 2)

    def test_failures_are_not_cached_so_they_are_retried(self):
        calls = []

        def flaky(svg):
            calls.append(svg)
            raise ValueError("boom")

        cache = sitebuild.ConvertCache(self.cache_dir, "fp1")
        for _ in range(2):
            sitebuild.build(self.out, [(LUCIDE, release(["heart"]))], convert=flaky, cache=cache, max_failed=1.0)
        self.assertEqual(len(calls), 2)

    def test_a_damaged_cache_file_is_ignored(self):
        rel = release()
        self.build(rel)
        for f in self.cache_dir.iterdir():
            f.write_bytes(b"not gzip at all")
        self.converted.clear()
        self.build(rel)
        self.assertEqual(len(self.converted), 3)

    def test_the_cache_is_written_only_after_a_successful_build(self):
        def convert(svg):
            raise ValueError("nope")

        cache = sitebuild.ConvertCache(self.cache_dir, "fp1")
        with self.assertRaises(sitebuild.BuildError):
            sitebuild.build(self.out, [(LUCIDE, release())], convert=convert, cache=cache)
        self.assertFalse(self.cache_dir.exists() and any(self.cache_dir.iterdir()))


class Recorder:
    """A reporter that remembers what it was told."""

    def __init__(self):
        self.calls = []

    def info(self, text=""):
        self.calls.append(("info", text))

    def start(self, title, total, reused=0):
        self.calls.append(("start", title, total, reused))

    def advance(self, n=1):
        self.calls.append(("advance", n))

    def done(self, stats):
        self.calls.append(("done", stats))
        return 1.5

    def table(self, rows):
        self.calls.append(("table", rows))


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "dist"
        self.addCleanup(shutil.rmtree, self.out.parent, True)

    def build(self, items, reporter, **kw):
        return sitebuild.build(self.out, items, convert=fake_convert, reporter=reporter, **kw)

    def test_the_reporter_is_told_the_total_every_step_and_the_result_per_source(self):
        rec = Recorder()
        self.build([(LUCIDE, release()), (TABLER, release(["home", "star"]))], rec)
        starts = [c for c in rec.calls if c[0] == "start"]
        self.assertEqual([(c[1], c[2], c[3]) for c in starts], [("Lucide", 3, 0), ("Tabler Icons", 2, 0)])
        advanced = [c[1] for c in rec.calls if c[0] == "advance"]
        self.assertEqual(sum(advanced), 5)
        dones = [c[1] for c in rec.calls if c[0] == "done"]
        self.assertEqual([d["icons"] for d in dones], [3, 2])
        self.assertEqual(dones[0]["notes"], 3)  # fake_convert gives every icon a note
        self.assertEqual(dones[0]["problems"], 0)

    def test_cached_icons_count_as_done_immediately_and_are_reported_as_reused(self):
        cache = sitebuild.ConvertCache(self.out.parent / "cache", "fp")
        self.build([(LUCIDE, release())], Recorder(), cache=cache)
        rec = Recorder()
        s = self.build([(LUCIDE, release())], rec, cache=cache)
        self.assertEqual(next(c for c in rec.calls if c[0] == "start")[3], 3)
        self.assertEqual(sum(c[1] for c in rec.calls if c[0] == "advance"), 3)
        self.assertEqual(s["lucide"]["cached"], 3)

    def test_the_summary_carries_problems_notes_and_time(self):
        def convert(svg):
            r = fake_convert(svg)
            r.problem = "heart" in svg
            return r

        rec = Recorder()
        s = sitebuild.build(self.out, [(LUCIDE, release())], convert=convert, reporter=rec)
        self.assertEqual((s["lucide"]["problems"], s["lucide"]["notes"]), (1, 2))  # 1 problem, 2 icons with only a note
        self.assertEqual(s["lucide"]["seconds"], 1.5)


class RevisionTests(unittest.TestCase):
    """Each icon records a short revision of its template and the day that template last changed."""

    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.out, self.cache_dir = tmp / "dist", tmp / "cache"

    def build(self, rel, today, fingerprint="fp1"):
        cache = sitebuild.ConvertCache(self.cache_dir, fingerprint)
        sitebuild.build(self.out, [(LUCIDE, rel)], convert=fake_convert, cache=cache, today=today, swiftdraw="0.29.0")
        return {i["name"]: i for i in json.loads((self.out / "lucide/index.json").read_text())["icons"]}

    def test_every_icon_has_a_revision_and_a_date(self):
        icons = self.build(release(), "2026-11-15")
        for i in icons.values():
            self.assertRegex(i["rev"], r"^[0-9a-f]{8}$")
            self.assertEqual(i["updated"], "2026-11-15")
        self.assertEqual(len({i["rev"] for i in icons.values()}), 1)  # fake_convert gives every icon the same template

    def test_the_revision_is_in_the_template_comment_too(self):
        icons = self.build(release(["house"]), "2026-11-15")
        head = (self.out / "lucide/templates/lucide.house.svg").read_text().split("<svg", 1)[0]
        self.assertIn(icons["house"]["rev"], head)

    def test_an_unchanged_icon_keeps_its_date_and_a_changed_one_gets_the_new_day(self):
        rel = release()
        before = self.build(rel, "2026-11-15")
        rel["svgs"]["heart"] = '<svg class="icon-heart" data-edited="1"/>'
        after = self.build(rel, "2026-12-01")
        self.assertEqual(after["house"]["updated"], "2026-11-15")
        self.assertEqual(after["heart"]["updated"], "2026-12-01")
        self.assertEqual(after["house"]["rev"], before["house"]["rev"])

    def test_a_new_engine_fingerprint_dates_everything_afresh(self):
        self.build(release(), "2026-11-15", fingerprint="fp1")
        after = self.build(release(), "2026-12-01", fingerprint="fp2")
        self.assertEqual({i["updated"] for i in after.values()}, {"2026-12-01"})

    def test_sources_json_names_the_engine(self):
        self.build(release(), "2026-11-15")
        d = json.loads((self.out / "sources.json").read_text())
        self.assertRegex(d["engine"], r"^[0-9a-f]{8}$")


class FakeRun:
    """Stands in for subprocess.run: answers `git rev-parse` and `git status` from a table."""

    def __init__(self, head="a" * 40, dirty="", fail=False):
        self.head, self.dirty, self.fail, self.calls = head, dirty, fail, []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd)
        if self.fail:
            raise OSError("no git")
        out = self.head if "rev-parse" in cmd else self.dirty
        return type("R", (), {"returncode": 0, "stdout": out + "\n", "stderr": ""})()


class CommitTests(unittest.TestCase):
    SHA = "0123456789abcdef0123456789abcdef01234567"

    def test_the_action_names_the_commit_in_the_environment(self):
        run = FakeRun()
        self.assertEqual(sitebuild.build_commit({"GITHUB_SHA": self.SHA}, run), {"sha": self.SHA, "dirty": False})
        self.assertEqual(run.calls, [], "git is not asked when the environment already knows")

    def test_a_local_build_asks_git_and_notices_uncommitted_changes(self):
        self.assertEqual(sitebuild.build_commit({}, FakeRun(head=self.SHA)), {"sha": self.SHA, "dirty": False})
        self.assertEqual(
            sitebuild.build_commit({}, FakeRun(head=self.SHA, dirty=" M site/site.js")),
            {"sha": self.SHA, "dirty": True},
        )

    def test_an_explicit_commit_wins_over_the_one_the_action_reports(self):
        # a release of an older tag is built from a checkout of that tag; GITHUB_SHA is whatever the run started on
        other = "b" * 40
        self.assertEqual(
            sitebuild.build_commit({"SYMBOLMAKER_COMMIT": self.SHA, "GITHUB_SHA": other}, FakeRun()),
            {"sha": self.SHA, "dirty": False},
        )

    def test_nothing_usable_means_no_commit(self):
        self.assertIsNone(sitebuild.build_commit({}, FakeRun(fail=True)))
        self.assertIsNone(sitebuild.build_commit({}, FakeRun(head="not a hash")))
        self.assertEqual(
            sitebuild.build_commit({"GITHUB_SHA": "garbage"}, FakeRun(head=self.SHA))["sha"],
            self.SHA,
            "a malformed value in the environment is ignored",
        )


class DescribeCommitTests(unittest.TestCase):
    SHA = "0123456789abcdef0123456789abcdef01234567"

    def test_a_commit_is_shown_short_and_a_dirty_one_says_so(self):
        self.assertEqual(sitebuild.describe_commit({"sha": self.SHA, "dirty": False}), "0123456")
        self.assertEqual(sitebuild.describe_commit({"sha": self.SHA, "dirty": True}), "0123456 (local changes)")

    def test_an_unknown_commit_is_called_unknown(self):
        self.assertEqual(sitebuild.describe_commit(None), "unknown")


class CommitInSitesJsonTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / "dist"
        self.addCleanup(shutil.rmtree, self.out.parent, True)

    def meta(self, **kw):
        sitebuild.build(self.out, [(LUCIDE, release())], convert=fake_convert, swiftdraw="0.29.0", **kw)
        return json.loads((self.out / "sources.json").read_text())

    def test_the_commit_is_recorded_when_known(self):
        sha = "f" * 40
        d = self.meta(commit={"sha": sha, "dirty": False})
        self.assertEqual((d["commit"], d["dirty"]), (sha, False))

    def test_nothing_is_recorded_when_unknown(self):
        d = self.meta()
        self.assertNotIn("commit", d)
        self.assertNotIn("dirty", d)


class WorkDirTests(unittest.TestCase):
    def test_the_temporary_folder_stays_unsynced_when_the_output_is(self):
        self.assertEqual(sitebuild.work_dir(Path("/x/dist")).name, "dist.building")
        self.assertEqual(sitebuild.work_dir(Path("/x/dist.nosync")).name, "dist.building.nosync")
        self.assertEqual(sitebuild.work_dir(Path("/x/dist.nosync")).parent, Path("/x"))


class FingerprintTests(unittest.TestCase):
    def test_depends_on_swiftdraw_version_and_is_stable(self):
        a = sitebuild.engine_fingerprint("0.29.0")
        self.assertEqual(a, sitebuild.engine_fingerprint("0.29.0"))
        self.assertNotEqual(a, sitebuild.engine_fingerprint("0.30.0"))
        self.assertRegex(a, r"^[0-9a-f]{64}$")

    def test_depends_on_the_engine_code(self):
        from unittest import mock

        a = sitebuild.engine_fingerprint("0.29.0")
        real = Path.read_bytes
        with mock.patch.object(
            Path, "read_bytes", lambda self: real(self) + b"x" if self.name == "weights.py" else real(self)
        ):
            self.assertNotEqual(a, sitebuild.engine_fingerprint("0.29.0"))


class ServeTests(unittest.TestCase):
    def test_serves_the_built_folder_on_localhost_only(self):
        import threading
        import urllib.request

        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        (d / "index.html").write_text("hello site")
        srv = sitebuild.make_preview_server(d, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.assertEqual(srv.server_address[0], "127.0.0.1")
        import contextlib

        err = io.StringIO()
        with (
            contextlib.redirect_stderr(err),
            urllib.request.urlopen(f"http://127.0.0.1:{srv.server_address[1]}/index.html") as r,
        ):
            self.assertEqual(r.read(), b"hello site")
        self.assertEqual(err.getvalue(), "")  # no request log lines mixed into the build output


@unittest.skipUnless(find_swiftdraw(), "swiftdraw not installed")
class RealConversionTests(unittest.TestCase):
    ICONS = ("heart", "circle", "house", "info")

    def rel(self):
        names = list(self.ICONS)
        return {
            "version": "1.0.0",
            "license": "x",
            "license_name": "ISC",
            "names": names,
            "svgs": {n: (ROOT / f"tests/fixtures/lucide/{n}.svg").read_text() for n in names},
        }

    def test_default_conversion_uses_apple_weights_and_produces_a_variable_template(self):
        r = sitebuild.convert_apple((ROOT / "tests/fixtures/lucide/heart.svg").read_text())
        self.assertEqual(r.status, "variable")

    def test_building_with_several_processes_gives_the_same_templates_as_one(self):
        outs = []
        for jobs in (1, 2):
            out = Path(tempfile.mkdtemp()) / "dist"
            self.addCleanup(shutil.rmtree, out.parent, True)
            sitebuild.build(out, [(LUCIDE, self.rel())], jobs=jobs, convert=sitebuild.convert_apple)
            outs.append({p.name: p.read_text() for p in sorted((out / "lucide/templates").iterdir())})
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(len(outs[0]), 4)


if __name__ == "__main__":
    unittest.main()
