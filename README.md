# Symbol Maker

Every [Lucide](https://lucide.dev) icon as a ready-to-use **SF Symbols template**, with Ultralight, Regular and Black
weights that line up the way Apple's do. The result is a static site on GitHub Pages: pick an icon, check it against the
template's guides, and download either

- the **`.svg`** template: open it in the SF Symbols app, or drag it onto a *Symbol Image Set* in Xcode, or
- the **`.symbolset`** folder (zipped): drop it into an asset catalog.

Layers and animations are tuned afterwards in the SF Symbols app. The templates ship with an automatic first guess at the
layers (a container is `secondary`, the rest `primary`) as a starting point.

## How it works

A GitHub Action on a macOS runner runs `./ci.sh`:

1. downloads the latest `lucide-static` from the npm registry (checked against its published SHA-512),
2. converts each icon with [SwiftDraw](https://github.com/swhitty/SwiftDraw), which expands the strokes at three widths
   (Apple's progression: Ultralight 0.30x, Black 1.90x of the Regular stroke),
3. lines the three outlines up node for node so SF Symbols can interpolate between them (`symbolmaker/engine/weights.py`),
4. guesses layers (`layers.py`) and writes the templates, previews and zips (`symbolmaker/sitebuild.py`).

Icons whose three weights cannot be aligned exactly are still published, with a note on the page.

## Run it yourself

You need a Mac with Python 3 and [SwiftDraw](https://github.com/swhitty/SwiftDraw) (`brew install swiftdraw`). Xcode is
needed only for one test that compiles a sample catalog with `actool`.

```sh
./ci.sh                  # run the tests, then build the site into ./dist
./ci.sh --serve          # ... and preview it at http://127.0.0.1:8000
./ci.sh --limit 50       # only convert the first 50 icons (quick)
```

That is exactly what the workflow runs. Only the Python standard library is used.

## Publishing

In the repository's **Settings → Pages**, set **Source** to **GitHub Actions**. The workflow in
`.github/workflows/pages.yml` then builds and deploys on every push to `master`, every Monday, and on demand.

The workflow installs whatever SwiftDraw version Homebrew has; the version used is recorded in `index.json` and shown on
the page.

## Licenses

The code in this repository is under the GPL-3.0 license (see `LICENSE`).

The icons are from Lucide (ISC License). Its notice is included on the site (`LICENSE-lucide.txt`), in every download, and
in each template as a comment. SF Symbols is a trademark of Apple Inc.; this project is not affiliated with Apple.
