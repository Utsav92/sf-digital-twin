"""Phase 9: hand-tuned parametric landmark geometry (versioned code, no hand edits).

Each generator places itself from OSM footprints/names (or published coordinates) and real dimensions,
emits pieces (verts in the city frame with absolute NAVD88 z, faces, material name), and returns the
footprint used to retire the generic DataSF extrusions underneath (landmark_exclude.json).
Pieces are assigned to the tile containing their centroid; long cables are split into ~40 m pieces.

Dimensions (published): Salesforce Tower 326 m; Transamerica Pyramid 260 m (base 53 m, spire 64 m);
Coit Tower 64 m (dia 11.3 m); Ferry Building clock tower 75 m; City Hall dome 94 m; Sutro Tower 298 m;
Palace of Fine Arts rotunda 49 m; Golden Gate towers 227 m above water, main span 1280 m, side 343 m;
Bay Bridge W span towers ~160 m, suspension spans 704 m + 353 m side spans, centre anchorage.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import shapely
from shapely.ops import linemerge

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom import prims as P  # noqa: E402
from geom.meshio import MeshBuf, planar_uv, save  # noqa: E402

PROC = crs.ROOT / "data/processed"
OX, OY = crs.origin_world()
SEA = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
MATS = ["white_stone", "concrete", "glass", "gold", "copper_green", "sutro_red", "sutro_white",
        "stadium_brick", "terracotta", "ggb_orange", "bridge_struct", "sport"]


class Out:
    def __init__(self):
        self.pieces = []      # (verts city-frame, faces, mat)
        self.footprints = []  # world-frame polygons whose DataSF buildings are replaced
        self.report = {}

    def add(self, vf, mat):
        v, f = vf
        self.pieces.append((np.asarray(v, float), f, MATS.index(mat)))


def _ground():
    from prep.prep_bridges import dem_sampler
    g = dem_sampler()
    return lambda x, y: float(g(np.array([x + OX]), np.array([y + OY]))[0])


GZ = None
OSM = None


def osm_fp(name):
    m = OSM[OSM.name == name]
    if not len(m):
        raise KeyError(name)
    g = max(m.geometry, key=lambda g: g.area)
    return max(getattr(g, "geoms", [g]), key=lambda p: p.area)


def mrr_frame(poly):
    """centre (city frame), long-axis angle, length, width of the minimum rotated rectangle."""
    r = shapely.minimum_rotated_rectangle(poly)
    c = shapely.get_coordinates(r)[:4]
    e0, e1 = c[1] - c[0], c[2] - c[1]
    if np.linalg.norm(e0) < np.linalg.norm(e1):
        e0, e1 = e1, e0
    ctr = c.mean(0) - (OX, OY)
    return ctr, float(np.arctan2(e0[1], e0[0])), float(np.linalg.norm(e0)), float(np.linalg.norm(e1))


def city(lon, lat):
    x, y = crs.lonlat_to_city(lon, lat)
    return np.array([float(x), float(y)])


# ------------------------------------------------------------------ towers / buildings
def salesforce(o):
    fp = osm_fp("Salesforce Tower")
    ctr, ang, L, W = mrr_frame(fp)
    z0 = GZ(*ctr) - 0.5
    rings = []
    for k, z in enumerate(np.linspace(0, 296, 12)):
        s = 1.0 - 0.13 * (z / 296) ** 1.4  # gentle taper, rounded corners
        rings.append(P.ring(P.rounded_rect(ctr, ang, 50 * s, 50 * s, 9 * s), z0 + z))
    o.add(P.loft(rings), "glass")
    top = P.rounded_rect(ctr, ang, 50 * 0.87, 50 * 0.87, 8)
    crown = P.rounded_rect(ctr, ang, 50 * 0.80, 50 * 0.80, 7)
    o.add(P.loft([P.ring(top, z0 + 296), P.ring(crown, z0 + 326)]), "white_stone")  # lattice crown
    for k in range(12):  # vertical fins on the crown read as the open lattice
        a = ang + k * np.pi / 6
        p = ctr + 21.5 * np.array([np.cos(a), np.sin(a)])
        o.add(P.box(p, a, 1.2, 0.6, z0 + 296, z0 + 326), "white_stone")
    o.footprints.append(fp)
    o.report["salesforce_top_m"] = z0 + 326 + 0.5 - GZ(*ctr)


def transamerica(o):
    fp = osm_fp("Transamerica Pyramid")
    ctr, ang, L, W = mrr_frame(fp)
    z0 = GZ(*ctr) - 0.5
    # square base 53 m tapering to 13 m at 196 m, spire to 260 m; 2 "wings" (elevators/stairs)
    rings = [P.ring(P.rect(ctr, ang, 53 * s, 44 * s), z0 + z)
             for z, s in ((0, 1.0), (16, 1.0), (196, 0.26))]
    o.add(P.loft(rings), "white_stone")
    o.add(P.prism(P.rect(ctr, ang, 53 * 0.26, 44 * 0.26), z0 + 196, z0 + 260, scale_top=0.02), "white_stone")
    f = P.frame(ctr, ang)
    for sgn in (-1, 1):
        base = f([sgn * 26.0], [0.0])[0]
        top = f([sgn * 8.0], [0.0])[0]
        v, F = P.loft([P.ring(P.rect(base, ang, 10, 12), z0 + 16), P.ring(P.rect(top, ang, 6, 8), z0 + 220)])
        o.add((v, F), "white_stone")
    o.footprints.append(fp)
    o.report["transamerica_top_m"] = 260.0


def coit(o):
    fp = osm_fp("Coit Tower")
    c = np.array(fp.centroid.coords[0]) - (OX, OY)
    z0 = GZ(*c) - 0.5
    o.add(P.box(c, 0.0, 22, 22, z0, z0 + 6), "concrete")
    flutes = []
    n = 32
    for k in range(n):  # fluted shaft: alternate radius
        t = 2 * np.pi * k / n
        r = 5.65 if k % 2 == 0 else 5.2
        flutes.append((c[0] + r * np.cos(t), c[1] + r * np.sin(t)))
    flutes = np.array(flutes)
    o.add(P.loft([P.ring(flutes, z0 + 6), P.ring(flutes, z0 + 58)]), "white_stone")
    o.add(P.cylinder(c, 6.2, z0 + 58, z0 + 64, n=24), "white_stone")  # observation crown
    o.footprints.append(fp.buffer(3))


def ferry_building(o):
    fp = osm_fp("San Francisco Ferry Building")
    ctr, ang, L, W = mrr_frame(fp)
    z0 = GZ(*ctr) - 0.5
    o.add(P.prism(P.rect(ctr, ang, L, W), z0, z0 + 15), "white_stone")
    o.add(P.prism(P.rect(ctr, ang, L - 2, W - 8), z0 + 15, z0 + 21, scale_top=0.6), "terracotta")  # skylight roof
    f = P.frame(ctr, ang)
    # clock tower on the city (west, Embarcadero) side of the centre
    side = f([0.0], [W / 2 - 6])[0]
    if np.linalg.norm(side - city(-122.3965, 37.7950)) > np.linalg.norm(f([0.0], [-(W / 2 - 6)])[0]
                                                                     - city(-122.3965, 37.7950)):
        side = f([0.0], [-(W / 2 - 6)])[0]
    zt = z0
    o.add(P.box(side, ang, 13, 13, zt, zt + 47), "white_stone")
    o.add(P.box(side, ang, 11, 11, zt + 47, zt + 60), "white_stone")   # clock / belfry stage
    o.add(P.box(side, ang, 8, 8, zt + 60, zt + 66), "white_stone")
    o.add(P.prism(P.rect(side, ang, 8, 8), zt + 66, zt + 75, scale_top=0.1), "terracotta")
    o.footprints.append(fp)


def city_hall(o):
    fp = osm_fp("San Francisco City Hall")
    ctr, ang, L, W = mrr_frame(fp)
    z0 = GZ(*ctr) - 0.5
    o.add(P.prism(P.rect(ctr, ang, L, W), z0, z0 + 24), "white_stone")
    o.add(P.box(ctr, ang, 44, 44, z0 + 24, z0 + 33), "white_stone")
    o.add(P.cylinder(ctr, 19, z0 + 33, z0 + 56, n=32), "white_stone")          # colonnaded drum
    o.add(P.dome(ctr, 19, z0 + 56, 24, n=32, rings=8, r_top=3.5), "concrete")  # lead-grey dome
    o.add(P.cylinder(ctr, 3.5, z0 + 79, z0 + 89, n=12), "gold")              # lantern
    o.add(P.cone(ctr, 2.5, z0 + 89, z0 + 94, n=12), "gold")
    o.footprints.append(fp)
    o.report["city_hall_dome_top_m"] = 94.0


def sutro(o):
    c = city(-122.45276, 37.75523)
    z0 = GZ(*c) - 1.0
    H = 298.0
    for k in range(3):
        a = np.radians(90 + 120 * k)
        d = np.array([np.cos(a), np.sin(a)])
        pts = []
        for z in np.linspace(0, H - 20, 11):
            r = 34 * (1 - z / 260) + 8 if z < 230 else 8 + 2 * (z - 230) / 50
            pts.append([*(c + r * d), z0 + z])
        pts = np.array(pts)
        for i in range(len(pts) - 1):  # red/white bands
            o.add(P.tube(pts[i:i + 2], 1.8 - 0.1 * i, n=4), "sutro_red" if i % 2 == 0 else "sutro_white")
        o._legs = getattr(o, "_legs", []) + [pts]
    legs = o._legs[-3:]
    for i in range(1, 10, 2):  # triangular bracing rings
        for k in range(3):
            o.add(P.tube(np.array([legs[k][i], legs[(k + 1) % 3][i]]), 0.6, n=4), "sutro_white")
    for zc, span in ((H - 75, 26), (H - 40, 22)):  # two crossarm levels
        for k in range(3):
            a = np.radians(90 + 120 * k)
            d = np.array([np.cos(a), np.sin(a)])
            o.add(P.box(c + d * span / 2, a, span, 3, z0 + zc, z0 + zc + 3), "sutro_red")
            o.add(P.cylinder(c + d * span, 0.8, z0 + zc, z0 + H, n=6), "sutro_white")  # antenna masts
    o.report["sutro_top_m_above_base"] = H
    o.footprints.append(osm_fp("Sutro Tower").buffer(5))  # retire the 298 m generic box extrusion


def palace_fine_arts(o):
    fp = osm_fp("Palace of Fine Arts")
    c = np.array(fp.centroid.coords[0]) - (OX, OY)
    z0 = GZ(*c) - 0.5
    oct8 = P.circle(c, 21, 8, phase=np.pi / 8)[:, :2]
    o.add(P.loft([P.ring(oct8, z0), P.ring(oct8, z0 + 30)]), "terracotta")
    o.add(P.dome(c, 21, z0 + 30, 19, n=24, rings=6), "terracotta")
    for k in range(8):  # corner columns
        t = np.pi / 8 + k * np.pi / 4
        o.add(P.cylinder(c + 23.5 * np.array([np.cos(t), np.sin(t)]), 1.4, z0, z0 + 28, n=8), "terracotta")
    # peristyle colonnade arcing around the west side of the lagoon
    lag = city(-122.4478, 37.8034)
    ang0 = np.arctan2(*(c - lag)[::-1])
    for t in np.linspace(ang0 - 1.4, ang0 + 1.4, 34):
        p = lag + 115 * np.array([np.cos(t), np.sin(t)])
        zz = GZ(*p) - 0.5
        o.add(P.cylinder(p, 1.0, zz, zz + 15, n=8), "terracotta")
    arc = np.array([[*(lag + 115 * np.array([np.cos(t), np.sin(t)])), 0] for t in
                    np.linspace(ang0 - 1.4, ang0 + 1.4, 30)])
    arc[:, 2] = [GZ(x, y) + 15.5 for x, y in arc[:, :2]]
    o.add(P.tube(arc, 1.6, n=4), "terracotta")
    o.footprints.append(fp.buffer(2))


def stadium_bowl(o, name, h_out, h_in, inset, field_mat="sport"):
    lu = gpd.read_parquet(PROC / "osm/landuse.parquet")
    poly = lu[(lu.name == name) & (lu.value == "stadium")].geometry.iloc[0]
    poly = max(getattr(poly, "geoms", [poly]), key=lambda p: p.area).simplify(1.0)
    inner = poly.buffer(-inset)
    ring_poly = poly.difference(inner)
    from geom.polytri import triangulate
    v2, t = triangulate(ring_poly, OX, OY)
    d_in = np.array([inner.exterior.distance(shapely.Point(x + OX, y + OY)) for x, y in v2])
    c = np.array(poly.centroid.coords[0]) - (OX, OY)
    zg = GZ(*c) - 0.5
    z = zg + h_in + (h_out - h_in) * np.clip(d_in / inset, 0, 1)  # raked seating rises outward
    o.add((np.c_[v2, z], t.tolist()), "stadium_brick")
    xy = shapely.get_coordinates(poly.exterior)[:-1] - (OX, OY)
    if shapely.Polygon(xy).exterior.is_ccw is False:
        xy = xy[::-1]
    o.add(P.loft([P.ring(xy, zg), P.ring(xy, zg + h_out)], cap_bottom=False, cap_top=False), "stadium_brick")
    for k in range(6):  # light towers
        p = np.asarray(poly.exterior.interpolate(k / 6, normalized=True).coords[0]) - (OX, OY)
        o.add(P.cylinder(p, 0.8, zg + h_out, zg + h_out + 22, n=6), "bridge_struct")
        o.add(P.box(p, 0.0, 8, 1.5, zg + h_out + 22, zg + h_out + 26), "white_stone")
    o.footprints.append(inner.buffer(inset * 0.9))


def oracle_park(o):
    stadium_bowl(o, "Oracle Park", 32, 6, 48)


def cathedrals(o):
    # Grace Cathedral: twin towers on the west front; St Mary's: hyperbolic-paraboloid cupola
    fp = osm_fp("Grace Cathedral")
    ctr, ang, L, W = mrr_frame(fp)
    z0 = GZ(*ctr) - 0.5
    o.add(P.prism(P.rect(ctr, ang, L, W), z0, z0 + 25), "concrete")
    o.add(P.prism(P.rect(ctr, ang, L, W * 0.6), z0 + 25, z0 + 33, scale_top=0.3), "copper_green")
    f = P.frame(ctr, ang)
    for s in (-1, 1):
        p = f([-L / 2 + 7], [s * (W / 2 - 6)])[0]
        o.add(P.box(p, ang, 11, 11, z0, z0 + 53), "concrete")
    o.footprints.append(fp)
    fp2 = osm_fp("Cathedral of Saint Mary of the Assumption")
    ctr, ang, L, W = mrr_frame(fp2)
    z0 = GZ(*ctr) - 0.5
    o.add(P.prism(P.rect(ctr, ang, 78, 78), z0, z0 + 18), "concrete")
    sq = P.rect(ctr, ang + np.pi / 4, 70, 70)
    o.add(P.loft([P.ring(sq, z0 + 18), P.ring(P.rect(ctr, ang, 10, 10), z0 + 58)]), "white_stone")
    o.add(P.cylinder(ctr, 0.5, z0 + 58, z0 + 74, n=6), "gold")  # cross
    o.footprints.append(fp2)


def alcatraz_lighthouse(o):
    fp = osm_fp("Alcatraz Island Lighthouse")
    c = np.array(fp.centroid.coords[0]) - (OX, OY)
    z0 = GZ(*c) - 0.5
    o.add(P.prism(P.circle(c, 3.0, 8)[:, :2], z0, z0 + 22, scale_top=0.7), "white_stone")
    o.add(P.cylinder(c, 2.3, z0 + 22, z0 + 26, n=8), "glass")
    o.add(P.cone(c, 2.5, z0 + 26, z0 + 28, n=8), "concrete")
    o.footprints.append(fp.buffer(1))


# ------------------------------------------------------------------ bridges
def deck_line(name_sub, upper=True):
    b = gpd.read_parquet(PROC / "bridges3d.parquet")
    m = b[b.name.fillna("").str.contains(name_sub) & (b.kind == "road")]
    m = m[m.cls == 0] if (m.cls == 0).any() else m
    pts = []
    for r in m.itertuples():
        C = np.frombuffer(r.center, np.float64).reshape(-1, 3)
        pts.append(C)
    return m, np.concatenate(pts)


def along(line_xy, s):
    """point and unit tangent at arclength s along a shapely LineString (world)."""
    p = np.array(line_xy.interpolate(s).coords[0])
    q = np.array(line_xy.interpolate(min(s + 5, line_xy.length)).coords[0])
    t = (q - p) / (np.linalg.norm(q - p) + 1e-9)
    return p - (OX, OY), t


def deck_z_at(pts3, p):
    d = np.hypot(pts3[:, 0] - p[0] - OX, pts3[:, 1] - p[1] - OY)
    return float(pts3[np.argmin(d), 2])


def suspension(o, line, pts3, towers_s, anchors_s, tower_h, sag, half_w, mat, leg=(10, 16), struts=(),
               x_brace=False, truss_depth=0.0):
    """Generic suspension span(s): towers at arclengths towers_s, cable anchors at anchors_s (incl. the
    centre anchorage), main cables following catenaries tower-to-tower and straight-ish side spans."""
    tops = {}
    for s in towers_s:
        p, t = along(line, s)
        nrm = np.array([-t[1], t[0]])
        ang = float(np.arctan2(t[1], t[0]))
        zb = min(GZ(*p), SEA) - 15
        for side in (-1, 1):
            q = p + nrm * side * (half_w + leg[0] / 2)
            v, F = P.loft([P.ring(P.rect(q, ang, leg[1], leg[0]), zb),
                           P.ring(P.rect(q, ang, leg[1] * 0.6, leg[0] * 0.6), SEA + tower_h)])
            o.add((v, F), mat)
            tops[(s, side)] = np.array([*q, SEA + tower_h - 2])
        for zs in struts:  # portal struts between the legs
            o.add(P.box(p, ang + np.pi / 2, 2 * half_w + leg[0], 5, SEA + zs, SEA + zs + 8), mat)
        if x_brace:
            for z0, z1 in ((70, 105), (105, 140)):
                for side in (-1, 1):
                    a = np.array([*(p + nrm * side * (half_w + 3)), SEA + z0])
                    b = np.array([*(p - nrm * side * (half_w + 3)), SEA + z1])
                    o.add(P.tube(np.array([a, b]), 1.4, n=4), mat)
    anchors = {}
    for s in anchors_s:
        p, t = along(line, s)
        nrm = np.array([-t[1], t[0]])
        for side in (-1, 1):
            q = p + nrm * side * (half_w + leg[0] / 2)
            anchors[(s, side)] = np.array([*q, deck_z_at(pts3, p) + 2])
    keys = sorted(set(towers_s) | set(anchors_s))
    for side in (-1, 1):
        for a, b in zip(keys[:-1], keys[1:]):
            pa = tops.get((a, side), anchors.get((a, side)))
            pb = tops.get((b, side), anchors.get((b, side)))
            both_towers = a in towers_s and b in towers_s
            cable = P.catenary(pa, pb, sag if both_towers else sag * 0.18, m=80)
            for i in range(0, len(cable) - 1, 8):  # ~40 m pieces -> tile-assignable
                o.add(P.tube(cable[i:i + 9], 0.55, n=6), mat)
            # suspenders every ~15 m
            n = int(np.linalg.norm(pb[:2] - pa[:2]) / 15)
            for k in range(1, n):
                c = cable[int(k / n * (len(cable) - 1))]
                dz = deck_z_at(pts3, c[:2])
                if c[2] - dz > 2:
                    o.add(P.tube(np.array([c, [c[0], c[1], dz + 0.5]]), 0.18, n=4), mat)
    if truss_depth > 0:  # stiffening truss fascia under both deck edges
        s = np.arange(min(keys), max(keys), 10.0)
        for side in (-1, 1):
            top = []
            for si in s:
                p, t = along(line, si)
                q = p + np.array([-t[1], t[0]]) * side * (half_w + 0.5)
                top.append([*q, deck_z_at(pts3, p)])
            top = np.array(top)
            bot = top - [0, 0, truss_depth]
            for i in range(len(top) - 1):
                o.add((np.array([bot[i], bot[i + 1], top[i + 1], top[i]]), [[0, 1, 2, 3], [3, 2, 1, 0]]), mat)


def golden_gate(o):
    m, pts3 = deck_line("Golden Gate Bridge")
    line = linemerge(shapely.union_all(m.geometry.values))
    line = max(getattr(line, "geoms", [line]), key=lambda g: g.length)
    if line.coords[0][1] > line.coords[-1][1]:
        line = shapely.LineString(line.coords[::-1])  # south -> north
    s_south = line.project(shapely.Point(*(city(-122.47736, 37.81074) + (OX, OY))))
    towers = [s_south, s_south + 1280.0]
    anchors = [s_south - 343.0, s_south + 1280.0 + 343.0]
    anchors = [a for a in anchors if 0 <= a <= line.length]
    suspension(o, line, pts3, towers, anchors, tower_h=227.0, sag=143.0, half_w=14.0, mat="ggb_orange",
               leg=(10, 16), struts=(80, 125, 165, 205), truss_depth=7.6)
    o.report["ggb_tower_top_m"] = SEA + 227.0
    o.report["ggb_span_m"] = 1280.0
    o.report["ggb_line_m"] = round(line.length, 1)


def bay_bridge(o):
    m, pts3 = deck_line("Eisenhower")
    gz = np.frombuffer(b"".join(m.ground), np.float64) if False else None
    line = linemerge(shapely.union_all(m.geometry.values))
    parts = getattr(line, "geoms", [line])
    land = gpd.read_file(PROC / "boundary/sf_land.gpkg")
    ybi = land[land.name == "Yerba Buena Island"].union_all()
    # mainland SF only (the "Treasure Island" neighbourhood polygon also contains Yerba Buena)
    main = land[(land.src == "datasf_neighborhoods") & (land.name != "Treasure Island")].union_all()
    # the West Span chain: starts on mainland SF and reaches Yerba Buena (East Span chains start at YBI)
    cands = [g for g in parts if g.distance(main) < 50 and g.distance(ybi) < 50
             and min(g.coords[0][0], g.coords[-1][0]) - OX < 1000]
    line = max(cands, key=lambda g: g.length)
    if line.coords[0][0] > line.coords[-1][0]:
        line = shapely.LineString(line.coords[::-1])  # west -> east
    s = np.arange(0, line.length, 5.0)
    xy = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
    on_main = shapely.contains_xy(main, xy[:, 0], xy[:, 1])
    on_ybi = shapely.contains_xy(ybi, xy[:, 0], xy[:, 1])
    # the OSM way continues across the East Span to Oakland: the West Span is the water stretch between
    # the last SF point and the FIRST contact with Yerba Buena Island
    s_ybi = float(s[on_ybi].min())
    s_shore = float(s[on_main & (s < s_ybi)].max())
    # W2 .. YBI anchorage = 704 + 353 + 353 + 704 + 353 = 2467 m; fit to the YBI shore
    w6 = s_ybi - 353.0
    w5 = w6 - 704.0
    w4 = w5 - 353.0  # centre anchorage
    w3 = w4 - 353.0
    w2 = w3 - 704.0
    sf_anchor = max(w2 - 353.0, 0.0)
    suspension(o, line, pts3, [w2, w3, w5, w6], [sf_anchor, w4, s_ybi], tower_h=160.0, sag=70.0,
               half_w=17.0, mat="bridge_struct", leg=(7, 12), struts=(40, 150), x_brace=True, truss_depth=9.0)
    p, t = along(line, w4)  # centre anchorage: concrete caisson + tower top
    ang = float(np.arctan2(t[1], t[0]))
    o.add(P.box(p, ang, 60, 40, SEA - 20, SEA + 85), "concrete")
    o.add(P.box(p, ang, 30, 30, SEA + 85, SEA + 115), "bridge_struct")
    o.report["baybridge_shore_to_ybi_m"] = round(s_ybi - s_shore, 1)
    o.report["baybridge_w2_offshore_m"] = round(w2 - s_shore, 1)


GENERATORS = [salesforce, transamerica, coit, ferry_building, city_hall, sutro, palace_fine_arts, oracle_park,
              cathedrals, alcatraz_lighthouse, golden_gate, bay_bridge]


def main():
    global GZ, OSM
    GZ = _ground()
    OSM = gpd.read_parquet(PROC / "osm/buildings_osm.parquet")
    idx = json.loads((PROC / "tile_index.json").read_text())
    o = Out()
    per_asset = {}
    for g in GENERATORS:
        try:
            n0 = len(o.pieces)
            g(o)
            per_asset[g.__name__] = o.pieces[n0:]
            print(f"  {g.__name__}: ok")
        except Exception as e:  # noqa: BLE001
            print(f"  {g.__name__}: FAILED {type(e).__name__}: {e}")
            raise
    # assign pieces to tiles by centroid
    bufs = {}
    S = idx["tile_size_m"]
    for v, F, mi in o.pieces:
        c = v.mean(0)
        k = f"t{int(np.floor(c[0] / S)):+03d}_{int(np.floor(c[1] / S)):+03d}"
        t = idx["tiles"].get(k)
        if t is None or t["status"] != "build":
            o.report.setdefault("pieces_outside_built_tiles", 0)
            o.report["pieces_outside_built_tiles"] += 1
            continue
        off = np.array(t["offset_city"])
        bufs.setdefault(k, MeshBuf()).add(v - off, F, mat=np.int32(mi))
    for k, b in bufs.items():
        arr = b.arrays()
        planar_uv(arr, idx["tiles"][k]["offset_city"])
        for lod in ("lod1", "lod0"):
            save(PROC / "tiles" / k / f"mesh_landmarks_{lod}.npz", arr,
                 {"layer": "landmarks", "lod": lod, "materials": MATS})
    # clear stale landmark meshes from tiles that no longer get any
    for f in (PROC / "tiles").glob("*/mesh_landmarks_*.npz"):
        if f.parent.name not in bufs:
            f.unlink()
    # hero assets: one npz per landmark, pivot = base centre (city frame xy, min z); world pos in a json
    adir = PROC / "landmarks"
    adir.mkdir(exist_ok=True)
    assets = {}
    for name, pcs in per_asset.items():
        allv = np.concatenate([v for v, _, _ in pcs])
        piv = np.array([*(allv[:, :2].min(0) + allv[:, :2].max(0)) / 2, allv[:, 2].min()])
        mb = MeshBuf()
        for v, F, mi in pcs:
            mb.add(v - piv, F, mat=np.int32(mi))
        arr = mb.arrays()
        planar_uv(arr, piv)
        save(adir / f"{name}.npz", arr, {"layer": "landmarks", "asset": name, "materials": MATS})
        assets[name] = {"pivot_city_m": piv.round(3).tolist(), "pieces": len(pcs),
                        "height_m": round(float(allv[:, 2].max() - allv[:, 2].min()), 2)}
    (adir / "assets.json").write_text(json.dumps(assets, indent=1))
    # retire generic extrusions under landmark footprints
    b = gpd.read_parquet(PROC / "buildings_all.parquet")
    rp = b.geometry.representative_point()
    fps = shapely.union_all(o.footprints)
    excl = b.bid[rp.within(fps)].astype(int).tolist()
    (PROC / "landmark_exclude.json").write_text(json.dumps({"bids": excl, "names": b.osm_name[rp.within(fps)]
                                                            .fillna("").tolist()}, indent=0))
    o.report.update({"pieces": len(o.pieces), "tiles": sorted(bufs), "excluded_buildings": len(excl)})
    (PROC / "landmarks_report.json").write_text(json.dumps(o.report, indent=1))
    print(json.dumps({k: v for k, v in o.report.items() if k != "tiles"}, indent=1))


if __name__ == "__main__":
    main()
