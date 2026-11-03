"""Phase 1 assertions: config, CRS, tile grid, Blender sanity outputs. Exit 1 on any failure."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs

ROOT = crs.ROOT
fails = []
def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok: fails.append(msg)

cfg = crs.config()
check(cfg["crs"] == "EPSG:26910", "CRS is EPSG:26910")
ox, oy = crs.origin_world()
check(553000 < ox < 554000 and 4183000 < oy < 4184000, f"origin UTM plausible ({ox:.1f}, {oy:.1f})")
x, y = crs.lonlat_to_city(cfg["origin"]["lon"], cfg["origin"]["lat"])
check(abs(float(x)) < 1e-6 and abs(float(y)) < 1e-6, "origin maps to (0,0)")
lo, la = crs.city_to_lonlat(-4738.8, -4589.6)
check(abs(float(la) - 37.75444) < 1e-4, "Twin Peaks round trip")

idx = json.loads((ROOT / "data/processed/tile_index.json").read_text())
T = idx["tiles"]; S = idx["tile_size_m"]
check(len(T) > 0, f"{len(T)} tiles")
ids = set(T)
check(all(n in ids for t in T.values() for n in t["neighbors"].values()), "all neighbor ids exist")
check(all(T[t["neighbors"]["E"]]["neighbors"]["W"] == t["id"] for t in T.values() if "E" in t["neighbors"]),
      "E/W neighbor symmetry")
area = sum((t["bounds_city"][2]-t["bounds_city"][0])*(t["bounds_city"][3]-t["bounds_city"][1]) for t in T.values())
e = idx["extent_city"]
check(abs(area - (e[2]-e[0])*(e[3]-e[1])) < 1, "tiles exactly cover extent (no gaps/overlaps)")
check(sum(t["pilot"] for t in T.values()) == 16, "pilot = 16 tiles (2x2 km)")
b = cfg["city_bbox_wgs84"]
cx, cy = crs.lonlat_to_city([b["west"], b["east"]], [b["south"], b["north"]])
check(e[0] <= cx.min() and e[2] >= cx.max() and e[1] <= cy.min() and e[3] >= cy.max(), "extent covers city bbox")
for k, v in cfg["landmarks_check"].items():
    lx, ly = crs.lonlat_to_city(v["lon"], v["lat"])
    check(e[0] < lx < e[2] and e[1] < ly < e[3], f"landmark {k} inside grid")

png = ROOT / "renders/phase1_test_cube.png"
check(png.exists() and png.stat().st_size > 10_000, "test render exists")
check((ROOT / "out/tiles/phase1_test.blend").exists(), "test .blend saved")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
