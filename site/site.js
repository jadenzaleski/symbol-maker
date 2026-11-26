'use strict';
/* Symbol Maker site: a searchable list of icons, a preview of the three weights on the template's guides, and downloads.
   No framework and no build step. Everything it needs is a static file next to this page. */

const $ = (s, r = document) => r.querySelector(s);
const SVGNS = 'http://www.w3.org/2000/svg';
const ROW = 26;
const WEIGHTS = [['ultralight', 'Ultralight'], ['regular', 'Regular'], ['black', 'Black']];
const BADGES = { variable: ['Variable weights', ''], 'single-weight': ['Single weight', 'warn'], 'identical-masters': ['No weight change', 'warn'] };

const REPO = 'https://github.com/jadenzaleski/symbol-maker';
const state = { meta: null, source: null, index: null, indexes: {}, items: [], picked: null, seq: 0, onlyProblems: false };

/* ---------- data ---------- */
async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
async function getText(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.text();
}

/* ---------- list (virtualized: 2,000+ rows) ---------- */
function filterList() {
  const q = $('#search').value.trim().toLowerCase().replace(/[\s.]+/g, '-');
  let all = state.index ? state.index.icons : [];
  if (state.onlyProblems) all = all.filter(i => i.flag === 'problem');
  state.items = q ? all.filter(i => i.name.includes(q)) : all;
  $('#count').textContent = String(state.items.length);
  $('#list').scrollTop = 0;
  renderList();
}
function renderList() {
  const list = $('#list'), rows = $('#list-rows');
  $('#list-spacer').style.height = state.items.length * ROW + 'px';
  const start = Math.max(0, Math.floor(list.scrollTop / ROW) - 6);
  const end = Math.min(state.items.length, Math.ceil((list.scrollTop + list.clientHeight) / ROW) + 6);
  rows.style.transform = `translateY(${start * ROW}px)`;
  const frag = document.createDocumentFragment();
  for (let i = start; i < end; i++) {
    const item = state.items[i], n = item.name;
    const d = document.createElement('div');
    d.className = 'row'; d.setAttribute('role', 'option'); d.dataset.name = n; d.textContent = n;
    if (item.flag) {                                   // a marker, with the reason on hover and for screen readers
      const f = document.createElement('span');
      f.className = 'flag ' + item.flag; f.setAttribute('aria-hidden', 'true');
      d.append(f);
      d.title = item.notes.join(' ');
      d.setAttribute('aria-label', `${n}: ${item.flag === 'problem' ? 'problem. ' : 'note. '}${item.notes.join(' ')}`);
    }
    d.style.setProperty('--icon', `url("${state.source.id}/icons/${n}.svg")`);
    d.setAttribute('aria-selected', String(n === state.picked));
    frag.appendChild(d);
  }
  rows.replaceChildren(frag);
}
function scrollToPicked() {
  const i = state.items.findIndex(x => x.name === state.picked), list = $('#list');
  if (i < 0) return;
  if (i * ROW < list.scrollTop) list.scrollTop = i * ROW;
  else if ((i + 1) * ROW > list.scrollTop + list.clientHeight) list.scrollTop = (i + 1) * ROW - list.clientHeight;
}

