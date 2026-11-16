'use strict';
/* The (i) buttons: short explanations that open in a small popover, so the page itself can stay short. A button is
   <button class="info" data-info="key"> (or Info.button('key') from script); the texts are below, in one place.
   A blank line in a text starts a new paragraph. The popover closes on Escape, on a click elsewhere and when focus leaves. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Info = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const TEXT = {
    source: { title: 'Icon sets',
      body: 'Each set is downloaded from its npm package when the site is built. Only its outline style is included, because outlines are drawn with strokes and can get real weights.\n\nSymbol names start with the set (lucide.house), so they never clash with Apple’s. Each set keeps its own licence, linked at the bottom of the page.' },
    problems: { title: 'Problem icons',
      body: 'The triangle marks an icon that will not follow font weight properly, or may look uneven between Regular and Black. Its note says why.\n\nThe small “i” is only a heads-up, for example that Black was made a little lighter so the weights could line up.\n\nReport a problem on an icon opens a GitHub issue already filled in.' },
    status: { title: 'Weights',
      body: 'Variable weights: Ultralight, Regular and Black line up point for point, so the symbol gets lighter and bolder with font weight and Bold Text.\n\nSingle weight: they could not be lined up, so the symbol looks the same at every weight.\n\nNo weight change: the SVG has no strokes, so all three weights are identical.' },
    downloads: { title: 'Downloads',
      body: '.svg is the template: open it in the SF Symbols app, or drag it onto a Symbol Image Set in Xcode.\n\n.symbolset is a folder (zipped) for an Xcode asset catalog: unzip it and drop it in.\n\nBoth include your layer edits.' },
    original: { title: 'Original',
      body: 'The icon exactly as its icon set publishes it, drawn from the same .svg file, on its own grid. The dashed box is that grid.\n\nTick “Original on top” on the Regular weight to draw it over the converted symbol in color. Wherever the black shows beyond the color, the conversion changed the shape (for example a tiny dot that was made solid).\n\nIt is only a preview: the downloads never contain it.' },
    layers: { title: 'Layers',
      body: 'A layer is a group of strokes that SF Symbols colors and animates together. Reorder layers, move strokes between them, add or remove layers, and set each layer’s level and color.\n\nThe downloads follow your edits. Edits stay in this browser, for each icon, until the icon itself changes.' },
    view: { title: 'Preview as',
      body: 'Monochrome: one color. Layers: each layer in its own color, numbered from the back. Levels: primary, secondary and tertiary in color. Hierarchical: levels as opacity (approximate). Multicolor: each layer’s chosen color.\n\nThis only changes the preview. The download carries the layer numbers, levels and colors.' },
    order: { title: 'Animation order',
      body: 'Layer 1 is at the back and the last layer at the front. By Layer animations and Variable Color use this order (in Apple’s own symbols, Variable Color thresholds rise with the layer number).\n\nThe timing is set in the SF Symbols app: check Animation Preview there. Play here only shows the order.' },
    level: { title: 'Level',
      body: 'Used by Hierarchical rendering: primary is drawn at full strength, secondary at about half and tertiary at about a quarter. It is set for the whole layer.' },
    color: { title: 'Color',
      body: 'Used by Multicolor rendering. Tint follows the app’s tint color; the others are fixed system colors. Monochrome and Hierarchical ignore it.' },
    unused: { title: 'Not in the symbol',
      body: 'Strokes here are left out of the downloads, in all three weights. Choose a layer in a stroke’s menu to put it back.' },
    projects: { title: 'Projects',
      body: 'A project is a named set of symbols, with your layer edits, that you can export together as an Xcode asset catalog or as .svg files.\n\nProjects are saved in this browser only. Clearing site data deletes them, so export what you want to keep.' },
    export: { title: 'Exporting a project',
      body: 'Asset catalog: a zip with a .xcassets folder holding one .symbolset for each symbol. Unzip it and drag it into Xcode.\n\nSVG files: a zip of the templates, for the SF Symbols app.\n\nThe licences of the icon sets you used are included. A symbol whose icon changed after you added it is exported with its automatic layers, and you are told.' },
    build: { title: 'About this build', body: '' },          // filled in by the page once it knows the build
  };

  const ICON_LABEL = key => `About: ${TEXT[key].title}`;
  let tip = null, current = null;

  function button(key) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'info'; b.dataset.info = key;
    b.setAttribute('aria-label', ICON_LABEL(key)); b.setAttribute('aria-expanded', 'false');
    const i = document.createElement('span'); i.className = 'ico i-info'; i.setAttribute('aria-hidden', 'true');
    b.append(i);
    return b;
  }

  function ensureTip() {
    if (tip) return tip;
    tip = document.createElement('div');
    tip.className = 'tip'; tip.id = 'tip'; tip.setAttribute('role', 'note'); tip.tabIndex = -1; tip.hidden = true;
    document.body.append(tip);
    return tip;
  }
  function place(b) {
    const r = b.getBoundingClientRect(), w = Math.min(320, innerWidth - 16);
    tip.style.width = w + 'px';
    const left = Math.max(8, Math.min(r.left + r.width / 2 - 16, innerWidth - w - 8));
    let top = r.bottom + 8;
    if (top + tip.offsetHeight > innerHeight - 8 && r.top - 8 - tip.offsetHeight > 8) top = r.top - 8 - tip.offsetHeight;
    tip.style.left = left + 'px'; tip.style.top = Math.max(8, top) + 'px';
  }
  function open(b) {
    const t = TEXT[b.dataset.info];
    if (!t || !t.body) return;
    ensureTip();
    close(false);
    const h = document.createElement('strong'); h.textContent = t.title;
    tip.replaceChildren(h, ...t.body.split('\n\n').map(p => Object.assign(document.createElement('p'), { textContent: p })));
    tip.hidden = false; current = b;
    b.setAttribute('aria-expanded', 'true'); b.setAttribute('aria-controls', 'tip');
    place(b);
    tip.focus({ preventScroll: true });
  }
  function close(refocus = true) {
    if (!current) return;
    const b = current; current = null;
    tip.hidden = true; b.setAttribute('aria-expanded', 'false');
    if (refocus && document.activeElement && (tip.contains(document.activeElement) || document.activeElement === document.body)) b.focus();
  }

  function hydrate(b) {
    if (!TEXT[b.dataset.info]) return;
    b.setAttribute('aria-label', ICON_LABEL(b.dataset.info)); b.setAttribute('aria-expanded', 'false');
    if (!b.querySelector('.ico')) { const i = document.createElement('span'); i.className = 'ico i-info'; i.setAttribute('aria-hidden', 'true'); b.append(i); }
  }

  function init() {
    document.querySelectorAll('button.info[data-info]').forEach(hydrate);
    document.addEventListener('click', e => {
      const b = e.target.closest && e.target.closest('button.info');
      if (b) { current === b ? close() : open(b); return; }
      if (current && !tip.contains(e.target)) close(false);
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && current) { e.preventDefault(); close(); } });
    document.addEventListener('focusin', e => { if (current && !tip.contains(e.target) && e.target !== current) close(false); });
    addEventListener('resize', () => close(false));
    addEventListener('scroll', () => close(false), true);
  }

  return { TEXT, button, init, close };
});
