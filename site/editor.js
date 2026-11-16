'use strict';
/* The layer editor next to the three weights. It works on the template's text through layers.js and never touches the
   server: edits live in the page (and in this browser's storage, per icon), and the downloads are rebuilt from them.
   site.js hands over the picked icon with Editor.open() and clears the editor with Editor.close(). */
const Editor = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, props = {}, ...kids) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...kids);
    return e;
  };
  const SVGNS = 'http://www.w3.org/2000/svg';
  const wrap = sel => el('span', { className: 'sw' }, sel);                     // a select with the page's chevron
  const svgEl = (tag, attrs = {}) => { const e = document.createElementNS(SVGNS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };

  // One color per layer number, only used to tell layers apart in the "Layers" preview. Dark text stays readable on each.
  const HUES = ['#0a84ff', '#ff9f0a', '#30d158', '#bf5af2', '#ff453a', '#64d2ff'];
  const hue = n => HUES[(n - 1) % HUES.length];
  const MODES = [['monochrome', 'Monochrome'], ['layers', 'Layers'], ['levels', 'Levels'], ['hierarchical', 'Hierarchical'], ['multicolor', 'Multicolor']];
  // One color per level, only for the "Levels" view (the colors do not appear in the symbol).
  const LEVEL_HUE = { primary: '#0a84ff', secondary: '#ff9f0a', tertiary: '#bf5af2' };
  const OPACITY = { primary: 1, secondary: 0.5, tertiary: 0.25 };      // roughly what SF Symbols draws; its own values differ a little
  const STEP_MS = 450;
  const KEY = 'symbolmaker.layers.';
  const MAX_UNDO = 100;

  const S = { ctx: null, text: '', model: null, past: [], future: [], mode: 'monochrome', sel: null, hover: null, focus: null,
              urls: [], token: 0, license: null, timer: 0, ready: false };

  const store = {
    get(k) { try { return JSON.parse(localStorage.getItem(KEY + k)); } catch { return null; } },
    set(k, v) { try { localStorage.setItem(KEY + k, JSON.stringify(v)); } catch { /* storage unavailable: edits just are not remembered */ } },
    del(k) { try { localStorage.removeItem(KEY + k); } catch { /* ignore */ } },
  };
  const storeKey = () => `${S.ctx.source.id}/${S.ctx.item.name}`;

  /* ---------- geometry (paths are SwiftDraw's absolute M/L/C/Z) ---------- */
  function bbox(d) {
    const n = (d.match(/-?\d*\.?\d+(?:e-?\d+)?/g) || []).map(Number);
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (let i = 0; i + 1 < n.length; i += 2) { x0 = Math.min(x0, n[i]); x1 = Math.max(x1, n[i]); y0 = Math.min(y0, n[i + 1]); y1 = Math.max(y1, n[i + 1]); }
    return [x0, y0, x1, y1];
  }

  /* ---------- state changes ---------- */
  function commit(next, focus = null) {
    if (JSON.stringify(next) === JSON.stringify(S.model)) return;
    S.past.push(S.model); if (S.past.length > MAX_UNDO) S.past.shift();
    S.future = []; S.model = next; S.focus = focus;
    persist(); render();
  }
  function undo() { if (!S.past.length) return; S.future.push(S.model); S.model = S.past.pop(); S.focus = null; persist(); render(); }
  function redo() { if (!S.future.length) return; S.past.push(S.model); S.model = S.future.pop(); S.focus = null; persist(); render(); }
  function edited() { return Layers.isEdited(S.model, S.text); }
  function persist() {
    if (edited()) store.set(storeKey(), { rev: S.ctx.item.rev, model: S.model }); else store.del(storeKey());
  }
  function say(msg) { $('#layers-status').textContent = msg; }

  /* ---------- naming ---------- */
  function names() {
    const o = Layers.order(S.model), byId = new Map(o.map(x => [x.id, x]));
    let empty = 0;
    const label = new Map(S.model.layers.map(l => [l.id, byId.has(l.id) ? `Layer ${byId.get(l.id).number}` : `Empty layer ${++empty}`]));
    return { order: o, byId, label };
  }

  /* ---------- preview ---------- */
  function cards() { return [...document.querySelectorAll('#masters .card svg')]; }
  function paint(nm) {
    const { byId } = nm;
    const cap = cards();
    cap.forEach((svg, ci) => {
      const art = $('.art', svg); if (!art) return;
      const els = [...art.querySelectorAll('path[data-i]')];
      const rank = p => { const id = S.model.strokes[Number(p.dataset.i)]; return id === null ? -1 : byId.get(id).number; };
      els.sort((a, b) => rank(a) - rank(b)).forEach(p => art.append(p));          // back to front, as the template will be written
      for (const p of els) {
        const i = Number(p.dataset.i), id = S.model.strokes[i], info = id === null ? null : byId.get(id);
        p.style.fill = ''; p.style.opacity = ''; p.style.stroke = '';
        p.classList.toggle('unused', !info);
        p.classList.toggle('sel', S.sel === i || S.hover === i);
        p.classList.toggle('white', !!info && S.mode === 'multicolor' && info.color === 'white');
        p.removeAttribute('data-n');
        if (!info) continue;
        p.dataset.n = String(info.number - 1);
        p.style.setProperty('--n', String(info.number - 1));
        if (S.mode === 'layers') { p.style.fill = hue(info.number); }
        else if (S.mode === 'levels') { p.style.fill = LEVEL_HUE[info.level]; }
        else if (S.mode === 'hierarchical') { p.style.opacity = String(OPACITY[info.level]); }
        else if (S.mode === 'multicolor') { p.style.fill = Layers.colorHex(info.color); }
      }
      $('.badges', svg)?.remove();
      if (ci === 1 && (S.mode === 'layers' || S.mode === 'levels')) {          // numbers on the Regular master only
        const g = svgEl('g', { class: 'badges', 'pointer-events': 'none' });
        for (const l of nm.order) {
          const boxes = l.strokes.map(i => bbox(S.ctx.guides.regular.paths[i]));
          const x = Math.min(...boxes.map(b => b[0])), y = Math.min(...boxes.map(b => b[1]));
          const b = svgEl('g', { transform: `translate(${x} ${y})` });
          b.append(svgEl('circle', { r: 5.2, fill: S.mode === 'levels' ? LEVEL_HUE[l.level] : hue(l.number), stroke: '#fff', 'stroke-width': 0.8 }),
                   Object.assign(svgEl('text', { 'text-anchor': 'middle', 'dominant-baseline': 'central', 'font-size': 6.6, 'font-weight': 700, fill: '#111' }), { textContent: String(l.number) }));
          g.append(b);
        }
        art.append(g);
      }
    });
    $('#masters').dataset.mode = S.mode;
    const legend = $('#legend');
    legend.hidden = S.mode !== 'levels';
    if (!legend.hidden) {
      const count = lv => S.model.layers.filter(l => l.level === lv && nm.byId.has(l.id)).length;
      legend.replaceChildren(...Layers.LEVELS.map(lv => {
        const dot = el('span', { className: 'dot' }); dot.style.background = LEVEL_HUE[lv];
        const n = count(lv);
        return el('li', {}, dot, `${lv[0].toUpperCase() + lv.slice(1)} `, el('span', { className: 'muted', textContent: `${n} ${n === 1 ? 'layer' : 'layers'}` }));
      }));
    }
  }

  /* ---------- the panel ---------- */
  function thumb(i) {
    const g = S.ctx.guides.regular, boxes = g.paths.map(bbox);
    const x0 = Math.min(...boxes.map(b => b[0])), y0 = Math.min(...boxes.map(b => b[1]));
    const x1 = Math.max(...boxes.map(b => b[2])), y1 = Math.max(...boxes.map(b => b[3]));
    const pad = 3;
    const svg = svgEl('svg', { viewBox: `${x0 - pad} ${y0 - pad} ${x1 - x0 + 2 * pad} ${y1 - y0 + 2 * pad}`, class: 'thumb', 'aria-hidden': 'true' });
    g.paths.forEach((d, k) => svg.append(svgEl('path', { d, class: k === i ? 'me' : 'rest' })));
    return svg;
  }
  function strokeRow(i, nm) {
    const here = S.model.strokes[i];
    const sel = el('select', { title: `Where stroke ${i + 1} goes` });
    sel.setAttribute('aria-label', `Layer for stroke ${i + 1}`);
    for (const l of S.model.layers) sel.append(Object.assign(new Option(nm.label.get(l.id), String(l.id)), { selected: l.id === here }));
    sel.append(Object.assign(new Option('Not in the symbol', ''), { selected: here === null }));
    sel.addEventListener('change', () => {
      const to = sel.value === '' ? null : Number(sel.value);
      commit(Layers.assign(S.model, i, to), { stroke: i });
      say(to === null ? `Stroke ${i + 1} is no longer in the symbol.` : `Stroke ${i + 1} moved to ${names().label.get(to)}.`);
    });
    const li = el('li', { className: 'stroke' + (S.sel === i ? ' sel' : '') }, thumb(i), el('span', { className: 'sname', textContent: `Stroke ${i + 1}` }), wrap(sel));
    li.dataset.i = String(i);
    li.addEventListener('pointerenter', () => hover(i)); li.addEventListener('pointerleave', () => hover(null));
    li.addEventListener('focusin', () => hover(i)); li.addEventListener('focusout', () => hover(null));
    li.addEventListener('click', e => { if (e.target === li || e.target.closest('.thumb') || e.target.classList.contains('sname')) select(i, false); });
    return li;
  }
  function layerCard(l, idx, nm) {
    const info = nm.byId.get(l.id), n = S.model.layers.length;
    const title = nm.label.get(l.id);
    const btn = (act, icon, label, disabled) => {
      const b = el('button', { type: 'button', className: 'icon-btn', title: label, disabled }, el('span', { className: `ico ${icon}`, ariaHidden: 'true' }));
      b.setAttribute('aria-label', `${label}: ${title}`); b.dataset.act = act; b.dataset.id = String(l.id);
      return b;
    };
    const up = btn('up', 'i-up', 'Move earlier in the animation order', idx === 0);
    const down = btn('down', 'i-down', 'Move later in the animation order', idx === n - 1);
    const del = btn('remove', 'i-trash', 'Remove layer', false);
    up.addEventListener('click', () => { commit(Layers.moveLayer(S.model, l.id, -1), { id: l.id, act: 'up' }); say(`${title} moved earlier.`); });
    down.addEventListener('click', () => { commit(Layers.moveLayer(S.model, l.id, +1), { id: l.id, act: 'down' }); say(`${title} moved later.`); });
    del.addEventListener('click', () => {
      const k = S.model.strokes.filter(s => s === l.id).length;
      commit(Layers.removeLayer(S.model, l.id), { add: true });
      say(`${title} removed${k ? `; its ${k === 1 ? 'stroke is' : 'strokes are'} now not in the symbol` : ''}.`);
    });
    const num = el('span', { className: 'num', textContent: info ? String(info.number) : '–' });
    if (info) num.style.setProperty('--c', hue(info.number));
    const level = el('select', { className: 'level' });
    level.setAttribute('aria-label', `Level of ${title}`);
    for (const v of Layers.LEVELS) level.append(Object.assign(new Option(v[0].toUpperCase() + v.slice(1), v), { selected: v === l.level }));
    level.addEventListener('change', () => commit(Layers.setLevel(S.model, l.id, level.value), { id: l.id, act: 'level' }));
    const colors = el('div', { className: 'swatches', role: 'radiogroup' });
    colors.setAttribute('aria-label', `Color of ${title} in Multicolor`);
    for (const c of Layers.COLORS) {
      const b = el('button', { type: 'button', className: 'swatch' + (c.id === l.color ? ' on' : ''), title: c.label + (c.id === 'tintColor' ? ' (follows the app tint)' : '') });
      b.style.setProperty('--sw', c.hex); b.setAttribute('role', 'radio'); b.setAttribute('aria-checked', String(c.id === l.color)); b.setAttribute('aria-label', c.label);
      b.dataset.act = 'color:' + c.id; b.dataset.id = String(l.id);
      b.addEventListener('click', () => commit(Layers.setColor(S.model, l.id, c.id), { id: l.id, act: 'color:' + c.id }));
      colors.append(b);
    }
    const mine = S.model.strokes.map((s, i) => (s === l.id ? i : -1)).filter(i => i >= 0);
    const strokes = el('ul', { className: 'strokes' }, ...mine.map(i => strokeRow(i, nm)));
    const li = el('li', { className: 'layer' + (info ? '' : ' empty'), tabIndex: -1 },
      el('div', { className: 'layer-top' }, num, el('strong', { textContent: title }),
         info ? el('span', { className: 'muted', textContent: `${mine.length} ${mine.length === 1 ? 'stroke' : 'strokes'}` }) : el('span', { className: 'muted', textContent: 'not written' }),
         el('span', { className: 'spacer' }), up, down, del),
      el('div', { className: 'layer-opts' },
         el('div', {}, el('span', { className: 'cap-row' }, el('span', { className: 'caption', textContent: 'Level' }), Info.button('level')), wrap(level)),
         el('div', {}, el('span', { className: 'cap-row' }, el('span', { className: 'caption', textContent: 'Color' }), Info.button('color')), colors)),
      info ? strokes : el('p', { className: 'note', textContent: 'Empty: not written until it has a stroke. Pick this layer in a stroke’s menu.' }));
    li.dataset.id = String(l.id);
    return li;
  }
  function renderOrder(nm) {
    const strip = $('#order-strip');
    strip.replaceChildren(...nm.order.map((l, k) => {
      const num = el('span', { className: 'num', textContent: String(l.number) });
      num.style.setProperty('--c', hue(l.number));
      const li = el('li', { title: k === 0 ? 'Back layer: first in the order' : k === nm.order.length - 1 ? 'Front layer: last in the order' : '' },
        num, el('span', { className: 'what', textContent: `${l.strokes.length} ${l.strokes.length === 1 ? 'stroke' : 'strokes'}` }));
      li.style.setProperty('--n', String(k));
      return li;
    }));
    $('#play').disabled = nm.order.length < 1;
  }
  function renderLayers(nm) {
    const list = $('#layer-list');
    list.replaceChildren(...S.model.layers.map((l, i) => layerCard(l, i, nm)));
    const out = S.model.strokes.map((s, i) => (s === null ? i : -1)).filter(i => i >= 0);
    $('#unused').hidden = out.length === 0;
    $('#unused-list').replaceChildren(...out.map(i => strokeRow(i, nm)));
  }
  function restoreFocus() {
    const f = S.focus; S.focus = null;
    if (!f) return;
    let target = null;
    if (f.add) target = $('#add-layer');
    else if (f.id !== undefined) {
      target = $(`#layer-list [data-act="${f.act}"][data-id="${f.id}"]`);
      if (!target || target.disabled) target = $(`#layer-list .layer[data-id="${f.id}"]`);      // e.g. it just reached the end
    } else if (f.stroke !== undefined) target = $(`#layers .stroke[data-i="${f.stroke}"] select`);
    else if (f.newLayer !== undefined) target = $(`#layer-list .layer[data-id="${f.newLayer}"]`);
    target?.focus();
  }

  /* ---------- downloads ---------- */
  function revoke() { S.urls.forEach(u => URL.revokeObjectURL(u)); S.urls = []; }
  function setLink(a, href, ok) {
    if (href) a.href = href; else a.removeAttribute('href');
    a.classList.toggle('disabled', !ok); a.setAttribute('aria-disabled', String(!ok));
  }
  async function updateDownloads() {
    const mine = ++S.token, c = S.ctx, svgA = $('#dl-svg'), zipA = $('#dl-zip');
    revoke();
    if (!edited()) { setLink(svgA, c.defaults.svg, true); setLink(zipA, c.defaults.zip, true); c.line.textContent = c.lineText; return; }
    c.line.textContent = `${c.lineText} · layers edited`;
    if (Layers.problem(S.model)) { setLink(svgA, null, false); setLink(zipA, null, false); return; }
    const svg = Layers.markEdited(Layers.apply(S.text, S.model));
    const url = u => { S.urls.push(u); return u; };
    setLink(svgA, url(URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }))), true);
    const lic = await S.license;
    if (mine !== S.token) return;
    const sym = c.item.symbol, id = c.source.id;
    const zip = Zip.build([
      { name: `${sym}.symbolset/Contents.json`, data: JSON.stringify({ info: { author: 'xcode', version: 1 }, symbols: [{ filename: `${sym}.svg`, idiom: 'universal' }] }, null, 2) },
      { name: `${sym}.symbolset/${sym}.svg`, data: svg },
      { name: `LICENSE-${id}.txt`, data: lic },
    ]);
    setLink(zipA, url(URL.createObjectURL(new Blob([zip], { type: 'application/zip' }))), true);
  }

  /* ---------- everything ---------- */
  function render() {
    const nm = names();
    paint(nm); renderOrder(nm); renderLayers(nm);
    const prob = Layers.problem(S.model), isEd = edited();
    const p = $('#layers-problem'); p.hidden = !prob; p.textContent = prob || '';
    $('#edited').hidden = !isEd;
    $('#undo').disabled = !S.past.length; $('#redo').disabled = !S.future.length; $('#reset').disabled = !isEd;
    $('#order-note').textContent = nm.order.length > 1 ? `Layer 1 is the back, layer ${nm.order.length} the front.` : '';
    updateDownloads();
    restoreFocus();
  }
  function hover(i) { S.hover = i; for (const p of document.querySelectorAll('#masters path[data-i]')) p.classList.toggle('sel', Number(p.dataset.i) === S.sel || Number(p.dataset.i) === i); }
  function select(i, scroll = true) {
    S.sel = S.sel === i ? null : i;
    for (const p of document.querySelectorAll('#masters path[data-i]')) p.classList.toggle('sel', Number(p.dataset.i) === S.sel);
    for (const r of document.querySelectorAll('#layers .stroke')) r.classList.toggle('sel', Number(r.dataset.i) === S.sel);
    if (scroll && S.sel !== null) $(`#layers .stroke[data-i="${S.sel}"]`)?.scrollIntoView({ block: 'nearest' });
  }
  function stop() {
    clearTimeout(S.timer);
    $('#masters').classList.remove('playing'); $('#order-strip').classList.remove('playing');
  }
  function play() {
    stop();
    const m = $('#masters'), strip = $('#order-strip'), n = Layers.order(S.model).length;
    void m.offsetWidth;                                                       // restart the animation if it was playing
    m.classList.add('playing'); strip.classList.add('playing');
    S.timer = setTimeout(stop, (n - 1) * STEP_MS + 1100);
  }

  function wire() {
    if (S.ready) return;
    S.ready = true;
    $('#mode').replaceChildren(...MODES.map(([k, label]) => {
      const i = el('input', { type: 'radio', name: 'mode', value: k, checked: k === S.mode });
      return el('label', {}, i, el('span', { textContent: label }));
    }));
    $('#mode').addEventListener('change', e => { S.mode = e.target.value; paint(names()); say(`Showing ${MODES.find(m => m[0] === S.mode)[1]}.`); });
    $('#undo').addEventListener('click', undo); $('#redo').addEventListener('click', redo);
    $('#reset').addEventListener('click', () => { commit(Layers.fromTemplate(S.text)); say('Back to the automatic layers.'); });
    $('#add-layer').addEventListener('click', () => {
      const next = Layers.addLayer(S.model);
      commit(next, { newLayer: next.layers.at(-1).id });
      say('Added an empty layer. Choose it in a stroke’s menu to put a stroke in it.');
    });
    $('#play').addEventListener('click', play);
    $('#masters').addEventListener('click', e => { const p = e.target.closest('path[data-i]'); if (p) select(Number(p.dataset.i)); });
    document.addEventListener('keydown', e => {
      if (!S.ctx || !(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== 'z') return;
      if (e.target.closest?.('input[type=search], input[type=text]')) return;
      e.preventDefault(); e.shiftKey ? redo() : undo();
    });
    $('#layers').append(el('p', { id: 'layers-status', className: 'sr-only', role: 'status' }));
  }

  /** The current layers for saving elsewhere (a project): { model, rev }, with model null while they are the automatic ones. */
  function snapshot() {
    if (!S.ctx || !S.model) return null;
    return { model: edited() ? JSON.parse(JSON.stringify(S.model)) : null, rev: S.ctx.item.rev };
  }

  /** Show an icon. `ctx.preset` = { model, rev }: layers saved elsewhere (a project) to start from, used only if the icon is
      still at the revision they were made for. -> { presetApplied } */
  function open(ctx) {
    wire();
    stop(); revoke();
    ctx.defaults = { svg: $('#dl-svg').getAttribute('href'), zip: $('#dl-zip').getAttribute('href') };
    S.ctx = ctx; S.text = ctx.text; S.past = []; S.future = []; S.sel = null; S.hover = null; S.focus = null;
    let base;
    try { base = Layers.fromTemplate(ctx.text); } catch { base = null; }
    $('#workspace').classList.toggle('no-layers', !base);
    if (!base) { S.model = null; return { presetApplied: false }; }
    let presetApplied = false, from = null;
    if (ctx.preset) {
      from = ctx.preset.rev === ctx.item.rev && ctx.preset.model ? Layers.restore(ctx.preset.model, ctx.text) : null;
      presetApplied = !!from;
    }
    const saved = store.get(storeKey());
    const back = ctx.preset ? null : saved && saved.rev === ctx.item.rev ? Layers.restore(saved.model, ctx.text) : null;
    if (saved && !back && !ctx.preset) store.del(storeKey());                // for an older version of this icon: not applicable
    S.model = from || back || base;
    if (ctx.preset) persist();                                                // opening a project's copy replaces this icon's draft
    S.license = fetch(`${ctx.source.id}/LICENSE.txt`).then(r => (r.ok ? r.text() : Promise.reject())).catch(() =>
      `${ctx.source.title} v${ctx.source.version}, ${ctx.source.license} License.\n`);
    render();
    return { presetApplied };
  }
  function close() { stop(); revoke(); S.ctx = null; S.token++; }

  return { open, close, snapshot };
})();
