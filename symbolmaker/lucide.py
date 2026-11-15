"""Download the newest `lucide-static` release from the npm registry.

We read the registry's metadata, fetch the tarball only from the official registry address, check its published SHA-512,
and read just the icon files, `icon-nodes.json` (the canonical icon names) and the LICENSE out of it in memory. Nothing
is extracted to disk, and nothing about the user is sent.
"""
import base64
import hashlib
import hmac
import io
import json
import re
import tarfile
import urllib.request

REGISTRY_URL = 'https://registry.npmjs.org/lucide-static/latest'
TARBALL_PREFIX = 'https://registry.npmjs.org/lucide-static/-/'
VERSION = re.compile(r'\d+\.\d+\.\d+')
NAME = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*')
ICON_FILE = re.compile(r'package/icons/([a-z0-9]+(?:-[a-z0-9]+)*)\.svg')
MAX_TARBALL = 40 * 1024 * 1024
MAX_ICON_BYTES = 64 * 1024
MAX_MEMBERS = 20000


def http_fetch(url, max_bytes):
    """GET an https URL, at most `max_bytes`. Sends nothing about the user."""
    if not url.startswith('https://'):
        raise OSError('only https is allowed')
    req = urllib.request.Request(url, headers={'User-Agent': 'symbol-maker'})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise OSError('the download is too large')
    return data


def _read_tarball(data):
    """(svgs by name, icon names from icon-nodes.json, license text) read in memory; nothing is extracted to disk."""
    svgs, nodes, license_text, seen = {}, [], '', 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as t:
        for m in t:
            seen += 1
            if seen > MAX_MEMBERS:
                raise ValueError('The download has too many files.')
            if not m.isfile():
                continue
            if m.name == 'package/icon-nodes.json' and m.size <= 4 * 1024 * 1024:
                nodes = [k for k in json.loads(t.extractfile(m).read()) if NAME.fullmatch(k)]
            elif m.name == 'package/LICENSE' and m.size <= MAX_ICON_BYTES:
                license_text = t.extractfile(m).read().decode('utf-8', 'replace')
            else:
                hit = ICON_FILE.fullmatch(m.name)
                if hit and m.size <= MAX_ICON_BYTES:
                    svgs[hit.group(1)] = t.extractfile(m).read().decode('utf-8', 'replace')
    return svgs, nodes, license_text


def download_latest(fetch=http_fetch):
    """The newest lucide-static release from npm as {'version', 'names', 'svgs', 'license'}.
    Raises ValueError (or OSError) on anything untrustworthy: an unexpected download address, a failed SHA-512 check, or a release with no icons."""
    meta = json.loads(fetch(REGISTRY_URL, 1024 * 1024))
    version, dist = meta['version'], meta['dist']
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError('The registry sent an unreadable version.')
    tarball, integrity = dist['tarball'], dist['integrity']
    if not isinstance(tarball, str) or not tarball.startswith(TARBALL_PREFIX):
        raise ValueError('The registry sent an unexpected download address.')
    data = fetch(tarball, MAX_TARBALL)
    if not isinstance(integrity, str) or not integrity.startswith('sha512-'):
        raise ValueError('The registry sent no checksum (integrity).')
    if not hmac.compare_digest(hashlib.sha512(data).digest(), base64.b64decode(integrity[len('sha512-'):])):
        raise ValueError('The download failed its integrity check.')
    svgs, nodes, license_text = _read_tarball(data)
    names = sorted(n for n in nodes if n in svgs)
    if not names:
        raise ValueError('The download holds no icons.')
    return {'version': version, 'names': names, 'svgs': {n: svgs[n] for n in names}, 'license': license_text}
