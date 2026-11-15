"""Icon sets we can turn into SF Symbols templates, and how to download each one.

Every set comes from a package on the npm registry. We read the registry's metadata, fetch the tarball only from the
registry's own address for that package, check its published SHA-512, and read what we need out of it in memory (nothing is
extracted to disk). Nothing about the user is sent.

Two package layouts are supported:

  lucide-static   the official Lucide package: one SVG per icon plus `icon-nodes.json` (the canonical icon names).
  iconify         `@iconify-json/<set>`: one JSON file with every icon's SVG markup, plus `info.json` (version, author,
                  license). Iconify publishes Tabler, Heroicons, Sidekickicons and many more this way.

Only the outline style of each set is kept: it is drawn with strokes, so it can get Ultralight and Black weights. The
filled styles have nothing to scale.
"""
import base64
import hashlib
import hmac
import io
import json
import re
import tarfile
import urllib.request
from dataclasses import dataclass
from typing import Callable

NPM = 'https://registry.npmjs.org/'
VERSION = re.compile(r'\d+\.\d+\.\d+')
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
ICON_FILE = re.compile(r'package/icons/([a-z0-9]+(?:-[a-z0-9]+)*)\.svg')
GITHUB_BLOB = re.compile(r'https://github\.com/([\w.-]+)/([\w.-]+)/blob/([\w./-]+)')
MAX_TARBALL = 40 * 1024 * 1024
MAX_ICON_BYTES = 64 * 1024
MAX_MEMBERS = 20000
MAX_TEXT = 64 * 1024
ALLOWED_TAGS = {'g', 'path', 'circle', 'rect', 'line', 'polyline', 'polygon', 'ellipse'}


