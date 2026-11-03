"""Phase 3b: land mask + merged 1 m topobathy DEM over the full grid extent.

- land mask = DataSF analysis neighborhoods (shoreline-clipped) U OSM islands (Alcatraz, YBI, ...)
- z = 3DEP 1 m where land (mask buffered 30 m, or 3DEP > 1 m: Marin/Daly City context)
      NOAA NCEI topobathy elsewhere, linearly blended over a 40 m band offshore
- writes data/processed/boundary/sf_land.gpkg, data/processed/dem/dem_1m.tif (+ hillshade preview)
Pixel grid: pixel edges at integer city-frame meters (3DEP chunks were requested on that grid).
"""
from __future__ import annotations

import glob
import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"
SEA_LEVEL = 0.95  # m NAVD88, mean sea level at SF tide gauge 9414290
BLEND_M = 40.0


def land_polygons() -> gpd.GeoDataFrame:
    nb = gpd.read_file(ROOT / "data/raw/datasf/analysis_neighborhoods.geojson").to_crs(26910)
    isl = gpd.read_parquet(PROC / "osm/islands.parquet")
    isl = isl[isl.area > 500]  # drop wash rocks
    parts = [nb[["geometry"]].assign(src="datasf_neighborhoods", name=nb.nhood),
             isl[["geometry"]].assign(src="osm_island", name=isl.name)]
    g = gpd.GeoDataFrame(np.concatenate([p.values for p in parts]), columns=["geometry", "src", "name"],
                         geometry="geometry", crs=26910)
    out = PROC / "boundary/sf_land.gpkg"
    out.parent.mkdir(parents=True, exist_ok=True)
    g.to_file(out, driver="GPKG")
    print(f"land polygons: {len(g)} ({(g.src == 'osm_island').sum()} islands), "
          f"union area {g.union_all().area / 1e6:.2f} km2 -> {out}")
    return g


def main() -> None:
    t0 = time.time()
    idx = json.loads((PROC / "tile_index.json").read_text())
    ox, oy = crs.origin_world()
    x0, y0, x1, y1 = idx["extent_city"]
    W, H = x1 - x0, y1 - y0
    tr = from_origin(ox + x0, oy + y1, 1.0, 1.0)
    prof = dict(driver="GTiff", width=W, height=H, count=1, crs="EPSG:26910", transform=tr, dtype="float32",
                tiled=True, blockxsize=512, blockysize=512, compress="deflate", predictor=3, nodata=np.nan)

    land = land_polygons()
    # 3DEP mosaic
    dep = np.full((H, W), np.nan, np.float32)
    for f in sorted(glob.glob(str(ROOT / "data/raw/dem/3dep1m/*.tif"))):
        with rasterio.open(f) as r:
            a = r.read(1)
            a[(a < -200) | (a > 1000)] = np.nan
            c0 = int(round(r.bounds.left - (ox + x0)))
            r0 = int(round((oy + y1) - r.bounds.top))
            ar0, ac0 = max(0, -r0), max(0, -c0)
            r0, c0 = max(r0, 0), max(c0, 0)
            sub = dep[r0:r0 + a.shape[0] - ar0, c0:c0 + a.shape[1] - ac0]
            src = a[ar0:ar0 + sub.shape[0], ac0:ac0 + sub.shape[1]]
            np.copyto(sub, src, where=np.isnan(sub))
    print(f"3DEP mosaic: valid {np.isfinite(dep).mean():.4f}")

    # NCEI resampled to the 1 m grid
    ncei = np.full((H, W), np.nan, np.float32)
    with rasterio.open(ROOT / "data/raw/dem/ncei_topobathy_5m.tif") as r:
        reproject(rasterio.band(r, 1), ncei, dst_transform=tr, dst_crs="EPSG:26910",
                  resampling=Resampling.bilinear, src_nodata=None, dst_nodata=np.nan)
    ncei[(ncei < -300) | (ncei > 1000)] = np.nan
    print(f"NCEI on 1 m grid: valid {np.isfinite(ncei).mean():.4f}")

    # land mask (SF land buffered 30 m, or 3DEP clearly above water)
    lm = rasterize([(g, 1) for g in land.buffer(30).geometry], out_shape=(H, W), transform=tr,
                   dtype="uint8").astype(bool)
    lm |= np.nan_to_num(dep, nan=-99) > 1.0
    # distance offshore (m) computed at 4 m and upsampled -> blend weight for NCEI
    D = 4
    small = lm[::D, ::D]
    dist = ndimage.distance_transform_edt(~small) * D
    dist = np.repeat(np.repeat(dist, D, 0), D, 1)[:H, :W]
    alpha = np.clip(dist / BLEND_M, 0, 1).astype(np.float32)  # 0 on land -> 1 offshore
    alpha[np.isnan(dep)] = 1.0
    z = np.where(np.isnan(ncei), dep, (1 - alpha) * np.nan_to_num(dep) + alpha * ncei)
    z = np.where(np.isnan(z), dep, z)
    holes = np.isnan(z)
    if holes.any():  # nearest-neighbour fill of any residual nodata
        ind = ndimage.distance_transform_edt(holes, return_distances=False, return_indices=True)
        z = z[tuple(ind)]
    print(f"merged: holes filled {int(holes.sum())}, z range {np.nanmin(z):.1f}..{np.nanmax(z):.1f}")

    out = PROC / "dem/dem_1m.tif"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.tif")
    with rasterio.open(tmp, "w", **prof) as w:
        w.write(z.astype(np.float32), 1)
        w.update_tags(sea_level_navd88=SEA_LEVEL, sources="USGS 3DEP 1m (land), NOAA NCEI DEM_all (water)",
                      frame="pixel edges on integer city-frame meters; origin Ferry Building")
    tmp.replace(out)
    with rasterio.open(PROC / "dem/landmask_1m.tif", "w", **{**prof, "dtype": "uint8", "nodata": None,
                                                              "predictor": 1}) as w:
        w.write(lm.astype(np.uint8), 1)
    meta = {"sea_level_navd88": SEA_LEVEL, "blend_m": BLEND_M, "shape": [H, W],
            "extent_city": idx["extent_city"], "seconds": round(time.time() - t0, 1)}
    (PROC / "dem/dem_meta.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {out} in {meta['seconds']} s")


if __name__ == "__main__":
    main()
