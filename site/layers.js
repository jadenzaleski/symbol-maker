'use strict';
/* The layer model behind the page's layer editor. Pure functions on the text of a template: no DOM, so Node can test it.

   A template draws the symbol once per weight (Ultralight-S, Regular-S, Black-S), one <path> per stroke, in the same
   order. A path belongs to a layer through its class:
       class="monochrome-N multicolor-N:<color> hierarchical-N:<level>"
   N is the layer's number, counted from 0 at the back, and the order of the paths in the file is the order they are drawn
   in, so a layer's number and its place in the drawing always go together. SF Symbols animates "by layer" using that list.

   The model keeps layers apart from numbers so they can be moved:
       { strokes: [layerId | null, ...],     // one per path of the template; null = taken out of the symbol
         layers:  [{ id, level, color }, ...], // back to front
         nextId }
   Layers with no stroke are not written, and the numbers are handed out again from 0 when writing. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Layers = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const LEVELS = ['primary', 'secondary', 'tertiary'];
  // The multicolor names Apple's own templates use (tintColor follows the app's tint; the rest are fixed system colors).
  const COLORS = [
    { id: 'tintColor', label: 'Tint', hex: '#007AFF' },
    { id: 'white', label: 'White', hex: '#FFFFFF' },
    { id: 'systemRedColor', label: 'Red', hex: '#FF3B30' },
    { id: 'systemOrangeColor', label: 'Orange', hex: '#FF9500' },
    { id: 'systemYellowColor', label: 'Yellow', hex: '#FFCC00' },
    { id: 'systemGreenColor', label: 'Green', hex: '#28CD41' },
    { id: 'systemBlueColor', label: 'Blue', hex: '#007AFF' },
  ];
  const WEIGHTS = ['Ultralight-S', 'Regular-S', 'Black-S'];
  const DEFAULT_COLOR = 'tintColor';

  const groupRe = w => new RegExp(`(<g id="${w}"[^>]*>)([\\s\\S]*?)(</g>)`);
  const pathRe = () => /<path\b[^>]*?\/?>/g;
  const clone = m => ({ strokes: m.strokes.slice(), layers: m.layers.map(l => ({ ...l })), nextId: m.nextId });
  const colorHex = id => (COLORS.find(c => c.id === id) || {}).hex;

  function body(text, weight) {
    const m = text.match(groupRe(weight));
    if (!m) throw new Error(`The template has no ${weight} group.`);
    return m;
  }

  /** The starting model: the layers the template already has (read from the Regular group). */
  function fromTemplate(text) {
    const tags = body(text, 'Regular-S')[2].match(pathRe()) || [];
    const byNumber = new Map();
    const strokes = tags.map(tag => {
      const h = tag.match(/hierarchical-(\d+):(\w+)/), c = tag.match(/multicolor-\d+:(\w+)/);
      const n = h ? Number(h[1]) : 0;
      if (!byNumber.has(n)) byNumber.set(n, { level: h && LEVELS.includes(h[2]) ? h[2] : 'primary', color: c && colorHex(c[1]) ? c[1] : DEFAULT_COLOR });
      return n;
    });
    const numbers = [...byNumber.keys()].sort((a, b) => a - b);
    return {
      strokes: strokes.map(n => numbers.indexOf(n)),
      layers: numbers.map((n, i) => ({ id: i, ...byNumber.get(n) })),
      nextId: numbers.length,
    };
  }

  const need = (m, id) => { if (!m.layers.some(l => l.id === id)) throw new Error(`No layer ${id}.`); };

  function addLayer(m) {
    const o = clone(m);
    o.layers.push({ id: o.nextId, level: 'primary', color: DEFAULT_COLOR });
    o.nextId += 1;
    return o;
  }
  function removeLayer(m, id) {
    need(m, id);
    const o = clone(m);
    o.layers = o.layers.filter(l => l.id !== id);
    o.strokes = o.strokes.map(s => (s === id ? null : s));
    return o;
  }
  function moveLayer(m, id, delta) {
    need(m, id);
    const o = clone(m), i = o.layers.findIndex(l => l.id === id), j = Math.max(0, Math.min(o.layers.length - 1, i + delta));
    if (i !== j) { const [l] = o.layers.splice(i, 1); o.layers.splice(j, 0, l); }
    return o;
  }
  function assign(m, stroke, id) {
    if (!(stroke >= 0 && stroke < m.strokes.length)) throw new Error(`No stroke ${stroke}.`);
    if (id !== null) need(m, id);
    const o = clone(m);
    o.strokes[stroke] = id;
    return o;
  }
  function setLevel(m, id, level) {
    need(m, id);
    if (!LEVELS.includes(level)) throw new Error(`Unknown level ${level}.`);
    const o = clone(m);
    o.layers.find(l => l.id === id).level = level;
    return o;
  }
  function setColor(m, id, color) {
    need(m, id);
    if (!colorHex(color)) throw new Error(`Unknown color ${color}.`);
    const o = clone(m);
    o.layers.find(l => l.id === id).color = color;
    return o;
  }

  /** The layers that will be written, back to front, numbered from 1 (the order SF Symbols animates them in). */
  function order(m) {
    const out = [];
    for (const l of m.layers) {
      const strokes = [];
      m.strokes.forEach((s, i) => { if (s === l.id) strokes.push(i); });
      if (strokes.length) out.push({ number: out.length + 1, id: l.id, level: l.level, color: l.color, strokes });
    }
    return out;
  }

  /** Why this model cannot be exported, or null. */
  function problem(m) {
    return order(m).length ? null : 'There are no strokes in the symbol. Put at least one stroke in a layer.';
  }

  const same = (a, b) => JSON.stringify({ s: a.strokes, l: a.layers }) === JSON.stringify({ s: b.strokes, l: b.layers });
  /** Has this model been changed from what the template itself says? */
  const isEdited = (m, text) => !same(m, fromTemplate(text));

  /** A model saved earlier (from JSON), checked against the template it is meant for; null when it does not fit. */
  function restore(saved, text) {
    try {
      const base = fromTemplate(text);
      if (!saved || !Array.isArray(saved.strokes) || !Array.isArray(saved.layers) || saved.strokes.length !== base.strokes.length) return null;
      const ids = new Set();
      for (const l of saved.layers) {
        if (!Number.isInteger(l.id) || ids.has(l.id) || !LEVELS.includes(l.level) || !colorHex(l.color)) return null;
        ids.add(l.id);
      }
      if (!saved.strokes.every(s => s === null || ids.has(s))) return null;
      return { strokes: saved.strokes.slice(), layers: saved.layers.map(l => ({ id: l.id, level: l.level, color: l.color })),
               nextId: Math.max(Number.isInteger(saved.nextId) ? saved.nextId : 0, ...ids, -1) + 1 };
    } catch { return null; }
  }

  const classFor = (n, l) => `monochrome-${n} multicolor-${n}:${l.color} hierarchical-${n}:${l.level}`;
  function withClass(tag, cls) {
    return tag.replace(/\sclass="[^"]*"/, '').replace(/^<path\b/, `<path class="${cls}"`);
  }

  /** The template with the layers of `m`: the strokes in layer order, each carrying its layer's class, in all three
      weights; strokes taken out are left out. Colors that are not the app's tint also get a style rule, as in Apple's. */
  function apply(text, m) {
    const err = problem(m);
    if (err) throw new Error(err);
    const layers = order(m);
    let out = text;
    for (const w of WEIGHTS) {
      const g = body(out, w), tags = g[2].match(pathRe()) || [];
      if (tags.length !== m.strokes.length) throw new Error(`${w} has ${tags.length} strokes but the layers describe ${m.strokes.length}.`);
      const lines = [];
      layers.forEach((l, n) => l.strokes.forEach(i => lines.push(withClass(tags[i], classFor(n, l)))));
      const indent = (g[2].match(/\n([ \t]*)<path/) || [, '            '])[1];
      const close = (g[2].match(/\n([ \t]*)$/) || [, ''])[1];
      out = out.replace(g[0], g[1] + '\n' + indent + lines.join('\n' + indent) + '\n' + close + g[3]);
    }
    const rules = layers.map((l, n) => (l.color === DEFAULT_COLOR ? null : `.multicolor-${n}:${l.color} {fill:${colorHex(l.color)}}`)).filter(Boolean);
    out = out.replace(/<style\b[\s\S]*?<\/style>\s*/, '');
    if (rules.length) out = out.replace(/(<svg\b[^>]*>)/, `$1\n<style>${rules.join('\n')}\n</style>`);
    return out;
  }

  const EDIT_NOTE = '<!-- Layers edited with Symbol Maker. -->\n';
  /** Say in the template that its layers were edited here: a comment right after the credit comment (once). */
  function markEdited(svg) {
    if (svg.includes(EDIT_NOTE)) return svg;
    if (/<!--[\s\S]*?-->\n/.test(svg)) return svg.replace(/(<!--[\s\S]*?-->\n)/, `$1${EDIT_NOTE}`);
    return svg.replace(/(<\?xml[^>]*\?>\s*)?/, m => (m ? m.trimEnd() + '\n' : '') + EDIT_NOTE);
  }

  return { LEVELS, COLORS, colorHex, markEdited, fromTemplate, addLayer, removeLayer, moveLayer, assign, setLevel, setColor,
           order, problem, isEdited, restore, apply };
});
