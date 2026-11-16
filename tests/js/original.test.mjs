// The original icon: how it is read (only plain shapes, nothing that could run or fetch) and where it lands on a template.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';

const Original = createRequire(import.meta.url)('../../site/original.js');

const LUCIDE = `<!-- @license lucide-static v1.73.0 - ISC -->
<svg
  class="lucide lucide-a-arrow-down"
  xmlns="http://www.w3.org/2000/svg"
  width="24"
  height="24"
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
>
  <path d="m14 12 4 4 4-4" />
  <g><circle cx="12" cy="12" r="10" /></g>
  <rect width="18" height="18" x="3" y="3" rx="2" />
</svg>`;

test('a 24-unit icon needs no scaling, and others are fitted to the grid the way the converter does', () => {
  assert.deepEqual(Original.grid(LUCIDE), { s: 1, tx: 0, ty: 0, w: 24, h: 24 });
  assert.deepEqual(Original.grid('<svg viewBox="0 0 16 16"></svg>'), { s: 1.5, tx: 0, ty: 0, w: 16, h: 16 });
  const wide = Original.grid('<svg viewBox="0 0 20 10"></svg>');
  assert.equal(wide.s, 1.2);
  assert.equal(wide.tx, 0);
  assert.equal(wide.ty, 6, 'centered: (24 - 10 * 1.2) / 2');
  const offset = Original.grid('<svg viewBox="-1 -1 26 26"></svg>');
  assert.ok(Math.abs(offset.s - 24 / 26) < 1e-12);
  assert.ok(Math.abs(offset.tx - offset.s) < 1e-12, 'the -1 origin is moved to 0');
  assert.deepEqual(Original.grid('<svg width="12" height="12"></svg>'), { s: 2, tx: 0, ty: 0, w: 12, h: 12 });
});

test('an icon with no usable size has no grid', () => {
  assert.equal(Original.grid('<svg></svg>'), null);
  assert.equal(Original.grid('<svg viewBox="0 0 0 24"></svg>'), null);
  assert.equal(Original.grid('<svg viewBox="0 0 24"></svg>'), null);
});

test('the shapes, and the style the svg sets for all of them, are read; the rest of the markup is ignored', () => {
  const r = Original.parse(LUCIDE);
  assert.equal(r.unsupported, undefined);
  assert.deepEqual(r.root, {
    fill: 'none',
    stroke: 'currentColor',
    'stroke-width': '2',
    'stroke-linecap': 'round',
    'stroke-linejoin': 'round',
  });
  assert.deepEqual(
    r.nodes.map(n => n.tag),
    ['path', 'g', 'rect'],
  );
  assert.deepEqual(r.nodes[0].attrs, { d: 'm14 12 4 4 4-4' });
  assert.equal(r.nodes[1].children[0].tag, 'circle');
  assert.deepEqual(r.nodes[1].children[0].attrs, { cx: '12', cy: '12', r: '10' });
  assert.deepEqual(r.nodes[2].attrs, { width: '18', height: '18', x: '3', y: '3', rx: '2' });
});

test('anything that could do more than draw is refused, and says what it was', () => {
  const svg = inner => `<svg viewBox="0 0 24 24">${inner}</svg>`;
  const cases = {
    '<script>alert(1)</script>': 'script',
    '<style>path{stroke:red}</style><path d="M0 0"/>': 'style',
    '<use href="#a"/>': 'use',
    '<defs><clipPath id="a"/></defs><path d="M0 0"/>': 'defs',
    '<image href="x.png"/>': 'image',
    '<foreignObject/>': 'foreignObject',
    '<path d="M0 0" style="stroke:red"/>': 'a style attribute',
    '<path d="M0 0" fill="url(#g)"/>': 'a reference (url)',
    '<path d="M0 0" onload="alert(1)"/>': null, // unknown attributes are dropped, not refused
  };
  for (const [inner, why] of Object.entries(cases)) {
    const r = Original.parse(svg(inner));
    if (why === null) {
      assert.equal(r.unsupported, undefined, inner);
      assert.deepEqual(r.nodes[0].attrs, { d: 'M0 0' }, 'only known attributes are kept');
    } else {
      assert.equal(r.unsupported, why, inner);
      assert.equal(r.nodes, undefined, 'nothing is drawn from an icon that was refused');
    }
  }
});

