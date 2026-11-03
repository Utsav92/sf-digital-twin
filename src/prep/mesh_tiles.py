"""Per-tile mesh generation (prep side). Writes data/processed/tiles/<id>/mesh_<layer>_<lod>.npz

python src/prep/mesh_tiles.py --layers terrain[,water,land,roads,rail,buildings,trees] [--pilot|--tiles ..]
                              [--force] [--workers N]
Each layer module exposes build(ctx) -> {lod: (arrays|None, meta)}.
"""
from __future__ import annotations

import argparse
import importlib
import json
import multiprocessing as mp
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom import meshio, terrain  # noqa: E402
from prep.prep_tiles import select_tiles  # noqa: E402

PROC = crs.ROOT / "data/processed"
ALL = ["terrain", "water", "roads", "rail", "buildings", "trees", "props"]  # land use lives in terrain (f_cls)


class Ctx:
    """Everything a layer builder needs for one tile."""

    def __init__(self, tile: dict, index: dict):
        self.tile, self.index = tile, index
        self.dir = PROC / "tiles" / tile["id"]
        self.ox, self.oy = crs.origin_world()
        cx, cy, _ = tile["offset_city"]
        self.wx, self.wy = self.ox + cx, self.oy + cy  # world coords of tile centre
        z, step = terrain.tile_lattice(self.dir, tile, index["tiles"], PROC)
        self.z, self.step = z, step
        self.ground = terrain.Sampler(z, step)
        z0 = terrain.carve_lakes(terrain.read_lattice(self.dir, "lod0"), tile, PROC)
        self.ground0 = terrain.Sampler(z0, 500.0 / (z0.shape[0] - 1))
        self.sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
        self.cfg = crs.config()

    def local(self, x, y):
        return x - self.wx, y - self.wy

    def read(self, layer: str):
        import geopandas as gpd
        return gpd.read_parquet(self.dir / f"{layer}.parquet")


def run_tile(args) -> dict:
    tile, index, layers, force = args
    tdir = PROC / "tiles" / tile["id"]
    rep = {"id": tile["id"], "layers": {}}
    try:
        ctx = None
        for layer in layers:
            marker = tdir / f"mesh_{layer}.done.json"
            if marker.exists() and not force:
                rep["layers"][layer] = json.loads(marker.read_text())
                continue
            ctx = ctx or Ctx(tile, index)
            t0 = time.time()
            mod = importlib.import_module(f"geom.{layer}")
            out = mod.build(ctx)
            lrep = {}
            for lod, (arrays, meta) in out.items():
                if arrays is not None and len(arrays.get("sizes", [])):
                    meshio.planar_uv(arrays, tile["offset_city"])
                lrep[lod] = meshio.save(tdir / f"mesh_{layer}_{lod}.npz", arrays, meta)
            lrep["seconds"] = round(time.time() - t0, 2)
            marker.write_text(json.dumps(lrep))
            rep["layers"][layer] = lrep
    except Exception:  # noqa: BLE001
        rep["error"] = traceback.format_exc()
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", default=",".join(ALL))
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tiles")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=crs.config()["parallel"]["prep_workers"])
    a = ap.parse_args()
    layers = a.layers.split(",")
    index = terrain.load_index(PROC)
    T = select_tiles(index, a.pilot, a.tiles)
    t0 = time.time()
    print(f"mesh {layers} for {len(T)} tiles, {a.workers} workers", flush=True)
    errs, tot = [], {}
    with mp.get_context("spawn").Pool(a.workers) as pool:
        for k, r in enumerate(pool.imap_unordered(run_tile, [(t, index, layers, a.force) for t in T])):
            if "error" in r:
                errs.append(r)
                print(f"  ERROR {r['id']}\n{r['error']}", flush=True)
            for layer, lr in r["layers"].items():
                for lod, m in lr.items():
                    if isinstance(m, dict):
                        key = f"{layer}_{lod}"
                        tot[key] = tot.get(key, 0) + m.get("ntris", 0)
            if k % 50 == 0 or k == len(T) - 1:
                print(f"  {k + 1}/{len(T)} {r['id']}", flush=True)
    print(f"done in {time.time() - t0:.1f} s, errors {len(errs)}; triangles: "
          + ", ".join(f"{k}={v:,}" for k, v in sorted(tot.items())))
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
