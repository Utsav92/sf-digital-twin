"""Terrain lattice -> grid mesh (tile-local), shared-edge seams, adaptive per-tile resolution,
and a bilinear height sampler used by every draped layer.

Adaptive rule: tiles with land get the 2 m lattice (LOD1); pure-water tiles use the 10 m lattice for
LOD1 too. Where a fine tile borders a coarse one, the fine tile's edge heights are replaced by linear
interpolation of the coarse edge -> identical polylines, no cracks or T-gaps.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import rasterio

# surface classes stored per terrain face (f_cls); Phase 5 fills land-use classes
CLS = {"ground": 0, "seabed": 1, "beach": 2, "grass": 3, "park": 4, "forest": 5, "scrub": 6, "golf": 7,
       "cemetery": 8, "sport": 9, "paved": 10, "industrial": 11, "rail_yard": 12, "construction": 13,
       "rock": 14, "wetland": 15, "residential": 16, "commercial": 17}


def read_lattice(tdir: Path, lod: str) -> np.ndarray:
    with rasterio.open(tdir / f"terrain_{lod}.tif") as r:
        return np.flipud(r.read(1)).astype(np.float64)  # row 0 = south


def lod1_step(tile: dict) -> str:
    return "lod1" if tile.get("land_fraction", 1) > 0 else "lod0"


_LAKES = {}


def _lakes(proc: Path):
    """City-wide lake/channel polygons (shrunk 1 m) with their surface level."""
    if "g" not in _LAKES:
        import geopandas as gpd
        lv = json.loads((proc / "water_levels.json").read_text())
        w = gpd.read_parquet(proc / "osm/water.parquet")
        w = w[w.osm_id.isin(lv)]
        _LAKES["g"] = [(g.buffer(-1.0), lv[i]["z"]) for i, g in zip(w.osm_id, w.geometry)]
    return _LAKES["g"]


def carve_lakes(z: np.ndarray, tile: dict, proc: Path) -> np.ndarray:
    """Lower lattice points inside water polygons to level - 1.5 m so lake surfaces never z-fight
    with the (flat, LiDAR-water) terrain. Depends only on world position -> seams stay identical."""
    import shapely
    from common import crs
    n = z.shape[0]
    x0, y0, x1, y1 = tile["bounds_city"]
    ox, oy = crs.origin_world()
    xs = np.linspace(x0, x1, n) + ox
    ys = np.linspace(y0, y1, n) + oy
    box = shapely.box(xs[0], ys[0], xs[-1], ys[-1])
    X, Y = np.meshgrid(xs, ys)
    for g, lvl in _lakes(proc):
        if g.is_empty or not g.intersects(box):
            continue
        inside = shapely.contains_xy(g, X, Y)
        z[inside] = np.minimum(z[inside], lvl - 1.5)
    return z


def tile_lattice(tdir: Path, tile: dict, tiles: dict, proc: Path) -> tuple[np.ndarray, float]:
    """LOD1 lattice with lake carving and edge stitching to coarse neighbours."""
    S = 500.0
    if lod1_step(tile) == "lod0":
        z = carve_lakes(read_lattice(tdir, "lod0"), tile, proc)
        return z, S / (z.shape[0] - 1)
    z = carve_lakes(read_lattice(tdir, "lod1"), tile, proc)
    n = z.shape[0]
    coarse = carve_lakes(read_lattice(tdir, "lod0"), tile, proc)
    m = coarse.shape[0]
    fx = np.linspace(0, m - 1, n)
    for d, sl in {"W": np.s_[:, 0], "E": np.s_[:, -1], "S": np.s_[0, :], "N": np.s_[-1, :]}.items():
        nb = tiles.get(tile["neighbors"].get(d, ""))
        # only a built coarse neighbour needs stitching; fine neighbours already share identical edges
        if nb is not None and nb.get("status") == "build" and lod1_step(nb) == "lod0":
            z[sl] = np.interp(fx, np.arange(m), coarse[sl])
    # tile corners are shared by up to 4 tiles of mixed resolution: always use the coarse value so every
    # tile agrees regardless of which of its edges were stitched
    for r, c in ((0, 0), (0, -1), (-1, 0), (-1, -1)):
        z[r, c] = coarse[r, c]
    return z, S / (n - 1)


def grid_mesh(z: np.ndarray, step: float):
    """Regular grid -> (verts, quads); tile-local coords, centred."""
    n = z.shape[0]
    half = step * (n - 1) / 2
    xs = -half + step * np.arange(n)
    X, Y = np.meshgrid(xs, xs)  # row = y index (south->north)
    verts = np.c_[X.ravel(), Y.ravel(), z.ravel()]
    i = np.arange(n - 1)
    I, J = np.meshgrid(i, i)  # J rows (y), I cols (x)
    v0 = (J * n + I).ravel()
    quads = np.c_[v0, v0 + 1, v0 + n + 1, v0 + n]  # CCW seen from +Z
    return verts, quads


class Sampler:
    """Bilinear sampling of the tile's LOD1 lattice in tile-local coordinates (clamped to tile)."""

    def __init__(self, z: np.ndarray, step: float):
        self.z, self.step = z, step
        self.n = z.shape[0]
        self.half = step * (self.n - 1) / 2

    def __call__(self, x, y):
        x = np.asarray(x, np.float64)
        y = np.asarray(y, np.float64)
        fx = np.clip((x + self.half) / self.step, 0, self.n - 1 - 1e-9)
        fy = np.clip((y + self.half) / self.step, 0, self.n - 1 - 1e-9)
        i, j = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - i, fy - j
        z = self.z
        return ((1 - tx) * (1 - ty) * z[j, i] + tx * (1 - ty) * z[j, i + 1]
                + (1 - tx) * ty * z[j + 1, i] + tx * ty * z[j + 1, i + 1])


