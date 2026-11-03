"""Phase 5a: city-wide water surface levels (one level per OSM water polygon, so lakes that span
several tiles stay perfectly flat). Level = median DEM inside the polygon (LiDAR water returns are
flat at the surface). Tidal channels (median below sea+0.5) snap to sea level.
Writes data/processed/water_levels.json {osm_id: {"z": level, "kind": "lake"|"tidal", "name": ...}}
"""
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.mask import mask

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

PROC = crs.ROOT / "data/processed"
sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
w = gpd.read_parquet(PROC / "osm/water.parquet")
w = w[w.geom_type.isin(["Polygon", "MultiPolygon"])]
out = {}
with rasterio.open(PROC / "dem/dem_1m.tif") as r:
    for _, row in w.iterrows():
        g = row.geometry.buffer(-1.5)  # stay off the banks
        if g.is_empty:
            g = row.geometry
        try:
            a, _ = mask(r, [g], crop=True, nodata=np.nan)
        except ValueError:
            continue
        v = a[0][np.isfinite(a[0])]
        if v.size == 0:
            continue
        z = float(np.median(v))
        kind = "tidal" if (z < sea + 0.5 or row.water in ("river",) and z < sea + 1.5) else "lake"
        out[row.osm_id] = {"z": sea if kind == "tidal" else z + 0.05, "kind": kind, "name": row["name"],
                           "area_m2": round(row.geometry.area, 1)}
(PROC / "water_levels.json").write_text(json.dumps(out, indent=1))
for k, v in sorted(out.items(), key=lambda kv: -kv[1]["area_m2"])[:8]:
    print(f"  {str(v['name']):22s} {v['kind']:5s} z={v['z']:.2f}")
print(f"{len(out)} water levels")
