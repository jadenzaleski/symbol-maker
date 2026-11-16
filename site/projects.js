'use strict';
/* Projects: named collections of symbols, each with its own layer edits, that can be exported as a whole.
   Pure functions on a plain store, so Node can test them; projects-ui.js does the page and the saving.

       store   = { version: 1, projects: [project] }
       project = { id, name, created, updated, items: [item] }
       item    = { source, name, symbol, rev, model }      model: a layers.js model, or null for the automatic layers

   Every function returns a new store and leaves the one it was given alone. A symbol is in a project once, keyed by
   `source/name`; adding it again replaces it, which is how a project's copy is updated. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./layers.js'));
  else root.Projects = factory(root.Layers);
})(typeof self !== 'undefined' ? self : this, function (Layers) {
  const VERSION = 1, MAX_NAME = 60;
  const SYMBOL = /^[A-Za-z0-9._-]+$/;

  const empty = () => ({ version: VERSION, projects: [] });
  const itemKey = (source, name) => `${source}/${name}`;
  const keyOf = i => itemKey(i.source, i.name);
  const find = (store, id) => store.projects.find(p => p.id === id);
  const hasItem = (project, key) => project.items.some(i => keyOf(i) === key);
  const copy = store => ({ version: VERSION, projects: store.projects.map(p => ({ ...p, items: p.items.map(i => ({ ...i })) })) });

  function need(store, id) {
    const p = find(store, id);
    if (!p) throw new Error('That project no longer exists.');
    return p;
  }

  /** Why this name cannot be used (for a new project, or for project `exceptId` being renamed), or null. */
  function validateName(store, name, exceptId = null) {
    const n = String(name ?? '').trim();
    if (!n) return 'Give the project a name.';
    if (n.length > MAX_NAME) return `The name is too long (${MAX_NAME} characters at most).`;
    if (store.projects.some(p => p.id !== exceptId && p.name.toLowerCase() === n.toLowerCase())) return 'A project with that name already exists.';
    return null;
  }
  /** `base`, or `base 2`, `base 3`... whichever is free. */
  function uniqueName(store, base) {
    let n = 1, name = base;
    while (validateName(store, name)) name = `${base} ${++n}`;
    return name;
  }

  function create(store, { id, name, now }) {
    const err = validateName(store, name);
    if (err) throw new Error(err);
    const o = copy(store);
    o.projects.push({ id, name: String(name).trim(), created: now, updated: now, items: [] });
    return o;
  }
  function rename(store, id, name, now) {
    need(store, id);
    const err = validateName(store, name, id);
    if (err) throw new Error(err);
    const o = copy(store), p = find(o, id);
    p.name = String(name).trim(); p.updated = now;
    return o;
  }
  function remove(store, id) {
    need(store, id);
    const o = copy(store);
    o.projects = o.projects.filter(p => p.id !== id);
    return o;
  }
  /** Put a removed project back at `index` (to undo a delete). */
  function insertProject(store, project, index) {
    const o = copy(store);
    o.projects.splice(Math.max(0, Math.min(o.projects.length, index)), 0, { ...project, items: project.items.map(i => ({ ...i })) });
    return o;
  }

  const clean = i => ({ source: i.source, name: i.name, symbol: i.symbol, rev: i.rev, model: i.model ?? null });
  function addItem(store, id, item, now) {
    need(store, id);
    const o = copy(store), p = find(o, id), at = p.items.findIndex(i => keyOf(i) === keyOf(item));
    if (at >= 0) p.items[at] = clean(item); else p.items.push(clean(item));
    p.updated = now;
    return o;
  }
  function removeItem(store, id, key, now) {
    const p = need(store, id);
    if (!hasItem(p, key)) throw new Error(`${key} is not in this project.`);
    const o = copy(store), q = find(o, id);
    q.items = q.items.filter(i => keyOf(i) !== key); q.updated = now;
    return o;
  }
  /** Put a removed symbol back at `index` (to undo a removal). */
  function insertItem(store, id, item, index, now) {
    need(store, id);
    const o = copy(store), p = find(o, id);
    p.items = p.items.filter(i => keyOf(i) !== keyOf(item));
    p.items.splice(Math.max(0, Math.min(p.items.length, index)), 0, clean(item)); p.updated = now;
    return o;
  }

  /* ---------- saving ---------- */
  const serialize = store => JSON.stringify(store);
  const isModel = m => m === null || (m && Array.isArray(m.strokes) && Array.isArray(m.layers));
  function validItem(i) {
    return i && typeof i.source === 'string' && typeof i.name === 'string' && typeof i.symbol === 'string' && SYMBOL.test(i.symbol)
      && typeof i.rev === 'string' && isModel(i.model ?? null);
  }
  /** The store saved in `text`; damaged or foreign data gives an empty store, and broken projects or symbols are dropped. */
  function parse(text) {
    let d;
    try { d = JSON.parse(text); } catch { return empty(); }
    if (!d || d.version !== VERSION || !Array.isArray(d.projects)) return empty();
    const out = empty(), ids = new Set();
    for (const p of d.projects) {
      if (!p || typeof p.id !== 'string' || ids.has(p.id) || typeof p.name !== 'string' || !p.name.trim() || !Array.isArray(p.items)) continue;
      if (out.projects.some(q => q.name.toLowerCase() === p.name.trim().toLowerCase())) continue;
      ids.add(p.id);
      const seen = new Set(), items = [];
      for (const i of p.items) if (validItem(i) && !seen.has(keyOf(i))) { seen.add(keyOf(i)); items.push(clean(i)); }
      out.projects.push({ id: p.id, name: p.name.trim().slice(0, MAX_NAME), created: String(p.created ?? ''), updated: String(p.updated ?? ''), items });
    }
    return out;
  }

  /* ---------- exporting ---------- */
  /** A project name as a folder name: no path characters, never empty. */
  function catalogName(name) {
    const n = String(name).replace(/[\\/:*?"<>|\u0000-\u001f]/g, '-').replace(/\s+/g, ' ').replace(/^[-\s.]+|[-\s.]+$/g, '');
    return n || 'Symbols';
  }
  const contents = symbol => JSON.stringify({ info: { author: 'xcode', version: 1 }, symbols: [{ filename: `${symbol}.svg`, idiom: 'universal' }] }, null, 2);

  /** The files of an export, as [{ name, data }]: kind 'catalog' = `<Name>.xcassets/` with one .symbolset per symbol; 'svg' =
      the templates in a folder. Either way the licences of the sets used sit beside it. `templates` are the published
      templates by key, `licenses` the licence text by source id. Saved layers are applied only if the icon is still the one
      they were made for (same revision, and they still describe its strokes); `notes` says which were not.
      -> { files, notes, count } */
  function buildExport(project, { templates, licenses }, kind = 'catalog') {
    if (!project.items.length) throw new Error('This project has no symbols yet.');
    const base = catalogName(project.name), files = [], notes = [], sources = new Set();
    if (kind === 'catalog') files.push({ name: `${base}.xcassets/Contents.json`, data: JSON.stringify({ info: { author: 'xcode', version: 1 } }, null, 2) });
    for (const item of project.items) {
      const key = keyOf(item), text = templates[key];
      if (typeof text !== 'string') throw new Error(`Could not load ${key}.`);
      let svg = text;
      if (item.model) {
        const rev = (text.match(/Template rev ([0-9a-f]+)/) || [])[1];
        const m = rev && rev === item.rev ? Layers.restore(item.model, text) : null;
        if (m && !Layers.problem(m)) svg = Layers.markEdited(Layers.apply(text, m));
        else notes.push(`${item.symbol}: the icon changed since you added it, so it was exported with its automatic layers.`);
      }
      if (kind === 'catalog') {
        const dir = `${base}.xcassets/${item.symbol}.symbolset`;
        files.push({ name: `${dir}/Contents.json`, data: contents(item.symbol) }, { name: `${dir}/${item.symbol}.svg`, data: svg });
      } else files.push({ name: `${base}/${item.symbol}.svg`, data: svg });
      sources.add(item.source);
    }
    for (const s of [...sources].sort()) files.push({ name: `LICENSE-${s}.txt`, data: licenses[s] ?? '' });
    return { files, notes, count: project.items.length };
  }

  return { empty, itemKey, find, hasItem, validateName, uniqueName, create, rename, remove, insertProject, addItem, removeItem,
           insertItem, serialize, parse, catalogName, buildExport, MAX_NAME };
});
