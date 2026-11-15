"""Layer guessing and annotation for SF Symbols templates.

A template (SwiftDraw output) has three weight groups (Ultralight-S, Regular-S, Black-S), each containing one <path>
per source element, in the same order. A path's layer is written as a class:
    class="monochrome-N multicolor-N:tintColor hierarchical-N:<level>"

Rules (defaults; cap=4):
  * A "container" exists if the largest path's bbox area is >= container_ratio x the second largest AND its bbox
    encloses every other path's bbox (8% tolerance). It becomes layer 0, `secondary`.
  * Small corner features of the container (touching two adjacent edges of its bbox, e.g. a file's folded corner)
    are absorbed into the container layer.
  * The remaining paths are grouped by geometry: touching outlines form one layer (an arrow's shaft + head), then
    the nearest groups merge until the icon has at most `cap` layers in total. Groups are `primary`.
  * No container -> all groups `primary`.
"""
import re
from dataclasses import dataclass

WEIGHTS = ('Ultralight-S', 'Regular-S', 'Black-S')
GROUP = r'(<g id="%s"[^>]*>)(.*?)(</g>)'
LEVELS = ['primary', 'secondary', 'tertiary']
NUM = r'-?\d*\.?\d+(?:e-?\d+)?'

STEP = 2.5     # sampling spacing along outlines (template units; a Regular stroke is ~7 units wide)
TOUCH = 2.5    # two outlines closer than this are "touching" (overlapping strokes / joined segments)


@dataclass(frozen=True)
class LayerAssignment:
    layer: int
    level: str   # 'primary' | 'secondary' | 'tertiary'


# --- geometry -------------------------------------------------------------------------------------------------

def bbox(d):
    n = [float(x) for x in re.findall(NUM, d)]
    xs, ys = n[0::2], n[1::2]
    return min(xs), min(ys), max(xs), max(ys)


def area(d):
    x0, y0, x1, y1 = bbox(d)
    return (x1 - x0) * (y1 - y0)


def encloses(big, small, tol):
    return (small[0] >= big[0] - tol and small[1] >= big[1] - tol and
            small[2] <= big[2] + tol and small[3] <= big[3] + tol)


def samples(d):
    """Flatten an absolute M/L/C/Z path (SwiftDraw output) into a list of points, ~STEP apart."""
    pts = []; cur = None; start = None
    toks = re.findall(r'[MLCZ]|' + NUM, d)
    i = 0; cmd = None

    def seg(p0, p1):
        n = max(1, int(((p1[0] - p0[0]) ** 2 + (p1[1] - p0[1]) ** 2) ** 0.5 / STEP))
        return [(p0[0] + (p1[0] - p0[0]) * t / n, p0[1] + (p1[1] - p0[1]) * t / n) for t in range(1, n + 1)]

    while i < len(toks):
        if toks[i] in 'MLCZ':
            cmd = toks[i]; i += 1
        if cmd == 'Z':
            if cur and start:
                pts += seg(cur, start); cur = start
            continue
        if cmd in 'ML':
            p = (float(toks[i]), float(toks[i + 1])); i += 2
            if cmd == 'M' or cur is None:
                start = p; pts.append(p)
            else:
                pts += seg(cur, p)
            cur = p; cmd = 'L' if cmd == 'M' else cmd
        elif cmd == 'C':
            c = [float(x) for x in toks[i:i + 6]]; i += 6
            p0 = cur; p1 = (c[0], c[1]); p2 = (c[2], c[3]); p3 = (c[4], c[5])
            ln = sum(((b[0] - a_[0]) ** 2 + (b[1] - a_[1]) ** 2) ** 0.5 for a_, b in ((p0, p1), (p1, p2), (p2, p3)))
            n = max(2, int(ln / STEP))
            for t in range(1, n + 1):
                u = t / n; v = 1 - u
                pts.append((v ** 3 * p0[0] + 3 * v * v * u * p1[0] + 3 * v * u * u * p2[0] + u ** 3 * p3[0],
                            v ** 3 * p0[1] + 3 * v * v * u * p1[1] + 3 * v * u * u * p2[1] + u ** 3 * p3[1]))
            cur = p3
    return pts


def gap(pa, pb, ba, bb_, limit):
    """Smallest point-to-point distance between two outlines (exact up to `limit`, else >= limit)."""
    dx = max(ba[0] - bb_[2], bb_[0] - ba[2], 0); dy = max(ba[1] - bb_[3], bb_[1] - ba[3], 0)
    if (dx * dx + dy * dy) ** 0.5 >= limit:
        return limit
    best = limit * limit
    for x, y in pa:
        for u, v in pb:
            d = (x - u) ** 2 + (y - v) ** 2
            if d < best:
                best = d
    return best ** 0.5


def cluster(members, pts, bb_of, avail):
    """Group path indices (`members`) by geometry: touching outlines form one group; if there are still more groups
    than `avail`, repeatedly merge the two nearest groups. Groups are ordered by their first member."""
    n = len(members); big = 1e9
    dist = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            dist[i][j] = dist[j][i] = gap(pts[i], pts[j], bb_of[i], bb_of[j], big)
    groups = [[i] for i in range(n)]

    def gd(g, h):
        return min(dist[i][j] for i in g for j in h)

    while True:   # 1) merge everything that touches
        pair = next(((x, y) for x in range(len(groups)) for y in range(x + 1, len(groups))
                     if gd(groups[x], groups[y]) <= TOUCH), None)
        if not pair:
            break
        x, y = pair; groups[x] += groups.pop(y)
    while len(groups) > avail:   # 2) still too many: merge the nearest pair (ties -> earliest)
        _, x, y = min((gd(groups[x], groups[y]), x, y) for x in range(len(groups)) for y in range(x + 1, len(groups)))
        groups[x] += groups.pop(y)
    groups = [sorted(members[i] for i in g) for g in groups]
    return sorted(groups, key=lambda g: g[0])


