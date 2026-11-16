// Projects: named collections of symbols (with their layer edits), kept in the browser and exported as a whole.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const require = createRequire(import.meta.url);
const P = require('../../site/projects.js');
const L = require('../../site/layers.js');
const fx = n => readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '../fixtures/export', n), 'utf8');

const T0 = '2026-11-15T10:00:00.000Z', T1 = '2026-11-15T11:00:00.000Z';
// the fixture templates carry no revision comment; add one the way the build does
const withRev = (svg, rev) => svg.replace('<svg', `<!-- Icon "x" from Lucide. Template rev ${rev}. -->\n<svg`);
const CHECK = withRev(fx('lucide.circle.check.svg'), 'aaaa1111');
const HEART = withRev(fx('lucide.heart.svg'), 'bbbb2222');
const item = (name, rev, model = null) => ({ source: 'lucide', name, symbol: 'lucide.' + name.replace(/-/g, '.'), rev, model });

test('a store starts empty, and a project is created with a name, an id and the time', () => {
  const s = P.create(P.empty(), { id: 'p1', name: '  My app  ', now: T0 });
  assert.equal(s.projects.length, 1);
  assert.deepEqual({ ...s.projects[0] }, { id: 'p1', name: 'My app', created: T0, updated: T0, items: [] });
});

test('names must be there, not too long, and different from the other projects (ignoring case)', () => {
  let s = P.create(P.empty(), { id: 'p1', name: 'Alpha', now: T0 });
  assert.match(P.validateName(s, '   '), /name/i);
  assert.match(P.validateName(s, 'x'.repeat(61)), /long/i);
  assert.match(P.validateName(s, 'alpha'), /already/i);
  assert.equal(P.validateName(s, 'alpha', 'p1'), null, 'a project may keep its own name');
  assert.equal(P.validateName(s, 'Beta'), null);
  assert.throws(() => P.create(s, { id: 'p2', name: 'ALPHA', now: T0 }));
});

test('a default name is offered that does not clash', () => {
  let s = P.empty();
  assert.equal(P.uniqueName(s, 'New project'), 'New project');
  s = P.create(s, { id: 'a', name: 'New project', now: T0 });
  assert.equal(P.uniqueName(s, 'New project'), 'New project 2');
  s = P.create(s, { id: 'b', name: 'New project 2', now: T0 });
  assert.equal(P.uniqueName(s, 'New project'), 'New project 3');
});

test('renaming changes the name and the updated time, and refuses a clash', () => {
  let s = P.create(P.empty(), { id: 'p1', name: 'Alpha', now: T0 });
  s = P.create(s, { id: 'p2', name: 'Beta', now: T0 });
  const r = P.rename(s, 'p1', 'Gamma', T1);
  assert.equal(P.find(r, 'p1').name, 'Gamma'); assert.equal(P.find(r, 'p1').updated, T1);
  assert.throws(() => P.rename(s, 'p1', 'beta', T1));
  assert.equal(P.find(s, 'p1').name, 'Alpha', 'the original is untouched');
});

test('adding a symbol puts it in the project once; adding it again replaces it (that is how it is updated)', () => {
  let s = P.create(P.empty(), { id: 'p1', name: 'A', now: T0 });
  s = P.addItem(s, 'p1', item('house', 'r1'), T0);
  s = P.addItem(s, 'p1', item('heart', 'r2'), T0);
  assert.deepEqual(P.find(s, 'p1').items.map(i => i.name), ['house', 'heart']);
  const m = L.fromTemplate(CHECK);
  s = P.addItem(s, 'p1', item('house', 'r9', m), T1);
  const p = P.find(s, 'p1');
  assert.deepEqual(p.items.map(i => i.name), ['house', 'heart'], 'same place, not a duplicate');
  assert.equal(p.items[0].rev, 'r9'); assert.deepEqual(p.items[0].model, m); assert.equal(p.updated, T1);
  assert.equal(P.hasItem(p, P.itemKey('lucide', 'house')), true);
  assert.equal(P.hasItem(p, P.itemKey('tabler', 'house')), false, 'the same name in another set is another symbol');
});

