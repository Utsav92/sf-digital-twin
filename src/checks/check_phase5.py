"""Phase 5: water + land-use assertions."""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom.terrain import CLS  # noqa: E402

PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
T = {k: t for k, t in idx["tiles"].items() if t["status"] == "build"}
sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
inv = {v: k for k, v in CLS.items()}
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


import geopandas as gpd  # noqa: E402
import shapely  # noqa: E402

LAND = shapely.union_all(gpd.read_file(PROC / "boundary/sf_land.gpkg").geometry.values)
OX, OY = crs.origin_world()
hist = np.zeros(len(CLS), np.int64)
need_water, have_water = 0, 0
for k in T:
    d = np.load(PROC / "tiles" / k / "mesh_terrain_lod1.npz")
    hist += np.bincount(d["f_cls"], minlength=len(CLS))
    w = np.load(PROC / "tiles" / k / "mesh_water_lod1.npz")
    low = d["verts"][d["verts"][:, 2] < sea - 0.5]
    if len(low):
        ox_, oy_ = T[k]["offset_city"][:2]
        offshore = ~shapely.contains_xy(LAND, low[:, 0] + ox_ + OX, low[:, 1] + oy_ + OY)
        if offshore.any():  # below-sea terrain outside the land polygon must be covered by water
            need_water += 1
            have_water += len(w["sizes"]) > 0
check(need_water == have_water, f"tiles with offshore below-sea terrain have water: {have_water}/{need_water} "
      "(inland pits e.g. Transit Center excavation intentionally stay dry)")
frac = hist / hist.sum()
print("surface classes:", {inv[i]: round(float(f), 4) for i, f in enumerate(frac) if f > 0.001})


def face_class(lon, lat):
    x, y = (float(v) for v in crs.lonlat_to_city(lon, lat))
    i, j = int(np.floor(x / 500)), int(np.floor(y / 500))
    k = f"t{i:+03d}_{j:+03d}"
    d = np.load(PROC / "tiles" / k / "mesh_terrain_lod1.npz")
    n = int(np.sqrt(len(d["sizes"])))
    st = 500 / n
    c, r = int((x - i * 500) / st), int((y - j * 500) / st)
    return inv[int(d["f_cls"][r * n + c])]


probes = {"Golden Gate Park meadow": (-122.4660, 37.7697, {"park", "grass", "sport"}),
          "Presidio forest": (-122.4600, 37.7930, {"forest", "park", "scrub", "golf", "grass"}),
          "Ocean Beach sand": (-122.5105, 37.7600, {"beach"}),
          "Lincoln Park golf": (-122.4985, 37.7840, {"golf"}),
          "McLaren Park": (-122.4200, 37.7190, {"park", "forest", "scrub", "grass"}),
          "Bay off Ferry Bldg": (-122.3880, 37.7970, {"seabed"})}
for n, (lo, la, ok) in probes.items():
    c = face_class(lo, la)
    check(c in ok, f"land use at {n}: {c}")

# lakes sit above their carved beds
lv = json.loads((PROC / "water_levels.json").read_text())
merced = [v for v in lv.values() if v["name"] == "Lake Merced"][0]
check(3 < merced["z"] < 8, f"Lake Merced surface {merced['z']:.2f} m NAVD88")
from geom.terrain import Sampler  # noqa: E402

wpoly = gpd.read_parquet(PROC / "osm/water.parquet")
wpoly = wpoly[wpoly.osm_id.isin(lv)]
worst = 0.0
for oid, g in zip(wpoly.osm_id, wpoly.geometry):
    gi = g.buffer(-3)  # interior: 3 m from the shore
    if gi.is_empty:
        continue
    x0, y0, x1, y1 = gi.bounds
    X, Y = np.meshgrid(np.arange(x0, x1, 4), np.arange(y0, y1, 4))
    m = shapely.contains_xy(gi, X, Y)
    px, py = X[m] - OX, Y[m] - OY
    if not len(px):
        continue
    above = 0
    for i, j in {(int(np.floor(a / 500)), int(np.floor(b / 500))) for a, b in zip(px, py)}:
        k = f"t{i:+03d}_{j:+03d}"
        d = np.load(PROC / "tiles" / k / "mesh_terrain_lod1.npz")
        n = int(np.sqrt(len(d["verts"])))
        samp = Sampler(d["verts"][:, 2].reshape(n, n).astype(float), 500 / (n - 1))
        sel = (np.floor(px / 500) == i) & (np.floor(py / 500) == j)
        z = samp(px[sel] - T[k]["offset_city"][0], py[sel] - T[k]["offset_city"][1])
        above += int((z > lv[oid]["z"]).sum())
    worst = max(worst, above / len(px))
check(worst < 0.01, f"lake interiors free of terrain poke-through (worst lake {worst:.3%})")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
