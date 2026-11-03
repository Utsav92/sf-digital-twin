"""Phase 6: roads + rail assertions.
- road/rail surfaces above the (sunk) terrain at every triangle centroid (sampled bilinearly)
- bridge decks: never below terrain; Golden Gate deck ~67-77 m; Bay Bridge W span upper deck 55-75 m
- class/system coverage: motorway, arterial, local, sidewalk present; cable car + Muni + Caltrain track
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom import roadclass as rc  # noqa: E402
from geom.terrain import Sampler  # noqa: E402

PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
T = {k: t for k, t in idx["tiles"].items() if t["status"] == "build"}
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


below, total, cls_tris, bad_tiles = 0, 0, np.zeros(9, np.int64), []
rail_tris = np.zeros(3, np.int64)
for k in T:
    td = PROC / "tiles" / k
    ter = np.load(td / "mesh_terrain_lod1.npz")
    n = int(np.sqrt(len(ter["verts"])))
    samp = Sampler(ter["verts"][:, 2].reshape(n, n).astype(float), 500 / (n - 1))
    for layer in ("roads", "rail"):
        d = np.load(td / f"mesh_{layer}_lod1.npz")
        if not len(d["sizes"]):
            continue
        tri = d["sizes"] == 3
        if layer == "roads":
            cls_tris += np.bincount(d["f_mat"], minlength=9)
        else:
            rail_tris += np.bincount(d["f_mat"], minlength=3)
        # ground surfaces only (bridge decks/supports are checked separately)
        ground = tri & (d["f_mat"] < (rc.BRIDGE_DECK if layer == "roads" else 2))
        if layer == "roads":
            ground |= tri & (d["f_mat"] == rc.PIER)
        starts = np.r_[0, np.cumsum(d["sizes"])[:-1]]
        idx3 = starts[ground][:, None] + np.arange(3)
        if not len(idx3):
            continue
        cen = d["verts"][d["loops"][idx3]].mean(1)
        z = samp(cen[:, 0], cen[:, 1])
        bl = int((cen[:, 2] < z - 0.02).sum())
        below += bl
        total += len(cen)
        if bl > 0.002 * len(cen):
            bad_tiles.append((k, layer, bl, len(cen)))
check(below / max(total, 1) < 0.001, f"road/rail surface triangles below terrain: {below}/{total} "
      f"({below / max(total, 1):.4%}); tiles over 0.2%: {bad_tiles[:5]}")
names = ["motorway", "arterial", "local", "service", "path", "sidewalk", "bridge_deck", "bridge_struct", "pier"]
print("road triangles by class:", dict(zip(names, cls_tris.tolist())))
print("rail triangles (track, embedded, bridge):", rail_tris.tolist())
check(all(cls_tris[[0, 1, 2, 5, 6]] > 0), "motorway, arterial, local, sidewalk, bridge deck all present")

b = gpd.read_parquet(PROC / "bridges3d.parquet")
lowest = 0.0
for r in b.itertuples():
    C = np.frombuffer(r.center, np.float64).reshape(-1, 3)
    g = np.frombuffer(r.ground, np.float64)
    lowest = min(lowest, float((C[:, 2] - g).min()))
check(lowest >= 0.0, f"bridge decks never below terrain (min clearance {lowest:.2f} m)")


def deck_max(name):
    m = b[b.name.fillna("").str.contains(name)]
    return max(np.frombuffer(c, np.float64).reshape(-1, 3)[:, 2].max() for c in m.center) if len(m) else np.nan


ggb = deck_max("Golden Gate Bridge")
check(65 <= ggb <= 80, f"Golden Gate Bridge deck max {ggb:.1f} m NAVD88 (real ~67-75)")
bb = deck_max("Eisenhower")
check(55 <= bb <= 75, f"Bay Bridge deck max {bb:.1f} m NAVD88 (real upper deck ~ 60-70)")

rail = gpd.read_parquet(PROC / "osm/rail.parquet")
for s in ("cable_car", "muni_metro", "caltrain"):
    check((rail.system == s).any(), f"rail system {s} present ({(rail.system == s).sum()} ways)")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
