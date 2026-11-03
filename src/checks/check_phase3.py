"""Phase 3 assertions over prepped tiles (all 'build' tiles that have prep.json, or --pilot)."""
import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

PROC = crs.ROOT / "data/processed"
ap = argparse.ArgumentParser()
ap.add_argument("--pilot", action="store_true")
a = ap.parse_args()
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


idx = json.loads((PROC / "tile_index.json").read_text())
T = {k: t for k, t in idx["tiles"].items() if t["status"] == "build" and (t["pilot"] or not a.pilot)}
missing = [k for k in T if not (PROC / "tiles" / k / "prep.json").exists()]
check(not missing, f"prep.json for all {len(T)} selected tiles (missing {len(missing)})")


def lat(k, lod):
    with rasterio.open(PROC / "tiles" / k / f"terrain_{lod}.tif") as r:
        return np.flipud(r.read(1))  # row 0 = south


bad_seams, n_seams, max_jump = 0, 0, 0.0
for k, t in T.items():
    for lod in ("lod1", "lod0"):
        z = lat(k, lod)
        if not np.isfinite(z).all():
            fails.append(f"{k} {lod} has NaN")
        for d, (mine, theirs) in {"E": (np.s_[:, -1], np.s_[:, 0]), "N": (np.s_[-1, :], np.s_[0, :])}.items():
            nb = t["neighbors"].get(d)
            if nb in T:
                n_seams += 1
                e1, e2 = z[mine], lat(nb, lod)[theirs]
                if not np.array_equal(e1, e2):
                    bad_seams += 1
                max_jump = max(max_jump, float(np.abs(e1 - e2).max()))
check(bad_seams == 0, f"terrain seams bit-identical: {n_seams - bad_seams}/{n_seams} (max diff {max_jump})")

ball = pd.read_parquet(PROC / "buildings_all.parquet", columns=["bid", "tile"])
ball = ball[ball.tile.isin(T)]
per = [pd.read_parquet(PROC / "tiles" / k / "buildings.parquet", columns=["bid"]) for k in T]
bids = np.concatenate([p.bid.values for p in per]) if per else np.array([])
check(len(bids) == len(ball), f"buildings in tiles {len(bids)} == assigned {len(ball)}")
check(len(np.unique(bids)) == len(bids), "each building in exactly one tile")

# landmark ground on the 2 m lattice
ox, oy = crs.origin_world()
for name, v in crs.config()["landmarks_check"].items():
    if "ground_m" not in v:
        continue
    x, y = crs.lonlat_to_city(v["lon"], v["lat"])
    i, j = int(np.floor(float(x) / 500)), int(np.floor(float(y) / 500))
    k = f"t{i:+03d}_{j:+03d}"
    if k not in T:
        continue
    z = lat(k, "lod1")
    c, r = (float(x) - i * 500) / 2, (float(y) - j * 500) / 2
    win = z[max(int(r) - 15, 0):int(r) + 16, max(int(c) - 15, 0):int(c) + 16]
    val = float(win.max()) if ("peak" in name or "davidson" in name or "coit" in name) else float(z[round(r), round(c)])
    lo, hi = v["ground_m"]
    check(lo - 1 <= val <= hi + 1, f"lattice ground {name}: {val:.1f} m (expect {lo}-{hi})")

tot = {}
for k in T:
    r = json.loads((PROC / "tiles" / k / "prep.json").read_text())
    for kk, vv in r["counts"].items():
        if isinstance(vv, int):
            tot[kk] = tot.get(kk, 0) + vv
print("totals:", tot)
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
