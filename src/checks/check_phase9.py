"""Phase 9: landmark assertions (heights measured from the generated meshes, absolute NAVD88)."""
import json, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa
PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
fails = []
def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok: fails.append(msg)
rep = json.loads((PROC / "landmarks_report.json").read_text())
sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
V = []
for k in rep["tiles"]:
    d = np.load(PROC / "tiles" / k / "mesh_landmarks_lod1.npz")
    V.append(d["verts"] + np.array(idx["tiles"][k]["offset_city"], np.float32))
V = np.concatenate(V)
from prep.prep_bridges import dem_sampler
g = dem_sampler(); ox, oy = crs.origin_world()
def top_near(lon, lat, r):
    x, y = (float(v) for v in crs.lonlat_to_city(lon, lat))
    m = np.hypot(V[:, 0] - x, V[:, 1] - y) < r
    gz = float(g(np.array([x + ox]), np.array([y + oy]))[0])
    return float(V[m, 2].max()) - gz if m.any() else -1, gz
for name, lon, lat, r, want, tol in [("Salesforce Tower", -122.39694, 37.78977, 40, 326, 3),
                                     ("Transamerica Pyramid", -122.40278, 37.79519, 40, 260, 3),
                                     ("Coit Tower", -122.40584, 37.80239, 15, 64, 3),
                                     ("City Hall dome", -122.41924, 37.77927, 30, 94, 4),
                                     ("Sutro Tower", -122.45276, 37.75523, 50, 298, 4)]:
    h, gz = top_near(lon, lat, r)
    check(abs(h - want) <= tol, f"{name}: top {h:.1f} m above ground (published {want})")
x, y = (float(v) for v in crs.lonlat_to_city(-122.47736, 37.81074))
m = np.hypot(V[:, 0] - x, V[:, 1] - y) < 80
check(abs(V[m, 2].max() - sea - 227) < 5, f"Golden Gate south tower {V[m, 2].max() - sea:.1f} m above water (227)")
check(rep.get("pieces_outside_built_tiles", 0) == 0, "all landmark pieces inside built tiles")
check(rep["excluded_buildings"] > 0, f"generic extrusions retired under landmarks: {rep['excluded_buildings']}")
print(f"\n{len(fails)} failure(s)"); sys.exit(1 if fails else 0)
