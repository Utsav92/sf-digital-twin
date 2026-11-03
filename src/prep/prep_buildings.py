"""Phase 3c: city-wide building table with resolved heights + tile assignment.

Source of footprints: DataSF Building Footprints (2010 LiDAR attributes, footprints current to 2023).
Height policy (height_source column):
  1 osm_tall     : OSM explicit height and max(osm, lidar) > 40 m           (towers; OSM is current/curated)
  2 osm_new      : LiDAR stale (hgt < 2.5 m, or OSM > 1.5x and +10 m)  -> OSM height / levels*3.2
  3 lidar        : DataSF hgt_median_m (median first-return height above ground)
  4 lidar_small  : stale, no OSM, footprint < 60 m2 (shed/garage) -> max(lidar, 3 m)
  5 nbhd_median  : stale, no OSM, larger -> analysis-neighborhood median of lidar heights
Tile assignment: tile containing the footprint's representative point (exactly one tile).
Writes data/processed/buildings_all.parquet (EPSG:26910) + buildings_report.json
"""
from __future__ import annotations

import json
import math
import re
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"
LEVEL_M = 3.2


def parse_m(v) -> float:
    """'12', '12 m', '40 ft', "12'6\"" -> meters (nan if unparsable)."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return np.nan
    s = str(v).strip().lower().replace(",", ".")
    m = re.match(r"^([\d.]+)\s*(m|ft|feet|')?", s)
    if not m:
        return np.nan
    x = float(m.group(1))
    return x * 0.3048 if m.group(2) in ("ft", "feet", "'") else x


def main() -> None:
    t0 = time.time()
    rep = {}
    b = gpd.read_file(ROOT / "data/raw/datasf/building_footprints.geojson",
                      columns=["sf16_bldgid", "gnd_min_m", "hgt_median_m", "median_1st_m", "peak_1st_m"])
    b = b.to_crs(26910)
    for c in ("gnd_min_m", "hgt_median_m", "median_1st_m", "peak_1st_m"):
        b[c] = pd.to_numeric(b[c], errors="coerce")
    rep["source_records"] = len(b)

    inval = ~b.is_valid
    b.loc[inval, "geometry"] = shapely.make_valid(b.geometry[inval].values)
    # make_valid may yield GeometryCollections: keep polygonal parts only
    b["geometry"] = b.geometry.apply(lambda g: g if g.geom_type in ("Polygon", "MultiPolygon")
                                     else shapely.union_all([p for p in getattr(g, "geoms", [])
                                                             if p.geom_type in ("Polygon", "MultiPolygon")]))
    rep["repaired_invalid"] = int(inval.sum())
    empty = b.geometry.is_empty | (b.area < 1.0)
    rep["dropped_empty_or_<1m2"] = int(empty.sum())
    b = b[~empty].copy()

    land = gpd.read_file(PROC / "boundary/sf_land.gpkg")
    nb = land[land.src == "datasf_neighborhoods"]
    rp = b.geometry.representative_point()
    inside = rp.within(land.union_all().buffer(50))
    rep["dropped_outside_sf"] = int((~inside).sum())
    b, rp = b[inside].copy(), rp[inside]
    b["rx"], b["ry"] = rp.x, rp.y

    # neighborhood of each building
    j = gpd.sjoin(gpd.GeoDataFrame(geometry=rp, crs=26910), nb[["name", "geometry"]], how="left",
                  predicate="within")
    b["nhood"] = j.groupby(level=0)["name"].first().reindex(b.index).fillna("unknown")

    # ---- OSM join: largest-overlap OSM building (non-part) per footprint
    o = gpd.read_parquet(PROC / "osm/buildings_osm.parquet")
    o = o[o.part.isna() & o.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    o["h_osm"] = o.height.map(parse_m)
    o["lv_osm"] = pd.to_numeric(o.levels, errors="coerce")
    o = o[o.h_osm.notna() | o.lv_osm.notna()]
    pairs = gpd.sjoin(b[["geometry"]], o[["geometry"]], how="inner", predicate="intersects")
    ia = pairs.index.values
    ib = pairs["index_right"].values
    inter = shapely.area(shapely.intersection(b.geometry.loc[ia].values, o.geometry.loc[ib].values))
    pairs = pd.DataFrame({"b": ia, "o": ib, "ov": inter})
    pairs["frac"] = pairs.ov / b.area.loc[pairs.b].values
    best = pairs.sort_values("ov", ascending=False).drop_duplicates("b")
    best = best[best.frac > 0.5]
    b["h_osm"] = np.nan
    b["lv_osm"] = np.nan
    b.loc[best.b.values, "h_osm"] = o.h_osm.loc[best.o].values
    b.loc[best.b.values, "lv_osm"] = o.lv_osm.loc[best.o].values
    b["osm_name"] = None
    b.loc[best.b.values, "osm_name"] = o.name.loc[best.o].values
    rep["osm_matched"] = int(len(best))

    # ---- height policy
    hl = b.hgt_median_m
    ho = b.h_osm.where(b.h_osm.notna(), b.lv_osm * LEVEL_M)
    tall = b.h_osm.notna() & (np.fmax(b.h_osm, hl) > 40)
    stale = (hl < 2.5) | (ho.notna() & (ho > 1.5 * hl) & (ho - hl > 10))
    small = b.area < 60  # sheds/carports/garages: low LiDAR height is real, don't inflate to a house
    src = np.select([tall, stale & ho.notna(), ~stale, small], ["osm_tall", "osm_new", "lidar", "lidar_small"],
                    "nbhd_median")
    b["height_source"] = src
    med = b[b.height_source == "lidar"].groupby("nhood").hgt_median_m.median()
    h = np.select([src == "osm_tall", src == "osm_new", src == "lidar", src == "lidar_small"],
                  [b.h_osm, ho, hl, np.fmax(hl, 3.0)],
                  b.nhood.map(med).fillna(med.median()))
    b["height_m"] = np.clip(h, 2.5, 400).astype("float32")
    # LiDAR roof relief (peak - median absolute first return) -> roof shape hint for LOD1
    b["roof_relief_m"] = (b.peak_1st_m - b.median_1st_m).clip(lower=0).astype("float32")
    rep["height_source"] = b.height_source.value_counts().to_dict()

    # ---- tile assignment by representative point
    idx = json.loads((PROC / "tile_index.json").read_text())
    S = idx["tile_size_m"]
    ox, oy = crs.origin_world()
    ti = np.floor((b.rx - ox) / S).astype(int)
    tj = np.floor((b.ry - oy) / S).astype(int)
    b["tile"] = [f"t{i:+03d}_{j:+03d}" for i, j in zip(ti, tj)]
    missing = ~b.tile.isin([k for k, t in idx["tiles"].items() if t["status"] == "build"])
    rep["in_non_build_tile"] = int(missing.sum())
    assert missing.sum() == 0, "buildings landed in skipped tiles"

    b = b.sort_values(["tile", "sf16_bldgid"]).reset_index(drop=True)
    b["bid"] = np.arange(1, len(b) + 1, dtype=np.int32)  # global int id, stored per face in Blender
    keep = ["bid", "sf16_bldgid", "tile", "nhood", "height_m", "height_source", "hgt_median_m", "h_osm",
            "lv_osm", "osm_name", "roof_relief_m", "gnd_min_m", "geometry"]
    b[keep].to_parquet(PROC / "buildings_all.parquet")
    rep["output_buildings"] = len(b)
    rep["seconds"] = round(time.time() - t0, 1)
    (PROC / "buildings_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))
    for n in ("Salesforce Tower", "Transamerica Pyramid", "181 Fremont", "Millennium Tower"):
        r = b[b.osm_name.fillna("").str.contains(n)]
        print(f"  {n:22s}", r[["height_m", "height_source", "hgt_median_m", "h_osm"]].round(1).values.tolist()[:3])


if __name__ == "__main__":
    main()
