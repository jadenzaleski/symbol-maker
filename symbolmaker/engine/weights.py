"""Make the three weight masters of a template structurally identical so SF Symbols / Xcode can interpolate them.

SwiftDraw expands strokes with a different number of curve segments at different widths (e.g. 36 / 45 / 45 for the
same arc). The shapes are fine; only the segmentation differs. For each contour we align the segment-start nodes of
the three weights by position (weights sit side by side in the template, so each is first shifted to a common
origin), then SPLIT segments (de Casteljau; geometry unchanged) wherever a weight lacks a node the others have.
Straight segments become curves where another weight has a curve there.

Public API: match_weights, masters_match, to_single_weight.
"""

import os
import re

from .bezier import cub, dist, lerp, split_cubic
from .loops import remove_loops, signed_area, split_loops

TOL = float(os.environ.get("TOL", "0.02"))
INS = "2.25,0,2.25,0"
NUM = r"-?\d*\.?\d+(?:e-?\d+)?"


def parse(d, min_len=1e-3):
    """-> list of contours; contour = (start, [seg]); seg = ('L', p) | ('C', c1, c2, p)."""
    toks = re.findall(r"[MLCZ]|" + NUM, d)
    i = 0
    cmd = None
    cs = []
    cur = None
    while i < len(toks):
        if toks[i] in "MLCZ":
            cmd = toks[i]
            i += 1
        if cmd == "Z":
            cur = None
            continue
        if cmd == "M":
            p = (float(toks[i]), float(toks[i + 1]))
            i += 2
            cur = (p, [])
            cs.append(cur)
            cmd = "L"
            pos = p
        elif cmd == "L":
            if cur is None:
                raise ValueError("Path data draws a line before it moves anywhere.")
            p = (float(toks[i]), float(toks[i + 1]))
            i += 2
            cur[1].append(("L", p))
            pos = p
        elif cmd == "C":
            if cur is None:
                raise ValueError("Path data draws a curve before it moves anywhere.")
            c = [float(x) for x in toks[i : i + 6]]
            i += 6
            cur[1].append(("C", (c[0], c[1]), (c[2], c[3]), (c[4], c[5])))
            pos = (c[4], c[5])
    out = []
    for start, segs in cs:
        if segs and dist(segs[-1][-1], start) > 1e-4:
            segs.append(("L", start))  # implicit closing line
        keep = []
        pos = start  # drop zero-length segments (duplicate nodes); shape is unchanged
        for sg in segs:
            if seg_len(pos, sg) > min_len:
                keep.append(sg)
            pos = sg[-1]
        out.append((start, keep))
    return out


def seg_len(p0, s):
    if s[0] == "L":
        return dist(p0, s[1])
    pts = [cub(p0, s[1], s[2], s[3], k / 24) for k in range(25)]
    return sum(dist(pts[k], pts[k + 1]) for k in range(24))


def t_at(p0, s, frac):
    """parameter t on cubic where arclength fraction == frac (sampled)."""
    N = 48
    pts = [cub(p0, s[1], s[2], s[3], k / N) for k in range(N + 1)]
    cum = [0.0]
    for k in range(N):
        cum.append(cum[-1] + dist(pts[k], pts[k + 1]))
    target = frac * cum[-1]
    for k in range(N):
        if cum[k + 1] >= target:
            r = (target - cum[k]) / (cum[k + 1] - cum[k]) if cum[k + 1] > cum[k] else 0
            return (k + r) / N
    return 1.0


def nodes_fracs(start, segs):
    pos = start
    lens = []
    for s in segs:
        lens.append(seg_len(pos, s))
        pos = s[-1]
    tot = sum(lens) or 1.0
    f = [0.0]
    acc = 0.0
    for seg_len_ in lens[:-1]:
        acc += seg_len_
        f.append(acc / tot)
    return f, lens, tot


