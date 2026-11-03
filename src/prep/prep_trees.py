"""Phase 3d: city-wide tree points (DataSF street trees + OSM natural=tree nodes, deduplicated).

Size from DBH (inches) via a simple urban allometry (clamped):
  height_m = 3 + 0.33 * dbh_in   (3..30 m), crown_r_m = 0.8 + 0.11 * dbh_in (0.8..9 m)
Missing DBH -> species-agnostic defaults (dbh 8 in).
Writes data/processed/trees_all.parquet + trees_report.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import osmium
import pandas as pd
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"


def genus_class(species: str) -> str:
    """Coarse visual class for instancing: palm / conifer / broadleaf."""
    s = (species or "").lower()
    if re.search(r"palm|phoenix|washingtonia|syagrus|trachycarpus|archontophoenix", s):
        return "palm"
    if re.search(r"pinus|cupressus|sequoia|cedrus|pine|cypress|redwood|araucaria|podocarpus|juniper", s):
        return "conifer"
    return "broadleaf"


def main() -> None:
    rep = {}
    t = pd.read_csv(ROOT / "data/raw/datasf/street_trees.csv",
                    usecols=["treeid", "species", "planttype", "mapdbh", "latitude", "longitude", "legalstatus"],
                    low_memory=False)
    rep["datasf_records"] = len(t)
    bad = t.latitude.isna() | t.longitude.isna() | ~t.latitude.between(37.6, 37.9)
    rep["datasf_dropped_no_coords"] = int(bad.sum())
    t = t[~bad]
    nt = t.planttype.fillna("Tree") != "Tree"
    rep["datasf_dropped_not_tree(landscaping)"] = int(nt.sum())
    t = t[~nt]
    dbh = pd.to_numeric(t.mapdbh, errors="coerce")
    dbh = dbh.where((dbh > 0) & (dbh < 120))
    rep["datasf_missing_dbh_defaulted"] = int(dbh.isna().sum())
    g1 = gpd.GeoDataFrame({"tree_id": "sf" + t.treeid.astype(str), "species": t.species.fillna(""),
                           "dbh_in": dbh.fillna(8.0).astype("float32"), "src": "datasf"},
                          geometry=gpd.points_from_xy(t.longitude, t.latitude), crs=4326).to_crs(26910)

    rows = []
    for o in osmium.FileProcessor(str(ROOT / "data/raw/osm/SanFrancisco.osm.pbf"), osmium.osm.NODE).with_filter(
            osmium.filter.TagFilter(("natural", "tree"))):
        rows.append((f"osm{o.id}", o.tags.get("species") or o.tags.get("genus") or o.tags.get("leaf_type", ""),
                     o.location.lon, o.location.lat))
    o = pd.DataFrame(rows, columns=["tree_id", "species", "lon", "lat"])
    g2 = gpd.GeoDataFrame({"tree_id": o.tree_id, "species": o.species, "dbh_in": np.float32(10.0), "src": "osm"},
                          geometry=gpd.points_from_xy(o.lon, o.lat), crs=4326).to_crs(26910)
    rep["osm_tree_nodes"] = len(g2)
    kd = cKDTree(np.c_[g1.geometry.x, g1.geometry.y])
    d, _ = kd.query(np.c_[g2.geometry.x, g2.geometry.y], k=1)
    g2 = g2[d > 3.0]
    rep["osm_after_dedupe_3m"] = len(g2)

    g = pd.concat([g1, g2], ignore_index=True)
    land = gpd.read_file(PROC / "boundary/sf_land.gpkg").union_all().buffer(30)
    inside = g.within(land)
    rep["dropped_outside_sf"] = int((~inside).sum())
    g = g[inside].copy()
    g["height_m"] = np.clip(3 + 0.33 * g.dbh_in, 3, 30).astype("float32")
    g["crown_r_m"] = np.clip(0.8 + 0.11 * g.dbh_in, 0.8, 9).astype("float32")
    g["vclass"] = g.species.map(genus_class)
    ox, oy = crs.origin_world()
    S = json.loads((PROC / "tile_index.json").read_text())["tile_size_m"]
    g["tile"] = [f"t{i:+03d}_{j:+03d}" for i, j in zip(np.floor((g.geometry.x - ox) / S).astype(int),
                                                          np.floor((g.geometry.y - oy) / S).astype(int))]
    g.to_parquet(PROC / "trees_all.parquet")
    rep["output_trees"] = len(g)
    rep["vclass"] = g.vclass.value_counts().to_dict()
    (PROC / "trees_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
