"""Polygon triangulation (with holes) and helpers, shapely >= 2.1 constrained Delaunay."""
from __future__ import annotations

import numpy as np
import shapely


def polys(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    if g.geom_type in ("MultiPolygon", "GeometryCollection"):
        return [p for sub in g.geoms for p in polys(sub)]
    return []


def triangulate(g, cx=0.0, cy=0.0, min_area=0.05):
    """Triangulate polygon(s) with holes. Returns (verts (n,2) local = world - (cx,cy), tris (m,3)), CCW up.
    Vertices are deduplicated so triangles share indices."""
    vs, fs, off = [], [], 0
    for p in polys(g):
        if p.area < min_area:
            continue
        p = shapely.set_precision(p, 0.01)
        if p.is_empty:
            continue
        tri = shapely.constrained_delaunay_triangles(p)
        coords = shapely.get_coordinates(tri.geoms if hasattr(tri, "geoms") else tri)
        if len(coords) == 0:
            continue
        c = coords.reshape(-1, 4, 2)[:, :3, :]  # each triangle ring has 4 coords (closed)
        flat = c.reshape(-1, 2)
        uniq, inv = np.unique(np.round(flat, 3), axis=0, return_inverse=True)
        t = inv.reshape(-1, 3)
        # orient CCW (normal +Z)
        a, b, d = uniq[t[:, 0]], uniq[t[:, 1]], uniq[t[:, 2]]
        cross = (b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (d[:, 0] - a[:, 0])
        t[cross < 0] = t[cross < 0][:, [0, 2, 1]]
        t = t[np.abs(cross) > 1e-6]
        vs.append(uniq - (cx, cy))
        fs.append(t + off)
        off += len(uniq)
    if not vs:
        return np.zeros((0, 2)), np.zeros((0, 3), np.int64)
    return np.concatenate(vs), np.concatenate(fs)
