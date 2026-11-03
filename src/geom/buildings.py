"""Phase 7: building extrusions for one tile.

base  = min terrain under footprint (vertices + interior samples) - 0.5 m   (never floats on slopes)
roof  = max(mean ground + height_m, max ground + 2.5 m)                     (hillside garages keep a roof)
LOD1: exact footprint (courtyards/holes -> inner walls + roof with holes); gable roofs for small
      near-rectangular residential buildings whose LiDAR roof relief > 1.5 m (ridge along long axis).
LOD0: footprint simplified 1 m, flat roof.
Per face: f_bid (global building id), f_mat (0 wall, 1 flat roof, 2 tall-building wall, 3 pitched roof).
Landmarks listed in data/processed/landmark_exclude.json are skipped (replaced in Phase 9).
Also writes buildings_meta.parquet (bid, base, roof, ground min/max/mean, roof type) for the checks.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.polygon import orient

from geom.meshio import MeshBuf
from geom.polytri import polys, triangulate

WALL, ROOF, WALL_TALL, ROOF_PITCH = 0, 1, 2, 3


def _exclude(proc):
    p = proc / "landmark_exclude.json"
    return set(json.loads(p.read_text())["bids"]) if p.exists() else set()


def ground_stats(ctx, poly):
    c = shapely.get_coordinates(poly)  # all rings incl. courtyards
    pts = [c]
    if poly.area > 200:  # interior samples on a 6 m grid for big footprints
        x0, y0, x1, y1 = poly.bounds
        X, Y = np.meshgrid(np.arange(x0, x1, 6.0), np.arange(y0, y1, 6.0))
        m = shapely.contains_xy(poly, X, Y)
        pts.append(np.c_[X[m], Y[m]])
    pts.append(np.array(poly.representative_point().coords))
    p = np.concatenate(pts)
    z = ctx.ground(p[:, 0] - ctx.wx, p[:, 1] - ctx.wy)
    return float(z.min()), float(z.max()), float(z.mean())


def walls(ring_xy, z0, z1):
    """ring (n,2) closed (first==last), oriented so outward is to the right -> verts, quads, corner UVs
    (u = metres along the ring, v = metres above the base: facade textures/windows stay to scale)."""
    r = ring_xy[:-1]
    n = len(r)
    v = np.r_[np.c_[r, np.full(n, z0)], np.c_[r, np.full(n, z1)]]
    i = np.arange(n)
    j = (i + 1) % n
    seg = np.linalg.norm(r[j] - r[i], axis=1)
    s0 = np.r_[0, np.cumsum(seg)[:-1]]
    s1 = s0 + seg
    h = z1 - z0
    uv = np.stack([np.c_[s0, np.zeros(n)], np.c_[s1, np.zeros(n)], np.c_[s1, np.full(n, h)],
                   np.c_[s0, np.full(n, h)]], axis=1).reshape(-1, 2)
    return v, np.c_[i, j, n + j, n + i], uv


def extrude(buf, poly, base, roof, bid, wall_mat, ox, oy):
    poly = orient(poly, 1.0)
    for ring in [poly.exterior, *poly.interiors]:
        xy = shapely.get_coordinates(ring) - (ox, oy)
        if len(xy) < 4:
            continue
        v, q, uv = walls(xy, base, roof)
        buf.add(v, q, uv=uv, bid=np.int32(bid), mat=np.int32(wall_mat))
    v2, t = triangulate(poly, ox, oy)
    if len(t):
        buf.add(np.c_[v2, np.full(len(v2), roof)], t, bid=np.int32(bid), mat=np.int32(ROOF))


def gable(buf, rect, base, eave, ridge_h, bid, ox, oy):
    """Gable house on a rectangle: 4 walls to the eave, gable-end triangles, 2 roof slopes."""
    c = shapely.get_coordinates(orient(rect, 1.0).exterior)[:4] - (ox, oy)
    e = [np.linalg.norm(c[(k + 1) % 4] - c[k]) for k in range(4)]
    if e[0] < e[1]:  # make c0->c1 a long edge
        c = np.roll(c, -1, axis=0)
    p0, p1, p2, p3 = c
    m03, m12 = (p0 + p3) / 2, (p1 + p2) / 2
    zr = eave + ridge_h
    V = np.array([[*p0, base], [*p1, base], [*p2, base], [*p3, base],
                  [*p0, eave], [*p1, eave], [*p2, eave], [*p3, eave],
                  [*m03, zr], [*m12, zr]])
    wallq = np.array([[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
    h = eave - base
    uvw = []
    for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
        L = float(np.linalg.norm(V[b, :2] - V[a, :2]))
        uvw += [[0, 0], [L, 0], [L, h], [0, h]]
    buf.add(V, wallq, uv=np.array(uvw), bid=np.int32(bid), mat=np.int32(WALL))
    buf.add(V, [[5, 6, 9], [7, 4, 8]], bid=np.int32(bid), mat=np.int32(WALL))       # gable ends
    buf.add(V, [[4, 5, 9, 8], [6, 7, 8, 9]], bid=np.int32(bid), mat=np.int32(ROOF_PITCH))  # slopes


def build(ctx) -> dict:
    b = ctx.read("buildings")
    excl = _exclude(ctx.dir.parents[1])
    buf1, buf0 = MeshBuf(), MeshBuf()
    meta = []
    for row in b.itertuples():
        if row.bid in excl:
            continue
        parts = polys(row.geometry)
        if not parts:
            continue
        gmin, gmax, gmean = ground_stats(ctx, max(parts, key=lambda p: p.area))
        for p in parts[1:]:
            a, bb, c = ground_stats(ctx, p)
            gmin, gmax = min(gmin, a), max(gmax, bb)
        h = float(row.height_m)
        base = gmin - 0.5
        roof = max(gmean + h, gmax + 2.5)
        wall_mat = WALL_TALL if h > 40 else WALL
        kind = "flat"
        # ---- LOD1
        rr = row.roof_relief_m if row.roof_relief_m == row.roof_relief_m else 0.0
        if len(parts) == 1 and h < 15 and rr > 1.5 and row.height_source == "lidar" and not parts[0].interiors:
            mrr = shapely.minimum_rotated_rectangle(parts[0])
            if mrr.area > 0 and parts[0].area / mrr.area > 0.85:
                cc = shapely.get_coordinates(mrr.exterior)[:4]
                short = min(np.linalg.norm(cc[1] - cc[0]), np.linalg.norm(cc[2] - cc[1]))
                ridge = float(min(rr, 0.5 * short * np.tan(np.radians(35))))
                eave = roof - ridge / 2  # LiDAR median sits mid-slope
                if eave - base > 2.0:
                    gable(buf1, mrr, base, eave, ridge, row.bid, ctx.wx, ctx.wy)
                    kind = "gable"
        if kind == "flat":
            for p in parts:
                extrude(buf1, p, base, roof, row.bid, wall_mat, ctx.wx, ctx.wy)
        # ---- LOD0
        for p in parts:
            ps = p.simplify(1.0, preserve_topology=True)
            if ps.is_empty or ps.area < 2:
                ps = p
            for q in polys(ps):
                extrude(buf0, q, base, roof, row.bid, wall_mat, ctx.wx, ctx.wy)
        meta.append((row.bid, base, roof, gmin, gmax, gmean, h, kind, row.height_source))
    pd.DataFrame(meta, columns=["bid", "base", "roof", "gmin", "gmax", "gmean", "height_m", "roof_kind",
                                "height_source"]).to_parquet(ctx.dir / "buildings_meta.parquet")
    m = {"layer": "buildings", "count": len(meta)}
    return {"lod1": (buf1.arrays(), {**m, "lod": "lod1"}), "lod0": (buf0.arrays(), {**m, "lod": "lod0"})}
