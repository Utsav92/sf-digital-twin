"""Phase 3e: per-tile clipping -> data/processed/tiles/<tile_id>/

terrain_lod1.tif  2 m lattice, (S/2+1)^2 points incl. both edges (shared with neighbours)
terrain_lod0.tif  10 m lattice
buildings/roads/rail/water/landuse/piers/trees.parquet  (EPSG:26910, world coords)
prep.json         per-layer counts

Seam rules
- Lattice value at a world point depends only on that point (mean of the DEM pixels around it),
  so the shared edge of two neighbouring tiles is bit-identical.
- Buildings/trees: by precomputed 'tile' (representative point) -> exactly one tile.
- Lines/polygons: shapely.clip_by_rect with the exact tile rectangle (consistent across neighbours).

python src/prep/prep_tiles.py [--pilot] [--tiles a,b] [--force] [--workers N]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.transform import from_origin
from rasterio.windows import Window

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"
LAYERS = {"roads": "osm/roads.parquet", "rail": "osm/rail.parquet", "water": "osm/water.parquet",
          "landuse": "osm/landuse.parquet", "piers": "osm/piers.parquet",
          "bridges_area": "osm/bridges_area.parquet"}
G: dict = {}


def select_tiles(idx: dict, pilot: bool, tiles: str | None) -> list[dict]:
    T = [t for t in idx["tiles"].values() if t["status"] == "build"]
    if pilot:
        T = [t for t in T if t["pilot"]]
    if tiles:
        want = set(tiles.split(","))
        T = [t for t in idx["tiles"].values() if t["id"] in want]
    return T


def _init():
    G["layers"] = {k: gpd.read_parquet(PROC / v) for k, v in LAYERS.items()}
    G["b"] = gpd.read_parquet(PROC / "buildings_all.parquet")
    G["t"] = gpd.read_parquet(PROC / "trees_all.parquet")
    G["dem"] = rasterio.open(PROC / "dem/dem_1m.tif")
    G["ox"], G["oy"] = crs.origin_world()
    G["cfg"] = crs.config()
    idx = json.loads((PROC / "tile_index.json").read_text())
    G["x0"], G["y1"] = idx["extent_city"][0], idx["extent_city"][3]


def lattice(bounds, step: float) -> np.ndarray:
    """Sample DEM at lattice points (row 0 = south edge). Value = mean of DEM pixels within +-step/2
    (step>=2) of the point; pixel edges sit on integer city meters."""
    x0, y0, x1, y1 = bounds
    h = int(round(step / 2))
    # pixel col of city x: x - X0 ; pixel row of city y: Y1 - y   (pixel covers [x, x+1) x (y-1, y])
    c0 = int(x0 - G["x0"]) - h
    r0 = int(G["y1"] - y1) - h
    n = int((x1 - x0) / step) + 1
    win = Window(c0, r0, int(x1 - x0) + 2 * h, int(y1 - y0) + 2 * h)
    a = G["dem"].read(1, window=win, boundless=True, fill_value=np.nan).astype(np.float64)
    # per-point block mean over a fixed (2h x 2h) pixel window: summation order depends only on the
    # pixels themselves, so neighbouring tiles produce bit-identical values on shared edges
    k = np.arange(n) * int(step)            # window start (pixel offset) for each lattice point
    blocks = np.lib.stride_tricks.sliding_window_view(a, (2 * h, 2 * h))[k][:, k]
    z = np.nanmean(blocks, axis=(-1, -2))  # nan = outside DEM extent (grid-edge tiles)
    return np.flipud(z).astype(np.float32)  # rows north->south in window; flip so row 0 = south


def write_lattice(path: Path, z: np.ndarray, bounds, step):
    ox, oy = G["ox"], G["oy"]
    tr = from_origin(ox + bounds[0] - step / 2, oy + bounds[3] + step / 2, step, step)
    with rasterio.open(path, "w", driver="GTiff", width=z.shape[1], height=z.shape[0], count=1, dtype="float32",
                       crs="EPSG:26910", transform=tr) as w:
        w.write(np.flipud(z), 1)  # GeoTIFF rows north->south
        w.update_tags(AREA_OR_POINT="Point", lattice_step_m=step, row0="north",
                      note="pixel centres are lattice points; tile edges included")


def do_tile(t: dict, force: bool) -> dict:
    out = PROC / "tiles" / t["id"]
    done = out / "prep.json"
    if done.exists() and not force:
        return json.loads(done.read_text())
    t0 = time.time()
    out.mkdir(parents=True, exist_ok=True)
    ox, oy = G["ox"], G["oy"]
    bx0, by0, bx1, by1 = t["bounds_city"]
    wb = (bx0 + ox, by0 + oy, bx1 + ox, by1 + oy)
    rec = {"id": t["id"], "counts": {}, "dropped": {}}
    for step, name in ((G["cfg"]["terrain"]["lattice_m"], "lod1"), (G["cfg"]["terrain"]["lod0_lattice_m"], "lod0")):
        z = lattice(t["bounds_city"], step)
        write_lattice(out / f"terrain_{name}.tif", z, t["bounds_city"], step)
        rec["counts"][f"terrain_{name}"] = list(z.shape)
        if name == "lod1":
            rec["z_min"], rec["z_max"] = float(np.nanmin(z)), float(np.nanmax(z))
    for name, g in (("buildings", G["b"]), ("trees", G["t"])):
        sub = g[g.tile == t["id"]]
        sub.to_parquet(out / f"{name}.parquet")
        rec["counts"][name] = len(sub)
    box = shapely.box(*wb)
    for name, g in G["layers"].items():
        cand = g.iloc[g.sindex.query(box, predicate="intersects")].copy()
        if len(cand):
            cand["geometry"] = shapely.clip_by_rect(cand.geometry.values, *wb)
            empty = cand.geometry.is_empty
            rec["dropped"][name + "_clip_empty"] = int(empty.sum())
            cand = cand[~empty]
        cand.to_parquet(out / f"{name}.parquet")
        rec["counts"][name] = len(cand)
    rec["seconds"] = round(time.time() - t0, 2)
    tmp = done.with_suffix(".part")
    tmp.write_text(json.dumps(rec))
    tmp.replace(done)
    return rec


def _run(args):
    return do_tile(*args)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tiles")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=crs.config()["parallel"]["prep_workers"])
    a = ap.parse_args()
    idx = json.loads((PROC / "tile_index.json").read_text())
    T = select_tiles(idx, a.pilot, a.tiles)
    t0 = time.time()
    print(f"prep {len(T)} tiles with {a.workers} workers")
    with mp.get_context("spawn").Pool(a.workers, initializer=_init) as pool:
        res = []
        for k, r in enumerate(pool.imap_unordered(_run, [(t, a.force) for t in T])):
            res.append(r)
            if k % 50 == 0 or k == len(T) - 1:
                print(f"  {k + 1}/{len(T)} {r['id']} {r['seconds']} s", flush=True)
    tot = {}
    for r in res:
        for k, v in r["counts"].items():
            if isinstance(v, int):
                tot[k] = tot.get(k, 0) + v
    print(f"done in {time.time() - t0:.1f} s; totals: {tot}")


if __name__ == "__main__":
    main()
