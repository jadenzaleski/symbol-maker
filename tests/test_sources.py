import base64
import hashlib
import io
import json
import tarfile
import unittest

from symbolmaker import sources
from symbolmaker.sources import SOURCES, load, symbol_name

LUCIDE = SOURCES['lucide']
TABLER = SOURCES['tabler']
HERO = SOURCES['heroicons']
SIDEKICK = SOURCES['sidekickicons']


def tgz(files):
    """A tarball holding {path: bytes}."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w:gz') as t:
        for path, data in files.items():
            info = tarfile.TarInfo(path); info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def lucide_tgz(names, extra=None, nodes=None):
    files = {f'package/icons/{n}.svg': f'<svg class="lucide lucide-{n}"><!-- {n} --></svg>'.encode() for n in names}
    files['package/icon-nodes.json'] = json.dumps(nodes if nodes is not None else {n: [] for n in names}).encode()
    files['package/LICENSE'] = b'ISC License\nCopyright (c) Lucide'
    files.update(extra or {})
    return tgz(files)


def iconify_tgz(icons, upstream='3.52.0', license_spdx='MIT', aliases=None, license_url='https://github.com/x/y/blob/master/LICENSE'):
    body = {'prefix': 'x', 'icons': icons, 'aliases': aliases or {}, 'width': 24, 'height': 24}
    info = {'name': 'X Icons', 'version': upstream, 'author': {'name': 'Ann Author', 'url': 'https://example.com/x'},
            'license': {'title': license_spdx, 'spdx': license_spdx, 'url': license_url}}
    return tgz({'package/icons.json': json.dumps(body).encode(), 'package/info.json': json.dumps(info).encode()})


STROKE = '<path fill="none" stroke="currentColor" stroke-width="2" d="M5 12h14"/>'


def registry_url(package):
    return f'https://registry.npmjs.org/{package}/latest'


def route(package, version, data, integrity=None, tarball=None):
    digest = integrity or 'sha512-' + base64.b64encode(hashlib.sha512(data).digest()).decode()
    url = tarball or f'https://registry.npmjs.org/{package}/-/{package.split("/")[-1]}-{version}.tgz'
    meta = json.dumps({'version': version, 'dist': {'tarball': url, 'integrity': digest}}).encode()
    return {registry_url(package): meta, url: data}


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


class RegistryTests(unittest.TestCase):
    def test_ids_prefixes_and_packages_are_unique_and_usable(self):
        self.assertEqual(set(SOURCES), {'lucide', 'tabler', 'heroicons', 'sidekickicons'})
        self.assertEqual(len({s.prefix for s in SOURCES.values()}), len(SOURCES))
        for s in SOURCES.values():
            self.assertEqual(s.id, s.prefix)
            self.assertRegex(s.prefix, r'^[a-z]+$')

    def test_symbol_names_get_the_source_prefix_and_dots(self):
        self.assertEqual(symbol_name(LUCIDE, 'a-arrow-down'), 'lucide.a.arrow.down')
        self.assertEqual(symbol_name(TABLER, 'home'), 'tabler.home')
        self.assertEqual(symbol_name(HERO, 'arrow-up-right'), 'heroicons.arrow.up.right')

    def test_only_the_outline_style_is_kept(self):
        self.assertTrue(TABLER.keep('home'))
        self.assertFalse(TABLER.keep('home-filled'))
        for s in (HERO, SIDEKICK):
            self.assertTrue(s.keep('home'))
            for suffix in ('-solid', '-20-solid', '-16-solid'):
                self.assertFalse(s.keep('home' + suffix), suffix)
        self.assertTrue(LUCIDE.keep('anything'))


class LucideLoadTests(unittest.TestCase):
    def net(self, names=('house', 'heart', 'a-arrow-down'), **kw):
        return Net(route('lucide-static', '9.9.9', lucide_tgz(list(names), **kw)))

    def test_returns_the_version_names_svgs_and_license(self):
        r = load(LUCIDE, fetch=self.net())
        self.assertEqual(r['version'], '9.9.9')
        self.assertEqual(r['names'], ['a-arrow-down', 'heart', 'house'])
        self.assertIn('lucide-heart', r['svgs']['heart'])
        self.assertIn('ISC License', r['license'])

    def test_a_bad_checksum_raises(self):
        net = Net(route('lucide-static', '9.9.9', lucide_tgz(['house']), integrity='sha512-' + base64.b64encode(b'0' * 64).decode()))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            load(LUCIDE, fetch=net)

    def test_a_foreign_tarball_address_raises_and_is_never_fetched(self):
        net = Net(route('lucide-static', '9.9.9', lucide_tgz(['house']), tarball='https://evil.example/x.tgz'))
        with self.assertRaises(ValueError):
            load(LUCIDE, fetch=net)
        self.assertEqual(net.calls, [registry_url('lucide-static')])

    def test_a_tarball_address_inside_another_package_is_refused(self):
        net = Net(route('lucide-static', '9.9.9', lucide_tgz(['house']), tarball='https://registry.npmjs.org/other-package/-/x.tgz'))
        with self.assertRaises(ValueError):
            load(LUCIDE, fetch=net)

    def test_an_empty_release_raises(self):
        with self.assertRaises(ValueError):
            load(LUCIDE, fetch=self.net(names=()))

    def test_a_missing_license_is_an_empty_string_not_an_error(self):
        data = tgz({'package/icons/house.svg': b'<svg/>', 'package/icon-nodes.json': b'{"house": []}'})
        r = load(LUCIDE, fetch=Net(route('lucide-static', '9.9.9', data)))
        self.assertEqual(r['license'], '')

    def test_hostile_names_and_members_are_ignored(self):
        nodes = {'house': [], '../../evil': [], 'UPPER': [], 'a b': []}
        extra = {'package/icons/../../evil.svg': b'<svg/>', 'package/icons/UPPER.svg': b'<svg/>', '/etc/passwd': b'x'}
        r = load(LUCIDE, fetch=self.net(names=('house',), extra=extra, nodes=nodes))
        self.assertEqual(r['names'], ['house'])

    def test_an_icon_listed_but_missing_its_svg_is_left_out(self):
        r = load(LUCIDE, fetch=self.net(names=('house',), nodes={'house': [], 'phantom-zzz': []}))
        self.assertEqual(r['names'], ['house'])


class IconifyLoadTests(unittest.TestCase):
    def net(self, icons, package='@iconify-json/tabler', fetch_license=b'MIT License\n\nCopyright (c) Ann Author', **kw):
        routes = route(package, '1.2.3', iconify_tgz(icons, **kw))
        routes['https://raw.githubusercontent.com/x/y/master/LICENSE'] = fetch_license
        return Net(routes)

    def test_builds_an_svg_from_each_body_and_reports_the_upstream_version(self):
        r = load(TABLER, fetch=self.net({'home': {'body': STROKE}, 'home-filled': {'body': '<path d="M0 0"/>'}, 'star': {'body': STROKE}}))
        self.assertEqual(r['version'], '3.52.0')                       # the icon set's own version, not the npm package's
        self.assertEqual(r['names'], ['home', 'star'])                 # the filled style is not kept
        self.assertIn('viewBox="0 0 24 24"', r['svgs']['home'])
        self.assertIn('xmlns="http://www.w3.org/2000/svg"', r['svgs']['home'])
        self.assertIn(STROKE, r['svgs']['home'])

    def test_license_text_comes_from_the_upstream_file(self):
        r = load(TABLER, fetch=self.net({'home': {'body': STROKE}}))
        self.assertIn('Copyright (c) Ann Author', r['license'])
        self.assertEqual(r['license_name'], 'MIT')

    def test_if_the_upstream_license_cannot_be_fetched_a_notice_with_the_link_is_used(self):
        net = self.net({'home': {'body': STROKE}})
        del net.routes['https://raw.githubusercontent.com/x/y/master/LICENSE']
        r = load(TABLER, fetch=net)
        self.assertIn('MIT', r['license'])
        self.assertIn('Ann Author', r['license'])
        self.assertIn('https://github.com/x/y/blob/master/LICENSE', r['license'])

    def test_aliases_are_not_listed(self):
        r = load(TABLER, fetch=self.net({'home': {'body': STROKE}}, aliases={'house': {'parent': 'home'}}))
        self.assertEqual(r['names'], ['home'])

    def test_a_body_with_script_or_other_unexpected_elements_is_skipped(self):
        icons = {'ok': {'body': STROKE}, 'evil': {'body': '<script>alert(1)</script>'},
                 'img': {'body': '<image href="https://x/y.png"/>'}, 'fo': {'body': '<foreignObject/>'},
                 'ev': {'body': '<path d="M0 0" onload="x()"/>'}}
        r = load(TABLER, fetch=self.net(icons))
        self.assertEqual(r['names'], ['ok'])

    def test_a_group_wrapping_shapes_is_fine(self):
        body = '<g fill="none" stroke="currentColor"><path d="M0 0h4"/><circle cx="1" cy="1" r="1"/></g>'
        self.assertEqual(load(TABLER, fetch=self.net({'x': {'body': body}}))['names'], ['x'])

    def test_a_non_default_size_is_carried_into_the_viewbox(self):
        data = tgz({'package/icons.json': json.dumps({'icons': {'a': {'body': STROKE, 'width': 16, 'height': 16}}, 'width': 24, 'height': 24}).encode(),
                    'package/info.json': json.dumps({'version': '1.0.0', 'license': {'spdx': 'MIT', 'url': 'x'}, 'author': {'name': 'A'}}).encode()})
        r = load(TABLER, fetch=Net(route('@iconify-json/tabler', '1.2.3', data)))
        self.assertIn('viewBox="0 0 16 16"', r['svgs']['a'])

    def test_heroicons_and_sidekick_keep_outline_only(self):
        icons = {'home': {'body': STROKE}, 'home-solid': {'body': STROKE}, 'home-20-solid': {'body': STROKE}}
        for src in (HERO, SIDEKICK):
            r = load(src, fetch=self.net(icons, package=src.package))
            self.assertEqual(r['names'], ['home'], src.id)

    def test_a_bad_checksum_raises(self):
        data = iconify_tgz({'home': {'body': STROKE}})
        net = Net(route('@iconify-json/tabler', '1.2.3', data, integrity='sha512-' + base64.b64encode(b'0' * 64).decode()))
        with self.assertRaisesRegex(ValueError, 'integrity'):
            load(TABLER, fetch=net)


if __name__ == '__main__':
    unittest.main()
