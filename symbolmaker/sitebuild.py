"""Build the static site: every icon of each source as a ready SF Symbols template.

    python3 -m symbolmaker.sitebuild --out dist

Downloads the latest release of each icon set (see sources.py), converts each icon with SwiftDraw at Apple's weights, and
writes, for every source `<id>` into `--out`:

    <id>/templates/<symbol>.svg          the three-weight template (SF Symbols and Xcode read this)
    <id>/guides/<symbol>.json            its baseline, cap line, margins and outlines, for the page's preview
    <id>/zips/<symbol>.symbolset.zip     a <symbol>.symbolset folder for an Xcode asset catalog, plus the license
    <id>/icons/<name>.svg                the original icon (the list shows these)
    <id>/index.json, <id>/LICENSE.txt

plus `sources.json`, `.nojekyll` and the page itself (site/).

Needs `swiftdraw` on PATH (`brew install swiftdraw`) and network access to the npm registry.
"""
import argparse
import datetime
import functools
import io
import json
import os
import re
import shutil
import subprocess
import sys
import webbrowser
import zipfile
from concurrent.futures import ProcessPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine.convert import find_swiftdraw
from .engine.guides import parse_template
from .engine.pipeline import make_template
from .engine.symbolset import contents_json
from .sources import SOURCES, load, symbol_name

# Apple's weight progression, measured from `sfsymbols export circle` (ring thickness relative to Regular).
APPLE_ULTRA, APPLE_BLACK = 0.30, 1.90
ROOT = Path(__file__).resolve().parent.parent


class BuildError(RuntimeError):
    pass


def convert_apple(svg):
    return make_template(svg, APPLE_ULTRA, APPLE_BLACK)


def stamp(template, source, icon, version, license_name):
    """Credit the icon set inside the template (its license asks for the notice to travel with copies)."""
    text = f'Icon "{icon}" from {source.title} (v{version}), {license_name} License: see LICENSE-{source.id}.txt. ' \
           'Converted to an SF Symbols template by Symbol Maker.'
    comment = '<!-- ' + re.sub(r'-{2,}', '-', text) + ' -->\n'      # "--" is not allowed inside an XML comment
    if template.startswith('<?xml'):
        end = template.index('?>') + 2
        return template[:end] + '\n' + comment + template[end:].lstrip('\n')
    return comment + template