def insert_nodes(start, segs, new_fracs):
    """Split segments so there is a node at each fraction in new_fracs (geometry unchanged)."""
    f, _lens, _tot = nodes_fracs(start, segs)
    out = []
    pos = start
    for k, s in enumerate(segs):
        lo = f[k]
        hi = f[k + 1] if k + 1 < len(f) else 1.0
        cuts = sorted(g for g in new_fracs if lo + 1e-9 < g < hi - 1e-9)
        if not cuts:
            out.append(s)
            pos = s[-1]
            continue
        pieces = []
        if s[0] == "L":
            for g in cuts:
                q = lerp(pos, s[1], (g - lo) / (hi - lo))
                pieces.append(("L", q))
            pieces.append(("L", s[1]))
        else:
            ts = [t_at(pos, s, (g - lo) / (hi - lo)) for g in cuts]
            prev_t = 0.0
            rest = s
            rp = pos
            for t in ts:
                tt = (t - prev_t) / (1 - prev_t) if prev_t < 1 else 0
                a, b = split_cubic(rp, rest[1], rest[2], rest[3], tt)
                pieces.append(a)
                rp = a[3]
                rest = ("C", b[1], b[2], b[3])
                prev_t = t
            pieces.append(rest)
        out += pieces
        pos = s[-1]
    return out


def node_pos(c):
    start, segs = c
    pos = [start]
    for sg in segs[:-1]:
        pos.append(sg[-1])
    return pos


def point_at(c, frac, fracs=None):
    """The point at arc-length fraction `frac` of contour `c`.

    Asking for many points of one contour is common: pass `fracs` (the first result of nodes_fracs) to work out the arc
    lengths once instead of for every point.
    """
    start, segs = c
    f = fracs if fracs is not None else nodes_fracs(start, segs)[0]
    pos = start
    for k, sg in enumerate(segs):
        lo = f[k]
        hi = f[k + 1] if k + 1 < len(f) else 1.0
        if frac <= hi or k == len(segs) - 1:
            r = (frac - lo) / (hi - lo) if hi > lo else 0
            if sg[0] == "L":
                return lerp(pos, sg[1], r)
            return cub(pos, sg[1], sg[2], sg[3], t_at(pos, sg, min(max(r, 0), 1)))
        pos = sg[-1]
    return start


DMAX = float(os.environ.get("DMAX", "10"))


def align(reps, nodes):
    """Monotonic alignment (Needleman-Wunsch) of two node position lists, first nodes forced.

    Returns {rep_idx: node_idx}.
    """
    n, m = len(reps), len(nodes)
    G = DMAX * 0.6
    INF = 1e18
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0
    for i in range(n + 1):
        for j in range(m + 1):
            if cost[i][j] >= INF:
                continue
            c0 = cost[i][j]
            if i < n and c0 + G < cost[i + 1][j]:
                cost[i + 1][j] = c0 + G
                back[i + 1][j] = (i, j, 0)
            if j < m and c0 + G < cost[i][j + 1]:
                cost[i][j + 1] = c0 + G
                back[i][j + 1] = (i, j, 0)
            if i < n and j < m:
                d = dist(reps[i], nodes[j])
                if i == 0 and j == 0:
                    d = 0
                if (d <= DMAX or (i == 0 and j == 0)) and c0 + d < cost[i + 1][j + 1]:
                    cost[i + 1][j + 1] = c0 + d
                    back[i + 1][j + 1] = (i, j, 1)
    i, j = n, m
    pairs = {}
    while (i, j) != (0, 0):
        step = back[i][j]
        if step is None:
            raise ValueError("The alignment has no way back to the start.")
        pi, pj, mt = step
        if mt:
            pairs[pi] = pj
        i, j = pi, pj
    return pairs


def equalize(c3):
    """c3 = [(start, segs)] for U, R, B -> three segment lists with identical structure."""
    pos = [node_pos(c) for c in c3]
    # clusters start from Regular's nodes; each: {'pos': rep position, 'n': {weight: node idx}}
    clusters = [{"pos": q, "n": {1: i}} for i, q in enumerate(pos[1])]
    for w in (0, 2):
        reps = [c["pos"] for c in clusters]
        pr = align(reps, pos[w])
        for i, j in pr.items():
            clusters[i]["n"][w] = j
        # rebuild ordered list inserting unmatched nodes of w between their neighbours
        inv = {j: i for i, j in pr.items()}
        out = []
        ptr = 0
        for j in range(len(pos[w])):
            if j in inv:
                while ptr <= inv[j]:
                    out.append(clusters[ptr])
                    ptr += 1
            else:
                out.append({"pos": pos[w][j], "n": {w: j}})
        while ptr < len(clusters):
            out.append(clusters[ptr])
            ptr += 1
        # Unmatched clusters (no node of w) that were skipped above are appended in order, so sorting is not needed to
        # keep the global order: the loop above emits clusters in sequence up to each matched one.
        clusters = out
    res = []
    for w in range(3):
        start, segs = c3[w]
        f, _lens, _tot = nodes_fracs(start, segs)
        new = []
        last_frac = -1.0
        for k, cl in enumerate(clusters):
            if w in cl["n"]:
                last_frac = f[cl["n"][w]]
                continue
            nxt = next((f[x["n"][w]] for x in clusters[k + 1 :] if w in x["n"]), 1.0)
            lo = max(last_frac, 0.0)
            best_d, g = float("inf"), (lo + nxt) / 2
            for t in range(1, 41):
                candidate = lo + (nxt - lo) * t / 41
                d = dist(point_at(c3[w], candidate, f), cl["pos"])
                if d < best_d:
                    best_d, g = d, candidate
            if g <= last_frac + 1e-6:
                g = last_frac + (nxt - last_frac) / 2
            new.append(g)
            last_frac = g
        res.append(insert_nodes(start, segs, new))
    if len({len(r) for r in res}) > 1:
        raise ValueError(f"node counts {[len(r) for r in res]} vs clusters {len(clusters)}")
    # unify verbs: if any weight has a curve at index i, all become cubics
    n = len(res[0])
    for i in range(n):
        if len({r[i][0] for r in res}) > 1:
            for w in range(3):
                if res[w][i][0] == "L":
                    p0 = c3[w][0] if i == 0 else res[w][i - 1][-1]
                    q = res[w][i][1]
                    res[w][i] = ("C", lerp(p0, q, 1 / 3), lerp(p0, q, 2 / 3), q)
    return res


