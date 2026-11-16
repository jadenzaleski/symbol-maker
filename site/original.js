'use strict';
/* The original icon, as its icon set draws it. Pure functions on the text of an SVG: no DOM, so Node can test them.

   The page shows the original in two ways. The Original card draws the file itself. The overlay draws the same icon over
   the Regular master of the template, to show what the conversion changed; for that the shapes are read here (never the
   file's markup as it stands, because the files come from other people's packages) and put where the template has them.

   Only plain shapes are read: path, circle, ellipse, rect, line, polyline, polygon and g, with a short list of attributes
   (geometry and paint). Anything that could do more than draw (script, style, use, image, a url(...) reference, a style
   attribute, ...) makes the icon "unsupported": nothing is drawn from it, and the reason is returned. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.Original = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  const SHAPES = new Set(['path', 'circle', 'ellipse', 'rect', 'line', 'polyline', 'polygon', 'g']);
  const NOT_DRAWN = new Set(['title', 'desc', 'metadata']);
  const GEOMETRY = ['d', 'cx', 'cy', 'r', 'rx', 'ry', 'x', 'y', 'width', 'height', 'x1', 'y1', 'x2', 'y2', 'points', 'transform'];
  const PAINT = ['fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin', 'stroke-miterlimit', 'stroke-dasharray',
                 'stroke-dashoffset', 'opacity', 'fill-opacity', 'stroke-opacity', 'fill-rule', 'clip-rule'];
  const KEEP = new Set([...GEOMETRY, ...PAINT]);
  const NUM = /-?\d*\.?\d+(?:e-?\d+)?/gi;
  const GRID = 24;                                      // the grid the converter fits every icon to (convert.normalize_grid)

  const TAG = /<!--[\s\S]*?-->|<\?[\s\S]*?\?>|<![^>]*>|<(\/?)([A-Za-z][\w:.-]*)((?:\s+[^\s=\/>]+(?:\s*=\s*(?:"[^"]*"|'[^']*'))?)*)\s*(\/?)>/g;
  const ATTR = /([^\s=\/]+)\s*=\s*(?:"([^"]*)"|'([^']*)')/g;
  const decode = s => s.replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

  function attributes(raw) {
    const a = {};
    for (const m of raw.matchAll(ATTR)) a[m[1]] = decode(m[2] ?? m[3]);
    return a;
  }
  /** The attributes of the <svg> tag, as written (or null when there is none). */
  function rootAttributes(text) {
    for (const m of String(text).matchAll(TAG)) if (m[2] === 'svg' && !m[1]) return attributes(m[3]);
    return null;
  }

  /** How an icon is fitted to the 24 grid: `s` times its coordinates, then moved by (tx, ty); w and h are its own size.
      null when it has no usable size. This is the converter's normalize_grid. */
  function grid(text) {
    const a = rootAttributes(text);
    if (!a) return null;
    let vx = 0, vy = 0, vw, vh;
    if (a.viewBox) {
      const n = (a.viewBox.match(NUM) || []).map(Number);
      if (n.length !== 4) return null;
      [vx, vy, vw, vh] = n;
    } else {
      vw = parseFloat(a.width); vh = parseFloat(a.height);
    }
    if (!(vw > 0) || !(vh > 0)) return null;
    const s = GRID / Math.max(vw, vh);
    return { s, tx: (GRID - vw * s) / 2 - vx * s, ty: (GRID - vh * s) / 2 - vy * s, w: vw, h: vh };
  }

  /** The shapes of an icon: { root: paint set on the <svg>, nodes: [{ tag, attrs, children }] }, or { unsupported: why }. */
  function parse(text) {
    const top = [], stack = [{ children: top }];
    let rootPaint = null, skipping = null;
    for (const m of String(text).matchAll(TAG)) {
      if (m[2] === undefined) continue;                    // a comment, declaration or doctype
      const [, closing, name, raw, selfClosing] = m;
      if (skipping) { if (closing && name === skipping) skipping = null; continue; }
      if (closing) { if (name !== 'svg' && stack.length > 1) stack.pop(); continue; }
      if (name === 'svg') {
        if (rootPaint) return { unsupported: 'svg' };
        const a = attributes(raw);
        if ('style' in a) return { unsupported: 'a style attribute' };
        rootPaint = Object.fromEntries(Object.entries(a).filter(([k]) => PAINT.includes(k)));
        if (Object.values(rootPaint).some(v => /url\(/i.test(v))) return { unsupported: 'a reference (url)' };
        continue;
      }
      if (!rootPaint) continue;
      if (NOT_DRAWN.has(name)) { if (!selfClosing) skipping = name; continue; }
      if (!SHAPES.has(name)) return { unsupported: name };
      const a = attributes(raw);
      if ('style' in a) return { unsupported: 'a style attribute' };
      if (Object.values(a).some(v => /url\(/i.test(v))) return { unsupported: 'a reference (url)' };
      const node = { tag: name, attrs: Object.fromEntries(Object.entries(a).filter(([k]) => KEEP.has(k))), children: [] };
      stack.at(-1).children.push(node);
      if (!selfClosing) stack.push(node);
    }
    if (!rootPaint) return { unsupported: 'not an svg' };
    return { root: rootPaint, nodes: top };
  }

  /** What to say about an icon: its grid and how its strokes are drawn. */
  function facts(text) {
    const a = rootAttributes(text) || {}, g = grid(text);
    return {
      grid: g ? `${g.w} × ${g.h}` : null,
      stroke: a['stroke-width'] ?? null,
      caps: a['stroke-linecap'] ?? null,
      joins: a['stroke-linejoin'] ?? null,
    };
  }

  /** Where an icon lands in the preview of a template's master, as x' = scale * X + tx, y' = scale * Y + ty for a point
      (X, Y) of the original. `g` is the master's guides ({ width, cap }) and `cap` the cap height the preview draws it at.
      The converter puts the 24 grid at a fixed size (the margins are 24 units apart, each unit is width / 24) with its
      middle half a cap height above the baseline; this was measured on published templates, not read from SwiftDraw. */
  function place(g, fit, cap = g.cap) {
    const k = g.width / GRID, S = cap / g.cap;
    return { scale: S * k * fit.s, tx: S * k * fit.tx, ty: S * (k * fit.ty - (g.cap / 2 + (GRID / 2) * k)) };
  }
  const round = v => Number(v.toFixed(6));
  function transform(m) { return `matrix(${round(m.scale)} 0 0 ${round(m.scale)} ${round(m.tx)} ${round(m.ty)})`; }

  return { grid, parse, facts, place, transform, rootAttributes };
});
