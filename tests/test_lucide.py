import base64
import hashlib
import io
import json
import tarfile
import unittest

from symbolmaker.lucide import download_latest

REGISTRY = 'https://registry.npmjs.org/lucide-static/latest'
TARBALL = 'https://registry.npmjs.org/lucide-static/-/lucide-static-9.9.9.tgz'


def make_tgz(names, extra=(), nodes=None):
    """A lucide-static-shaped tarball: package/icons/<name>.svg for each name plus package/icon-nodes.json."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        def add(path, data, **kw):
            info = tarfile.TarInfo(path); info.size = len(data)
            for k, v in kw.items():
                setattr(info, k, v)
            t.addfile(info, io.BytesIO(data))
        for n in names:
            add(f'package/icons/{n}.svg', f'<svg class="lucide lucide-{n}"><!-- {n} --></svg>'.encode())
        add('package/icon-nodes.json', json.dumps(nodes if nodes is not None else {n: [] for n in names}).encode())
        for path, data in extra:
            add(path, data)
    return buf.getvalue()


def registry(version, tgz, integrity=None, tarball=TARBALL):
    digest = integrity or 'sha512-' + base64.b64encode(hashlib.sha512(tgz).digest()).decode()
    return json.dumps({'version': version, 'dist': {'tarball': tarball, 'integrity': digest}}).encode()


class Net:
    """A fake network: url -> bytes, or an exception to raise."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, url, max_bytes):
        self.calls.append(url)
        r = self.routes.get(url)
        if r is None:
            raise OSError(f'no route to {url}')
        if isinstance(r, Exception):
            raise r
        return r


class DownloadLatestTests(unittest.TestCase):
    """The site build downloads a release without any bundled copy to start from."""

    def net(self, names=('house', 'heart', 'a-arrow-down'), license_text=b'ISC License\nCopyright (c) Lucide'):
        tgz = make_tgz(list(names), extra=[('package/LICENSE', license_text)])
        return Net({REGISTRY: registry('9.9.9', tgz), TARBALL: tgz})

    def test_returns_the_version_names_svgs_and_license(self):
        r = download_latest(fetch=self.net())
        self.assertEqual(r['version'], '9.9.9')
        self.assertEqual(r['names'], ['a-arrow-down', 'heart', 'house'])
        self.assertIn('lucide-heart', r['svgs']['heart'])
        self.assertIn('ISC License', r['license'])

    def test_a_bad_checksum_raises(self):
        tgz = make_tgz(['house'])
        net = Net({REGISTRY: registry('9.9.9', tgz, integrity='sha512-' + base64.b64encode(b'0' * 64).decode()), TARBALL: tgz})
        with self.assertRaisesRegex(ValueError, 'integrity'):
            download_latest(fetch=net)

    def test_a_foreign_tarball_address_raises_and_is_never_fetched(self):
        tgz = make_tgz(['house'])
        net = Net({REGISTRY: registry('9.9.9', tgz, tarball='https://evil.example/x.tgz')})
        with self.assertRaises(ValueError):
            download_latest(fetch=net)
        self.assertEqual(net.calls, [REGISTRY])

    def test_an_empty_release_raises(self):
        with self.assertRaises(ValueError):
            download_latest(fetch=self.net(names=()))

    def test_a_missing_license_is_an_empty_string_not_an_error(self):
        tgz = make_tgz(['house'])
        r = download_latest(fetch=Net({REGISTRY: registry('9.9.9', tgz), TARBALL: tgz}))
        self.assertEqual(r['license'], '')


if __name__ == '__main__':
    unittest.main()
