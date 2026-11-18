"""The few curve operations the engine needs: distance, points on a segment, and cutting a cubic."""

import math


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def cub(p0, c1, c2, p3, t):
    u = 1 - t
    return (
        u**3 * p0[0] + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * p3[0],
        u**3 * p0[1] + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * p3[1],
    )


def split_cubic(p0, c1, c2, p3, t):
    a = lerp(p0, c1, t)
    b = lerp(c1, c2, t)
    c = lerp(c2, p3, t)
    d = lerp(a, b, t)
    e = lerp(b, c, t)
    m = lerp(d, e, t)
    return ("C", a, d, m), ("C", e, c, p3)
