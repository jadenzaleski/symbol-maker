"""What goes on a GitHub release besides the notes: the built templates, packed so that they fit.

A release can hold at most 1000 files, and there are thousands of templates, so each icon set becomes one zip:

    <set>.zip
        <set>/templates/<symbol>.svg                       every template, for the SF Symbols app
        <set>/<set>.xcassets/<symbol>.symbolset/...        the same symbols as an Xcode asset catalog
        <set>/LICENSE-<set>.txt

with `build-info.json` (what the site's sources.json says about this build) and `SHA256SUMS.txt` beside them. The names carry
no version, so https://github.com/<repo>/releases/latest/download/<name> always means the newest release. Zips are
reproducible: the same site gives the same bytes.

    python3 -m symbolmaker.release_assets assets --site dist.nosync --out release-assets
    gh release view TAG --json body --jq .body | python3 -m symbolmaker.release_assets notes --site dist.nosync
"""
import argparse
import hashlib
import json
import os
import sys
import zipfile
from pathlib import Path

from .engine.symbolset import contents_json

START, END = '<!-- symbol-maker:build -->', '<!-- /symbol-maker:build -->'
DEFAULT_REPO = 'jadenzaleski/symbol-maker'
DATE = (2020, 1, 1, 0, 0, 0)


def _write_zip(path, entries):
    """entries: [(name in the zip, bytes)]."""
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            info = zipfile.ZipInfo(name, date_time=DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, data)


def build_assets(site, out):
    """Write the release files for the built `site` into the new folder `out`. -> [Path], sorted by name."""
    site, out = Path(site), Path(out)
    sources_json = site / 'sources.json'
    if not sources_json.is_file():
        raise ValueError(f'{site} has no sources.json: build the site first.')
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'{out} is not empty.')
    meta = json.loads(sources_json.read_text(encoding='utf-8'))
    out.mkdir(parents=True, exist_ok=True)
    for src in meta['sources']:
        sid = src['id']
        templates = sorted((site / sid / 'templates').glob('*.svg'))
        if not templates:
            raise ValueError(f'{sid} has no templates in {site}.')
        lic_path = site / sid / 'LICENSE.txt'
        lic = lic_path.read_bytes() if lic_path.is_file() else b''
        svgs = [(p.stem, p.read_bytes()) for p in templates]
        entries = [(f'{sid}/LICENSE-{sid}.txt', lic)] + [(f'{sid}/templates/{sym}.svg', data) for sym, data in svgs]
        entries.append((f'{sid}/{sid}.xcassets/Contents.json', json.dumps({'info': {'author': 'xcode', 'version': 1}}, indent=2).encode()))
        for sym, data in svgs:
            entries += [(f'{sid}/{sid}.xcassets/{sym}.symbolset/Contents.json', contents_json(sym).encode()),
                        (f'{sid}/{sid}.xcassets/{sym}.symbolset/{sym}.svg', data)]
        _write_zip(out / f'{sid}.zip', entries)
    (out / 'build-info.json').write_bytes(sources_json.read_bytes())
    others = sorted(p for p in out.iterdir())
    sums = ''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in others)
    (out / 'SHA256SUMS.txt').write_text(sums, encoding='utf-8')
    return sorted(out.iterdir(), key=lambda p: p.name)


def notes_block(meta, repo=DEFAULT_REPO):
    """The part of the release notes that says what is in the zips: the icon sets and their versions, and how it was made."""
    rows = ''.join(f'| {s["title"]} | {s["version"]} | {s["count"]:,} | {s["license"]} |\n' for s in meta['sources'])
    w = meta.get('weights', {})
    made = (f'Converted with SwiftDraw {meta["swiftdraw"]} at Apple\'s weights (Ultralight {w.get("ultralight", 0):.2f}×, '
            f'Black {w.get("black", 0):.2f}× the Regular stroke), engine `{meta["engine"]}`')
    if meta.get('commit') and not meta.get('dirty'):
        made += f', from commit [`{meta["commit"][:7]}`](https://github.com/{repo}/commit/{meta["commit"]})'
    files = ''.join(f'- {s["title"]}: `{s["id"]}.zip`\n' for s in meta['sources'])
    return (f'{START}\n### Templates in this release\n\n| Icon set | Version | Icons | License |\n| --- | --- | --- | --- |\n{rows}\n{made}.\n\n'
            f'Each icon set is one zip. In it, `templates/` holds the plain `.svg` templates (for the SF Symbols app) and '
            f'`<set>.xcassets` the same symbols as an Xcode asset catalog; the set\'s license is in there too.\n\n{files}\n'
            f'`SHA256SUMS.txt` has the checksums and `build-info.json` the full description of the build.\n{END}\n')


def merge_notes(body, block):
    """`body` (the release notes so far) with `block` at the end; if an earlier block is there it is replaced, so running
    this again after a rebuild updates the notes instead of repeating them."""
    block = block.strip()
    body = body or ''
    if START in body and END in body:
        head, rest = body.split(START, 1)
        tail = rest.split(END, 1)[1]
        return head + block + tail
    return (body.rstrip() + '\n\n' if body.strip() else '') + block + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description='Release files for a built site.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('assets', help='write the zips and checksums')
    a.add_argument('--site', default='dist.nosync'); a.add_argument('--out', default='release-assets')
    n = sub.add_parser('notes', help='read the release notes on stdin, print them with the build block added or updated')
    n.add_argument('--site', default='dist.nosync'); n.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY', DEFAULT_REPO))
    args = ap.parse_args(argv)
    try:
        if args.cmd == 'assets':
            for p in build_assets(args.site, args.out):
                print(f'{p.stat().st_size / 1e6:8.1f} MB  {p.name}')
        else:
            meta = json.loads((Path(args.site) / 'sources.json').read_text(encoding='utf-8'))
            sys.stdout.write(merge_notes(sys.stdin.read(), notes_block(meta, args.repo)))
    except (ValueError, OSError) as e:
        sys.exit(str(e))


if __name__ == '__main__':
    main()
