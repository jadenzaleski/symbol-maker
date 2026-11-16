'use strict';
/* Projects on the page: a tab in the sidebar to make, rename and delete projects, the project view with its symbols, the
   "Add to project" menu on an icon, and export. The data and the export files come from projects.js; this file is the
   page and the saving (localStorage, this browser only). site.js starts it with ProjectsUI.init() once the icon sets are
   known, and tells it which icon is open with ProjectsUI.setCurrent(). */
const ProjectsUI = (() => {
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, props = {}, ...kids) => { const e = Object.assign(document.createElement(tag), props); e.append(...kids); return e; };
  const KEY = 'symbolmaker.projects';

  const S = { store: Projects.empty(), selected: null, tab: 'icons', current: null, ctx: null, storageOk: true,
              renaming: null, iconTitle: 'Symbol Maker', toastTimer: 0, busy: false, menuOpen: false, newBtn: null };

  const now = () => new Date().toISOString();
  const newId = () => (globalThis.crypto && crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2));
  const project = () => (S.selected ? Projects.find(S.store, S.selected) : null);
  const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;

  /* ---------- saving ---------- */
  function load() {
    try { S.store = Projects.parse(localStorage.getItem(KEY) || ''); S.storageOk = true; }
    catch { S.store = Projects.empty(); S.storageOk = false; }
  }
  function save() {
    try { localStorage.setItem(KEY, Projects.serialize(S.store)); S.storageOk = true; }
    catch { S.storageOk = false; }
  }
  // Every change to the projects goes through here: keep it, save it, redraw.
  function change(next, { select } = {}) {
    S.store = next;
    if (select !== undefined) S.selected = select;
    if (S.selected && !Projects.find(S.store, S.selected)) S.selected = null;
    save(); render();
  }

  /* ---------- a message with an optional Undo ---------- */
  function toast(text, action = null) {
    const t = $('#toast');
    clearTimeout(S.toastTimer);
    t.replaceChildren(el('span', { textContent: text }));
    if (action) {
      const b = el('button', { type: 'button', className: 'toast-btn', textContent: action.label });
      b.addEventListener('click', () => { hideToast(); action.run(); });
      t.append(b);
    }
    t.hidden = false;
    S.toastTimer = setTimeout(hideToast, action ? 9000 : 6000);
  }
  function hideToast() { clearTimeout(S.toastTimer); $('#toast').hidden = true; }

  /* ---------- tabs ---------- */
  function setTab(tab) {
    if (tab === S.tab) return;
    if (tab === 'projects') S.iconTitle = $('#title').textContent;
    S.tab = tab;
    closeMenu(false);
    $('#app').dataset.tab = tab;
    for (const r of document.querySelectorAll('#side-tabs input')) r.checked = r.value === tab;
    $('#pane-icons').hidden = tab !== 'icons'; $('#pane-projects').hidden = tab !== 'projects';
    $('#icon-stage').hidden = tab !== 'icons'; $('#project-view').hidden = tab !== 'projects';
    if (tab === 'icons') $('#title').textContent = S.iconTitle;
    render();
  }

  /* ---------- the sidebar list ---------- */
  function renameBox(p) {
    const input = el('input', { type: 'text', className: 'rename', value: p.name, maxLength: Projects.MAX_NAME, spellcheck: false });
    input.setAttribute('aria-label', `Name of project ${p.name}`);
    const err = el('span', { className: 'row-error', role: 'alert' });
    let done = false;
    const finish = commit => {
      if (done) return; done = true;
      S.renaming = null;
      if (commit && input.value.trim() !== p.name) {
        try { change(Projects.rename(S.store, p.id, input.value, now())); }
        catch (e) { toast(e.message); render(); }
      } else render();
    };
    input.addEventListener('keydown', e => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const bad = input.value.trim() === p.name ? null : Projects.validateName(S.store, input.value, p.id);
        if (bad) { err.textContent = bad; input.setAttribute('aria-invalid', 'true'); } else finish(true);
      } else if (e.key === 'Escape') { e.preventDefault(); finish(false); }
    });
    input.addEventListener('input', () => { err.textContent = ''; input.removeAttribute('aria-invalid'); });
    input.addEventListener('blur', () => { const bad = Projects.validateName(S.store, input.value, p.id); finish(!bad); });
    queueMicrotask(() => { input.focus(); input.select(); });
    return el('div', { className: 'rename-wrap' }, input, err);
  }
  function projectRow(p) {
    const on = p.id === S.selected;
    const iconBtn = (icon, label, run) => {
      const b = el('button', { type: 'button', className: 'icon-btn', title: label }, el('span', { className: `ico ${icon}`, ariaHidden: 'true' }));
      b.setAttribute('aria-label', `${label}: ${p.name}`);
      b.addEventListener('click', e => { e.stopPropagation(); run(); });
      return b;
    };
    const main = S.renaming === p.id ? renameBox(p) : (() => {
      const b = el('button', { type: 'button', className: 'project-main' },
        el('span', { className: 'ico i-folder', ariaHidden: 'true' }), el('span', { className: 'pname', textContent: p.name }),
        el('span', { className: 'muted pcount', textContent: String(p.items.length) }));
      b.setAttribute('aria-label', `${p.name}, ${plural(p.items.length, 'symbol', 'symbols')}`);
      b.addEventListener('click', () => { S.selected = p.id; render(); });
      b.addEventListener('dblclick', () => { S.selected = p.id; S.renaming = p.id; render(); });
      return b;
    })();
    const li = el('li', { className: 'project-row' + (on ? ' on' : '') }, main);
    if (S.renaming !== p.id) li.append(
      iconBtn('i-pencil', 'Rename', () => { S.selected = p.id; S.renaming = p.id; render(); }),
      iconBtn('i-trash', 'Delete', () => deleteProject(p.id)));
    if (on) li.setAttribute('aria-current', 'true');
    return li;
  }
  function createProject(name) {
    const id = newId();
    change(Projects.create(S.store, { id, name, now: now() }), { select: id });
    return id;
  }
  function deleteProject(id) {
    const p = Projects.find(S.store, id), at = S.store.projects.findIndex(x => x.id === id);
    change(Projects.remove(S.store, id));
    toast(`Deleted “${p.name}”.`, { label: 'Undo', run: () => change(Projects.insertProject(S.store, p, at), { select: p.id }) });
  }

  /* ---------- the project view ---------- */
  function card(item, p) {
    const pic = el('span', { className: 'card-icon', ariaHidden: 'true' });
    pic.style.setProperty('--icon', `url("${item.source}/icons/${item.name}.svg")`);
    const btn = (icon, label, run, cls = 'btn small') => {
      const b = el('button', { type: 'button', className: cls }, el('span', { className: `ico ${icon}`, ariaHidden: 'true' }), ` ${label}`);
      b.setAttribute('aria-label', `${label} ${item.symbol}`);
      b.addEventListener('click', run);
      return b;
    };
    const key = Projects.itemKey(item.source, item.name);
    const li = el('li', { className: 'pcard' }, pic,
      el('div', { className: 'pcard-text' },
        el('strong', { textContent: item.name }),
        el('span', { className: 'muted mono', textContent: item.symbol }),
        el('span', { className: 'muted', textContent: S.ctx.sourceTitle(item.source) })),
      item.model ? el('span', { className: 'badge', textContent: 'Edited' }) : '',
      el('span', { className: 'spacer' }),
      btn('i-layers', 'Edit', () => openItem(item)),
      btn('i-x', 'Remove', () => {
        const at = p.items.findIndex(i => Projects.itemKey(i.source, i.name) === key);
        change(Projects.removeItem(S.store, p.id, key, now()));
        toast(`Removed ${item.symbol} from “${p.name}”.`, { label: 'Undo', run: () => change(Projects.insertItem(S.store, p.id, item, at, now())) });
      }));
    return li;
  }
  function renderView() {
    const p = project();
    const none = $('#project-empty');
    $('#title').textContent = p ? p.name : 'Projects';
    for (const id of ['#export-catalog', '#export-svg', '#info-export']) $(id).hidden = !p;
    for (const id of ['#export-catalog', '#export-svg']) $(id).disabled = !p || !p.items.length || S.busy;
    const cards = $('#project-cards');
    if (!p) {
      cards.replaceChildren(); none.hidden = false;
      $('h2', none).textContent = S.store.projects.length ? 'Pick a project' : 'No projects yet';
      $('p', none).replaceChildren(...(S.store.projects.length ? ['Choose one on the left to see its symbols and export it.'] : ['Make a project with ', el('strong', { textContent: 'New project' }), ', then add icons to it from the Icons tab.']));
      return;
    }
    none.hidden = p.items.length > 0;
    $('h2', none).textContent = 'No symbols in this project yet';
    $('p', none).replaceChildren('Switch to Icons, pick an icon, and use ', el('strong', { textContent: 'Add to project' }), '. Layer edits come along.');
    cards.replaceChildren(...p.items.map(i => card(i, p)));
  }

  /* ---------- opening a symbol from a project ---------- */
  async function openItem(item) {
    setTab('icons');
    await S.ctx.openIcon(item.source, item.name, { model: item.model, rev: item.rev });
  }

  /* ---------- Add to project ---------- */
  const fp = m => (m ? JSON.stringify({ s: m.strokes, l: m.layers }) : 'auto');
  function currentItem() {
    const cur = S.current, snap = cur && Editor.snapshot();
    if (!cur || !snap) return null;
    return { source: cur.source.id, name: cur.item.name, symbol: cur.item.symbol, rev: snap.rev, model: snap.model };
  }
  function menuRow(p, item) {
    const key = Projects.itemKey(item.source, item.name), have = p.items.find(i => Projects.itemKey(i.source, i.name) === key);
    const same = have && have.rev === item.rev && fp(have.model) === fp(item.model);
    const btn = (label, run, cls = 'btn small') => {
      const b = el('button', { type: 'button', className: cls, textContent: label });
      b.setAttribute('aria-label', `${label}: ${p.name}`);
      b.addEventListener('click', run);
      return b;
    };
    const status = !have ? '' : same ? 'In this project' : 'In this project, different layers';
    const row = el('li', { className: 'menu-row' }, el('span', { className: 'menu-name' }, el('strong', { textContent: p.name }), status ? el('span', { className: 'muted', textContent: status }) : ''), el('span', { className: 'spacer' }));
    if (!have) row.append(btn('Add', () => addCurrent(p.id)));
    else {
      if (!same) row.append(btn('Update', () => addCurrent(p.id, true)));
      row.append(btn('Remove', () => {
        const at = p.items.indexOf(have);
        change(Projects.removeItem(S.store, p.id, key, now()));
        toast(`Removed ${item.symbol} from “${p.name}”.`, { label: 'Undo', run: () => change(Projects.insertItem(S.store, p.id, have, at, now())) });
      }));
    }
    return row;
  }
  function renderMenu() {
    const item = currentItem(), list = $('#project-menu-list');
    list.replaceChildren(...(item ? S.store.projects.map(p => menuRow(p, item)) : []));
    if (item && !S.store.projects.length) list.append(el('li', { className: 'note', textContent: 'No projects yet.' }));
  }
  function addCurrent(pid, updating = false) {
    const item = currentItem(), p = Projects.find(S.store, pid);
    if (!item || !p) return;
    change(Projects.addItem(S.store, pid, item, now()));
    toast(`${updating ? 'Updated' : 'Added'} ${item.symbol} ${updating ? 'in' : 'to'} “${p.name}”${item.model ? ', with your layer edits' : ''}.`);
  }
  function openMenu() {
    if (!currentItem()) return;
    S.menuOpen = true; renderMenu();
    $('#project-menu').hidden = false; $('#add-project').setAttribute('aria-expanded', 'true');
    resetNewForm();
  }
  function closeMenu(refocus = true) {
    if (!S.menuOpen) return;
    S.menuOpen = false;
    $('#project-menu').hidden = true; $('#add-project').setAttribute('aria-expanded', 'false');
    if (refocus) $('#add-project').focus();
  }
  function resetNewForm() {                                    // back to the "New project…" button (kept, since the form replaces it)
    const form = $('#menu-form');
    if (form) form.replaceWith(S.newBtn);
    S.newBtn.hidden = false;
  }
  function newProjectForm() {
    const input = el('input', { type: 'text', className: 'rename', maxLength: Projects.MAX_NAME, placeholder: 'Project name', value: Projects.uniqueName(S.store, 'New project'), spellcheck: false });
    input.setAttribute('aria-label', 'Name of the new project');
    const err = el('span', { className: 'row-error', role: 'alert' });
    const go = el('button', { type: 'submit', className: 'btn small primary', textContent: 'Create and add' });
    const form = el('form', { id: 'menu-form', className: 'menu-form' }, el('div', { className: 'rename-wrap' }, input, err), go);
    form.addEventListener('submit', e => {
      e.preventDefault();
      const bad = Projects.validateName(S.store, input.value);
      if (bad) { err.textContent = bad; input.setAttribute('aria-invalid', 'true'); return; }
      const id = createProject(input.value);
      addCurrent(id);
      renderMenu(); resetNewForm();
    });
    input.addEventListener('input', () => { err.textContent = ''; input.removeAttribute('aria-invalid'); });
    return { form, input };
  }

  /* ---------- export ---------- */
  async function fetchText(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`${url}: ${r.status}`);
    return r.text();
  }
  async function exportProject(kind) {
    const p = project();
    if (!p || !p.items.length || S.busy) return;
    S.busy = true; renderView();
    toast(`Preparing ${plural(p.items.length, 'symbol', 'symbols')}…`);
    try {
      const templates = {}, licenses = {};
      const jobs = [...p.items];
      await Promise.all(Array.from({ length: Math.min(6, jobs.length) }, async () => {
        for (let i = jobs.shift(); i; i = jobs.shift()) {
          try { templates[Projects.itemKey(i.source, i.name)] = await fetchText(`${i.source}/templates/${i.symbol}.svg`); }
          catch { throw new Error(`Could not load ${Projects.itemKey(i.source, i.name)}. Is it still in the icon set?`); }
        }
      }));
      for (const id of new Set(p.items.map(i => i.source))) licenses[id] = await fetchText(`${id}/LICENSE.txt`).catch(() => `See the ${S.ctx.sourceTitle(id)} project for its license.\n`);
      const out = Projects.buildExport(p, { templates, licenses }, kind);
      const bytes = Zip.build(out.files), base = Projects.catalogName(p.name);
      download(new Blob([bytes], { type: 'application/zip' }), kind === 'catalog' ? `${base}.zip` : `${base} svg.zip`);
      toast(`Exported ${plural(out.count, 'symbol', 'symbols')}.${out.notes.length ? ' ' + out.notes.join(' ') : ''}`);
    } catch (e) { toast(`Could not export: ${e.message}`); }
    finally { S.busy = false; renderView(); }
  }
  function download(blob, name) {
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
  }

  /* ---------- everything ---------- */
  function render() {
    const n = S.store.projects.length, count = $('#project-count');
    count.hidden = n === 0; count.textContent = String(n);
    $('#projects-warning').hidden = S.storageOk;
    $('#project-list').replaceChildren(...S.store.projects.map(projectRow));
    $('#projects-empty').hidden = n > 0;
    if (S.tab === 'projects') renderView();
    if (S.menuOpen) renderMenu();
  }

  function setCurrent(cur) {
    S.current = cur;
    closeMenu(false);
  }

  function init(ctx) {
    S.ctx = ctx;
    load();
    for (const r of document.querySelectorAll('#side-tabs input')) r.addEventListener('change', e => setTab(e.target.value));
    $('#new-project').addEventListener('click', () => {
      const id = createProject(Projects.uniqueName(S.store, 'New project'));
      S.renaming = id; render();
    });
    $('#add-project').addEventListener('click', () => (S.menuOpen ? closeMenu() : openMenu()));
    S.newBtn = $('#menu-new');
    S.newBtn.addEventListener('click', () => {
      const { form, input } = newProjectForm();
      S.newBtn.replaceWith(form); input.focus(); input.select();
    });
    // composedPath, not e.target.closest: a click on a button the menu replaces (New project…) has left the page by now
    document.addEventListener('click', e => { if (S.menuOpen && !e.composedPath().some(n => n.id === 'add-wrap')) closeMenu(false); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && S.menuOpen) { e.preventDefault(); closeMenu(); } });
    $('#export-catalog').addEventListener('click', () => exportProject('catalog'));
    $('#export-svg').addEventListener('click', () => exportProject('svg'));
    addEventListener('storage', e => { if (e.key === KEY) { load(); if (S.selected && !project()) S.selected = null; render(); } });
    render();
  }

  return { init, setCurrent, toast };
})();
