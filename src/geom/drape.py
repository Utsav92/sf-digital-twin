"""Draping helpers: polygons -> grid-subdivided triangles on terrain; polylines -> ribbons."""
from __future__ import annotations

import numpy as np
import shapely


def drape_polygons(geom, ctx, cell: float, sampler, offset: float, rough=None):
    """Cut (multi)polygon (world coords) by a cell grid aligned to the city frame, triangulate pieces,
    lift vertices to sampler(x,y)+offset. Returns verts (n,3) tile-local, tris (m,3)."""
    if geom is None or geom.is_empty:
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    x0, y0, x1, y1 = geom.bounds
    # grid aligned to integer multiples of `cell` in the city frame -> identical cuts across tiles
    gx0 = np.floor((x0 - ctx.ox) / cell) * cell + ctx.ox
    gy0 = np.floor((y0 - ctx.oy) / cell) * cell + ctx.oy
    xs = np.arange(gx0, x1 + cell, cell)
    ys = np.arange(gy0, y1 + cell, cell)
    X, Y = np.meshgrid(xs[:-1], ys[:-1])
    boxes = shapely.box(X.ravel(), Y.ravel(), X.ravel() + cell, Y.ravel() + cell)
    prepared = shapely.prepare(geom) or geom
    hit = shapely.intersects(geom, boxes)
    boxes = boxes[hit]
    if rough is not None and len(boxes):
        # split cells where the terrain is not ~planar into 4 half-size cells
        b = shapely.bounds(boxes)
        r = rough(b[:, 0], b[:, 1], cell)
        if r.any():
            h = cell / 2
            bx, by = b[r, 0], b[r, 1]
            sub = [shapely.box(bx + dx, by + dy, bx + dx + h, by + dy + h) for dx in (0, h) for dy in (0, h)]
            sub = np.concatenate(sub)
            sub = sub[shapely.intersects(geom, sub)]
            boxes = np.concatenate([boxes[~r], sub])
    if not len(boxes):
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    inside = shapely.contains(geom, boxes)
    pieces = np.empty(len(boxes), object)
    pieces[inside] = boxes[inside]
    pieces[~inside] = shapely.intersection(geom, boxes[~inside])
    parts = shapely.get_parts(pieces)
    parts = parts[(shapely.get_type_id(parts) == 3) & (shapely.area(parts) > 0.01)]
    if not len(parts):
        return np.zeros((0, 3)), np.zeros((0, 3), np.int64)
    tri = shapely.get_parts(shapely.constrained_delaunay_triangles(parts))
    tri = tri[shapely.get_type_id(tri) == 3]
    ring = shapely.get_coordinates(shapely.get_exterior_ring(tri))
    c = ring.reshape(-1, 4, 2)[:, :3, :].reshape(-1, 2)
    uniq, inv = np.unique(np.round(c, 3), axis=0, return_inverse=True)
    t = inv.reshape(-1, 3)
    a, b, d = uniq[t[:, 0]], uniq[t[:, 1]], uniq[t[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (d[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (d[:, 0] - a[:, 0])
    t = t[np.abs(cross) > 1e-8]
    cross = cross[np.abs(cross) > 1e-8]
    t[cross < 0] = t[cross < 0][:, [0, 2, 1]]
    lx, ly = uniq[:, 0] - ctx.wx, uniq[:, 1] - ctx.wy
    z = sampler(lx, ly) + offset
    return np.c_[lx, ly, z], t


def ribbon(xy, width, z, closed_ends=False):
    """Polyline (n,2 tile-local) with per-vertex z (n,) -> strip verts (2n,3) and quads (n-1,4) CCW up."""
    n = len(xy)
    t = np.gradient(xy, axis=0)
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
    nrm = np.c_[-t[:, 1], t[:, 0]]
    L = xy + nrm * width / 2
    R = xy - nrm * width / 2
    v = np.r_[np.c_[L, z], np.c_[R, z]]
    i = np.arange(n - 1)
    quads = np.c_[n + i, n + i + 1, i + 1, i]  # R_i, R_i+1, L_i+1, L_i  -> CCW from above
    return v, quads


def densify_line(line, step):
    if line.length == 0:
        return np.zeros((0, 2))
    n = max(2, int(np.ceil(line.length / step)) + 1)
    return shapely.get_coordinates(shapely.line_interpolate_point(line, np.linspace(0, line.length, n)))


def lines_of(g):
    if g is None or g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [p for p in getattr(g, "geoms", []) if p.geom_type == "LineString" and p.length > 0.05]