/* ---------- preview ---------- */
// Each weight is drawn on the template's own guides: baseline and cap line (blue), and the side margins (cyan).
const CAP = 70, TOP = 96, BOTTOM = 26, PAD = 14;
const BLUE = '#27AAE1', MARGIN = '#00AEEF';
function svgEl(tag, attrs = {}) {
  const e = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  return e;
}
function drawWeight(g, label, name, over = null) {
  const svg = svgEl('svg', { viewBox: `${-PAD} ${-TOP} ${g.width + 2 * PAD} ${TOP + BOTTOM}`, role: 'img',
    'aria-label': `${name}, ${label} weight, with baseline, cap line and margins` });
  const line = (x1, y1, x2, y2, c) => svgEl('line', { x1, y1, x2, y2, stroke: c, 'stroke-width': 0.5, 'vector-effect': 'non-scaling-stroke' });
  const scale = CAP / g.cap;
  const art = svgEl('g', { class: 'art', transform: `scale(${scale}) translate(${-g.origin[0]} ${-g.origin[1]})` });
  g.paths.forEach((d, i) => art.append(svgEl('path', { d, 'data-i': i })));
  svg.append(line(-PAD, 0, g.width + PAD, 0, BLUE), line(-PAD, -CAP, g.width + PAD, -CAP, BLUE), art);
  if (over) svg.append(over);                                    // the original icon, when it is asked for (see overlay())
  svg.append(line(0, -TOP + 6, 0, 18, MARGIN), line(g.width, -TOP + 6, g.width, 18, MARGIN));
  return svg;
}
/* ---------- the original icon: its own card, and optionally drawn over the Regular weight ---------- */
const OVERLAY_KEY = 'symbolmaker.overlay';
function overlayOn() { try { return localStorage.getItem(OVERLAY_KEY) === '1'; } catch { return false; } }
function rememberOverlay(on) { try { localStorage.setItem(OVERLAY_KEY, on ? '1' : '0'); } catch { /* not remembered */ } }