def http_fetch(url, max_bytes):
    """GET an https URL, at most `max_bytes`."""
    if not url.startswith('https://'):
        raise OSError('only https is allowed')
    req = urllib.request.Request(url, headers={'User-Agent': 'symbol-maker'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise OSError('the download is too large')
    return data


@dataclass(frozen=True)
class Source:
    id: str                                  # folder name on the site and prefix of the symbol names
    title: str
    package: str                             # npm package
    kind: str                                # 'lucide-static' | 'iconify'
    homepage: str
    keep: Callable[[str], bool] = lambda name: True      # which icons of the package to use (outline style only)

    @property
    def prefix(self):
        return self.id


SOURCES = {s.id: s for s in (
    Source('lucide', 'Lucide', 'lucide-static', 'lucide-static', 'https://lucide.dev'),
    Source('tabler', 'Tabler Icons', '@iconify-json/tabler', 'iconify', 'https://tabler.io/icons',
           keep=lambda n: not n.endswith('-filled')),
    Source('heroicons', 'Heroicons', '@iconify-json/heroicons', 'iconify', 'https://heroicons.com',
           keep=lambda n: not n.endswith('-solid')),                      # also drops -20-solid and -16-solid
    Source('sidekickicons', 'Sidekickicons', '@iconify-json/sidekickicons', 'iconify', 'https://github.com/ndri/sidekickicons',
           keep=lambda n: not n.endswith('-solid')),
)}


def symbol_name(source, icon):
    """The SF Symbols name: the set's prefix, then the icon name with dots, e.g. lucide.arrow.up.right."""
    return f'{source.prefix}.{icon.replace("-", ".")}'


def _fetch_package(package, fetch):
    """(npm version, tarball bytes) of the package's latest release, after the address and checksum checks."""
    meta = json.loads(fetch(f'{NPM}{package}/latest', 1024 * 1024))
    version, dist = meta['version'], meta['dist']
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError('The registry sent an unreadable version.')
    tarball, integrity = dist['tarball'], dist['integrity']
    if not isinstance(tarball, str) or not tarball.startswith(f'{NPM}{package}/-/'):
        raise ValueError('The registry sent an unexpected download address.')
    data = fetch(tarball, MAX_TARBALL)
    if not isinstance(integrity, str) or not integrity.startswith('sha512-'):
        raise ValueError('The registry sent no checksum (integrity).')
    if not hmac.compare_digest(hashlib.sha512(data).digest(), base64.b64decode(integrity[len('sha512-'):])):
        raise ValueError('The download failed its integrity check.')
    return version, data


def _members(data):
    """Yield (name, size, read) for the regular files of a gzipped tarball, in memory."""
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
        for seen, m in enumerate(t, 1):
            if seen > MAX_MEMBERS:
                raise ValueError('The download has too many files.')
            if m.isfile():
                yield m.name, m.size, lambda m=m: t.extractfile(m).read()


def _lucide(data, source):
    svgs, nodes, license_text = {}, [], ''
    for name, size, read in _members(data):
        if name == 'package/icon-nodes.json' and size <= 4 * 1024 * 1024:
            nodes = [k for k in json.loads(read()) if NAME.fullmatch(k)]
        elif name == 'package/LICENSE' and size <= MAX_TEXT:
            license_text = read().decode('utf-8', 'replace')
        else:
            hit = ICON_FILE.fullmatch(name)
            if hit and size <= MAX_ICON_BYTES:
                svgs[hit.group(1)] = read().decode('utf-8', 'replace')
    names = sorted(n for n in nodes if n in svgs and source.keep(n))
    return {'names': names, 'svgs': {n: svgs[n] for n in names}, 'license': license_text, 'license_name': 'ISC', 'upstream': None}


def _safe_body(body):
    """Only plain drawing elements, no event handlers or scripts: SwiftDraw reads these, and the icon file is also served."""
    tags = re.findall(r'<\s*/?\s*([A-Za-z][\w:-]*)', body)
    if not tags or any(t.lower() not in ALLOWED_TAGS for t in tags):
        return False
    return not re.search(r'\son\w+\s*=|javascript:|<!|<\?', body, re.I)


def _size(v, default):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v <= 1024 else default


def _license_notice(info, fetch):
    """The upstream LICENSE text when its address is a GitHub file, else a short notice that links to it."""
    lic = info.get('license') or {}
    url = lic.get('url') or ''
    hit = GITHUB_BLOB.fullmatch(url)
    if hit:
        try:
            return fetch(f'https://raw.githubusercontent.com/{hit.group(1)}/{hit.group(2)}/{hit.group(3)}', MAX_TEXT).decode('utf-8', 'replace')
        except (OSError, ValueError):
            pass
    author = info.get('author') or {}
    return (f'{info.get("name", "This icon set")} by {author.get("name", "its authors")} ({author.get("url", "")}) '
            f'is licensed under the {lic.get("title") or lic.get("spdx") or "license"} License.\n'
            f'The full text is at {url}\n')


def _iconify(data, source, fetch):
    icons_json = info = None
    for name, size, read in _members(data):
        if name == 'package/icons.json' and size <= 8 * 1024 * 1024:
            icons_json = json.loads(read())
        elif name == 'package/info.json' and size <= MAX_TEXT:
            info = json.loads(read())
    if not icons_json or not isinstance(icons_json.get('icons'), dict) or not info:
        raise ValueError('The download is missing icons.json or info.json.')
    w0, h0 = _size(icons_json.get('width'), 24), _size(icons_json.get('height'), 24)
    svgs = {}
    for name, ic in icons_json['icons'].items():          # aliases live elsewhere in the file, so they are not listed
        if not (isinstance(name, str) and NAME.fullmatch(name) and source.keep(name) and isinstance(ic, dict)):
            continue
        body = ic.get('body')
        if not isinstance(body, str) or not _safe_body(body):
            continue
        w, h = _size(ic.get('width'), w0), _size(ic.get('height'), h0)
        svgs[name] = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" '
                      f'viewBox="0 0 {w:g} {h:g}">{body}</svg>')
    lic = info.get('license') or {}
    return {'names': sorted(svgs), 'svgs': svgs, 'license': _license_notice(info, fetch),
            'license_name': lic.get('spdx') or lic.get('title') or '', 'upstream': info.get('version')}


def load(source, fetch=http_fetch):
    """The newest release of a source as {'version', 'names', 'svgs', 'license', 'license_name'}.
    `version` is the icon set's own version when the package states it. Raises ValueError (or OSError) on anything
    untrustworthy: an unexpected download address, a failed SHA-512 check, or a release with no icons."""
    npm_version, data = _fetch_package(source.package, fetch)
    got = _lucide(data, source) if source.kind == 'lucide-static' else _iconify(data, source, fetch)
    if not got['names']:
        raise ValueError('The download holds no icons.')
    up = got.pop('upstream')
    got['version'] = up if isinstance(up, str) and VERSION.fullmatch(up) else npm_version
    return got
