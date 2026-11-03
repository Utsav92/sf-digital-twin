"""Numpy mesh primitives for landmark generators. All return (verts (n,3), faces list/array).
Coordinates are whatever frame the caller uses (landmarks use the city frame, metres, Z up)."""
from __future__ import annotations

import numpy as np


def frame(center, angle):
    """2D rotation about center: local (u along angle, v across) -> xy."""
    c, s = np.cos(angle), np.sin(angle)
    cx, cy = center

    def f(u, v):
        u, v = np.asarray(u, float), np.asarray(v, float)
        return np.c_[cx + c * u - s * v, cy + s * u + c * v]
    return f


def loft(rings, cap_bottom=True, cap_top=True):
    """Stack of closed rings (k rings of n pts (n,3), CCW from above) -> side quads + n-gon caps."""
    rings = [np.asarray(r, float) for r in rings]
    n = len(rings[0])
    V = np.concatenate(rings)
    F = []
    for k in range(len(rings) - 1):
        a, b = k * n, (k + 1) * n
        for i in range(n):
            j = (i + 1) % n
            F.append([a + i, a + j, b + j, b + i])
    if cap_bottom:
        F.append(list(range(n))[::-1])
    if cap_top:
        F.append(list(range((len(rings) - 1) * n, len(rings) * n)))
    return V, F


def ring(xy, z):
    xy = np.asarray(xy, float)
    return np.c_[xy, np.full(len(xy), z)]


def circle(center, r, n=24, z=0.0, rx=None, ry=None, phase=0.0):
    t = phase + np.linspace(0, 2 * np.pi, n, endpoint=False)
    return np.c_[center[0] + (rx or r) * np.cos(t), center[1] + (ry or r) * np.sin(t), np.full(n, z)]


def rounded_rect(center, angle, w, d, r, n_corner=4):
    """CCW rounded rectangle (w along angle, d across), corner radius r."""
    pts = []
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cy = sx * (w / 2 - r), sy * (d / 2 - r)
        for t in np.radians(np.linspace(a0, a0 + 90, n_corner)):
            pts.append((cx + r * np.cos(t), cy + r * np.sin(t)))
    pts = np.array(pts)
    return frame(center, angle)(pts[:, 0], pts[:, 1])


def rect(center, angle, w, d):
    u = np.array([w, -w, -w, w]) / 2
    v = np.array([d, d, -d, -d]) / 2
    return frame(center, angle)(u, v)[[3, 0, 1, 2]]  # CCW starting (+w,-d)


def box(center, angle, w, d, z0, z1):
    r = rect(center, angle, w, d)
    return loft([ring(r, z0), ring(r, z1)])


def prism(xy_ring, z0, z1, scale_top=1.0, center=None):
    xy = np.asarray(xy_ring, float)
    c = np.asarray(center if center is not None else xy.mean(0))
    top = c + (xy - c) * scale_top
    return loft([ring(xy, z0), ring(top, z1)])


def cylinder(center, r0, z0, z1, r1=None, n=16):
    return loft([circle(center, r0, n, z0), circle(center, r1 if r1 is not None else r0, n, z1)])


def dome(center, r, z0, h, n=24, rings=6, r_top=0.0):
    """Ellipsoidal dome from radius r at z0 to an opening r_top (0 = closed apex)."""
    rs = []
    for k in range(rings + 1):
        t = k / rings * np.arccos(r_top / r if r > 0 else 0)
        rs.append(circle(center, max(r * np.cos(t), 1e-3), n, z0 + h * np.sin(t)))
    return loft(rs, cap_bottom=False, cap_top=True)


def cone(center, r, z0, z1, n=12):
    base = circle(center, r, n, z0)
    V = np.r_[base, [[center[0], center[1], z1]]]
    F = [[i, (i + 1) % n, n] for i in range(n)] + [list(range(n))[::-1]]
    return V, F


def tube(path, r, n=6):
    """Tube along a 3D polyline (m,3) -> verts, quads (no caps)."""
    p = np.asarray(path, float)
    t = np.gradient(p, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    up = np.where(np.abs(t[:, 2:3]) > 0.9, np.array([[1.0, 0, 0]]), np.array([[0, 0, 1.0]]))
    a = np.cross(t, up)
    a /= np.linalg.norm(a, axis=1, keepdims=True) + 1e-12
    b = np.cross(t, a)
    ang = np.linspace(0, 2 * np.pi, n, endpoint=False)
    V = (p[:, None, :] + r * (np.cos(ang)[None, :, None] * a[:, None, :]
                              + np.sin(ang)[None, :, None] * b[:, None, :])).reshape(-1, 3)
    F = []
    for k in range(len(p) - 1):
        for i in range(n):
            j = (i + 1) % n
            F.append([k * n + i, k * n + j, (k + 1) * n + j, (k + 1) * n + i])
    return V, F


def beam(p0, p1, w, h=None):
    """Square-section beam between two 3D points."""
    return tube(np.array([p0, p1]), (w if h is None else w) * 0.7071, n=4)


def catenary(p0, p1, sag, m=60):
    """Points along a parabola-approximated cable from p0 to p1 sagging `sag` below the chord midpoint."""
    t = np.linspace(0, 1, m)[:, None]
    p = (1 - t) * np.asarray(p0, float) + t * np.asarray(p1, float)
    p[:, 2] -= 4 * sag * (t[:, 0] * (1 - t[:, 0]))
    return p
