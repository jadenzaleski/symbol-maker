"""Build the static site: every Lucide icon as a ready SF Symbols template.

    python3 -m symbolmaker.sitebuild --out dist

Downloads the latest `lucide-static`, converts each icon with SwiftDraw at Apple's weights, and writes into `--out`:

    templates/<symbol>.svg          the three-weight template (SF Symbols and Xcode read this)
    guides/<symbol>.json            its baseline, cap line, margins and outlines, for the page's preview
    zips/<symbol>.symbolset.zip     a <symbol>.symbolset folder for an Xcode asset catalog, plus the Lucide license
    icons/<name>.svg                the original icon (the list shows these)
    index.json, LICENSE-lucide.txt, .nojekyll, and the page itself (site/)

Needs `swiftdraw` on PATH (`brew install swiftdraw`) and network access to the npm registry.
"""
import argparse
import datetime
import functools
import io
import json
import re
import shutil
import subprocess
import sys
import webbrowser
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine.convert import find_swiftdraw
from .engine.guides import parse_template
from .engine.pipeline import make_template
from .engine.symbolset import contents_json
from .lucide import download_latest

# Apple's weight progression, measured from `sfsymbols export circle` (ring thickness relative to Regular).
APPLE_ULTRA, APPLE_BLACK = 0.30, 1.90
ROOT = Path(__file__).resolve().parent.parent


class BuildError(RuntimeError):
    pass


def symbol_name(icon):
    return 'lucide.' + icon.replace('-', '.')


def convert_apple(svg):
    return make_template(svg, APPLE_ULTRA, APPLE_BLACK)


def stamp(template, icon, version):
    """Credit Lucide inside the template (ISC asks for the notice to travel with copies)."""
    comment = (f'<!-- Icon "{icon}" from Lucide (lucide-static v{version}), ISC License: see LICENSE-lucide.txt. '
               f'Converted to an SF Symbols template by Symbol Maker. -->\n')
    if template.startswith('<?xml'):
        end = template.index('?>') + 2
        return template[:end] + '\n' + comment + template[end:].lstrip('\n')
    return comment + template


def symbolset_zip(symbol, svg, license_text):
    """A zip holding `<symbol>.symbolset/` (what goes into an asset catalog) and the license beside it. Reproducible."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in ((f'{symbol}.symbolset/Contents.json', contents_json(symbol)),
                           (f'{symbol}.symbolset/{symbol}.svg', svg),
                           ('LICENSE-lucide.txt', license_text)):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, text)
    return buf.getvalue()


def swiftdraw_version():
    exe = find_swiftdraw()
    if not exe:
        return 'unknown'
    r = subprocess.run([exe, '--help'], capture_output=True, text=True, timeout=30)
    m = re.search(r'version (\d+\.\d+\.\d+)', r.stdout + r.stderr)
    return m.group(1) if m else 'unknown'


def build(out, release, convert=convert_apple, swiftdraw=None, site_dir=None, max_failed=0.02, limit=None, log=None):
    """Write the site into `out` (replacing it). Returns {'icons': n, 'failed': n}. Raises BuildError, leaving `out`
    untouched, when more than `max_failed` of the icons fail to convert."""
    out = Path(out)
    work = out.parent / (out.name + '.building')
    shutil.rmtree(work, ignore_errors=True)
    for d in ('templates', 'guides', 'zips', 'icons'):
        (work / d).mkdir(parents=True)
    names = release['names'][:limit] if limit else release['names']
    icons, failed = [], []
    for i, icon in enumerate(names, 1):
        svg = release['svgs'][icon]
        try:
            res = convert(svg)
            symbol = symbol_name(icon)
            template = stamp(res.template, icon, release['version'])
            guides = parse_template(template)
            zipped = symbolset_zip(symbol, template, release['license'])
        except (ValueError, OSError, KeyError, RuntimeError) as e:      # SwiftDrawError is a RuntimeError
            failed.append({'name': icon, 'error': str(e)})
            continue
        (work / 'templates' / f'{symbol}.svg').write_text(template, encoding='utf-8')
        (work / 'guides' / f'{symbol}.json').write_text(json.dumps(guides, separators=(',', ':')), encoding='utf-8')
        (work / 'zips' / f'{symbol}.symbolset.zip').write_bytes(zipped)
        (work / 'icons' / f'{icon}.svg').write_text(svg, encoding='utf-8')
        icons.append({'name': icon, 'symbol': symbol, 'status': res.status,
                      'layers': len({a.layer for a in res.assignments}), 'notes': list(res.notes)})
        if log and i % 250 == 0:
            log(f'{i}/{len(names)}')
    if len(failed) > max_failed * len(names):
        shutil.rmtree(work, ignore_errors=True)
        raise BuildError(f'{len(failed)} of {len(names)} icons failed to convert, so nothing was published. '
                         f'First: {failed[0]["name"]}: {failed[0]["error"]}')
    index = {'library': 'Lucide', 'version': release['version'], 'license': 'ISC',
             'swiftdraw': swiftdraw or 'unknown',
             'built': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
             'weights': {'ultralight': APPLE_ULTRA, 'black': APPLE_BLACK},
             'icons': icons, 'failed': failed}
    (work / 'index.json').write_text(json.dumps(index, separators=(',', ':')), encoding='utf-8')
    (work / 'LICENSE-lucide.txt').write_text(release['license'], encoding='utf-8')
    (work / '.nojekyll').write_text('', encoding='utf-8')
    if site_dir:
        for f in Path(site_dir).iterdir():
            if f.is_file():
                shutil.copy2(f, work / f.name)
    shutil.rmtree(out, ignore_errors=True)
    work.rename(out)
    return {'icons': len(icons), 'failed': len(failed)}


def make_preview_server(directory, port=8000):
    """A local web server for the built folder, reachable from this machine only."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    return ThreadingHTTPServer(('127.0.0.1', port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Symbol Maker site')
    ap.add_argument('--out', default='dist')
    ap.add_argument('--site', default=str(ROOT / 'site'), help='folder with the page (index.html, site.js, site.css)')
    ap.add_argument('--limit', type=int, help='only convert the first N icons (quick local runs)')
    ap.add_argument('--serve', action='store_true', help='after building, preview the site at http://127.0.0.1:8000')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args(argv)
    if not find_swiftdraw():
        sys.exit('swiftdraw is not installed. Install it with: brew install swiftdraw')
    print('Downloading the latest Lucide release…', flush=True)
    release = download_latest()
    print(f'Lucide {release["version"]}: {len(release["names"])} icons. Converting…', flush=True)
    summary = build(args.out, release, swiftdraw=swiftdraw_version(), site_dir=args.site, limit=args.limit,
                    log=lambda m: print(m, flush=True))
    print(f'Done: {summary["icons"]} icons, {summary["failed"]} failed. Wrote {args.out}/')
    if args.serve:
        srv = make_preview_server(args.out, args.port)
        url = f'http://127.0.0.1:{srv.server_address[1]}/'
        print(f'Preview: {url}  (Ctrl-C to stop)', flush=True)
        webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