test('title and desc are skipped, not refused', () => {
  const r = Original.parse('<svg viewBox="0 0 24 24"><title>x</title><desc>y</desc><path d="M1 1h2"/></svg>');
  assert.equal(r.unsupported, undefined);
  assert.deepEqual(
    r.nodes.map(n => n.tag),
    ['path'],
  );
});

test('text that is not an svg is refused', () => {
  assert.equal(Original.parse('<html></html>').unsupported, 'not an svg');
  assert.equal(Original.parse('').unsupported, 'not an svg');
});

test('what the caption says about an icon: its grid and how its strokes are drawn', () => {
  assert.deepEqual(Original.facts(LUCIDE), { grid: '24 × 24', stroke: '2', caps: 'round', joins: 'round' });
  assert.deepEqual(Original.facts('<svg viewBox="0 0 16 16" fill="currentColor"><path d="M0 0"/></svg>'), {
    grid: '16 × 16',
    stroke: null,
    caps: null,
    joins: null,
  });
});

// Measured on the published Lucide templates: the circle (outer edge 1..23 on the 24 grid) is 3.59..82.564 wide in the
// Regular master whose margins are 86.154 apart and whose cap height is 70, with its center 35 above the baseline.
const GUIDE = { width: 86.154, cap: 70 };
const at = (m, X, Y) => [m.scale * X + m.tx, m.scale * Y + m.ty];
const close = (a, b) => assert.ok(a.every((v, i) => Math.abs(v - b[i]) < 0.01), `${a} vs ${b}`);

test('a point of the 24 grid lands where the template has it', () => {
  const m = Original.place(GUIDE, Original.grid(LUCIDE));
  close(at(m, 1, 1), [3.59, -74.487]); // circle, top left of its edge
  close(at(m, 23, 23), [82.564, 4.487]); // bottom right
  close(at(m, 4, 11), [14.359, -38.59]); // minus: round cap of M5 12h14
  close(at(m, 12, 12), [43.077, -35]); // the middle sits half a cap height above the baseline
});

test('an icon on another grid lands in the same place as the same drawing on the 24 grid', () => {
  const m = Original.place(GUIDE, Original.grid('<svg viewBox="0 0 16 16"></svg>'));
  close(at(m, 8, 8), [43.077, -35]);
  close(at(m, 0.6667, 0.6667), [3.59, -74.487]);
});

test('the preview scales the template to a fixed cap height, and the original follows', () => {
  const m = Original.place({ width: 86.154, cap: 35 }, Original.grid(LUCIDE), 70);
  close(at(m, 12, 12), [86.154, -35], 'twice as large, still centered on the cap height');
});

test('the transform is written as an svg matrix', () => {
  const m = Original.place(GUIDE, Original.grid(LUCIDE));
  const t = Original.transform(m);
  assert.match(t, /^matrix\(/);
  const n = t.match(/-?\d*\.?\d+(?:e-?\d+)?/g).map(Number);
  assert.equal(n.length, 6);
  assert.deepEqual([n[1], n[2]], [0, 0]);
  assert.ok(Math.abs(n[0] - m.scale) < 1e-6 && Math.abs(n[3] - m.scale) < 1e-6);
});

test('the page loads this script before the one that uses it', () => {
  const html = readFileSync(new URL('../../site/index.html', import.meta.url), 'utf8');
  const at = name => html.indexOf(`<script src="${name}"></script>`);
  assert.ok(at('original.js') > 0, 'original.js is not loaded by index.html');
  assert.ok(at('original.js') < at('site.js'), 'original.js must come before site.js');
});