function originalCard(item, text) {
  const src = state.source;
  const card = document.createElement('figure'); card.className = 'card original';
  const cap = document.createElement('figcaption'); cap.className = 'label';
  cap.append(Object.assign(document.createElement('strong'), { textContent: 'Original' }), Info.button('original'));
  card.append(cap);
  const url = `${src.id}/icons/${item.name}.svg`;
  if (text === null) {
    card.append(Object.assign(document.createElement('p'), { className: 'note', textContent: 'The original could not be loaded.' }));
    return card;
  }
  const fit = Original.grid(text) || { w: 24, h: 24 };
  const frame = document.createElement('div'); frame.className = 'orig-frame';
  frame.style.aspectRatio = `${fit.w} / ${fit.h}`;                // the box is the file's own grid
  const art = document.createElement('div'); art.className = 'orig-art';
  art.setAttribute('role', 'img'); art.setAttribute('aria-label', `${item.name}, the original icon as ${src.title} draws it`);
  art.style.setProperty('--icon', `url("${url}")`);               // the file itself, tinted for the theme
  frame.append(art);
  const f = Original.facts(text);
  const how = [f.grid, f.stroke && `stroke ${f.stroke}`, f.caps && `${f.caps} caps`].filter(Boolean).join(' · ');
  const meta = document.createElement('p'); meta.className = 'orig-meta';
  const link = Object.assign(document.createElement('a'), { href: url, target: '_blank', rel: 'noopener', textContent: 'Open the SVG' });
  meta.append(`${src.title} ${src.version}`, document.createElement('br'), how, how ? document.createElement('br') : '', link);
  card.append(frame, meta);
  return card;
}
// The original's shapes drawn over the Regular weight, where the converter put them. Returns { layer, why }: the SVG group
// (null when the icon cannot be drawn this way) and, then, a reason to show instead of the switch.
function overlay(guides, text) {
  if (text === null) return { layer: null, why: 'The original could not be loaded.' };
  const fit = Original.grid(text), parsed = Original.parse(text);
  if (!fit) return { layer: null, why: 'The original has no usable size, so it cannot be drawn on top.' };
  if (parsed.unsupported) return { layer: null, why: `The original uses ${parsed.unsupported}, which is not drawn on top.` };
  const build = n => { const e = svgEl(n.tag, n.attrs); n.children.forEach(c => e.append(build(c))); return e; };
  const layer = svgEl('g', { class: 'overlay', 'pointer-events': 'none', 'aria-hidden': 'true',
    transform: Original.transform(Original.place(guides.regular, fit, CAP)) });
  const paint = svgEl('g', parsed.root);
  parsed.nodes.forEach(n => paint.append(build(n)));
  layer.append(paint);
  return { layer, why: null };
}
function overlaySwitch(host, why) {
  const label = document.createElement('label'); label.className = 'check overlay-switch';
  const box = document.createElement('input'); box.type = 'checkbox';
  box.checked = !why && overlayOn(); box.disabled = !!why;
  host.classList.toggle('show-overlay', box.checked);
  box.addEventListener('change', () => { rememberOverlay(box.checked); host.classList.toggle('show-overlay', box.checked); });
  label.append(box, ' Original on top');
  if (why) label.title = why; else label.title = 'Draw the original icon over the Regular weight, in color';
  return label;
}
function showBadge(status) {
  const b = $('#badge'), m = BADGES[status];
  b.hidden = !m; $('#info-status').hidden = !m;
  if (m) { b.textContent = m[0]; b.classList.toggle('warn', m[1] === 'warn'); }
}
function showNotes(notes, status) {
  const b = $('#banner');
  b.replaceChildren(...notes.map(t => Object.assign(document.createElement('p'), { textContent: t })));
  b.className = 'banner' + (status === 'variable' ? '' : ' warn');
  b.hidden = notes.length === 0;
}
async function pick(name, { scroll = true, preset = null } = {}) {
  const item = state.index.icons.find(i => i.name === name);
  if (!item) return;
  state.picked = name;
  const id = state.source.id, hash = `#${id}/${name}`;
  if (location.hash !== hash) history.replaceState(null, '', hash);
  renderList(); if (scroll) scrollToPicked();
  const mine = ++state.seq;
  let guides, text, original;
  try {
    [guides, text, original] = await Promise.all([getJSON(`${id}/guides/${item.symbol}.json`), getText(`${id}/templates/${item.symbol}.svg`),
      getText(`${id}/icons/${name}.svg`).catch(() => null)]);       // the original is a bonus: the page works without it
  } catch { showNotes(['Could not load this icon. Check your connection and try again.'], 'error'); return; }
  if (mine !== state.seq) return;                      // a newer pick is loading
  $('#title').textContent = name;
  showBadge(item.status); showNotes(item.notes, item.status);
  $('#empty').hidden = true;
  $('#workspace').hidden = false;
  const host = $('#masters');
  const over = overlay(guides, original);
  host.replaceChildren(originalCard(item, original), ...WEIGHTS.map(([key, label]) => {
    const card = document.createElement('figure'); card.className = 'card';
    const cap = document.createElement('figcaption'); cap.className = 'label';
    cap.append(Object.assign(document.createElement('strong'), { textContent: label }));
    if (key === 'regular') cap.append(overlaySwitch(host, over.why));
    card.append(cap, drawWeight(guides[key], label, name, key === 'regular' ? over.layer : null));   // the weight's name sits at the top left of its box
    return card;
  }));
  const svg = $('#dl-svg'), zip = $('#dl-zip');
  svg.href = `${id}/templates/${item.symbol}.svg`; svg.setAttribute('download', `${item.symbol}.svg`); svg.hidden = false;
  zip.href = `${id}/zips/${item.symbol}.symbolset.zip`; zip.setAttribute('download', `${item.symbol}.symbolset.zip`); zip.hidden = false;
  const line = $('#symbol-line');
  line.textContent = `${item.symbol} · rev ${item.rev} · updated ${item.updated}`; line.hidden = false;
  const report = $('#report'); report.href = reportUrl(item); report.hidden = false;
  $('#info-downloads').hidden = false; $('#add-wrap').hidden = false;
  const r = Editor.open({ source: state.source, item, guides, text, line: $('#symbol-line'), lineText: line.textContent, preset });
  ProjectsUI.setCurrent({ source: state.source, item });
  if (preset && preset.model && !r.presetApplied) ProjectsUI.toast(`${item.symbol} changed since you added it, so its layers start from the automatic ones.`);
}

