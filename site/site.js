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
function drawWeight(g, label, name) {
  const svg = svgEl('svg', { viewBox: `${-PAD} ${-TOP} ${g.width + 2 * PAD} ${TOP + BOTTOM}`, role: 'img',
    'aria-label': `${name}, ${label} weight, with baseline, cap line and margins` });
  const line = (x1, y1, x2, y2, c) => svgEl('line', { x1, y1, x2, y2, stroke: c, 'stroke-width': 0.5, 'vector-effect': 'non-scaling-stroke' });
  const scale = CAP / g.cap;
  const art = svgEl('g', { transform: `scale(${scale}) translate(${-g.origin[0]} ${-g.origin[1]})` });
  g.paths.forEach(d => art.append(svgEl('path', { d })));
  svg.append(line(-PAD, 0, g.width + PAD, 0, BLUE), line(-PAD, -CAP, g.width + PAD, -CAP, BLUE), art,
    line(0, -TOP + 6, 0, 18, MARGIN), line(g.width, -TOP + 6, g.width, 18, MARGIN));
  return svg;
}
function showBadge(status) {
  const b = $('#badge'), m = BADGES[status];
  b.hidden = !m;
  if (m) { b.textContent = m[0]; b.className = 'badge ' + m[1]; }
}
function showNotes(notes, status) {
  const b = $('#banner');
  b.replaceChildren(...notes.map(t => Object.assign(document.createElement('p'), { textContent: t })));
  b.className = 'banner' + (status === 'variable' ? '' : ' warn');
  b.hidden = notes.length === 0;
}
async function pick(name, { scroll = true } = {}) {
  const item = state.index.icons.find(i => i.name === name);
  if (!item) return;
  state.picked = name;
  const id = state.source.id, hash = `#${id}/${name}`;
  if (location.hash !== hash) history.replaceState(null, '', hash);
  renderList(); if (scroll) scrollToPicked();
  const mine = ++state.seq;
  let guides;
  try { guides = await getJSON(`${id}/guides/${item.symbol}.json`); }
  catch { showNotes(['Could not load this icon. Check your connection and try again.'], 'error'); return; }
  if (mine !== state.seq) return;                      // a newer pick is loading
  $('#title').textContent = name;
  showBadge(item.status); showNotes(item.notes, item.status);
  $('#empty').hidden = true;
  const host = $('#masters'); host.hidden = false;
  host.replaceChildren(...WEIGHTS.map(([key, label]) => {
    const card = document.createElement('figure'); card.className = 'card';
    const cap = document.createElement('figcaption'); cap.className = 'label';
    cap.append(Object.assign(document.createElement('strong'), { textContent: label }));
    card.append(drawWeight(guides[key], label, name), cap);
    return card;
  }));
  const svg = $('#dl-svg'), zip = $('#dl-zip');
  svg.href = `${id}/templates/${item.symbol}.svg`; svg.setAttribute('download', `${item.symbol}.svg`); svg.hidden = false;
  zip.href = `${id}/zips/${item.symbol}.symbolset.zip`; zip.setAttribute('download', `${item.symbol}.symbolset.zip`); zip.hidden = false;
  const line = $('#symbol-line');
  line.textContent = `${item.symbol} · rev ${item.rev} · updated ${item.updated}`; line.hidden = false;
  const report = $('#report'); report.href = reportUrl(item); report.hidden = false;
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
    `Site build: ${m.built.slice(0, 10)}, engine ${m.engine}, SwiftDraw ${m.swiftdraw}`,
    `Page: ${location.origin}${location.pathname}#${src.id}/${item.name}`,
  ].join('\n');
  const q = new URLSearchParams({ template: 'icon-problem.yml', title: `[${src.id}] ${item.name}: `, set: src.title, icon: item.name, build });
  return `${REPO}/issues/new?${q}`;
}

/* ---------- draggable divider between the icon list and the preview ---------- */
const SIDE_KEY = 'symbolmaker.sideWidth', SIDE_MIN = 220, SIDE_MAX = 560, SIDE_DEFAULT = 300;
function initResizer() {
  const app = $('#app'), bar = $('#resizer');
  const clamp = w => Math.max(SIDE_MIN, Math.min(Math.min(SIDE_MAX, innerWidth - 360), Math.round(w)));
  const set = (w, save = true) => {
    w = clamp(w);
    app.style.setProperty('--side', w + 'px');
    bar.setAttribute('aria-valuenow', String(w));
    if (save) { try { localStorage.setItem(SIDE_KEY, String(w)); } catch { /* storage unavailable: just not remembered */ } }
    return w;
  };
  let saved = SIDE_DEFAULT;
  try { saved = Number(localStorage.getItem(SIDE_KEY)) || SIDE_DEFAULT; } catch { /* ignore */ }
  set(saved, false);
  bar.addEventListener('pointerdown', e => {
    if (e.button !== 0) return;
    e.preventDefault(); bar.setPointerCapture(e.pointerId); document.body.classList.add('resizing');
    const move = ev => set(ev.clientX - app.getBoundingClientRect().left, false);
    const up = ev => {
      bar.releasePointerCapture(ev.pointerId); document.body.classList.remove('resizing');
      bar.removeEventListener('pointermove', move); bar.removeEventListener('pointerup', up); bar.removeEventListener('pointercancel', up);
      set(ev.clientX - app.getBoundingClientRect().left); renderList();
    };
    bar.addEventListener('pointermove', move); bar.addEventListener('pointerup', up); bar.addEventListener('pointercancel', up);
  });
  bar.addEventListener('keydown', e => {
    const cur = Number(bar.getAttribute('aria-valuenow')), step = e.shiftKey ? 64 : 16;
    const next = { ArrowLeft: cur - step, ArrowRight: cur + step, Home: SIDE_MIN, End: SIDE_MAX }[e.key];
    if (next === undefined) return;
    e.preventDefault(); set(next);
  });
  bar.addEventListener('dblclick', () => { set(SIDE_DEFAULT); renderList(); });
  addEventListener('resize', () => set(Number(bar.getAttribute('aria-valuenow')), false));    // keep it inside the window
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
  $('#masters').hidden = true; $('#empty').hidden = false; $('#title').textContent = 'Symbol Maker';
  $('#badge').hidden = true; showNotes([], 'variable');
  for (const b of ['#dl-svg', '#dl-zip', '#symbol-line', '#report']) $(b).hidden = true;
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

/* ---------- boot ---------- */
async function boot() {
  try { state.meta = await getJSON('sources.json'); }
  catch { showNotes(['Could not load the icon list.'], 'error'); return; }
  const m = state.meta;
  $('#source').replaceChildren(...m.sources.map(s => Object.assign(document.createElement('option'), { value: s.id, textContent: `${s.title} (${s.count})` })));
  $('#build-info').textContent = `${m.sources.map(s => `${s.title} v${s.version}`).join(', ')}. Converted with SwiftDraw ${m.swiftdraw} at Apple's weights (Ultralight ${m.weights.ultralight.toFixed(2)}×, Black ${m.weights.black.toFixed(2)}×). Built ${m.built.slice(0, 10)}.`;
  $('#year').textContent = String(new Date(m.built).getFullYear());
  $('#build-line').textContent = `Built ${m.built.slice(0, 10)} · engine ${m.engine} · SwiftDraw ${m.swiftdraw}`;
  initResizer();
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
boot();
