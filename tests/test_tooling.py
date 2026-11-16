"""The development tooling (uv, ruff, ty) and the places that enforce it, checked so that editing one file cannot
quietly switch the enforcement off."""

import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


PYPROJECT = tomllib.loads(read("pyproject.toml"))


class ProjectSetupTests(unittest.TestCase):
    def test_uv_manages_the_dev_tools_and_nothing_else(self):
        dev = PYPROJECT["dependency-groups"]["dev"]
        names = {re.split(r"[<>=!~ ]", d, maxsplit=1)[0] for d in dev}
        self.assertEqual(names, {"ruff", "ty"})
        self.assertEqual(PYPROJECT["project"]["dependencies"], [], "the program itself needs only the standard library")
        self.assertIs(PYPROJECT["tool"]["uv"]["package"], False, "an application: uv has nothing to build or install")

    def test_the_lock_file_is_there_and_records_the_tools_and_this_project(self):
        lock = tomllib.loads(read("uv.lock"))
        packages = {p["name"]: p for p in lock["package"]}
        self.assertTrue({"ruff", "ty", PYPROJECT["project"]["name"]} <= set(packages))
        self.assertEqual(
            packages[PYPROJECT["project"]["name"]]["version"],
            PYPROJECT["project"]["version"],
            "release-please must bump the lock file with pyproject.toml (see release-please-config.json)",
        )

    def test_the_python_version_is_one_number_everywhere(self):
        floor = PYPROJECT["project"]["requires-python"].lstrip(">=")
        major_minor = ".".join(floor.split(".")[:2])
        self.assertEqual(read(".python-version").strip(), major_minor)
        self.assertEqual(PYPROJECT["tool"]["ruff"]["target-version"], "py" + major_minor.replace(".", ""))
        self.assertEqual(PYPROJECT["tool"]["ty"]["environment"]["python-version"], major_minor)
        self.assertIn(f"python-version: '{major_minor}'", read(".github/actions/build-site/action.yml"))

    def test_ruff_checks_a_real_set_of_rules(self):
        select = set(PYPROJECT["tool"]["ruff"]["lint"]["select"])
        self.assertTrue(
            {"E", "F", "I", "B", "UP"} <= select, "pycodestyle, pyflakes, imports, likely bugs, modern syntax"
        )
        self.assertNotIn(
            "E501", PYPROJECT["tool"]["ruff"]["lint"].get("ignore", []), "long lines are enforced, not ignored"
        )

    def test_the_virtual_environment_is_not_committed(self):
        ignored = read(".gitignore")
        self.assertIn("/.venv/", ignored)
        self.assertIn("/.venv.nosync/", ignored)


class EnforcementTests(unittest.TestCase):
    def test_ci_sh_runs_every_check_through_the_locked_environment(self):
        ci = read("ci.sh")
        for command in ("ruff check .", "ruff format --check .", "ty check"):
            self.assertIn(f"uv run --locked {command}", ci)
        self.assertIn("uv run --locked python -m unittest", ci)
        self.assertIn("uv run --locked python -m symbolmaker.sitebuild", ci)
        self.assertLess(ci.index("ty check"), ci.index("unittest"), "the checks run before the tests and the build")

    def test_the_workflows_get_uv_and_run_python_only_through_it(self):
        self.assertIn("astral-sh/setup-uv@", read(".github/actions/build-site/action.yml"))
        self.assertNotIn("setup-python", read(".github/actions/build-site/action.yml"))
        files = (
            ".github/workflows/ci.yml",
            ".github/workflows/release.yml",
            ".github/actions/build-site/action.yml",
            "ci.sh",
        )
        for rel in files:
            for line in read(rel).splitlines():
                runs_python = re.search(r"\bpython3?\s+(-m|-c|\S+\.py)\b", line)
                if runs_python and not line.lstrip().startswith("#"):
                    self.assertIn(
                        "uv run --locked", line, f"{rel}: run Python through `uv run --locked`: {line.strip()}"
                    )

    def test_every_build_goes_through_ci_sh_so_nothing_can_skip_the_checks(self):
        self.assertIn("./ci.sh", read(".github/actions/build-site/action.yml"))
        for rel in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
            self.assertIn("./.github/actions/build-site", read(rel))

    def test_dependabot_keeps_the_dev_tools_current(self):
        self.assertRegex(read(".github/dependabot.yml"), r"package-ecosystem: uv\b")


class ReleaseKeepsTheLockInStepTests(unittest.TestCase):
    # release-please edits TOML with a parser that wraps every string in an object, so a filter that compares a string
    # (`@.name=='symbol-maker'`) never matches and the lock was silently left at the old version. A key that merely has
    # to exist does match, and the project is the only "virtual" package in uv.lock (it is not built or installed).
    JSONPATH = "$.package[?(@.source.virtual)].version"

    def test_release_please_bumps_the_project_version_in_uv_lock_too(self):
        cfg = json.loads(read("release-please-config.json"))
        extra = cfg["packages"]["."]["extra-files"]
        self.assertIn({"type": "toml", "path": "uv.lock", "jsonpath": self.JSONPATH}, extra)

    def test_the_project_is_the_only_virtual_package_in_the_lock(self):
        lock = tomllib.loads(read("uv.lock"))
        virtual = [p["name"] for p in lock["package"] if "virtual" in p.get("source", {})]
        self.assertEqual(virtual, [PYPROJECT["project"]["name"]])


if __name__ == "__main__":
    unittest.main()
