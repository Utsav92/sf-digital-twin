"""Phase 5: water surfaces for one tile.
- bay/ocean: (tile box - SF land polygons buffered -3 m) at sea level; the 3 m overlap tucks under the
  terrain at seawalls so there is no visible gap. Inland below-sea pits are NOT flooded.
- lakes/channels: OSM water polygons at their city-wide level (water_levels.json), clipped to the tile.
f_mat: 0 = bay, 1 = lake.  Same geometry for LOD0 and LOD1 (already cheap).
"""
from __future__ import annotations

import json

import geopandas as gpd
import numpy as np
import shapely

from geom.meshio import MeshBuf
from geom.polytri import triangulate

_G = {}


def _land(proc):
    if "land" not in _G:
        g = gpd.read_file(proc / "boundary/sf_land.gpkg")
        _G["land"] = shapely.union_all(g.geometry.values)
        _G["tree"] = None
        _G["levels"] = json.loads((proc / "water_levels.json").read_text())
    return _G["land"], _G["levels"]


def build(ctx) -> dict:
    proc = ctx.dir.parents[1]
    land, levels = _land(proc)
    bx0, by0, bx1, by1 = ctx.tile["bounds_city"]
    box = shapely.box(bx0 + ctx.ox, by0 + ctx.oy, bx1 + ctx.ox, by1 + ctx.oy)
    buf = MeshBuf()
    # bay: only where terrain actually goes below sea level in this tile
    if ctx.z.min() < ctx.sea:
        sea_poly = box.difference(land.intersection(box.buffer(10)).buffer(-3.0))
        if not sea_poly.is_empty:
            v, f = triangulate(sea_poly, ctx.wx, ctx.wy)
            if len(f):
                buf.add(np.c_[v, np.full(len(v), ctx.sea)], f, mat=np.int32(0))
    w = ctx.read("water")
    for _, row in w.iterrows():
        lv = levels.get(row.osm_id)
        if lv is None or row.geometry.is_empty:
            continue
        g = row.geometry
        if lv["kind"] == "tidal":
            g = g.buffer(2.0)  # channels: overlap the banks slightly
        v, f = triangulate(shapely.clip_by_rect(g, *box.bounds), ctx.wx, ctx.wy)
        if len(f):
            buf.add(np.c_[v, np.full(len(v), lv["z"])], f, mat=np.int32(0 if lv["kind"] == "tidal" else 1))
    arr = buf.arrays()
    meta = {"layer": "water"}
    return {"lod1": (arr, meta), "lod0": (arr, meta)}