test('removing a symbol or a project can be undone by putting it back where it was', () => {
  let s = P.create(P.empty(), { id: 'p1', name: 'A', now: T0 });
  s = P.create(s, { id: 'p2', name: 'B', now: T0 });
  s = P.addItem(s, 'p1', item('a', 'r'), T0); s = P.addItem(s, 'p1', item('b', 'r'), T0); s = P.addItem(s, 'p1', item('c', 'r'), T0);
  const gone = P.find(s, 'p1').items[1];
  const s2 = P.removeItem(s, 'p1', P.itemKey('lucide', 'b'), T1);
  assert.deepEqual(P.find(s2, 'p1').items.map(i => i.name), ['a', 'c']);
  assert.deepEqual(P.find(P.insertItem(s2, 'p1', gone, 1, T1), 'p1').items.map(i => i.name), ['a', 'b', 'c']);
  const p = P.find(s, 'p1'), s3 = P.remove(s, 'p1');
  assert.equal(P.find(s3, 'p1'), undefined);
  assert.deepEqual(P.insertProject(s3, p, 0).projects.map(x => x.id), ['p1', 'p2']);
});

test('unknown ids are errors, not silent no-ops', () => {
  const s = P.create(P.empty(), { id: 'p1', name: 'A', now: T0 });
  assert.throws(() => P.addItem(s, 'nope', item('a', 'r'), T0));
  assert.throws(() => P.rename(s, 'nope', 'X', T0));
  assert.throws(() => P.removeItem(s, 'p1', 'lucide/zzz', T0));
});

test('saving and loading give back the same projects, and damaged data gives an empty store, not an error', () => {
  let s = P.create(P.empty(), { id: 'p1', name: 'A', now: T0 });
  s = P.addItem(s, 'p1', item('house', 'r1', L.fromTemplate(CHECK)), T0);
  assert.deepEqual(P.parse(P.serialize(s)), s);
  for (const bad of ['', 'not json', '[]', '{"version":99,"projects":[]}', 'null', '{"projects":"x"}']) assert.deepEqual(P.parse(bad), P.empty(), bad);
});

test('loading keeps good projects and symbols and drops the broken ones', () => {
  const raw = JSON.stringify({ version: 1, projects: [
    { id: 'p1', name: 'Good', created: T0, updated: T0, items: [
      { source: 'lucide', name: 'house', symbol: 'lucide.house', rev: 'r', model: null },
      { source: 'lucide', name: 'evil', symbol: '../../etc/passwd', rev: 'r', model: null },
      { source: 5, name: 'x' }] },
    { id: 'p2', name: '', items: [] },
    { id: 'p1', name: 'Dup id', items: [] }] });
  const s = P.parse(raw);
  assert.deepEqual(s.projects.map(p => p.name), ['Good']);
  assert.deepEqual(s.projects[0].items.map(i => i.name), ['house']);
});

test('a project name becomes a safe folder name', () => {
  assert.equal(P.catalogName('My App'), 'My App');
  assert.equal(P.catalogName('a/b\\c:d*e?'), 'a-b-c-d-e');
  assert.equal(P.catalogName('  ..  '), 'Symbols');
  assert.equal(P.catalogName('Café ☕'), 'Café ☕');
});

function project(items) {
  let s = P.create(P.empty(), { id: 'p1', name: 'My App', now: T0 });
  for (const i of items) s = P.addItem(s, 'p1', i, T0);
  return P.find(s, 'p1');
}
const LIC = { lucide: 'ISC license text', tabler: 'MIT license text' };

