# Contributing

Thanks for helping. This page covers how the site is built, how to run it yourself (with its code checks), and how changes become releases.

## How it works

A GitHub Action on a macOS runner runs `./ci.sh`, which

1. downloads the latest release of each icon set from the npm registry (checked against its published SHA-512; the sets are
   listed in `symbolmaker/sources.py`),
2. converts each icon with [SwiftDraw](https://github.com/swhitty/SwiftDraw), which expands the strokes at three widths
   (Apple's progression: Ultralight 0.30x, Black 1.90x of the Regular stroke); `symbolmaker/engine/variants.py` explains
   what happens when SwiftDraw 0.30 or later refuses an icon (below),
3. lines the three outlines up node for node so SF Symbols can interpolate between them (`symbolmaker/engine/weights.py`),
4. guesses layers (`layers.py`: a container is `secondary`, the rest `primary`) and writes the templates, previews and zips
   (`symbolmaker/sitebuild.py`).

Some icons need a little help. Tiny stroked dots are drawn solid, because a hole cannot appear and vanish between weights.
An icon whose curves close up at Apple's Black weight gets the heaviest Black that still lines up, with a note on the page.
A hole that still closes up at Black is left out of all three weights (a hole cannot appear and vanish between weights), with a note
saying how many.
An icon whose weights still cannot be lined up is published with a note.

SwiftDraw 0.30 added a check that refuses to write a template whose three weights differ in structure (SF Symbols would crash
drawing it), and exits with *Variants are not interpolatable*. Lining those weights up is our aligner's job, so it needs
them written out. When SwiftDraw refuses, `variants.py` runs it once per weight on the SVG with its strokes scaled to that
weight, which it has no reason to refuse, and puts the three outlines together itself. Icons SwiftDraw accepts are untouched,
and 0.29 (which never refused) works too. A test checks that the weights made this way are where and as big as SwiftDraw's own.

The page is plain HTML, CSS and JavaScript in `site/` with no build step:

| File | What it does |
| --- | --- |
| `site/layers.js` | the layer model and how it is written into a template (no DOM, so Node tests it) |
| `site/original.js` | reads the original icon and places it on the template, for the Original card and the overlay (no DOM, so Node tests it) |
| `site/editor.js` | the Layers panel and its preview |
| `site/projects.js`, `site/projects-ui.js` | projects: the model and export, and the page for them |
| `site/zip.js` | a small zip writer for edited downloads and exports |
| `site/info.js` | the (i) buttons and all their texts |
| `site/site.js` | the icon list, the preview, the build line and the rest |

## Run it yourself

You need a Mac with [uv](https://docs.astral.sh/uv/) (`brew install uv`) and [SwiftDraw](https://github.com/swhitty/SwiftDraw)
(`brew install swiftdraw`). uv installs the right Python (3.12) and the dev tools for you; the program itself uses only the
standard library. Node (for the page's JavaScript tests) is optional, and Xcode is only needed for the tests that compile a
sample catalog with `actool`.

```sh
./ci.sh                  # check the code, run the tests, then build the site into ./dist.nosync
./ci.sh --serve          # ... and preview it at http://127.0.0.1:8000
./ci.sh --limit 50       # only convert the first 50 icons of each set (quick)
./ci.sh --only tabler    # only build some sets (comma-separated)
OUT=somewhere ./ci.sh    # write the site somewhere other than ./dist.nosync
```

Conversions are cached in `./build-cache.nosync` (or `$CACHE`): an icon is converted again only if its SVG, the engine code,
the SwiftDraw version or the weights changed, so a rebuild after a new icon-set release takes seconds. Delete the folder to
start fresh. The `.nosync` names keep iCloud from syncing build output if the folder lives on a synced Desktop.

To try the release zips locally, after a build:
`uv run python -m symbolmaker.release_assets assets --site dist.nosync --out release-assets`.

### Code checks

`./ci.sh` (and both workflows, through it) stops before building if any of these fail, so they are enforced, not advisory:

| Check | What it does | Fix |
| --- | --- | --- |
| `uv run ruff check .` | lint: pycodestyle, pyflakes, import order, likely bugs, modern syntax, simplifications | `uv run ruff check --fix .` for what can be fixed automatically |
| `uv run ruff format --check .` | the code is formatted the way `ruff format` writes it (120 columns) | `uv run ruff format .` |
| `uv run ty check` | type checking with [ty](https://docs.astral.sh/ty/) | fix the code; use `# ty: ignore[rule]` only with a reason |

They are configured in `pyproject.toml`, and `uv run --locked` refuses to run if `uv.lock` is out of date, so after changing
the dev tools run `uv lock` and commit the result. Dependabot updates ruff and ty weekly. If this folder is on an iCloud-synced
Desktop, keep the virtual environment out of iCloud with `export UV_PROJECT_ENVIRONMENT=.venv.nosync`.

## Revisions and fingerprints

Every template has a **revision** (`rev`, eight characters of a hash of the template) and an **updated** date: the day the
icon was last converted. Both appear on the page, in `<set>/index.json` and (the revision) in a comment inside the SVG. An
unchanged icon keeps its revision and date across builds, because its conversion is reused from the cache. They change when
the icon's SVG, the engine code, the weights or the SwiftDraw version change.

`rev` and the build line's `engine` are fingerprints of content (the template; the engine code plus the SwiftDraw version),
not git commits. The build line also names the git **commit** the site was built from and links it, and links the engine to
the engine code at that commit. A local build with uncommitted changes shows its commit without links, since they would
point at different code.

**Report a problem** on an icon opens an issue from `.github/ISSUE_TEMPLATE/icon-problem.yml`, filled in with the icon set,
the icon, its revision and notes, and the build.

## Commits and releases

The site is published to GitHub Pages **only when a release is made**, so what is live is always a numbered version. Pushes
and pull requests (and a run every Monday, to notice upstream icon changes that break a conversion) only test and build:
`.github/workflows/ci.yml`.

Versions follow [Semantic Versioning](https://semver.org) and are made by [release-please](https://github.com/googleapis/release-please)
from [Conventional Commits](https://www.conventionalcommits.org), so please write commit messages like this:

| Commit | Bumps | Example |
| --- | --- | --- |
| `fix: ...` | patch | `fix: keep the Black weight from closing up in donut` |
| `feat: ...` | minor | `feat: add Phosphor` |
| `feat!: ...` or a `BREAKING CHANGE:` footer | major (minor while below 1.0) | `feat!: rename symbols to <set>.<name>.<style>` |
| `docs:`, `perf:`, `revert:` | listed in the changelog, patch | |
| `chore:`, `ci:`, `test:`, `build:`, `refactor:`, `style:` | no release by themselves | |

Breaking means anything that makes a symbol someone already uses stop working: a changed or removed symbol name, a removed
icon set, or a change to how the template is laid out. A new icon set or a new feature is a minor release.

How a release happens:

1. Commits land on `master`. release-please keeps a pull request open (*chore(master): release x.y.z*) that adds them to
   `CHANGELOG.md` and bumps the version in `pyproject.toml`.
2. Merging that pull request tags `vx.y.z` and creates the GitHub release. In the same run (`release.yml`) the site is built,
   the templates are attached to the release, the release notes get a table of the icon sets and versions in them, and the
   site is deployed to Pages.

Attached to every release, with names that do not change, so
`https://github.com/jadenzaleski/symbol-maker/releases/latest/download/<name>` always means the newest release (a release
cannot hold thousands of files, so each icon set is one zip):

- `<set>.zip` (`lucide.zip`, `tabler.zip`, ...), which holds `<set>/templates/` (every template as a plain `.svg`, for the
  SF Symbols app), `<set>/<set>.xcassets` (the same symbols as an Xcode asset catalog, one `.symbolset` each) and the set's license.
- `SHA256SUMS.txt` and `build-info.json` (the icon set versions, SwiftDraw version, engine and commit that made it).

The templates are built from the newest version of each icon set at the time of the release, so a release records which
versions it contains (in its notes) rather than pinning them.

### One-time repository setup

- **Settings → Pages → Source**: *GitHub Actions*.
- **Settings → Actions → General → Workflow permissions**: *Read and write permissions*, and tick *Allow GitHub Actions to
  create and approve pull requests*. Without these release-please cannot open its pull request.
- Pull requests that release-please opens with the default token do not start other workflows, so `ci.yml` does not run on
  the release pull request (it only changes the version and the changelog). A personal access token fixes that if you want it.

If a release's deploy fails, run **Release** by hand from the Actions tab with that tag: it builds and publishes it again
(files already attached are replaced). The first release will be `0.1.0` (the version starts at `0.0.0`, and below 1.0 a
feature is a minor bump); to make a particular version, put `Release-As: 1.0.0` in the footer of a commit message.

The workflows install whatever SwiftDraw version Homebrew has; the version used is recorded in `sources.json` and shown on
the page. Dependabot (`.github/dependabot.yml`) opens a weekly pull request for newer versions of the GitHub Actions the
workflows use and of the dev tools in `uv.lock`.