// A pre-filled GitHub issue (the form in .github/ISSUE_TEMPLATE/icon-problem.yml): the field ids are the query names.
function reportUrl(item) {
  const src = state.source, m = state.meta;
  const build = [
    `Icon set: ${src.title} v${src.version} (${src.license})`,
    `Symbol: ${item.symbol}`,
    `Template rev: ${item.rev}, last updated ${item.updated}`,
    `Status: ${item.status}${item.flag ? ` (${item.flag})` : ''}`,
    ...item.notes.map(n => `Note: ${n}`),
    `Site build: ${m.built.slice(0, 10)}${m.version ? `, v${m.version}` : ''}, engine ${m.engine}, SwiftDraw ${m.swiftdraw}${m.commit ? `, commit ${m.commit.slice(0, 7)}${m.dirty ? ' (local changes)' : ''}` : ''}`,
    `Page: ${location.origin}${location.pathname}#${src.id}/${item.name}`,
  ].join('\n');
  const q = new URLSearchParams({ template: 'icon-problem.yml', title: `[${src.id}] ${item.name}: `, set: src.title, icon: item.name, build });
  return `${REPO}/issues/new?${q}`;
}

/* ---------- draggable dividers: icon list | preview | layers panel ---------- */
// One helper for both. `edge` says which side the sized panel is on: 'left' grows as the divider moves right, 'right' grows
// as it moves left. The width is a CSS variable on `host`, remembered per divider, and kept inside [min, max] and the window.
function makeResizer({ bar, host, prop, key, min, max, def, edge, room, onChange = () => {} }) {
  const clamp = w => Math.max(min, Math.min(Math.min(max, room()), Math.round(w)));
  const set = (w, save = true) => {
    w = clamp(w);
    host.style.setProperty(prop, w + 'px');
    bar.setAttribute('aria-valuenow', String(w));
    if (save) { try { localStorage.setItem(key, String(w)); } catch { /* storage unavailable: just not remembered */ } }
    return w;
  };
  const widthAt = x => { const r = host.getBoundingClientRect(); return edge === 'left' ? x - r.left : r.right - x; };
  let saved = def;
  try { saved = Number(localStorage.getItem(key)) || def; } catch { /* ignore */ }
  set(saved, false);
  bar.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault(); bar.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const move = ev => set(widthAt(ev.clientX), false);
    const up = ev => {
      bar.releasePointerCapture(ev.pointerId); document.body.classList.remove('resizing');
      bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up); bar.removeEventListener('pointercancel', up);
      set(widthAt(ev.clientX)); onChange();
    };
    bar.addEventListener('pointermove', move); bar.addEventListener('pointerup', up); bar.addEventListener('pointercancel', up);
  });
  bar.addEventListener('keydown', e => {
    const cur = Number(bar.getAttribute('aria-valuenow')), step = e.shiftKey ? 64 : 16, grow = edge === 'left' ? 'ArrowRight' : 'ArrowLeft';
    const next = { [grow]: cur + step, [edge === 'left' ? 'ArrowLeft' : 'ArrowRight']: cur - step, Home: min, End: max }[e.key];
    if (next === undefined) return;
    e.preventDefault(); set(next); onChange();
  });
  bar.addEventListener('dblclick', () => { set(def); onChange(); });
  addEventListener('resize', () => set(Number(bar.getAttribute('aria-valuenow')), false));    // keep it inside the window
}
function initResizers() {
  makeResizer({ bar: $('#resizer'), host: $('#app'), prop: '--side', key: 'symbolmaker.sideWidth', min: 220, max: 560, def: 340,
    edge: 'left', room: () => innerWidth - 360, onChange: renderList });
  const ws = $('#workspace');
  makeResizer({ bar: $('#resizer-layers'), host: ws, prop: '--layers', key: 'symbolmaker.layersWidth', min: 280, max: 640, def: 400,
    edge: 'right', room: () => (ws.clientWidth || innerWidth) - 320 });                       // always leave the preview 320 px
}

