"""Phase 7: building assertions (LOD1 meshes vs. source and vs. the terrain mesh).
- building count city-wide within 1% of the source (DataSF footprints inside SF)
- every face carries a source building id; each bid appears in exactly one tile
- Salesforce Tower ~326 m above ground; Transamerica ~260 m
- automated floating / buried detection against the LOD1 terrain mesh:
    floating: building's lowest vertex above the lowest terrain point under its footprint (+5 cm)
    buried  : building's highest vertex below the highest terrain point under its footprint + 1 m
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom.terrain import Sampler  # noqa: E402

PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
T = {k: t for k, t in idx["tiles"].items() if t["status"] == "build"}
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


rep = json.loads((PROC / "buildings_report.json").read_text())
src_city = rep["source_records"] - rep["dropped_outside_sf"]
excl = set(json.loads((PROC / "landmark_exclude.json").read_text())["bids"]) \
    if (PROC / "landmark_exclude.json").exists() else set()
ox, oy = crs.origin_world()
seen, floating, buried, nofaceid, total_tris = [], [], [], 0, 0
heights = {}
for k, t in T.items():
    td = PROC / "tiles" / k
    d = np.load(td / "mesh_buildings_lod1.npz")
    if not len(d["sizes"]):
        continue
    total_tris += int(np.maximum(d["sizes"] - 2, 0).sum())
    fb = d["f_bid"]
    nofaceid += int((fb <= 0).sum())
    # per-bid vertex z range via face corners
    corner_bid = np.repeat(fb, d["sizes"])
    cz = d["verts"][d["loops"], 2]
    u, inv = np.unique(corner_bid, return_inverse=True)
    zmin = np.full(len(u), np.inf)
    zmax = np.full(len(u), -np.inf)
    np.minimum.at(zmin, inv, cz)
    np.maximum.at(zmax, inv, cz)
    seen.append(u)
    ter = np.load(td / "mesh_terrain_lod1.npz")
    n = int(np.sqrt(len(ter["verts"])))
    samp = Sampler(ter["verts"][:, 2].reshape(n, n).astype(float), 500 / (n - 1))
    bl = gpd.read_parquet(td / "buildings.parquet").set_index("bid")
    cx, cy = t["offset_city"][0] + ox, t["offset_city"][1] + oy
    for b, lo, hi in zip(u, zmin, zmax):
        g = bl.geometry.loc[b]
        c = shapely.get_coordinates(g)
        gz = samp(c[:, 0] - cx, c[:, 1] - cy)
        if lo > gz.min() + 0.05:
            floating.append((k, int(b), round(float(lo - gz.min()), 2)))
        if hi < gz.max() + 1.0:
            buried.append((k, int(b), round(float(hi - gz.max()), 2)))
        heights[int(b)] = float(hi - np.mean(gz))
allb = np.concatenate(seen)
n_mesh = len(np.unique(allb))
check(len(allb) == n_mesh, "each building id appears in exactly one tile")
check(nofaceid == 0, f"every building face has a source id (missing: {nofaceid})")
dev = (n_mesh + len(excl) - src_city) / src_city
check(abs(dev) < 0.01, f"building count {n_mesh:,} (+{len(excl)} landmark-replaced) vs source in-city "
      f"{src_city:,}: {dev:+.3%}  [raw source incl. Daly City fringe: {rep['source_records']:,}]")
check(not floating, f"floating buildings: {len(floating)} {floating[:5]}")
check(not buried, f"buried buildings: {len(buried)} {buried[:5]}")

b = pd.read_parquet(PROC / "buildings_all.parquet", columns=["bid", "osm_name"])
for name, want, tol in (("Salesforce Tower", 326, 4), ("Transamerica Pyramid", 260, 4)):
    ids = b[b.osm_name == name].bid.tolist()
    if ids and ids[0] in excl:
        print(f"SKIP {name}: replaced by landmark geometry (checked in Phase 9)")
        continue
    h = max(heights.get(i, 0) for i in ids) if ids else 0
    check(abs(h - want) <= tol, f"{name} height above ground {h:.1f} m (expect ~{want})")
print(f"building LOD1 triangles: {total_tris:,}")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
