"""Phase 2: validate source coverage against the SF land boundary; render a coverage map."""
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import rasterio
from rasterio.enums import Resampling

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
RAW = ROOT / "data/raw"
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


man = json.loads((RAW / "fetch_manifest.json").read_text())
for k, v in man.items():
    print(f"  {k:24s} {v.get('bytes', 0) / 1e6:9.1f} MB  records={v.get('records', v.get('records_lines', '-'))}")

nb = gpd.read_file(RAW / "datasf/analysis_neighborhoods.geojson").to_crs(26910)
land = nb.union_all()
check(abs(land.area / 1e6 - 121.4) < 3, f"boundary land area {land.area / 1e6:.1f} km2 ~ 121.4")

# buildings
b = gpd.read_file(RAW / "datasf/building_footprints.geojson", columns=["sf16_bldgid", "hgt_median_m"])
b = b.to_crs(26910)
ox, oy = crs.origin_world()
check(len(b) == man["buildings"]["source_count"], f"buildings {len(b)} == source count")
cent = b.geometry.representative_point()
inmask = cent.within(land.buffer(50))
ys = cent.y - oy
print(f"INFO buildings outside SF boundary: {(~inmask).sum()} "
      f"(all south of county line: {bool((ys[~inmask] < -9700).all())}) -> dropped in prep")
check(bool((ys[~inmask] < -9700).all()), "every out-of-boundary building is Daly City/Brisbane fringe")
check(inmask.sum() > 170000, f"in-city buildings: {inmask.sum()}")
check(b.hgt_median_m.notna().mean() > 0.95, f"buildings with LiDAR height: {b.hgt_median_m.notna().mean():.4f}")

# trees
t = pd.read_csv(RAW / "datasf/street_trees.csv", usecols=["latitude", "longitude"], low_memory=False)
tv = t.dropna()
tv = tv[(tv.latitude > 37.6) & (tv.latitude < 37.9)]
print(f"INFO trees with valid coords: {len(tv)}/{len(t)} ({len(t) - len(tv)} lack lat/lon in source; dropped in prep)")
check(len(tv) / len(t) > 0.95, "tree coordinate coverage > 95%")
tg = gpd.GeoSeries(gpd.points_from_xy(tv.longitude, tv.latitude), crs=4326).to_crs(26910)

# OSM header bbox
import osmium  # noqa: E402

box = osmium.io.Reader(str(RAW / "osm/SanFrancisco.osm.pbf"), osmium.osm.osm_entity_bits.NOTHING).header().box()
bb = crs.config()["city_bbox_wgs84"]
osm_ok = (box.bottom_left.lon <= bb["west"] and box.bottom_left.lat <= bb["south"]
          and box.top_right.lon >= bb["east"] and box.top_right.lat >= bb["north"])
check(osm_ok, f"OSM extract bbox {box} covers city bbox")

# DEM coverage (decimated 20x)
idx = json.loads((ROOT / "data/processed/tile_index.json").read_text())
ox, oy = crs.origin_world()
x0, y0, x1, y1 = idx["extent_city"]
D = 20
cov = np.full(((y1 - y0) // D, (x1 - x0) // D), np.nan, np.float32)
for f in sorted((RAW / "dem/3dep1m").glob("*.tif")):
    with rasterio.open(f) as r:
        a = r.read(1, out_shape=(r.height // D, r.width // D), resampling=Resampling.nearest)
        a = np.where((a < -100) | (a > 1000), np.nan, a)
        c0 = int(round((r.bounds.left - ox - x0) / D))
        r0 = int(round((oy + y1 - r.bounds.top) / D))
        # clip chunk window to the grid (top row of chunks extends past y1)
        ar0, ac0 = max(0, -r0), max(0, -c0)
        r0, c0 = max(r0, 0), max(c0, 0)
        sub = cov[r0:r0 + a.shape[0] - ar0, c0:c0 + a.shape[1] - ac0]
        src = a[ar0:ar0 + sub.shape[0], ac0:ac0 + sub.shape[1]]
        sub[...] = np.where(np.isnan(sub), src, sub)
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.transform import from_origin  # noqa: E402

tr = from_origin(ox + x0, oy + y1, D, D)
landmask = ~geometry_mask([land], cov.shape, tr)
land_valid = np.isfinite(cov[landmask]).mean()
check(land_valid > 0.999, f"3DEP valid over land: {land_valid:.5f}")
with rasterio.open(RAW / "dem/ncei_topobathy_5m.tif") as r:
    n = r.read(1)
    nvalid = ((n > -200) & (n < 1000)).mean()
    nmin = float(n[(n > -200)].min())
check(nvalid > 0.99, f"NCEI topobathy valid over full extent: {nvalid:.4f} (min {nmin:.1f} m)")

# landmark ground sanity on 3DEP
cfg = crs.config()["landmarks_check"]
for k, v in cfg.items():
    if "ground_m" not in v:
        continue
    wx, wy = crs.lonlat_to_world(v["lon"], v["lat"])
    z = np.nan
    for f in (RAW / "dem/3dep1m").glob("*.tif"):
        with rasterio.open(f) as r:
            if r.bounds.left <= wx < r.bounds.right and r.bounds.bottom <= wy < r.bounds.top:
                rr, cc = r.index(float(wx), float(wy))
                win = r.read(1)[max(rr - 60, 0):rr + 61, max(cc - 60, 0):cc + 61]  # +-60 m: summit max
                z = float(win[(win > -100) & (win < 1000)].max()) if "peak" in k or "coit" in k or "davidson" in k \
                    else float(win[55:66, 55:66].mean())
                break
    lo, hi = v["ground_m"]
    check(lo - 5 <= z <= hi + 5, f"3DEP ground at {k}: {z:.1f} m (expect {lo}-{hi})")

# coverage map
fig, ax = plt.subplots(figsize=(12, 11.6), dpi=110)
ext = [x0, x1, y0, y1]
ax.imshow(cov, extent=ext, cmap="terrain", vmin=-20, vmax=300)
gpd.GeoSeries([land], crs=26910).translate(-ox, -oy).boundary.plot(ax=ax, color="k", lw=0.8)
cs = cent.sample(min(len(cent), 40000), random_state=0).translate(-ox, -oy)
ax.scatter(cs.x, cs.y, s=0.15, c="crimson", label="building centroids (40k sample)")
ts = tg.sample(20000, random_state=0).translate(-ox, -oy)
ax.scatter(ts.x, ts.y, s=0.15, c="green", label="street trees (20k sample)")
for tl in idx["tiles"].values():
    if tl["pilot"]:
        bx = tl["bounds_city"]
        ax.add_patch(plt.Rectangle((bx[0], bx[1]), 500, 500, fill=False, ec="blue", lw=0.6))
ax.set_title("Phase 2 coverage: 3DEP 1 m (decimated), SF land boundary, buildings, trees, pilot tiles (blue)")
ax.legend(loc="lower left", markerscale=20)
ax.set_xlabel("x east of Ferry Building (m)")
ax.set_ylabel("y north (m)")
out = ROOT / "renders/phase2_coverage.png"
fig.savefig(out, bbox_inches="tight")
print(f"wrote {out}")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