/* ---------- build line: the commit and the engine code link to GitHub ---------- */
// The engine id is a fingerprint of the engine code plus the SwiftDraw version, not a commit; it links to that code as it
// was at the build's commit. A build with uncommitted changes names its commit but links nothing, since the link would
// show different code from what ran.
function renderBuildLine(m) {
  const link = (href, text, title) => Object.assign(document.createElement('a'), { href, textContent: text, title, target: '_blank', rel: 'noopener' });
  const parts = [`Built ${m.built.slice(0, 10)}`];
  const released = m.version && m.version !== 'unknown' && m.version !== '0.0.0';      // 0.0.0: nothing has been released yet
  if (m.version && m.version !== 'unknown') parts.push(released ? ['', link(`${REPO}/releases/tag/v${m.version}`, `v${m.version}`, 'This release on GitHub, with every template attached')] : `v${m.version}`);
  const exact = m.commit && !m.dirty;
  if (m.commit) {
    const short = m.commit.slice(0, 7);
    parts.push(['commit ', exact ? link(`${REPO}/commit/${m.commit}`, short, 'The commit this site was built from') : `${short} (local changes)`]);
  }
  parts.push(['engine ', exact ? link(`${REPO}/tree/${m.commit}/symbolmaker/engine`, m.engine, 'The conversion code at this commit. The id is a fingerprint of that code and the SwiftDraw version.') : m.engine]);
  parts.push([link('https://github.com/swhitty/SwiftDraw', 'SwiftDraw', 'SwiftDraw on GitHub, the tool that converts the strokes into SF Symbols templates'), ` ${m.swiftdraw}`]);
  const out = [];
  parts.forEach((p, i) => { if (i) out.push(' · '); out.push(...[].concat(p)); });
  $('#build-line').replaceChildren(...out);
}

/* ---------- showing an icon from elsewhere (a project) ---------- */
async function openIcon(sourceId, name, preset) {
  if (!state.source || state.source.id !== sourceId) await useSource(sourceId);
  if (!state.index || !state.index.icons.some(i => i.name === name)) {
    ProjectsUI.toast(`${name} is no longer in ${state.source ? state.source.title : 'that icon set'}.`);
    return;
  }
  await pick(name, { preset });
}

/* ---------- sources ---------- */
async function useSource(id, { keepSearch = false } = {}) {
  const src = state.meta.sources.find(x => x.id === id) || state.meta.sources[0];
  state.source = src; state.picked = null; state.seq++;
  $('#source').value = src.id;
  if (!keepSearch) $('#search').value = '';
  state.index = state.indexes[src.id];
  if (!state.index) {
    try { state.index = state.indexes[src.id] = await getJSON(`${src.id}/index.json`); }
    catch { showNotes([`Could not load the ${src.title} icon list.`], 'error'); return; }
  }
  const bad = state.index.icons.filter(i => i.flag === 'problem').length;
  state.onlyProblems = false; $('#problems').checked = false;
  $('#problems-label').hidden = bad === 0;
  $('#problems-text').textContent = `Show only icons with problems (${bad})`;
  renderLicenses(src);
  Editor.close(); $('#workspace').hidden = true; $('#empty').hidden = false; $('#title').textContent = 'Symbol Maker';
  $('#badge').hidden = true; showNotes([], 'variable');
  for (const b of ['#dl-svg', '#dl-zip', '#symbol-line', '#report', '#info-downloads', '#add-wrap', '#info-status']) $(b).hidden = true;
  ProjectsUI.setCurrent(null);
  filterList();
}
// Which licenses apply: the icon set's own, and Lucide's for the icons the page itself uses (the same notice when Lucide
// is the selected set, so then it is one link).
function renderLicenses(src) {
  const link = (href, text) => Object.assign(document.createElement('a'), { href, textContent: text });
  const host = $('#licenses');
  if (src.id === 'lucide') { host.replaceChildren('Icons and page icons: ', link('lucide/LICENSE.txt', 'Lucide (ISC)')); return; }
  host.replaceChildren('Icons: ', link(`${src.id}/LICENSE.txt`, `${src.title} (${src.license})`), ' · Page icons: ', link('ui/LICENSE.txt', 'Lucide (ISC)'));
}
function parseHash() {
  const [a, b] = decodeURIComponent(location.hash.slice(1)).split('/');
  if (b === undefined) return { id: 'lucide', name: a || null };          // older links: #house
  return { id: a, name: b || null };
}