test('an asset catalog export holds one symbolset per symbol and the licences of the sets used', () => {
  const p = project([item('circle-check', 'aaaa1111'), item('heart', 'bbbb2222')]);
  const r = P.buildExport(p, { templates: { 'lucide/circle-check': CHECK, 'lucide/heart': HEART }, licenses: LIC }, 'catalog');
  const names = r.files.map(f => f.name).sort();
  assert.deepEqual(names, [
    'LICENSE-lucide.txt',
    'My App.xcassets/Contents.json',
    'My App.xcassets/lucide.circle.check.symbolset/Contents.json',
    'My App.xcassets/lucide.circle.check.symbolset/lucide.circle.check.svg',
    'My App.xcassets/lucide.heart.symbolset/Contents.json',
    'My App.xcassets/lucide.heart.symbolset/lucide.heart.svg'].sort());
  const get = n => r.files.find(f => f.name === n).data;
  assert.deepEqual(JSON.parse(get('My App.xcassets/Contents.json')), { info: { author: 'xcode', version: 1 } });
  assert.deepEqual(JSON.parse(get('My App.xcassets/lucide.heart.symbolset/Contents.json')).symbols, [{ filename: 'lucide.heart.svg', idiom: 'universal' }]);
  assert.equal(get('My App.xcassets/lucide.heart.symbolset/lucide.heart.svg'), HEART, 'unedited: the template as published');
  assert.equal(get('LICENSE-lucide.txt'), 'ISC license text');
  assert.deepEqual(r.notes, []); assert.equal(r.count, 2);
});

test('an edited symbol is exported with its edits, and a licence is added for each set used', () => {
  let m = L.fromTemplate(CHECK); m = L.setColor(m, m.layers[1].id, 'systemRedColor'); m = L.moveLayer(m, m.layers[1].id, -1);
  const p = project([item('circle-check', 'aaaa1111', m), { source: 'tabler', name: 'home', symbol: 'tabler.home', rev: 'cccc3333', model: null }]);
  const r = P.buildExport(p, { templates: { 'lucide/circle-check': CHECK, 'tabler/home': withRev(fx('lucide.heart.svg'), 'cccc3333') }, licenses: LIC }, 'catalog');
  const svg = r.files.find(f => f.name.endsWith('lucide.circle.check.svg')).data;
  assert.match(svg, /multicolor-0:systemRedColor/); assert.match(svg, /Layers edited with Symbol Maker/);
  assert.deepEqual(r.files.map(f => f.name).filter(n => n.startsWith('LICENSE')).sort(), ['LICENSE-lucide.txt', 'LICENSE-tabler.txt']);
});

test('if the icon changed since it was added, its saved layers are not applied and the export says so', () => {
  const m = L.setColor(L.fromTemplate(CHECK), 0, 'white');
  const p = project([item('circle-check', 'OLDREV00', m)]);
  const r = P.buildExport(p, { templates: { 'lucide/circle-check': CHECK }, licenses: LIC }, 'catalog');
  assert.equal(r.files.find(f => f.name.endsWith('.svg')).data, CHECK);
  assert.equal(r.notes.length, 1); assert.match(r.notes[0], /lucide\.circle\.check/); assert.match(r.notes[0], /automatic/i);
});

test('saved layers that cannot describe the template are not applied either', () => {
  const p = project([item('circle-check', 'aaaa1111', { strokes: [0], layers: [{ id: 0, level: 'primary', color: 'tintColor' }], nextId: 1 })]);
  const r = P.buildExport(p, { templates: { 'lucide/circle-check': CHECK }, licenses: LIC }, 'catalog');
  assert.equal(r.files.find(f => f.name.endsWith('.svg')).data, CHECK); assert.equal(r.notes.length, 1);
});

test('an svg export is just the templates in a folder, with the licences', () => {
  const p = project([item('heart', 'bbbb2222')]);
  const r = P.buildExport(p, { templates: { 'lucide/heart': HEART }, licenses: LIC }, 'svg');
  assert.deepEqual(r.files.map(f => f.name).sort(), ['LICENSE-lucide.txt', 'My App/lucide.heart.svg']);
});

test('exporting an empty project, or one whose template is missing, is an error with a message', () => {
  assert.throws(() => P.buildExport(project([]), { templates: {}, licenses: LIC }, 'catalog'), /no symbols/i);
  assert.throws(() => P.buildExport(project([item('heart', 'r')]), { templates: {}, licenses: LIC }, 'catalog'), /lucide\/heart/);
});

test('the edited-note helper is shared, and adds its comment once, after the credit comment', () => {
  const m = L.setColor(L.fromTemplate(CHECK), 0, 'white');
  const out = L.markEdited(L.apply(CHECK, m));
  assert.equal(out.split('Layers edited with Symbol Maker').length, 2);
  assert.ok(out.indexOf('Template rev') < out.indexOf('Layers edited'));
});
