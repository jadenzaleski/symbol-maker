"""Cut the loops off a contour that crosses itself.

SwiftDraw draws the inner edge of a stroked closed shape (the edge of a hole) by moving each side of the path
inwards, and at a sharp corner the two moved sides overshoot each other. The edge then crosses itself and runs backwards
for a moment, which leaves a small loop (a spur) at the corner. The heavier the weight, the larger the spurs, until the
hole looks turned inside out. The hole itself is fine: it is what is left when the loops that run the other way are cut
off.

A contour is (start, [seg]) with seg = ('L', p) | ('C', c1, c2, p), as in weights.parse.
Public API: signed_area, intersections, split_loops, remove_loops.
"""

import math

from .bezier import cub, dist, lerp, split_cubic

EPS = 1e-9
TOUCH = 1e-6  # two positions along the contour this close are the same place
SIZE = 1e-5  # curves are cut down to boxes this small to find where they cross
LIMIT = 40000  # boxes looked at for one pair of curves, so that curves lying along each other cannot take forever
MAX_LOOPS = 24  # more than this many loops in one contour is not a corner artifact: it is left alone
TINY = 1e-3  # a segment smaller than this is a point, and a point crosses nothing
NODE = 1e-3  # a crossing this close to the node where two neighbouring segments meet is that node


def _point(p0, s, t):
    return lerp(p0, s[1], t) if s[0] == "L" else cub(p0, s[1], s[2], s[3], t)


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def signed_area(c, samples=16):
    """The area enclosed by the contour (a curve counts with its bulge); positive one way round, negative the other."""
    start, segs = c
    pts, pos = [start], start
    for s in segs:
        if s[0] == "L":
            pts.append(s[1])
        else:
            pts.extend(cub(pos, s[1], s[2], s[3], k / samples) for k in range(1, samples + 1))
        pos = s[-1]
    return sum(_cross(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))) / 2


# ---------- where two segments cross ----------


def _lines(p, a, q, b):
    r, s = (a[0] - p[0], a[1] - p[1]), (b[0] - q[0], b[1] - q[1])
    den = _cross(r, s)
    if abs(den) < 1e-12:
        return []  # parallel (or along each other: not a crossing)
    qp = (q[0] - p[0], q[1] - p[1])
    t, u = _cross(qp, s) / den, _cross(qp, r) / den
    if -EPS <= t <= 1 + EPS and -EPS <= u <= 1 + EPS:
        return [(min(max(t, 0.0), 1.0), min(max(u, 0.0), 1.0))]
    return []


def _line_curve(p, a, q, s):
    """Where the line p-a crosses the cubic that starts at q: [(t on the line, t on the curve)]."""
    d = (a[0] - p[0], a[1] - p[1])
    n2 = d[0] * d[0] + d[1] * d[1]
    if n2 < 1e-18:
        return []

    def side(t):
        pt = cub(q, s[1], s[2], s[3], t)
        return _cross(d, (pt[0] - p[0], pt[1] - p[1]))

    out, steps = [], 48
    lo, f_lo = 0.0, side(0.0)
    for k in range(1, steps + 1):
        hi = k / steps
        f_hi = side(hi)
        if f_lo == 0.0 or f_lo * f_hi < 0:
            a_, b_, fa = lo, hi, f_lo
            for _ in range(60):
                m = (a_ + b_) / 2
                fm = side(m)
                if fa * fm <= 0:
                    b_ = m
                else:
                    a_, fa = m, fm
            t = (a_ + b_) / 2
            pt = cub(q, s[1], s[2], s[3], t)
            u = ((pt[0] - p[0]) * d[0] + (pt[1] - p[1]) * d[1]) / n2
            if -EPS <= u <= 1 + EPS and all(abs(t - o[1]) > 1e-6 for o in out):
                out.append((min(max(u, 0.0), 1.0), t))
        lo, f_lo = hi, f_hi
    return out