def symbolset_zip(symbol, svg, license_text, license_file):
    """A zip holding `<symbol>.symbolset/` (what goes into an asset catalog) and the license beside it. Reproducible."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in ((f'{symbol}.symbolset/Contents.json', contents_json(symbol)),
                           (f'{symbol}.symbolset/{symbol}.svg', svg),
                           (license_file, license_text)):
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


def _run(convert, svg):
    """Convert one icon. Returns ('ok', template, status, layers, notes, problem) or ('err', message); never raises, so a worker
    process can hand a failure back instead of dying."""
    try:
        r = convert(svg)
        return ('ok', r.template, r.status, len({a.layer for a in r.assignments}), list(r.notes), bool(r.problem))
    except Exception as e:                                   # one bad icon must not stop the build
        return ('err', str(e) or e.__class__.__name__)


def _convert_all(svgs, convert, jobs):
    if jobs > 1 and convert is convert_apple:               # processes need a function they can import
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            return list(pool.map(functools.partial(_run, convert), svgs, chunksize=16))
    return [_run(convert, s) for s in svgs]


def _write_source(work, source, rel, convert, max_failed, limit, jobs, log):
    base = work / source.id
    for d in ('templates', 'guides', 'zips', 'icons'):
        (base / d).mkdir(parents=True)
    names = rel['names'][:limit] if limit else rel['names']
    license_file = f'LICENSE-{source.id}.txt'
    icons, failed = [], []
    results = _convert_all([rel['svgs'][n] for n in names], convert, jobs)
    for icon, res in zip(names, results):
        if res[0] == 'err':
            failed.append({'name': icon, 'error': res[1]})
            continue
        _, template, status, layers, notes, problem = res
        symbol = symbol_name(source, icon)
        try:
            template = stamp(template, source, icon, rel['version'], rel['license_name'])
            guides = parse_template(template)
            zipped = symbolset_zip(symbol, template, rel['license'], license_file)
        except (ValueError, OSError, KeyError) as e:
            failed.append({'name': icon, 'error': str(e)})
            continue
        (base / 'templates' / f'{symbol}.svg').write_text(template, encoding='utf-8')
        (base / 'guides' / f'{symbol}.json').write_text(json.dumps(guides, separators=(',', ':')), encoding='utf-8')
        (base / 'zips' / f'{symbol}.symbolset.zip').write_bytes(zipped)
        (base / 'icons' / f'{icon}.svg').write_text(rel['svgs'][icon], encoding='utf-8')
        entry = {'name': icon, 'symbol': symbol, 'status': status, 'layers': layers, 'notes': notes}
        if problem or notes:                          # what the list shows next to the icon
            entry['flag'] = 'problem' if problem else 'note'
        icons.append(entry)
    if len(failed) > max_failed * len(names):
        raise BuildError(f'{source.id}: {len(failed)} of {len(names)} icons failed to convert, so nothing was published. '
                         f'First: {failed[0]["name"]}: {failed[0]["error"]}')
    (base / 'index.json').write_text(json.dumps({'icons': icons, 'failed': failed}, separators=(',', ':')), encoding='utf-8')
    (base / 'LICENSE.txt').write_text(rel['license'], encoding='utf-8')
    if log:
        log(f'{source.title}: {len(icons)} icons, {len(failed)} failed')
    return {'icons': len(icons), 'failed': len(failed)}


def build(out, items, convert=convert_apple, swiftdraw=None, site_dir=None, max_failed=0.02, limit=None, jobs=1, log=None):
    """Write the site into `out` (replacing it) from [(Source, release), ...]. Returns {source id: {'icons', 'failed'}}.
    Raises BuildError, leaving `out` untouched, when more than `max_failed` of any source's icons fail to convert."""
    out = Path(out)
    work = out.parent / (out.name + '.building')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        summary, listing = {}, []
        for source, rel in items:
            summary[source.id] = _write_source(work, source, rel, convert, max_failed, limit, jobs, log)
            listing.append({'id': source.id, 'title': source.title, 'version': rel['version'], 'license': rel['license_name'],
                            'homepage': source.homepage, 'count': summary[source.id]['icons'],
                            'failed': summary[source.id]['failed']})
        (work / 'sources.json').write_text(json.dumps({
            'built': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'swiftdraw': swiftdraw or 'unknown', 'weights': {'ultralight': APPLE_ULTRA, 'black': APPLE_BLACK},
            'sources': listing}, separators=(',', ':')), encoding='utf-8')
        (work / '.nojekyll').write_text('', encoding='utf-8')
        if site_dir:
            shutil.copytree(site_dir, work, dirs_exist_ok=True)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    shutil.rmtree(out, ignore_errors=True)
    work.rename(out)
    return summary


def make_preview_server(directory, port=8000):
    """A local web server for the built folder, reachable from this machine only."""
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(directory))
    return ThreadingHTTPServer(('127.0.0.1', port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Symbol Maker site')
    ap.add_argument('--out', default='dist')
    ap.add_argument('--site', default=str(ROOT / 'site'), help='folder with the page (index.html, site.js, site.css)')
    ap.add_argument('--only', help=f'comma-separated sources to build (default: all of {", ".join(SOURCES)})')
    ap.add_argument('--limit', type=int, help='only convert the first N icons of each source (quick local runs)')
    ap.add_argument('--jobs', type=int, default=os.cpu_count() or 1, help='conversion processes (default: all cores)')
    ap.add_argument('--serve', action='store_true', help='after building, preview the site at http://127.0.0.1:8000')
    ap.add_argument('--port', type=int, default=8000)
    args = ap.parse_args(argv)
    if not find_swiftdraw():
        sys.exit('swiftdraw is not installed. Install it with: brew install swiftdraw')
    ids = args.only.split(',') if args.only else list(SOURCES)
    unknown = [i for i in ids if i not in SOURCES]
    if unknown:
        sys.exit(f'Unknown source: {", ".join(unknown)}. Choose from: {", ".join(SOURCES)}')
    items = []
    for i in ids:
        print(f'Downloading {SOURCES[i].title}…', flush=True)
        rel = load(SOURCES[i])
        print(f'  v{rel["version"]}: {len(rel["names"])} icons', flush=True)
        items.append((SOURCES[i], rel))
    print('Converting…', flush=True)
    summary = build(args.out, items, swiftdraw=swiftdraw_version(), site_dir=args.site, limit=args.limit, jobs=args.jobs,
                    log=lambda m: print('  ' + m, flush=True))
    print(f'Done. Wrote {args.out}/')
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
