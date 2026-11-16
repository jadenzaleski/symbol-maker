// The layer model behind the page's layer editor: pure functions on a template's text, no DOM.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const L = require('../../site/layers.js');
const fx = n => readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '../fixtures/export', n), 'utf8');

const WEIGHTS = ['Ultralight-S', 'Regular-S', 'Black-S'];
const group = (svg, w) => svg.match(new RegExp(`<g id="${w}"[^>]*>([\\s\\S]*?)</g>`))[1];
const paths = (svg, w) => [...group(svg, w).matchAll(/<path\b([^>]*?)\/?>/g)].map(m => ({
  cls: (m[1].match(/class="([^"]*)"/) || [, ''])[1], d: (m[1].match(/\sd="([^"]*)"/) || [, ''])[1] }));
const layerOf = cls => Number(cls.match(/hierarchical-(\d+):/)[1]);

const CHECK = fx('lucide.circle.check.svg');       // two layers: the circle (secondary), then the tick
const HEART = fx('lucide.heart.svg');

test('reads the strokes, layers, levels and colors already in a template', () => {
  const m = L.fromTemplate(CHECK);
  assert.equal(m.strokes.length, paths(CHECK, 'Regular-S').length);
  assert.ok(m.layers.length >= 2);
  assert.equal(m.layers[0].level, 'secondary');
  assert.equal(m.layers[0].color, 'tintColor');
});

test('writing the model back unchanged keeps every outline and every layer', () => {
  const out = L.apply(CHECK, L.fromTemplate(CHECK));
  for (const w of WEIGHTS) {
    const a = paths(CHECK, w), b = paths(out, w);
    assert.equal(b.length, a.length, w);
    assert.deepEqual(b.map(p => p.d).sort(), a.map(p => p.d).sort(), `${w}: same outlines`);
  }
  assert.deepEqual(paths(out, 'Regular-S').map(p => layerOf(p.cls)).sort(),
                   paths(CHECK, 'Regular-S').map(p => layerOf(p.cls)).sort());
});

test('all three weights get the same classes in the same order (they must, to interpolate)', () => {
  let m = L.fromTemplate(CHECK);
  m = L.moveLayer(m, m.layers[0].id, +1);
  const out = L.apply(CHECK, m);
  const base = paths(out, 'Regular-S').map(p => p.cls);
  for (const w of WEIGHTS) assert.deepEqual(paths(out, w).map(p => p.cls), base, w);
});

test('moving a layer renumbers it and puts its outlines in front, since layer 1 is the back', () => {
  let m = L.fromTemplate(CHECK);
  const firstId = m.layers[0].id;
  const circle = paths(CHECK, 'Regular-S').filter(p => layerOf(p.cls) === 0).map(p => p.d);
  m = L.moveLayer(m, firstId, +1);
  const out = paths(L.apply(CHECK, m), 'Regular-S');
  const last = out.filter(p => layerOf(p.cls) === 1).map(p => p.d);
  assert.deepEqual(last, circle);
  assert.deepEqual(out.map(p => layerOf(p.cls)), [...out.map(p => layerOf(p.cls))].sort((a, b) => a - b), 'document order = layer order');
});

test('moving the first layer up or the last layer down changes nothing', () => {
  const m = L.fromTemplate(CHECK);
  assert.deepEqual(L.moveLayer(m, m.layers[0].id, -1), m);
  assert.deepEqual(L.moveLayer(m, m.layers.at(-1).id, +1), m);
});

test('a stroke taken out of the symbol is dropped from all three weights', () => {
  let m = L.fromTemplate(CHECK);
  const n = m.strokes.length;
  m = L.assign(m, 0, null);
  const out = L.apply(CHECK, m);
  for (const w of WEIGHTS) assert.equal(paths(out, w).length, n - 1, w);
});

