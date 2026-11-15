'use strict';
/* Symbol Maker site: a searchable list of icons, a preview of the three weights on the template's guides, and downloads.
   No framework and no build step. Everything it needs is a static file next to this page. */

const $ = (s, r = document) => r.querySelector(s);
const SVGNS = 'http://www.w3.org/2000/svg';
const ROW = 26;
const WEIGHTS = [['ultralight', 'Ultralight'], ['regular', 'Regular'], ['black', 'Black']];
const BADGES = { variable: ['Variable weights', ''], 'single-weight': ['Single weight', 'warn'], 'identical-masters': ['No weight change', 'warn'] };

const state = { index: null, items: [], picked: null, seq: 0 };

/* ---------- data ---------- */
async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ---------- list (virtualized: 2,000+ rows) ---------- */
function filterList() {
  const q = $('#search').value.trim().toLowerCase().replace(/[\s.]+/g, '-');
  const all = state.index.icons;
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
    const n = state.items[i].name;
    const d = document.createElement('div');
    d.className = 'row'; d.setAttribute('role', 'option'); d.dataset.name = n; d.textContent = n;
    d.style.setProperty('--icon', `url("icons/${n}.svg")`);
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
  if (location.hash.slice(1) !== name) history.replaceState(null, '', '#' + name);
  renderList(); if (scroll) scrollToPicked();
  const mine = ++state.seq;
  let guides;
  try { guides = await getJSON(`guides/${item.symbol}.json`); }
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
  svg.href = `templates/${item.symbol}.svg`; svg.setAttribute('download', `${item.symbol}.svg`); svg.hidden = false;
  zip.href = `zips/${item.symbol}.symbolset.zip`; zip.setAttribute('download', `${item.symbol}.symbolset.zip`); zip.hidden = false;
  const line = $('#symbol-line'); line.textContent = item.symbol; line.hidden = false;
}

/* ---------- boot ---------- */
async function boot() {
  try { state.index = await getJSON('index.json'); }
  catch { showNotes(['Could not load the icon list.'], 'error'); return; }
  const ix = state.index;
  $('#lver').textContent = 'v' + ix.version;
  $('#build-info').textContent = `Lucide v${ix.version}, converted with SwiftDraw ${ix.swiftdraw} at Apple's weights (Ultralight ${ix.weights.ultralight.toFixed(2)}×, Black ${ix.weights.black.toFixed(2)}×). Built ${ix.built.slice(0, 10)}.`;
  filterList();
  $('#search').addEventListener('input', filterList);
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
  addEventListener('hashchange', () => { const n = location.hash.slice(1); if (n && n !== state.picked) pick(n); });
  if (location.hash.length > 1) pick(decodeURIComponent(location.hash.slice(1)));
}
boot();
