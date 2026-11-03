"""Phase 8: tree instance points for one tile.

Sources: trees_all.parquet (DataSF street trees + OSM natural=tree) and a procedural scatter inside
OSM forest/wood polygons (jittered 7 m grid hashed on world cell index -> identical regardless of tiling),
excluding road/sidewalk surfaces, building footprints and water.
npz: verts = tree base points (tile-local, on terrain), p_scale (N,3) = (crown r, crown r, height),
     p_cls (N,) 0 broadleaf / 1 conifer / 2 palm, p_rot (N,) radians, p_src (N,) 0 data / 1 procedural.
"""
from __future__ import annotations

import numpy as np
import shapely

CLS = {"broadleaf": 0, "conifer": 1, "palm": 2}
SPACING = 7.0


def _hash(i, j, k):
    """Deterministic pseudo-random [0,1) from integer cell coordinates."""
    h = (i * 73856093) ^ (j * 19349663) ^ (k * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0x1000000)


def forest_points(ctx):
    lu = ctx.read("landuse")
    forest = lu[(lu.key == "natural") & (lu.value == "wood") | (lu.key == "landuse") & (lu.value == "forest")]
    if not len(forest):
        return np.zeros((0, 2)), np.zeros(0)
    g = shapely.union_all(forest.geometry.values)
    bx0, by0, bx1, by1 = ctx.tile["bounds_city"]
    i = np.arange(int(np.floor(bx0 / SPACING)), int(np.ceil(bx1 / SPACING)))
    j = np.arange(int(np.floor(by0 / SPACING)), int(np.ceil(by1 / SPACING)))
    I, J = np.meshgrid(i, j)
    I, J = I.ravel().astype(np.int64), J.ravel().astype(np.int64)
    jx = _hash(I, J, 1)
    jy = _hash(I, J, 2)
    x = (I + 0.15 + 0.7 * jx) * SPACING  # city frame
    y = (J + 0.15 + 0.7 * jy) * SPACING
    own = (x >= bx0) & (x < bx1) & (y >= by0) & (y < by1)
    x, y, I, J = x[own], y[own], I[own], J[own]
    wx, wy = x + ctx.ox, y + ctx.oy
    keep = shapely.contains_xy(g, wx, wy)
    # exclude roads, buildings, water
    from geom import roads
    roads.ground_network(ctx)
    raw = roads._G.get("last_raw")
    blocks = [raw] if raw is not None else []
    b = ctx.read("buildings")
    if len(b):
        blocks.append(shapely.union_all(b.geometry.values).buffer(2.0))
    w = ctx.read("water")
    if len(w):
        blocks.append(shapely.union_all(w.geometry.values))
    if blocks:
        keep &= ~shapely.contains_xy(shapely.union_all(blocks), wx, wy)
    return np.c_[wx[keep], wy[keep]], _hash(I[keep], J[keep], 3)


def build(ctx) -> dict:
    t = ctx.read("trees")
    pts = np.c_[t.geometry.x.values, t.geometry.y.values] if len(t) else np.zeros((0, 2))
    h = t.height_m.values.astype(np.float32) if len(t) else np.zeros(0, np.float32)
    r = t.crown_r_m.values.astype(np.float32) if len(t) else np.zeros(0, np.float32)
    c = t.vclass.map(CLS).values.astype(np.int32) if len(t) else np.zeros(0, np.int32)
    src = np.zeros(len(pts), np.int32)
    fp, rnd = forest_points(ctx)
    if len(fp):
        # Presidio/Sutro/GG Park woods: mostly cypress/pine/eucalyptus -> mix of conifer and tall broadleaf
        fh = (14 + 14 * rnd).astype(np.float32)
        fr = (3.0 + 2.5 * rnd).astype(np.float32)
        fc = np.where(rnd < 0.55, 1, 0).astype(np.int32)
        pts, h, r, c = np.r_[pts, fp], np.r_[h, fh], np.r_[r, fr], np.r_[c, fc]
        src = np.r_[src, np.ones(len(fp), np.int32)]
    out = {}
    for lod, sampler in (("lod1", ctx.ground), ("lod0", ctx.ground0)):
        lx, ly = pts[:, 0] - ctx.wx, pts[:, 1] - ctx.wy
        z = sampler(lx, ly) if len(pts) else np.zeros(0)
        rot = (np.abs(np.sin(pts[:, 0] * 12.9898 + pts[:, 1] * 78.233)) * 6.2831).astype(np.float32) \
            if len(pts) else np.zeros(0, np.float32)
        arr = {"verts": np.c_[lx, ly, z].astype(np.float32), "loops": np.zeros(0, np.int32),
               "sizes": np.zeros(0, np.int32), "p_scale": np.c_[r, r, h].astype(np.float32),
               "p_cls": c, "p_rot": rot, "p_src": src}
        out[lod] = (arr, {"layer": "trees", "lod": lod, "count": int(len(pts)),
                          "procedural": int(src.sum())})
    return out
