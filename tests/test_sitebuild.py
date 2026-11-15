import json
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from symbolmaker import sitebuild
from symbolmaker.engine.convert import find_swiftdraw
from symbolmaker.engine.layers import LayerAssignment, read_assignments
from symbolmaker.engine.pipeline import MakeResult

ROOT = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HOUSE = (ROOT / 'tests/fixtures/export/lucide.house.svg').read_text()
RELEASE = {'version': '9.9.9', 'license': 'ISC License\nCopyright (c) Lucide',
           'names': ['a-arrow-down', 'heart', 'house'],
           'svgs': {n: f'<svg class="lucide lucide-{n}"/>' for n in ('a-arrow-down', 'heart', 'house')}}


def fake_convert(svg):
    return MakeResult(HOUSE, 'variable', ['a note'], [LayerAssignment(0, 'secondary'), LayerAssignment(1, 'primary')])


class SymbolNameTests(unittest.TestCase):
    def test_hyphens_become_dots_with_a_lucide_prefix(self):
        self.assertEqual(sitebuild.symbol_name('house'), 'lucide.house')
        self.assertEqual(sitebuild.symbol_name('a-arrow-down'), 'lucide.a.arrow.down')
        self.assertEqual(sitebuild.symbol_name('grid-3x3'), 'lucide.grid.3x3')


class StampTests(unittest.TestCase):
    def test_the_license_comment_is_added_and_the_template_still_reads(self):
        out = sitebuild.stamp(HOUSE, 'house', '9.9.9')
        self.assertIn('Lucide', out.split('<svg', 1)[0])
        self.assertIn('ISC', out.split('<svg', 1)[0])
        self.assertTrue(out.startswith('<?xml'))
        ET.fromstring(out)                                           # still well-formed XML
        self.assertEqual(read_assignments(out), read_assignments(HOUSE))

    def test_the_comment_never_contains_a_double_hyphen(self):
        comment = sitebuild.stamp(HOUSE, 'a-arrow-down', '1.2.3').split('<svg', 1)[0]
        body = comment.split('<!--', 1)[1].rsplit('-->', 1)[0]
        self.assertNotIn('--', body)


class ZipTests(unittest.TestCase):
    def test_the_zip_holds_a_symbolset_folder_and_the_license_beside_it(self):
        data = sitebuild.symbolset_zip('lucide.house', HOUSE, 'ISC License text')
        import io
        z = zipfile.ZipFile(io.BytesIO(data))
        self.assertEqual(sorted(z.namelist()), ['LICENSE-lucide.txt', 'lucide.house.symbolset/Contents.json',
                                                'lucide.house.symbolset/lucide.house.svg'])
        self.assertEqual(z.read('lucide.house.symbolset/lucide.house.svg').decode(), HOUSE)
        self.assertEqual(json.loads(z.read('lucide.house.symbolset/Contents.json'))['symbols'][0]['filename'], 'lucide.house.svg')
        self.assertEqual(z.read('LICENSE-lucide.txt').decode(), 'ISC License text')

    def test_the_same_input_gives_the_same_bytes(self):
        a = sitebuild.symbolset_zip('lucide.house', HOUSE, 'x')
        b = sitebuild.symbolset_zip('lucide.house', HOUSE, 'x')
        self.assertEqual(a, b)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.out = Path(tempfile.mkdtemp()) / 'dist'
        self.addCleanup(shutil.rmtree, self.out.parent, True)

    def build(self, **kw):
        kw.setdefault('convert', fake_convert)
        return sitebuild.build(self.out, RELEASE, swiftdraw='0.29.0', **kw)

    def test_writes_every_artifact_for_every_icon(self):
        self.build()
        for sym, icon in (('lucide.house', 'house'), ('lucide.heart', 'heart'), ('lucide.a.arrow.down', 'a-arrow-down')):
            self.assertTrue((self.out / 'templates' / f'{sym}.svg').read_text().startswith('<?xml'))
            self.assertEqual(set(json.loads((self.out / 'guides' / f'{sym}.json').read_text())), {'ultralight', 'regular', 'black'})
            self.assertTrue(zipfile.is_zipfile(self.out / 'zips' / f'{sym}.symbolset.zip'))
            self.assertIn(f'lucide-{icon}', (self.out / 'icons' / f'{icon}.svg').read_text())
        self.assertEqual((self.out / 'LICENSE-lucide.txt').read_text(), RELEASE['license'])
        self.assertTrue((self.out / '.nojekyll').exists())

    def test_index_describes_the_build_and_each_icon(self):
        self.build()
        d = json.loads((self.out / 'index.json').read_text())
        self.assertEqual((d['library'], d['version'], d['swiftdraw']), ('Lucide', '9.9.9', '0.29.0'))
        self.assertEqual(d['weights'], {'ultralight': 0.30, 'black': 1.90})
        self.assertEqual([i['name'] for i in d['icons']], ['a-arrow-down', 'heart', 'house'])
        first = d['icons'][0]
        self.assertEqual((first['symbol'], first['status'], first['layers'], first['notes']),
                         ('lucide.a.arrow.down', 'variable', 2, ['a note']))
        self.assertEqual(d['failed'], [])

    def test_the_site_files_are_copied_in(self):
        site = self.out.parent / 'site'
        site.mkdir()
        (site / 'index.html').write_text('<html>')
        self.build(site_dir=site)
        self.assertEqual((self.out / 'index.html').read_text(), '<html>')

    def test_one_failing_icon_is_recorded_and_skipped(self):
        def convert(svg):
            if 'lucide-heart' in svg:
                raise ValueError('cannot convert')
            return fake_convert(svg)
        s = self.build(convert=convert, max_failed=0.5)
        d = json.loads((self.out / 'index.json').read_text())
        self.assertEqual(d['failed'], [{'name': 'heart', 'error': 'cannot convert'}])
        self.assertEqual([i['name'] for i in d['icons']], ['a-arrow-down', 'house'])
        self.assertFalse((self.out / 'templates' / 'lucide.heart.svg').exists())
        self.assertEqual(s['failed'], 1)

    def test_too_many_failures_stop_the_build_before_anything_is_published(self):
        def convert(svg):
            raise ValueError('nope')
        with self.assertRaises(sitebuild.BuildError):
            self.build(convert=convert, max_failed=0.02)
        self.assertFalse(self.out.exists())

    def test_an_existing_output_folder_is_replaced_not_merged(self):
        self.out.mkdir(parents=True)
        (self.out / 'stale.txt').write_text('old')
        self.build()
        self.assertFalse((self.out / 'stale.txt').exists())


class ServeTests(unittest.TestCase):
    def test_serves_the_built_folder_on_localhost_only(self):
        import threading
        import urllib.request
        d = Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d, True)
        (d / 'index.html').write_text('hello site')
        srv = sitebuild.make_preview_server(d, port=0)
        self.addCleanup(srv.server_close)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.shutdown)
        self.assertEqual(srv.server_address[0], '127.0.0.1')
        with urllib.request.urlopen(f'http://127.0.0.1:{srv.server_address[1]}/index.html') as r:
            self.assertEqual(r.read(), b'hello site')


@unittest.skipUnless(find_swiftdraw(), 'swiftdraw not installed')
class RealConversionTests(unittest.TestCase):
    def test_default_conversion_uses_apple_weights_and_produces_a_variable_template(self):
        svg = (ROOT / 'tests/fixtures/lucide/heart.svg').read_text()
        r = sitebuild.convert_apple(svg)
        self.assertEqual(r.status, 'variable')


if __name__ == '__main__':
    unittest.main()
