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
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
import zipfile
from concurrent.futures import ProcessPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .engine.convert import find_swiftdraw
from .engine.guides import parse_template
from .engine.pipeline import make_template
from .engine.symbolset import contents_json
from .progress import NullReporter, Reporter, fmt_count, fmt_duration
from .sources import SOURCES, load, symbol_name

# Apple's weight progression, measured from `sfsymbols export circle` (ring thickness relative to Regular).
APPLE_ULTRA, APPLE_BLACK = 0.30, 1.90
ROOT = Path(__file__).resolve().parent.parent


class BuildError(RuntimeError):
    pass


def engine_id(fingerprint):
    """A short, stable name for an engine fingerprint (shown on the page and in issue reports)."""
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:8]


def engine_fingerprint(swiftdraw):
    """Identifies everything a converted icon depends on besides its own SVG: the engine code, the weights and the
    SwiftDraw version. When it changes, every cached conversion is stale."""
    h = hashlib.sha256()
    for f in sorted((ROOT / 'symbolmaker' / 'engine').glob('*.py')):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    h.update(f'weights {APPLE_ULTRA} {APPLE_BLACK}; swiftdraw {swiftdraw}; cache format 2'.encode())
    return h.hexdigest()


class ConvertCache:
    """Conversion results kept between builds, one gzip file per source, keyed by the hash of the icon's SVG.
    A file written under a different fingerprint, or damaged, is treated as empty. Only successes are kept."""

    def __init__(self, directory, fingerprint):
        self.directory, self.fingerprint = Path(directory), fingerprint

    @staticmethod
    def key(svg):
        return hashlib.sha256(svg.encode('utf-8')).hexdigest()

    def _path(self, source_id):
        return self.directory / f'{source_id}.json.gz'

    def load(self, source_id):
        try:
            with gzip.open(self._path(source_id), 'rt', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('fingerprint') != self.fingerprint:
                return {}
            return {k: ('ok', *v) for k, v in data['entries'].items()}
        except (OSError, ValueError, KeyError, TypeError, EOFError):
            return {}

    def save(self, source_id, entries):
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self._path(source_id)
        tmp = target.with_suffix('.tmp')
        payload = {'fingerprint': self.fingerprint, 'entries': {k: list(v[1:]) for k, v in entries.items()}}
        with gzip.GzipFile(tmp, 'wb', mtime=0) as f:
            f.write(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
        os.replace(tmp, target)


def convert_apple(svg):
    return make_template(svg, APPLE_ULTRA, APPLE_BLACK)


def stamp(template, source, icon, version, license_name, rev=None):
    """Credit the icon set inside the template (its license asks for the notice to travel with copies)."""
    text = f'Icon "{icon}" from {source.title} (v{version}), {license_name} License: see LICENSE-{source.id}.txt. ' \
           'Converted to an SF Symbols template by Symbol Maker.' + (f' Template rev {rev}.' if rev else '')
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


def _convert_all(svgs, convert, jobs, on_done=None):
    """Results in input order. `on_done()` is called once per finished icon, as it finishes."""
    out = []
    if jobs > 1 and convert is convert_apple:               # processes need a function they can import
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            for r in pool.map(functools.partial(_run, convert), svgs, chunksize=2):
                out.append(r)
                if on_done:
                    on_done()
        return out
    for svg in svgs:
        out.append(_run(convert, svg))
        if on_done:
            on_done()
    return out


def _write_source(work, source, rel, convert, max_failed, limit, jobs, reporter, today, cache=None):
    base = work / source.id
    for d in ('templates', 'guides', 'zips', 'icons'):
        (base / d).mkdir(parents=True)
    names = rel['names'][:limit] if limit else rel['names']
    license_file = f'LICENSE-{source.id}.txt'
    svgs = [rel['svgs'][n] for n in names]
    keys = [ConvertCache.key(v) for v in svgs]
    known = cache.load(source.id) if cache else {}
    todo = [i for i, k in enumerate(keys) if k not in known]
    cached = len(names) - len(todo)
    reporter.start(source.title, len(names), cached)
    if cached:
        reporter.advance(cached)
    fresh = dict(zip(todo, _convert_all([svgs[i] for i in todo], convert, jobs, reporter.advance)))
    # ('ok', template, status, layers, notes, problem, date): a reused entry keeps the day it was converted
    results = [(fresh[i] + (today,) if fresh[i][0] == 'ok' else fresh[i]) if i in fresh else known[k]
               for i, k in enumerate(keys)]
    kept = {k: r for k, r in zip(keys, results) if r[0] == 'ok'}          # failures are retried next time
    icons, failed = [], []
    for icon, res in zip(names, results):
        if res[0] == 'err':
            failed.append({'name': icon, 'error': res[1]})
            continue
        _, template, status, layers, notes, problem, updated = res
        symbol = symbol_name(source, icon)
        rev = hashlib.sha256(template.encode('utf-8')).hexdigest()[:8]
        try:
            stamped = stamp(template, source, icon, rel['version'], rel['license_name'], rev)
            guides = parse_template(stamped)
            zipped = symbolset_zip(symbol, stamped, rel['license'], license_file)
        except (ValueError, OSError, KeyError) as e:
            failed.append({'name': icon, 'error': str(e)})
            continue
        (base / 'templates' / f'{symbol}.svg').write_text(stamped, encoding='utf-8')
        (base / 'guides' / f'{symbol}.json').write_text(json.dumps(guides, separators=(',', ':')), encoding='utf-8')
        (base / 'zips' / f'{symbol}.symbolset.zip').write_bytes(zipped)
        (base / 'icons' / f'{icon}.svg').write_text(rel['svgs'][icon], encoding='utf-8')
        entry = {'name': icon, 'symbol': symbol, 'status': status, 'layers': layers, 'notes': notes,
                 'rev': rev, 'updated': updated}
        if problem or notes:                          # what the list shows next to the icon
            entry['flag'] = 'problem' if problem else 'note'
        icons.append(entry)
    stats = {'icons': len(icons), 'failed': len(failed), 'cached': cached, 'reused': cached,
             'problems': sum(1 for i in icons if i.get('flag') == 'problem'),
             'notes': sum(1 for i in icons if i.get('flag') == 'note')}
    stats['seconds'] = reporter.done(stats)
    if len(failed) > max_failed * len(names):
        raise BuildError(f'{source.id}: {len(failed)} of {len(names)} icons failed to convert, so nothing was published. '
                         f'First: {failed[0]["name"]}: {failed[0]["error"]}')
    (base / 'index.json').write_text(json.dumps({'icons': icons, 'failed': failed}, separators=(',', ':')), encoding='utf-8')
    (base / 'LICENSE.txt').write_text(rel['license'], encoding='utf-8')
    return stats, kept


def build(out, items, convert=convert_apple, swiftdraw=None, site_dir=None, max_failed=0.02, limit=None, jobs=1,
          reporter=None, cache=None, today=None):
    """Write the site into `out` (replacing it) from [(Source, release), ...]. Returns {source id: {'icons', 'failed'}}.
    Raises BuildError, leaving `out` untouched, when more than `max_failed` of any source's icons fail to convert.
    With a `cache` (a ConvertCache), icons already converted under the same fingerprint are not converted again; the
    cache is written only once the whole build has succeeded. `reporter` (see progress.py) is told about the progress.
    Each icon records a short revision of its template and the day it was last converted (`today`, a date string)."""
    out = Path(out)
    reporter = reporter or NullReporter()
    today = today or datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    work = out.parent / (out.name + '.building')
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    try:
        summary, listing, to_cache = {}, [], {}
        for source, rel in items:
            summary[source.id], to_cache[source.id] = _write_source(work, source, rel, convert, max_failed, limit, jobs,
                                                                    reporter, today, cache)
            listing.append({'id': source.id, 'title': source.title, 'version': rel['version'], 'license': rel['license_name'],
                            'homepage': source.homepage, 'count': summary[source.id]['icons'],
                            'failed': summary[source.id]['failed']})
        (work / 'sources.json').write_text(json.dumps({
            'built': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
            'swiftdraw': swiftdraw or 'unknown', 'engine': engine_id(cache.fingerprint if cache else engine_fingerprint(swiftdraw)),
            'weights': {'ultralight': APPLE_ULTRA, 'black': APPLE_BLACK},
            'sources': listing}, separators=(',', ':')), encoding='utf-8')
        (work / '.nojekyll').write_text('', encoding='utf-8')
        if site_dir:
            shutil.copytree(site_dir, work, dirs_exist_ok=True)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    shutil.rmtree(out, ignore_errors=True)
    work.rename(out)
    if cache:
        for source_id, entries in to_cache.items():
            cache.save(source_id, entries)
    return summary


def make_preview_server(directory, port=8000):
    """A local web server for the built folder, reachable from this machine only."""
    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *args):                       # request logs would only clutter the terminal
            pass
    handler = functools.partial(Quiet, directory=str(directory))
    return ThreadingHTTPServer(('127.0.0.1', port), handler)


def main(argv=None):
    ap = argparse.ArgumentParser(description='Build the Symbol Maker site')
    ap.add_argument('--out', default='dist')
    ap.add_argument('--site', default=str(ROOT / 'site'), help='folder with the page (index.html, site.js, site.css)')
    ap.add_argument('--only', help=f'comma-separated sources to build (default: all of {", ".join(SOURCES)})')
    ap.add_argument('--limit', type=int, help='only convert the first N icons of each source (quick local runs)')
    ap.add_argument('--cache', metavar='DIR', help='reuse conversions from earlier builds kept in DIR (unchanged icons are skipped)')
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
    started = time.monotonic()
    say = Reporter()
    sd = swiftdraw_version()
    fingerprint = engine_fingerprint(sd)
    cache = ConvertCache(args.cache, fingerprint) if args.cache else None
    say.info('Symbol Maker site build')
    say.info(f'  {len(ids)} icon set{"s" if len(ids) != 1 else ""} · {args.jobs} process{"es" if args.jobs != 1 else ""} · '
             f'SwiftDraw {sd} · engine {engine_id(fingerprint)} · cache {args.cache or "off"}'
             + (f' · first {args.limit} icons of each set' if args.limit else ''))
    say.info()
    say.info('Downloading')
    items = []
    for i in ids:
        t = time.monotonic()
        rel = load(SOURCES[i])
        say.info(f'  ✓ {SOURCES[i].title:<14} v{rel["version"]:<8} {fmt_count(len(rel["names"])):>6} icons · '
                 f'{rel["license_name"] or "license unknown"} · {fmt_duration(time.monotonic() - t)}')
        items.append((SOURCES[i], rel))
    say.info()
    say.info('Converting')
    try:
        summary = build(args.out, items, swiftdraw=sd, site_dir=args.site, limit=args.limit, jobs=args.jobs, cache=cache,
                        reporter=say)
    except BuildError as e:
        sys.exit(f'\nBuild failed: {e}')
    say.info()
    say.table([{'title': src.title, 'version': rel['version'], **summary[src.id]} for src, rel in items])
    size, files = 0, 0
    for root, _, names in os.walk(args.out):
        files += len(names)
        size += sum(os.path.getsize(os.path.join(root, n)) for n in names)
    say.info()
    say.info(f'Wrote {args.out}/ ({size / 1e6:.0f} MB in {fmt_count(files)} files) in {fmt_duration(time.monotonic() - started)}')
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