def fmt(v):
    return f"{v:.3f}".rstrip("0").rstrip(".")


def to_d(contours):
    parts = []
    for start, segs in contours:
        parts.append(f"M{fmt(start[0])},{fmt(start[1])}")
        for s in segs:
            parts.append(("L" if s[0] == "L" else "C") + " ".join(f"{fmt(x)},{fmt(y)}" for x, y in s[1:]))
        parts.append("Z")
    return " ".join(parts)


GROUP = r'(<g id="%s"[^>]*>)(.*?)(</g>)'
WEIGHT_GROUPS = ("Ultralight-S", "Regular-S", "Black-S")


def weight_group(svg, name):
    """The match for one weight's group of a template (group 2 is what is inside it); raises if it has none."""
    m = re.search(GROUP % name, svg, re.S)
    if m is None:
        raise ValueError(f"The template has no {name} group.")
    return m


def weight_groups(svg):
    """The three weight groups of a template, in order (Ultralight, Regular, Black)."""
    return [weight_group(svg, name) for name in WEIGHT_GROUPS]


def group_center(ds):
    xs = []
    ys = []
    for d in ds:
        n = [float(x) for x in re.findall(NUM, d)]
        xs += n[0::2]
        ys += n[1::2]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def shift(contours, dx, dy):
    def sp(p):
        return (p[0] + dx, p[1] + dy)

    out = []
    for start, segs in contours:
        out.append((sp(start), [(sg[0], *(sp(q) for q in sg[1:])) for sg in segs]))
    return out


def c_center(c):
    ps = node_pos(c)
    xs = [q[0] for q in ps]
    ys = [q[1] for q in ps]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)


def s_area(c):
    ps = node_pos(c)
    a = 0.0
    for k in range(len(ps)):
        x0, y0 = ps[k]
        x1, y1 = ps[(k + 1) % len(ps)]
        a += x0 * y1 - x1 * y0
    return a / 2


def reverse(c):
    start, segs = c
    pts = [start] + [sg[-1] for sg in segs]  # pts[i] = start of segment i, pts[-1] == start
    out = []
    for i in range(len(segs) - 1, -1, -1):
        sg = segs[i]
        out.append(("L", pts[i]) if sg[0] == "L" else ("C", sg[2], sg[1], pts[i]))
    return (start, out)


def rotate_to(c, ref):
    _start, segs = c
    ps = node_pos(c)
    k = min(range(len(ps)), key=lambda i: dist(ps[i], ref))
    if k == 0:
        return c
    return (ps[k], segs[k:] + segs[:k])


def match_contours(c_ref, c_w):
    """Re-order/orient/rotate the contours of one weight so contour i corresponds to the reference contour i."""
    if len(c_ref) != len(c_w):
        return None
    left = list(range(len(c_w)))
    out = []
    for r in c_ref:
        rc = c_center(r)
        j = min(left, key=lambda i: dist(c_center(c_w[i]), rc))
        left.remove(j)
        w = c_w[j]
        if (s_area(w) > 0) != (s_area(r) > 0):
            w = reverse(w)
        out.append(rotate_to(w, r[0]))
    return out


