"""Phase 3a: OSM .pbf -> per-layer GeoParquet (EPSG:26910), clipped to the grid extent.

Layers: roads, rail, water, landuse, piers, bridges_area, islands, buildings_osm, coastline
python src/prep/osm_extract.py
"""
from __future__ import annotations

import json
import sys
import time
from collections import Counter
from pathlib import Path

import geopandas as gpd
import osmium
import shapely
from shapely import wkb

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PBF = ROOT / "data/raw/osm/SanFrancisco.osm.pbf"
OUT = ROOT / "data/processed/osm"

ROAD_KEEP = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
             "secondary_link", "tertiary", "tertiary_link", "residential", "unclassified", "living_street",
             "service", "pedestrian", "footway", "path", "cycleway", "steps", "track"}
RAIL_KEEP = {"rail", "light_rail", "subway", "tram", "narrow_gauge", "funicular", "monorail"}
LANDUSE_TAGS = {
    "leisure": {"park", "garden", "golf_course", "pitch", "playground", "nature_reserve", "recreation_ground",
                "stadium", "track", "dog_park"},
    "landuse": {"grass", "forest", "meadow", "cemetery", "recreation_ground", "residential", "commercial",
                "retail", "industrial", "railway", "construction", "military", "village_green", "brownfield",
                "allotments", "flowerbed", "religious", "education", "port"},
    "natural": {"wood", "scrub", "grassland", "beach", "sand", "heath", "bare_rock", "wetland", "scree"},
    "amenity": {"parking", "university", "school", "hospital"},
}
ROAD_TAGS = ("highway", "name", "lanes", "width", "bridge", "tunnel", "layer", "oneway", "sidewalk", "ref", "footway",
             "surface", "bridge:name", "level", "man_made", "parking:lane:both", "parking:both",
             "covered", "level", "service", "area")
RAIL_TAGS = ("railway", "name", "bridge", "tunnel", "layer", "bridge:name", "covered", "service", "usage", "gauge", "electrified", "operator")


def route_systems() -> dict[int, str]:
    """way id -> transit system, from OSM route relations (cable cars are railway=tram ways that
    belong to '... Cable Car' route relations)."""
    sysmap: dict[int, str] = {}
    prio = {"cable_car": 0, "bart": 1, "caltrain": 2, "muni_metro": 3, "muni_streetcar": 4, "other": 5}
    for r in osmium.FileProcessor(str(PBF), osmium.osm.RELATION).with_filter(
            osmium.filter.TagFilter(("type", "route"))):
        rt, name = r.tags.get("route"), r.tags.get("name", "")
        net = (r.tags.get("network", "") + r.tags.get("operator", "")).lower()
        if rt not in ("tram", "light_rail", "subway", "train", "cable_car", "funicular"):
            continue
        if "cable car" in name.lower() or rt == "cable_car":
            s = "cable_car"
        elif "bart" in name.lower() or "bart" in net:
            s = "bart"
        elif "caltrain" in net or (rt == "train" and name in ("Local", "Limited", "Express", "Local Weekend",
                                                               "Baby Bullet", "Weekend")):
            s = "caltrain"
        elif "muni metro" in name.lower():
            s = "muni_metro"
        elif "streetcar" in name.lower():
            s = "muni_streetcar"
        else:
            s = "other"
        for m in r.members:
            if m.type == "w" and prio[s] < prio.get(sysmap.get(m.ref, "other"), 9):
                sysmap[m.ref] = s
            elif m.type == "w":
                sysmap.setdefault(m.ref, s)
    return sysmap


