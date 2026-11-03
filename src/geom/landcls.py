"""Phase 5: classify terrain faces by land use (rasterize polygons onto the tile's face grid).

Priority (later wins): residential/commercial < paved/industrial < grass/park < sport < cemetery <
golf < scrub/forest < beach/sand/rock < wetland.  Faces below sea level stay 'seabed'.
Sources: OSM landuse/leisure/natural/amenity (clipped per tile) + DataSF RPD parks.
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize
from rasterio.transform import from_origin

from geom.terrain import CLS

MAP = {
    ("landuse", "residential"): "residential", ("landuse", "commercial"): "commercial",
    ("landuse", "retail"): "commercial", ("landuse", "industrial"): "industrial", ("landuse", "port"): "industrial",
    ("landuse", "railway"): "rail_yard", ("landuse", "construction"): "construction",
    ("landuse", "brownfield"): "construction", ("landuse", "military"): "ground",
    ("landuse", "education"): "paved", ("landuse", "religious"): "paved",
    ("amenity", "parking"): "paved", ("amenity", "university"): "paved", ("amenity", "school"): "paved",
    ("amenity", "hospital"): "paved",
    ("landuse", "grass"): "grass", ("landuse", "meadow"): "grass", ("landuse", "village_green"): "grass",
    ("landuse", "recreation_ground"): "park", ("landuse", "allotments"): "park", ("landuse", "flowerbed"): "park",
    ("leisure", "park"): "park", ("leisure", "garden"): "park", ("leisure", "playground"): "park",
    ("leisure", "dog_park"): "park", ("leisure", "nature_reserve"): "scrub",
    ("leisure", "recreation_ground"): "park", ("natural", "grassland"): "grass", ("natural", "heath"): "scrub",
    ("leisure", "pitch"): "sport", ("leisure", "stadium"): "sport", ("leisure", "track"): "sport",
    ("landuse", "cemetery"): "cemetery", ("leisure", "golf_course"): "golf",
    ("natural", "scrub"): "scrub", ("landuse", "forest"): "forest", ("natural", "wood"): "forest",
    ("natural", "beach"): "beach", ("natural", "sand"): "beach", ("natural", "bare_rock"): "rock",
    ("natural", "scree"): "rock", ("natural", "wetland"): "wetland",
}
ORDER = ["ground", "residential", "commercial", "paved", "industrial", "rail_yard", "construction", "grass",
         "park", "sport", "cemetery", "golf", "scrub", "forest", "beach", "rock", "wetland"]
_G = {}


def _rpd(proc):
    if "rpd" not in _G:
        g = gpd.read_file(proc.parent / "raw/datasf/rpd_parks.geojson").to_crs(26910)
        _G["rpd"] = g[g.geom_type.isin(["Polygon", "MultiPolygon"])]
    return _G["rpd"]


def classify_faces(ctx, verts, quads, cls):
    n = int(round(np.sqrt(len(quads))))  # faces per side
    step = 500.0 / n
    x0, y0, _, y1 = ctx.tile["bounds_city"]
    tr = from_origin(ctx.ox + x0, ctx.oy + y1, step, step)
    lu = ctx.read("landuse")
    shapes = {}
    for _, r in lu.iterrows():
        c = MAP.get((r.key, r.value))
        if c and not r.geometry.is_empty:
            shapes.setdefault(c, []).append(r.geometry)
    rpd = _rpd(ctx.dir.parents[1])
    bx = (ctx.ox + x0, ctx.oy + y0, ctx.ox + x0 + 500, ctx.oy + y1)
    sub = rpd.cx[bx[0]:bx[2], bx[1]:bx[3]]
    shapes.setdefault("park", []).extend(sub.geometry.values)
    grid = np.full((n, n), -1, np.int32)
    for c in ORDER:
        if c in shapes:
            r = rasterize([(g, 1) for g in shapes[c]], out_shape=(n, n), transform=tr, dtype="uint8")
            grid[r == 1] = CLS[c]
    grid = np.flipud(grid).ravel()  # row 0 = south, matching quad order j*(n)+i
    out = cls.copy()
    land = cls != CLS["seabed"]
    sel = land & (grid >= 0)
    out[sel] = grid[sel]
    return out