def process(svg):
    gs = weight_groups(svg)
    PD = r'<path\b[^>]*?\sd="([^"]+)"'
    ds = [re.findall(PD, g.group(2)) for g in gs]
    if not (len(ds[0]) == len(ds[1]) == len(ds[2])):
        return None, "path count differs"
    ctr = [group_center(d) for d in ds]  # weights sit side by side in the template: normalise to a common origin
    new_ds = [[], [], []]
    for pi in range(len(ds[0])):
        cs = [shift(parse(ds[w][pi]), -ctr[w][0], -ctr[w][1]) for w in range(3)]
        if not (len(cs[0]) == len(cs[1]) == len(cs[2])):
            return None, f"contour count differs in path {pi}: {[len(c) for c in cs]}"
        for w in (0, 2):
            cs[w] = match_contours(cs[1], cs[w])
            if cs[w] is None:
                return None, "contour matching failed"
        res = [[], [], []]
        for ci in range(len(cs[0])):
            eq = equalize([cs[0][ci], cs[1][ci], cs[2][ci]])
            for w in range(3):
                res[w].append((cs[w][ci][0], eq[w]))
        for w in range(3):
            new_ds[w].append(to_d(shift(res[w], ctr[w][0], ctr[w][1])))
    for w in range(3):
        it = iter(new_ds[w])
        body = re.sub(
            r'(<path\b[^>]*?\sd=")([^"]+)(")', lambda m, it=it: m.group(1) + next(it) + m.group(3), gs[w].group(2)
        )
        svg = svg.replace(gs[w].group(0), gs[w].group(1) + body + gs[w].group(3), 1)
    return svg, None


def signature_ok(svg):
    sg = []
    for w in WEIGHT_GROUPS:
        g = weight_group(svg, w).group(2)
        sg.append([tuple(re.findall(r"[MLCZ]", d)) for d in re.findall(r'\sd="([^"]*)"', g)])
    return sg[0] == sg[1] == sg[2]


DMAX_TRIES = (10, 6, 14, 20, 30, 8, 12, 16, 24)


def _parsed_structure(template_svg):
    """Per weight: per path: per contour: verb sequence, after dropping exactly-zero-length (degenerate) segments."""
    out = []
    for w in WEIGHT_GROUPS:
        g = weight_group(template_svg, w).group(2)
        out.append(
            [
                tuple(tuple(sg[0] for sg in segs) for _, segs in parse(d, 1e-6))
                for d in re.findall(r'<path\b[^>]*?\sd="([^"]+)"', g)
            ]
        )
    return out


def masters_match(template_svg):
    """True when the three weight groups have the same contours and segment verbs.

    Zero-length segments are ignored: two masters can have the same raw verb sequence while their degenerate
    segments sit at different places, so node i of one master does not correspond to node i of another (the symbol
    then interpolates into lumps at intermediate weights)."""
    a, b, c = _parsed_structure(template_svg)
    return a == b == c


HOLE_MIN_AREA = 1.0  # a contour whose node polygon is smaller than this (template units squared) is a point


def _collapses(contours_by_weight, k):
    """True when contour k closes up (or turns inside out) in at least one weight."""
    areas = []
    for cs in contours_by_weight:
        c = cs[k]
        areas.append(s_area(c) if c[1] else 0.0)
    if any(abs(a) < HOLE_MIN_AREA for a in areas):
        return True
    return len({a > 0 for a in areas}) > 1


def _mend(cs, k):
    """The hole k of every weight with the loops SwiftDraw left on its edge cut off: [contour per weight], or None.

    SwiftDraw draws the edge of a hole with a small loop at each sharp corner, large enough at the heavy weights to make
    the hole look turned inside out. Cut off, what is left is a sound hole when it goes the same way round, and is big
    enough to be one, at every weight. A hole that really closes up (a dot) leaves nothing, so it is not mended."""
    lightest = split_loops(cs[0][k])
    sign = 1 if signed_area(max(lightest, key=lambda c: abs(signed_area(c)))) > 0 else -1
    fixed = [remove_loops(cs[w][k], sign, HOLE_MIN_AREA) for w in range(3)]
    return None if any(c is None for c in fixed) else fixed