def load_index(proc: Path) -> dict:
    return json.loads((proc / "tile_index.json").read_text())


ROAD_SINK = 0.35


def sink_under_roads(ctx, verts, n, step, stitched):
    """Lower terrain vertices that lie under any road/sidewalk/path surface by ROAD_SINK so the draped
    road mesh (ground + 0.12) can never be poked through. Decided purely by world position against the
    deterministic road network -> identical on shared tile edges. Vertices on edges stitched to a coarse
    neighbour are left alone (they must stay on the coarse polyline)."""
    import shapely
    from geom import roads
    roads.ground_network(ctx)
    raw = roads._G.get("last_raw")
    if raw is None:
        return verts
    # unclipped network (all roads within the 60 m margin) -> identical decision on both sides of a seam;
    # +1.5 m covers lattice points just outside road edges
    u = raw.buffer(1.5, quad_segs=2)
    inside = shapely.contains_xy(u, verts[:, 0] + ctx.wx, verts[:, 1] + ctx.wy).reshape(n, n)
    for d in stitched:
        inside[{"W": np.s_[1:-1, 0], "E": np.s_[1:-1, -1], "S": np.s_[0, 1:-1], "N": np.s_[-1, 1:-1]}[d]] = False
    inside[[0, 0, -1, -1], [0, -1, 0, -1]] = False  # corners are shared by up to 4 mixed-LOD tiles: never sunk
    v = verts.copy()
    v[inside.ravel(), 2] -= ROAD_SINK
    return v


def stitched_edges(tile, tiles):
    """Edges whose interior vertices must not be sunk: for a fine tile the edges stitched to a coarse
    neighbour; for a coarse tile the edges facing a fine neighbour (the fine side interpolates them)."""
    me = lod1_step(tile)
    return [d for d in "WESN" if (nb := tiles.get(tile["neighbors"].get(d, ""))) is not None
            and nb.get("status") == "build" and lod1_step(nb) != me]


def build(ctx) -> dict:
    """Layer entry point. LOD1 = stitched adaptive lattice, LOD0 = 10 m lattice.
    f_cls: surface class per face (seabed below sea level; Phase 5 overwrites with land use)."""
    out = {}
    lod0 = carve_lakes(read_lattice(ctx.dir, "lod0"), ctx.tile, ctx.dir.parents[1])
    for lod, (z, step) in {"lod1": (ctx.z, ctx.step), "lod0": (lod0, 500.0 / (lod0.shape[0] - 1))}.items():
        verts, quads = grid_mesh(z, step)
        st = stitched_edges(ctx.tile, ctx.index["tiles"]) if lod == "lod1" else []
        verts = sink_under_roads(ctx, verts, z.shape[0], step, st)
        zf = verts[quads, 2].mean(1)
        cls = np.where(zf < ctx.sea - 0.3, CLS["seabed"], CLS["ground"]).astype(np.int32)
        from geom import landcls  # Phase 5: land-use classification of terrain faces
        cls = landcls.classify_faces(ctx, verts, quads, cls)
        out[lod] = ({"verts": verts.astype(np.float32), "loops": quads.ravel().astype(np.int32),
                     "sizes": np.full(len(quads), 4, np.int32), "f_cls": cls},
                    {"layer": "terrain", "lod": lod, "step_m": step,
                     "z_min": float(z.min()), "z_max": float(z.max())})
    return out
