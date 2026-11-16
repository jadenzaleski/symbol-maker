# Symbol Maker

**Popular open-source icon sets as custom SF Symbols, ready for Xcode and the SF Symbols app.**

### [Open Symbol Maker](https://jadenzaleski.github.io/symbol-maker/)

Over 9,000 icons from [Lucide](https://lucide.dev), [Tabler Icons](https://tabler.io/icons), [Heroicons](https://heroicons.com),
[Iconoir](https://iconoir.com) and [Sidekickicons](https://github.com/ndri/sidekickicons), each converted into an SF Symbols
template with **Ultralight, Regular and Black weights** that line up the way Apple's do. They get lighter and bolder with the
font weight and Bold Text, just like system symbols.

## What you can do

- **Search and preview** every icon against the template's baseline, cap height and margins.
- **Tune the layers** before you download: reorder them, regroup strokes, set each layer's level and color, and see the
  order SF Symbols will animate them in.
- **Download** one symbol as an `.svg` template or as a `.symbolset` folder.
- **Collect symbols in a project** (with your layer edits) and export the whole set as an Xcode asset catalog.
- **Take a whole icon set** at once: every [release](https://github.com/jadenzaleski/symbol-maker/releases/latest) has one zip per set.

## Using a symbol

1. Pick an icon set and an icon on the [site](https://jadenzaleski.github.io/symbol-maker/).
2. Optionally adjust its layers in the panel on the right.
3. Download it:
   - the **`.svg`** template: open it in the SF Symbols app, or drag it onto a *Symbol Image Set* in Xcode;
   - the **`.symbolset`** folder (zipped): drop it into an asset catalog.

Symbol names start with the set (`lucide.house`, `tabler.home`, `heroicons.home`, ...), so they never clash with Apple's or
with each other. Only each set's outline style is included, because outlines are drawn with strokes and can get real weights.

## Good to know

- Conversion is automatic, and a few icons can't be lined up perfectly across weights. Those are marked in the list with a
  note saying why. If one looks wrong, **Report a problem** on the icon opens a GitHub issue already filled in.
- Your layer edits and projects stay in your browser. Nothing is uploaded, and clearing the site's data deletes them, so
  export what you want to keep.
- Layers and weights are only half of an animation: the timing is set in the SF Symbols app.

## Icon sets and licenses

| Set | License |
| --- | --- |
| [Lucide](https://lucide.dev) | ISC |
| [Tabler Icons](https://tabler.io/icons) | MIT |
| [Heroicons](https://heroicons.com) | MIT |
| [Iconoir](https://iconoir.com) | MIT |
| [Sidekickicons](https://github.com/ndri/sidekickicons) | MIT |

Each set keeps its own license. The notice is on the site, in every download and in each template as a comment.

The code in this repository is under the GPL-3.0 license (see [`LICENSE`](LICENSE)). SF Symbols is a trademark of Apple Inc.;
this project is not affiliated with Apple.

## Contributing

Bug reports, icon problems and ideas are welcome as [issues](https://github.com/jadenzaleski/symbol-maker/issues). To run the
build yourself, see how it works, or make a change, read [CONTRIBUTING.md](CONTRIBUTING.md).