def drop_collapsing_holes(template_svg, mend=True):
    """Remove, from all three weights, an inner contour that collapses in one of them (unless it can be mended).

    A stroked dot (Lucide draws one as a circle of radius 1 with a 2-wide stroke) has a real hole at Ultralight, a hole
    that has shrunk to a single point at Regular, and a hole that has turned inside out at Black. A hole cannot appear
    and vanish between weights, so the symbol could never be interpolated. Dropping the hole from every weight makes the
    dot solid at all of them, which is what it looks like at Regular and Black anyway.

    A hole that only looks turned inside out because of loops on its edge is mended instead (see _mend) and kept,
    unless `mend` is False (then every collapsing hole is dropped, which is how it used to be done).

    Only paths with the same number of contours in every weight are touched, and a path always keeps at least one."""
    try:
        gs = weight_groups(template_svg)
    except ValueError:
        return template_svg
    path = re.compile(r'(<path\b[^>]*?\sd=")([^"]+)(")')
    ds = [[m.group(2) for m in path.finditer(g.group(2))] for g in gs]
    if not (len(ds[0]) == len(ds[1]) == len(ds[2])):
        return template_svg
    out = template_svg
    changed = False
    for i in range(len(ds[0])):
        cs = [parse(ds[w][i], 0) for w in range(3)]  # keep degenerate segments: a point must stay a contour
        if not (len(cs[0]) == len(cs[1]) == len(cs[2])) or len(cs[0]) < 2:
            continue
        collapsing = [k for k in range(len(cs[0])) if _collapses(cs, k)]
        mended = {k: m for k in collapsing if mend and (m := _mend(cs, k)) is not None}
        drop = [k for k in collapsing if k not in mended]
        if not mended and (not drop or len(drop) == len(cs[0])):
            continue
        if len(drop) == len(cs[0]):
            drop = []  # never every contour of a path
            mended = {}
        for w in range(3):
            keep = [mended[k][w] if k in mended else c for k, c in enumerate(cs[w]) if k not in drop]
            ds[w][i] = to_d(keep)
        changed = True
    if not changed:
        return template_svg
    for w in range(3):
        it = iter(ds[w])
        body = path.sub(lambda m, it=it: m.group(1) + next(it) + m.group(3), gs[w].group(2))
        out = out.replace(gs[w].group(0), gs[w].group(1) + body + gs[w].group(3), 1)
    return out


def match_weights(template_svg, tries=DMAX_TRIES):
    """-> (matched_svg, None) or (None, reason). Retries with several alignment tolerances.

    When the first three tolerances fail with the same error (e.g. the same node counts), the remaining ones would only
    repeat it, so it stops there."""
    global DMAX
    last = "weights could not be matched"
    if masters_match(template_svg):
        return template_svg, None
    errors = []
    for dm in tries:
        DMAX = float(dm)
        try:
            new, err = process(template_svg)
        except Exception as e:  # geometry we cannot parse/align: report, never crash
            new, err = None, f"could not align weights ({e!r})"
            errors.append(err)
        else:
            errors.append(None)
        if new is not None and signature_ok(new):  # what SF Symbols compares: the verbs actually emitted
            return new, None
        last = err or "weights still differ after alignment"
        if err and "contour" in err:
            break  # a contour appears/disappears between weights; no tolerance fixes that
        if len(errors) >= 3 and errors[-1] is not None and len(set(errors[-3:])) == 1:
            break
    return None, last


def shift_d(d, dx, dy):
    """Translate an absolute M/L/C/Z path string by (dx, dy), keeping its structure exactly."""
    toks = re.findall(r"[MLCZ]|" + NUM, d)
    out = []
    k = 0
    for t in toks:
        if t in "MLCZ":
            out.append(t)
            k = 0
        else:
            out.append(fmt(float(t) + (dx if k % 2 == 0 else dy)))
            k += 1
    return " ".join(out)


def to_single_weight(template_svg):
    """Three identical masters copied from Regular (each in its own slot). Always interpolatable."""
    gs = weight_groups(template_svg)
    ds = [re.findall(r'<path\b[^>]*?\sd="([^"]+)"', g.group(2)) for g in gs]
    ctr = [group_center(d) for d in ds]
    out = template_svg
    for w in (0, 2):
        dx, dy = ctr[w][0] - ctr[1][0], ctr[w][1] - ctr[1][1]
        new_ds = iter([shift_d(d, dx, dy) for d in ds[1]])
        body = re.sub(
            r'(<path\b[^>]*?\sd=")([^"]+)(")',
            lambda m, new_ds=new_ds: m.group(1) + next(new_ds) + m.group(3),
            gs[w].group(2),
        )
        out = out.replace(gs[w].group(0), gs[w].group(1) + body + gs[w].group(3), 1)
    return out
