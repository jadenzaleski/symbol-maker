# Symbol Maker

Icons from [Lucide](https://lucide.dev), [Tabler Icons](https://tabler.io/icons), [Heroicons](https://heroicons.com),
[Sidekickicons](https://github.com/ndri/sidekickicons) and [Iconoir](https://iconoir.com) as ready-to-use **SF Symbols templates**, with Ultralight, Regular
and Black weights that line up the way Apple's do. The result is a static site on GitHub Pages: pick an icon set and an
icon, check it against the template's guides, and download either

- the **`.svg`** template: open it in the SF Symbols app, or drag it onto a *Symbol Image Set* in Xcode, or
- the **`.symbolset`** folder (zipped): drop it into an asset catalog.

Symbol names are prefixed with the set (`lucide.house`, `tabler.home`, `heroicons.home`, ...) so they never clash with
Apple's or with each other. Only the outline style of each set is included: it is drawn with strokes, so it can get real
weights. Layers and animations are tuned afterwards in the SF Symbols app; the templates ship with an automatic first
guess at the layers (a container is `secondary`, the rest `primary`).

## How it works

A GitHub Action on a macOS runner runs `./ci.sh`:

1. downloads the latest release of each set from the npm registry (checked against its published SHA-512; the sets are
   listed in `symbolmaker/sources.py`),
2. converts each icon with [SwiftDraw](https://github.com/swhitty/SwiftDraw), which expands the strokes at three widths
   (Apple's progression: Ultralight 0.30x, Black 1.90x of the Regular stroke),
3. lines the three outlines up node for node so SF Symbols can interpolate between them (`symbolmaker/engine/weights.py`),
4. guesses layers (`layers.py`) and writes the templates, previews and zips (`symbolmaker/sitebuild.py`).

Some icons need a little help: tiny stroked dots are drawn solid (a hole cannot appear and vanish between weights), and
an icon whose curves close up at Apple's Black weight gets the heaviest Black that still lines up, with a note on the
page. An icon whose weights still cannot be lined up is published with a note.

## Run it yourself

You need a Mac with Python 3 and [SwiftDraw](https://github.com/swhitty/SwiftDraw) (`brew install swiftdraw`). Xcode is
needed only for one test that compiles a sample catalog with `actool`.

```sh
./ci.sh                  # run the tests, then build the site into ./dist.nosync
./ci.sh --serve          # ... and preview it at http://127.0.0.1:8000
./ci.sh --limit 50       # only convert the first 50 icons of each set (quick)
./ci.sh --only tabler    # only build some sets (comma-separated)
OUT=somewhere ./ci.sh    # write the site somewhere other than ./dist.nosync
```

Conversions are cached in `./build-cache.nosync` (or `$CACHE`): an icon is converted again only if its SVG, the engine
code, the SwiftDraw version or the weights changed, so a rebuild after a new icon-set release takes seconds. Delete the
folder to start fresh.

That is exactly what the workflow runs. Only the Python standard library is used.

## Revisions and reporting a problem

Every template has a **revision** (`rev`, eight characters of a hash of the template) and an **updated** date: the day the
icon was last converted. Both appear on the page, in `<set>/index.json` and (the revision) in a comment inside the SVG.
An unchanged icon keeps its revision and date across builds, because its conversion is reused from the cache; they change
when the icon's SVG, the engine code, the weights or the SwiftDraw version change. (If the cache is lost, dates restart
at the next build; revisions stay the same.)

On each icon, **Report a problem** opens a GitHub issue from the form in `.github/ISSUE_TEMPLATE/icon-problem.yml`, already
filled in with the icon set, the icon, its revision and notes, and the build (engine and SwiftDraw versions).

## Publishing

In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**. The workflow in
`.github/workflows/pages.yml` then builds and deploys on every push to `master`, every Monday, and on demand.

The workflow installs whatever SwiftDraw version Homebrew has; the version used is recorded in `sources.json` and shown on
the page. Dependabot (`.github/dependabot.yml`) opens a weekly pull request for newer versions of the GitHub Actions the
workflow uses; the Python code has no third-party dependencies (`pyproject.toml` declares the Python version, 3.12+).

## Licenses

The code in this repository is under the GPL-3.0 license (see `LICENSE`).

Each icon set keeps its own license (Lucide: ISC; Tabler Icons, Heroicons, Sidekickicons and Iconoir: MIT). The notice is on the
site, in every download and in each template as a comment. SF Symbols is a trademark of Apple Inc.; this project is not affiliated with Apple.