def _box(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _cut(c, t):
    """Two cubics (as four points) that together are the cubic c, cut at t."""
    left, right = split_cubic(*c, t)
    return (c[0], left[1], left[2], left[3]), (left[3], right[1], right[2], right[3])


def _curves(p0, s, q0, r):
    """Where two cubics cross, by cutting both into smaller and smaller pieces whose boxes meet."""
    found, budget = [], [LIMIT]

    def go(a, ta0, ta1, b, tb0, tb1):
        budget[0] -= 1
        if budget[0] < 0:
            return
        x0, y0, x1, y1 = _box(a)
        u0, v0, u1, v1 = _box(b)
        if x1 < u0 or u1 < x0 or y1 < v0 or v1 < y0:
            return
        if max(x1 - x0, y1 - y0, u1 - u0, v1 - v0) < SIZE:
            found.append(((ta0 + ta1) / 2, (tb0 + tb1) / 2))
            return
        if max(x1 - x0, y1 - y0) >= max(u1 - u0, v1 - v0):
            first, second = _cut(a, 0.5)
            mid = (ta0 + ta1) / 2
            go(first, ta0, mid, b, tb0, tb1)
            go(second, mid, ta1, b, tb0, tb1)
        else:
            first, second = _cut(b, 0.5)
            mid = (tb0 + tb1) / 2
            go(a, ta0, ta1, first, tb0, mid)
            go(a, ta0, ta1, second, mid, tb1)

    go((p0, s[1], s[2], s[3]), 0.0, 1.0, (q0, r[1], r[2], r[3]), 0.0, 1.0)
    merged = []
    for t, u in sorted(found):
        if not any(abs(t - m[0]) < 1e-3 and abs(u - m[1]) < 1e-3 for m in merged):
            merged.append((t, u))
    return merged


def intersections(p0, s, q0, r):
    """Where segment s (starting at p0) and segment r (starting at q0) cross: [(t on s, t on r)]."""
    if s[0] == "L" and r[0] == "L":
        return _lines(p0, s[1], q0, r[1])
    if s[0] == "L":
        return _line_curve(p0, s[1], q0, r)
    if r[0] == "L":
        return [(t, u) for u, t in _line_curve(q0, r[1], p0, s)]
    return _curves(p0, s, q0, r)


# ---------- loops ----------


def _starts(c):
    start, segs = c
    out, pos = [], start
    for s in segs:
        out.append(pos)
        pos = s[-1]
    return out


def _extent(p0, s):
    """How far the segment reaches: the larger side of the box round its points."""
    x0, y0, x1, y1 = _box([p0, *s[1:]])
    return max(x1 - x0, y1 - y0)


def _first_crossing(c):
    """(u_a, u_b) with u_a < u_b: the first place the contour crosses itself, as positions along it (segment + t)."""
    starts, segs = _starts(c), c[1]
    n = len(segs)
    big = [_extent(starts[k], segs[k]) > TINY for k in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if not (big[i] and big[j]):
                continue
            for ta, tb in intersections(starts[i], segs[i], starts[j], segs[j]):
                nodes = ([starts[j]] if j == i + 1 else []) + ([starts[0]] if (i == 0 and j == n - 1) else [])
                here = _point(starts[i], segs[i], ta)
                if any(dist(here, node) < NODE for node in nodes):
                    continue  # neighbours meet at a node: that is not a crossing
                ua, ub = i + ta, j + tb
                if ub - ua < TOUCH or n - (ub - ua) < TOUCH:
                    continue
                return ua, ub
    return None


def _trim(p0, s, t0, t1):
    """The part of segment s (starting at p0) between t0 and t1, as (start, seg)."""
    if s[0] == "L":
        return _point(p0, s, t0), ("L", _point(p0, s, t1))
    c = (p0, s[1], s[2], s[3])
    if t0 > 0:
        c = _second(c, t0)
        t1 = (t1 - t0) / (1 - t0)
    if t1 < 1:
        left, _ = split_cubic(*c, t1)
        return c[0], left
    return c[0], ("C", c[1], c[2], c[3])


def _second(c, t):
    left, right = split_cubic(*c, t)
    return (left[3], right[1], right[2], right[3])


def _walk(c, u1, u2):
    """The part of the contour from position u1 forward to u2 (round the end if u2 is first), as a closed contour."""
    starts, segs = _starts(c), c[1]
    n = len(segs)
    if u2 <= u1:
        u2 += n
    pieces = []
    for m in range(math.floor(u1), math.floor(u2) + 1):
        t0 = u1 - m if m == math.floor(u1) else 0.0
        t1 = u2 - m if m == math.floor(u2) else 1.0
        if t1 - t0 < 1e-9:
            continue
        k = m % n
        pieces.append(_trim(starts[k], segs[k], max(t0, 0.0), min(t1, 1.0)))
    if not pieces:
        return None
    start = pieces[0][0]
    out = [s for _, s in pieces]
    out[-1] = (*out[-1][:-1], start)  # the end meets the start at the crossing: make it exactly so
    return start, out


class _Tangled(Exception):
    """The contour crosses itself too often to be a corner artifact."""


def _split(c, budget):
    budget[0] -= 1
    if budget[0] < 0:
        raise _Tangled
    if len(c[1]) < 2:
        return [c]
    hit = _first_crossing(c)
    if hit is None:
        return [c]
    ua, ub = hit
    inner, outer = _walk(c, ua, ub), _walk(c, ub, ua)
    if inner is None or outer is None:
        return [c]
    return _split(inner, budget) + _split(outer, budget)


def split_loops(c):
    """The closed loops the contour is made of when cut where it crosses itself (itself, if it does not, or if it
    crosses itself too often to be told apart)."""
    try:
        return _split(c, [MAX_LOOPS])
    except _Tangled:
        return [c]


def remove_loops(c, sign, minimum=1.0):
    """The contour with every loop that goes round the other way cut off, or None if that does not leave exactly one.

    `sign` says which way the contour should go round (+1 or -1, as signed_area): a hole goes the way it does at the
    weight where it is still sound. A contour that does not cross itself and goes the right way comes back as it is."""
    try:
        loops = _split(c, [MAX_LOOPS])
    except _Tangled:
        return None
    keep = [x for x in loops if signed_area(x) * sign > minimum]
    return keep[0] if len(keep) == 1 else None
