"""Generate data/processed/tile_index.json: regular grid over the city bbox + margin.

Tile (i, j) covers city-frame [i*S, (i+1)*S) x [j*S, (j+1)*S); the Ferry Building
(origin) sits on the corner shared by tiles (0,0), (-1,0), (0,-1), (-1,-1).
Tile ID: "t{i:+03d}_{j:+03d}" e.g. t-03_+01. Blender names use tileX_tileY = i_j.

Land/water classification is filled in after the SF boundary is fetched
(--boundary path); before that every tile has status "unclassified".

Usage: python src/prep/make_tile_grid.py [--boundary data/raw/.../boundary.gpkg]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402


def tile_id(i: int, j: int) -> str:
    return f"t{i:+03d}_{j:+03d}"


def build_grid(cfg: dict) -> dict:
    S = cfg["grid"]["tile_size_m"]
    m = cfg["grid"]["margin_m"]
    b = cfg["city_bbox_wgs84"]
    # project all 4 corners (UTM is not axis-aligned with lon/lat)
    lons = [b["west"], b["east"], b["east"], b["west"]]
    lats = [b["south"], b["south"], b["north"], b["north"]]
    cx, cy = crs.lonlat_to_city(lons, lats)
    xmin, xmax = cx.min() - m, cx.max() + m
    ymin, ymax = cy.min() - m, cy.max() + m
    i0, i1 = math.floor(xmin / S), math.ceil(xmax / S)
    j0, j1 = math.floor(ymin / S), math.ceil(ymax / S)

    pilot = cfg["pilot"]
    tiles = {}
    for i in range(i0, i1):
        for j in range(j0, j1):
            x0, y0 = i * S, j * S
            in_pilot = (x0 >= pilot["xmin"] and x0 + S <= pilot["xmax"]
                        and y0 >= pilot["ymin"] and y0 + S <= pilot["ymax"])
            tiles[tile_id(i, j)] = {
                "id": tile_id(i, j),
                "i": i, "j": j,
                "name": f"{i}_{j}",
                "bounds_city": [x0, y0, x0 + S, y0 + S],
                "offset_city": [x0 + S / 2, y0 + S / 2, 0.0],
                "neighbors": {
                    k: tile_id(i + di, j + dj)
                    for k, (di, dj) in {"E": (1, 0), "W": (-1, 0), "N": (0, 1), "S": (0, -1)}.items()
                    if i0 <= i + di < i1 and j0 <= j + dj < j1
                },
                "pilot": in_pilot,
                "status": "unclassified",
            }
    ox, oy = crs.origin_world()
    return {
        "crs": cfg["crs"],
        "origin": {**cfg["origin"], "world_xy": [ox, oy]},
        "tile_size_m": S,
        "i_range": [i0, i1], "j_range": [j0, j1],
        "extent_city": [i0 * S, j0 * S, i1 * S, j1 * S],
        "tiles": tiles,
    }


def classify(index: dict, boundary_path: Path) -> None:
    """Mark tiles land / water using the SF land boundary (shoreline-clipped)."""
    import geopandas as gpd
    from shapely.geometry import box

    S = index["tile_size_m"]
    g = gpd.read_file(boundary_path).to_crs(index["crs"])
    ox, oy = index["origin"]["world_xy"]
    land = g.geometry.union_all()
    for t in index["tiles"].values():
        x0, y0, x1, y1 = t["bounds_city"]
        cell = box(x0 + ox, y0 + oy, x1 + ox, y1 + oy)
        # include tiles within 150 m of land so shoreline/bathymetry/piers are built
        frac = cell.intersection(land).area / (S * S)
        near = cell.distance(land) < 150
        t["land_fraction"] = round(frac, 4)
        t["status"] = "build" if (frac > 0 or near) else "skip_water"
    # tiles crossed by major road bridges (Golden Gate, Bay Bridge spans) are built even over open water
    rp = boundary_path.parents[1] / "osm/roads.parquet"
    if rp.exists():
        r = gpd.read_parquet(rp)
        br = r[r.bridge.notna() & r.highway.isin(["motorway", "trunk", "primary"])]
        lines = br.geometry.union_all()
        for t in index["tiles"].values():
            x0, y0, x1, y1 = t["bounds_city"]
            if t["status"] != "build" and box(x0 + ox, y0 + oy, x1 + ox, y1 + oy).intersects(lines):
                t["status"] = "build"
                t["reason"] = "bridge"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boundary", type=Path)
    ap.add_argument("--out", type=Path, default=crs.ROOT / "data/processed/tile_index.json")
    a = ap.parse_args()
    idx = build_grid(crs.config())
    if a.boundary:
        classify(idx, a.boundary)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(idx, indent=1))
    n = len(idx["tiles"])
    npilot = sum(t["pilot"] for t in idx["tiles"].values())
    nbuild = sum(t["status"] == "build" for t in idx["tiles"].values())
    ext = idx["extent_city"]
    print(f"grid {idx['i_range']} x {idx['j_range']}: {n} tiles, pilot={npilot}, build={nbuild}")
    print(f"extent (city m): x {ext[0]}..{ext[2]}  y {ext[1]}..{ext[3]}  "
          f"= {(ext[2]-ext[0])/1000:.1f} x {(ext[3]-ext[1])/1000:.1f} km")
    print(f"origin world xy: {idx['origin']['world_xy']}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