test('a new layer is empty and is not written until it holds a stroke', () => {
  let m = L.fromTemplate(CHECK);
  m = L.addLayer(m);
  const added = m.layers.at(-1);
  assert.equal(added.level, 'primary');
  assert.equal(L.order(m).length, m.layers.length - 1, 'an empty layer has no place in the animation order');
  assert.deepEqual(paths(L.apply(CHECK, m), 'Regular-S').map(p => layerOf(p.cls)),
                   paths(L.apply(CHECK, L.fromTemplate(CHECK)), 'Regular-S').map(p => layerOf(p.cls)));
  m = L.assign(m, 0, added.id);
  const out = paths(L.apply(CHECK, m), 'Regular-S');
  assert.equal(layerOf(out.at(-1).cls), L.order(m).length - 1, 'now it is the front layer');
});

test('removing a layer sends its strokes out of the symbol and renumbers the rest', () => {
  let m = L.fromTemplate(CHECK);
  const total = m.strokes.length, firstId = m.layers[0].id;
  const inFirst = m.strokes.filter(s => s === firstId).length;
  m = L.removeLayer(m, firstId);
  assert.equal(m.layers.length, L.fromTemplate(CHECK).layers.length - 1);
  const out = paths(L.apply(CHECK, m), 'Regular-S');
  assert.equal(out.length, total - inFirst);
  assert.equal(Math.min(...out.map(p => layerOf(p.cls))), 0, 'numbering starts at 0 again');
});

test('color and level are written per layer, numbered after any reordering', () => {
  let m = L.fromTemplate(CHECK);
  const tickId = m.layers[1].id;
  m = L.setColor(m, tickId, 'systemRedColor');
  m = L.setLevel(m, tickId, 'tertiary');
  m = L.moveLayer(m, tickId, -1);                   // the tick is now layer 0
  const out = L.apply(CHECK, m);
  const tick = paths(out, 'Regular-S').find(p => layerOf(p.cls) === 0);
  assert.match(tick.cls, /^monochrome-0 multicolor-0:systemRedColor hierarchical-0:tertiary$/);
  assert.match(out, /\.multicolor-0:systemRedColor \{fill:#FF3B30\}/);
});

test('a color nobody chose gets no style rule, and the style block is optional', () => {
  assert.doesNotMatch(L.apply(HEART, L.fromTemplate(HEART)), /<style/);
});

test('the animation order lists layers from the back, with their strokes', () => {
  const m = L.fromTemplate(CHECK);
  const o = L.order(m);
  assert.deepEqual(o.map(x => x.number), o.map((_, i) => i + 1));
  assert.equal(o.reduce((n, x) => n + x.strokes.length, 0), m.strokes.length);
});

test('an unknown level or color is refused', () => {
  const m = L.fromTemplate(CHECK);
  assert.throws(() => L.setLevel(m, m.layers[0].id, 'quaternary'));
  assert.throws(() => L.setColor(m, m.layers[0].id, 'hotpink'));
});

test('the edit functions leave the model they were given alone', () => {
  const m = L.fromTemplate(CHECK), copy = JSON.stringify(m);
  L.addLayer(m); L.removeLayer(m, m.layers[0].id); L.moveLayer(m, m.layers[0].id, 1); L.assign(m, 0, null);
  L.setColor(m, m.layers[0].id, 'white'); L.setLevel(m, m.layers[0].id, 'tertiary');
  assert.equal(JSON.stringify(m), copy);
});

test('a symbol with nothing left in it cannot be exported', () => {
  let m = L.fromTemplate(HEART);
  for (let i = 0; i < m.strokes.length; i++) m = L.assign(m, i, null);
  assert.match(L.problem(m), /no strokes/i);
  assert.throws(() => L.apply(HEART, m));
  assert.equal(L.problem(L.fromTemplate(HEART)), null);
});

test('edits can be told apart from the starting point, and survive being saved as JSON', () => {
  const m = L.fromTemplate(CHECK);
  assert.equal(L.isEdited(m, CHECK), false);
  const e = L.setColor(m, m.layers[0].id, 'white');
  assert.equal(L.isEdited(e, CHECK), true);
  assert.equal(L.isEdited(L.restore(JSON.parse(JSON.stringify(e)), CHECK), CHECK), true);
  assert.equal(L.restore({ strokes: [1, 2, 3], layers: [] }, CHECK), null, 'a saved model for another icon is ignored');
});