def _split(n, k):
    """n items into k contiguous groups of near-equal size -> list of group index per item."""
    out = []; base, extra = divmod(n, k)
    for g in range(k):
        out += [g] * (base + (1 if g < extra else 0))
    return out


# --- planning -------------------------------------------------------------------------------------------------

def plan_layers(ds, cap=4, container_ratio=1.5, mode='container', grouping='geometry'):
    """One LayerAssignment per path `d` string, in order."""
    k = len(ds)
    if k == 0:
        return []
    if mode == 'flat' or k == 1:
        return [LayerAssignment(0, 'primary')] * k
    if mode == 'order':
        return [LayerAssignment(i, LEVELS[min(i, 2)]) for i in range(k)]
    ar = [area(d) for d in ds]
    order = sorted(range(k), key=lambda i: -ar[i])
    bb = [bbox(d) for d in ds]; big = bb[order[0]]
    tol = 0.08 * max(big[2] - big[0], big[3] - big[1])
    container = order[0] if (ar[order[0]] >= container_ratio * ar[order[1]] and
                             all(encloses(big, bb[i], tol) for i in range(k) if i != order[0])) else None
    idx = [0] * k; off = 0; rest = [i for i in range(k) if i != container]
    if container is not None:
        off = 1
        W, H = big[2] - big[0], big[3] - big[1]

        def corner(b):
            L, T = abs(b[0] - big[0]) <= tol, abs(b[1] - big[1]) <= tol
            R, B = abs(b[2] - big[2]) <= tol, abs(b[3] - big[3]) <= tol
            small = (b[2] - b[0]) < 0.6 * W and (b[3] - b[1]) < 0.6 * H
            return small and ((T and R) or (T and L) or (B and R) or (B and L))

        absorbed = [i for i in rest if corner(bb[i])]
        for i in absorbed:
            idx[i] = 0
        rest = [i for i in rest if i not in absorbed]
    avail = cap - (1 if container is not None else 0)
    groups = []
    if rest:
        if grouping == 'geometry':
            groups = cluster(rest, [samples(ds[i]) for i in rest], bb_of=[bb[i] for i in rest], avail=avail)
        else:
            ng = max(1, min(len(rest), avail))
            groups = [[] for _ in range(ng)]
            for i, g in zip(rest, _split(len(rest), ng)):
                groups[g].append(i)
        for g, members in enumerate(groups):
            for i in members:
                idx[i] = g + off
    levels = (['secondary'] if container is not None else []) + ['primary'] * len(groups)
    return [LayerAssignment(idx[i], levels[idx[i]]) for i in range(k)]


# --- reading and writing annotations --------------------------------------------------------------------------

_PATH_TAG = re.compile(r'<path\b([^>]*?)(/?)>')


def _group_body(svg, weight):
    m = re.search(GROUP % weight, svg, re.S)
    if not m:
        raise ValueError(f'template has no {weight} group')
    return m


def path_ds(template_svg, weight='Regular-S'):
    """The `d` strings of the paths in one weight group, in order."""
    body = _group_body(template_svg, weight).group(2)
    return re.findall(r'<path\b[^>]*?\sd="([^"]+)"', body)


def read_assignments(template_svg):
    """LayerAssignments read from the Regular-S group's classes (paths without a class read as layer 0 primary)."""
    body = _group_body(template_svg, 'Regular-S').group(2)
    out = []
    for m in _PATH_TAG.finditer(body):
        h = re.search(r'hierarchical-(\d+):(\w+)', m.group(1))
        out.append(LayerAssignment(int(h.group(1)), h.group(2)) if h else LayerAssignment(0, 'primary'))
    return out


def annotate(template_svg, assignments):
    """Write/replace the layer class on every path of all three weight groups."""
    levels = {}
    for a in assignments:
        if a.level not in LEVELS:
            raise ValueError(f'unknown level {a.level!r}')
        if levels.setdefault(a.layer, a.level) != a.level:
            raise ValueError(f'layer {a.layer} has paths with different levels')
    out = template_svg
    for w in WEIGHTS:
        m = _group_body(out, w)
        n = len(_PATH_TAG.findall(m.group(2)))
        if n != len(assignments):
            raise ValueError(f'{w} has {n} paths but {len(assignments)} assignments were given')
        it = iter(assignments)

        def rewrite(pm):
            a = next(it)
            attrs = re.sub(r'\sclass="[^"]*"', '', pm.group(1))
            cls = (f'monochrome-{a.layer} multicolor-{a.layer}:tintColor '
                   f'hierarchical-{a.layer}:{a.level}')
            return f'<path class="{cls}"{attrs}{pm.group(2)}>'

        body = _PATH_TAG.sub(rewrite, m.group(2))
        out = out.replace(m.group(0), m.group(1) + body + m.group(3), 1)
    return out