/* ---------- appearance: System / Light / Dark (the saved choice is applied by a script in <head>) ---------- */
const THEME_KEY = 'symbolmaker.theme';
function initTheme() {
  const root = document.documentElement;
  let saved = 'system';
  try { const t = localStorage.getItem(THEME_KEY); if (t === 'light' || t === 'dark') saved = t; } catch { /* ignore */ }
  for (const r of document.querySelectorAll('#theme input')) r.checked = r.value === saved;
  $('#theme').addEventListener('change', e => {
    const v = e.target.value;
    if (v === 'system') delete root.dataset.theme; else root.dataset.theme = v;
    try { if (v === 'system') localStorage.removeItem(THEME_KEY); else localStorage.setItem(THEME_KEY, v); } catch { /* not remembered */ }
  });
}

/* ---------- boot ---------- */
async function boot() {
  try { state.meta = await getJSON('sources.json'); }
  catch { showNotes(['Could not load the icon list.'], 'error'); return; }
  const m = state.meta;
  $('#source').replaceChildren(...m.sources.map(s => Object.assign(document.createElement('option'), { value: s.id, textContent: `${s.title} (${s.count})` })));
  Info.TEXT.build.body = `${m.sources.map(s => `${s.title} v${s.version}`).join(', ')}.\n\nConverted with SwiftDraw ${m.swiftdraw} at Apple’s weights (Ultralight ${m.weights.ultralight.toFixed(2)}×, Black ${m.weights.black.toFixed(2)}× the Regular stroke).\n\nThe engine id is a fingerprint of the conversion code and the SwiftDraw version. It links to that code at the commit the site was built from.${m.version && m.version !== 'unknown' ? `\n\nThis is version ${m.version} of Symbol Maker. Each release on GitHub has every template attached as zips.` : ''}`;
  $('#year').textContent = String(new Date(m.built).getFullYear());
  renderBuildLine(m);
  initResizers();
  ProjectsUI.init({ sourceTitle: id => (m.sources.find(s => s.id === id) || { title: id }).title, openIcon });
  const want = parseHash();
  await useSource(want.id);
  $('#source').addEventListener('change', e => { history.replaceState(null, '', '#' + e.target.value); useSource(e.target.value); });
  $('#search').addEventListener('input', filterList);
  $('#problems').addEventListener('change', e => { state.onlyProblems = e.target.checked; filterList(); });
  $('#list').addEventListener('scroll', renderList, { passive: true });
  $('#list').addEventListener('click', e => { const r = e.target.closest('.row'); if (r) pick(r.dataset.name, { scroll: false }); });
  $('#list').addEventListener('keydown', e => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const cur = state.items.findIndex(x => x.name === state.picked);
    const i = Math.max(0, Math.min(state.items.length - 1, cur + (e.key === 'ArrowDown' ? 1 : -1)));
    if (state.items[i]) pick(state.items[i].name);
  });
  addEventListener('resize', renderList);
  addEventListener('hashchange', async () => {
    const h = parseHash();
    if (h.id !== state.source.id) await useSource(h.id);
    if (h.name && h.name !== state.picked) pick(h.name);
  });
  if (want.name) pick(want.name);
}
initTheme();
Info.init();
boot();