def main() -> None:
    t0 = time.time()
    sysmap = route_systems()
    idx = json.loads((ROOT / "data/processed/tile_index.json").read_text())
    ox, oy = crs.origin_world()
    x0, y0, x1, y1 = idx["extent_city"]
    lon0, lat0 = crs.world_to_lonlat(ox + x0 - 500, oy + y0 - 500)
    lon1, lat1 = crs.world_to_lonlat(ox + x1 + 500, oy + y1 + 500)
    clipbox = shapely.box(ox + x0, oy + y0, ox + x1, oy + y1)

    layers: dict[str, list] = {k: [] for k in
                               ("roads", "rail", "water", "landuse", "piers", "bridges_area", "islands",
                                "buildings_osm", "coastline")}
    stats = Counter()
    fab = osmium.geom.WKBFactory()

    fp = (osmium.FileProcessor(str(PBF))
          .with_areas()
          .with_filter(osmium.filter.KeyFilter("highway", "railway", "natural", "water", "waterway", "landuse",
                                               "leisure", "man_made", "building", "place", "amenity",
                                               "building:part")))
    for o in fp:
        tags = o.tags
        try:
            if o.is_way():
                hw, rw = tags.get("highway"), tags.get("railway")
                if hw in ROAD_KEEP and tags.get("area") != "yes":
                    g = wkb.loads(fab.create_linestring(o), hex=True)
                    layers["roads"].append({"osm_id": f"w{o.id}", **{k: tags.get(k) for k in ROAD_TAGS}, "geometry": g})
                elif rw in RAIL_KEEP or (rw == "abandoned" and False):
                    g = wkb.loads(fab.create_linestring(o), hex=True)
                    layers["rail"].append({"osm_id": f"w{o.id}", **{k: tags.get(k) for k in RAIL_TAGS},
                                           "system": sysmap.get(o.id, "bart" if rw == "subway" else "other"),
                                           "geometry": g})
                if tags.get("natural") == "coastline":
                    layers["coastline"].append({"osm_id": f"w{o.id}", "geometry": wkb.loads(fab.create_linestring(o),
                                                                                       hex=True)})
                if tags.get("man_made") in ("pier", "breakwater", "groyne") and not o.is_closed():
                    layers["piers"].append({"osm_id": f"w{o.id}", "kind": tags.get("man_made"),
                                            "width": tags.get("width"),
                                            "geometry": wkb.loads(fab.create_linestring(o), hex=True)})
            elif o.is_area():
                g = None

                def geom():
                    return wkb.loads(fab.create_multipolygon(o), hex=True)

                oid = o.orig_id()
                kind = "w" if o.from_way() else "r"
                if tags.get("natural") == "water" or tags.get("waterway") == "riverbank" \
                        or tags.get("landuse") in ("reservoir", "basin"):
                    g = geom()
                    layers["water"].append({"osm_id": f"{kind}{oid}", "water": tags.get("water"),
                                            "name": tags.get("name"), "geometry": g})
                if tags.get("man_made") in ("pier", "breakwater"):
                    layers["piers"].append({"osm_id": f"{kind}{oid}", "kind": tags.get("man_made"),
                                            "width": None, "geometry": g or geom()})
                if tags.get("man_made") == "bridge":
                    layers["bridges_area"].append({"osm_id": f"{kind}{oid}", "name": tags.get("name"),
                                                   "geometry": g or geom()})
                if tags.get("place") in ("island", "islet"):
                    layers["islands"].append({"osm_id": f"{kind}{oid}", "name": tags.get("name"),
                                              "geometry": g or geom()})
                for key, vals in LANDUSE_TAGS.items():
                    v = tags.get(key)
                    if v in vals:
                        layers["landuse"].append({"osm_id": f"{kind}{oid}", "key": key, "value": v,
                                                  "name": tags.get("name"), "geometry": g or geom()})
                        break
                if "building" in tags or "building:part" in tags:
                    layers["buildings_osm"].append({
                        "osm_id": f"{kind}{oid}", "building": tags.get("building"),
                        "part": tags.get("building:part"), "name": tags.get("name"),
                        "height": tags.get("height"), "levels": tags.get("building:levels"),
                        "min_height": tags.get("min_height"), "roof_shape": tags.get("roof:shape"),
                        "roof_height": tags.get("roof:height"), "geometry": g or geom()})
        except Exception as e:  # noqa: BLE001  (broken multipolygons etc.)
            stats[f"geom_error:{type(e).__name__}"] += 1

    OUT.mkdir(parents=True, exist_ok=True)
    report = {"seconds": None, "geom_errors": dict(stats), "layers": {}}
    for name, rows in layers.items():
        if not rows:
            report["layers"][name] = {"count": 0}
            continue
        g = gpd.GeoDataFrame(rows, geometry="geometry", crs=4326)
        g = g.cx[lon0:lon1, lat0:lat1].to_crs(26910)
        n0 = len(g)
        invalid = ~g.is_valid
        g.loc[invalid, "geometry"] = shapely.make_valid(g.geometry[invalid].values)
        g = g[g.intersects(clipbox)]
        g.to_parquet(OUT / f"{name}.parquet")
        report["layers"][name] = {"count": len(g), "outside_extent": n0 - len(g), "repaired": int(invalid.sum())}
        print(f"  {name:14s} {len(g):7d}  (repaired {int(invalid.sum())}, outside extent {n0 - len(g)})")
    report["seconds"] = round(time.time() - t0, 1)
    (OUT / "osm_extract_report.json").write_text(json.dumps(report, indent=1))
    print(f"osm extract done in {report['seconds']} s, geometry errors: {dict(stats)}")


if __name__ == "__main__":
    main()
