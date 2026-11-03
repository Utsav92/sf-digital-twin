"""Phase 6: roads, sidewalks, paths, piers, bridges for one tile.

Ground network: every road within 60 m of the tile is buffered (width by class/lanes, round joins),
unioned per class, higher-priority classes are subtracted from lower ones (clean intersections, no
overlap), sidewalks = (carriageway + 2.6 m) minus all carriageways, then clipped to the tile rectangle and
draped on the terrain with a 4 m grid (LOD1) / 10 m (LOD0, no sidewalks/paths).
Bridges: deck ribbons from bridges3d (segments owned by the tile holding their midpoint), deck slab
sides, and support columns every ~40 m where the deck is > 4 m above ground (generic spans only; the
Golden Gate / Bay Bridge towers come from the landmark pass).
f_mat -> materials.SLOTS["roads"].
"""
from __future__ import annotations

import geopandas as gpd
import numpy as np
import shapely

from geom import roadclass as rc
from geom.drape import drape_polygons, ribbon
from geom.meshio import MeshBuf

_G = {}
MARGIN = 60.0


def _globals(proc):
    if "roads" not in _G:
        r = gpd.read_parquet(proc / "osm/roads.parquet")
        r = r[r.highway.isin(rc.CLASS) & ~r.footway.isin(rc.SKIP_FOOTWAY) & (r.geom_type == "LineString")]
        r = r[[rc.is_ground(x) for x in r.itertuples()]].copy()
        r["cls"] = r.highway.map(rc.CLASS)
        r["w"] = [rc.width(x) for x in r.itertuples()]
        r["sw"] = [rc.has_sidewalk(x) for x in r.itertuples()]
        _G["roads"] = r.reset_index(drop=True)
        _G["roads_sidx"] = _G["roads"].sindex
        pr = gpd.read_parquet(proc / "osm/piers.parquet")
        geoms = []
        for g, w in zip(pr.geometry, pr.width):
            if g.geom_type in ("Polygon", "MultiPolygon"):
                geoms.append(g)
            elif g.length > 0:
                ww = rc.num(w)
                geoms.append(g.buffer((ww if ww == ww and ww > 0 else 4.0) / 2, cap_style="flat"))
        _G["piers"] = gpd.GeoSeries(geoms, crs=26910)
        _G["piers_sidx"] = _G["piers"].sindex
        b = gpd.read_parquet(proc / "bridges3d.parquet")
        _G["bridges"] = b
        _G["bridges_sidx"] = b.sindex
    return _G


def ground_network(ctx):
    G = _globals(ctx.dir.parents[1])
    r = G["roads"]
    bx0, by0, bx1, by1 = ctx.tile["bounds_city"]
    wb = (bx0 + ctx.ox, by0 + ctx.oy, bx1 + ctx.ox, by1 + ctx.oy)
    q = shapely.box(wb[0] - MARGIN, wb[1] - MARGIN, wb[2] + MARGIN, wb[3] + MARGIN)
    sub = r.iloc[G["roads_sidx"].query(q, predicate="intersects")]
    polys = {}
    for c in (rc.MOTORWAY, rc.ARTERIAL, rc.LOCAL, rc.SERVICE, rc.PATH):
        s = sub[sub.cls == c]
        if len(s):
            polys[c] = shapely.union_all(shapely.buffer(s.geometry.values, s.w.values / 2, quad_segs=4))
    sw = sub[sub.sw]
    if len(sw):
        polys[rc.SIDEWALK] = shapely.union_all(shapely.buffer(sw.geometry.values, sw.w.values / 2 + rc.SIDEWALK_W,
                                                              quad_segs=4))
    pq = G["piers"].iloc[G["piers_sidx"].query(q, predicate="intersects")]
    _G["last_piers"] = shapely.union_all(pq.values) if len(pq) else None
    raw = list(polys.values()) + ([_G["last_piers"]] if _G["last_piers"] is not None else [])
    _G["last_raw"] = shapely.union_all(raw) if raw else None  # unclipped roads + piers, for terrain sink
    taken = None
    out = {}
    for c in rc.PRIORITY:
        if c not in polys:
            continue
        g = polys[c] if taken is None else polys[c].difference(taken)
        taken = polys[c] if taken is None else shapely.union(taken, polys[c])
        g = shapely.clip_by_rect(g, *wb)
        if not g.is_empty:
            out[c] = g
    return out, wb


def piers(ctx, wb):
    """Pier/breakwater surfaces (global table, computed in ground_network) clipped to the tile."""
    g = _G.get("last_piers")
    return shapely.clip_by_rect(g, *wb) if g is not None else None


def bridges(ctx, buf: MeshBuf, rail=False):
    """Deck ribbons + slab sides + supports for bridge segments owned by this tile."""
    G = _globals(ctx.dir.parents[1])
    b = G["bridges"]
    bx0, by0, bx1, by1 = ctx.tile["bounds_city"]
    wb = (bx0 + ctx.ox, by0 + ctx.oy, bx1 + ctx.ox, by1 + ctx.oy)
    sub = b.iloc[G["bridges_sidx"].query(shapely.box(*wb), predicate="intersects")]
    sub = sub[(sub.kind == "rail") == rail]
    for row in sub.itertuples():
        n = row.n
        C = np.frombuffer(row.center, np.float64).reshape(n, 3)
        Lft = np.frombuffer(row.left, np.float64).reshape(n, 3)
        Rgt = np.frombuffer(row.right, np.float64).reshape(n, 3)
        gz = np.frombuffer(row.ground, np.float64)
        mid = (C[:-1, :2] + C[1:, :2]) / 2
        own = (mid[:, 0] >= wb[0]) & (mid[:, 0] < wb[2]) & (mid[:, 1] >= wb[1]) & (mid[:, 1] < wb[3])
        if not own.any():
            continue
        off = np.array([ctx.wx, ctx.wy, 0.0])
        Lc, Rc = Lft - off, Rgt - off
        deck_mat = rc.BRIDGE_DECK if not rail else 0
        top_off = 0.0 if not rail else 0.25
        thick = 1.6 if row.width < 12 else 2.4
        for i in np.flatnonzero(own):
            a, bb = i, i + 1
            l0, l1, r0, r1 = Lc[a], Lc[bb], Rc[a], Rc[bb]
            up = np.array([0, 0, top_off])
            dn = np.array([0, 0, -thick])
            v = np.array([r0 + up, r1 + up, l1 + up, l0 + up,      # deck top
                          r0 + dn, r1 + dn, l1 + dn, l0 + dn])     # slab bottom
            f = np.array([[0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [3, 2, 6, 7]])
            mats = np.array([deck_mat, rc.BRIDGE_STRUCT if not rail else 2,
                             rc.BRIDGE_STRUCT if not rail else 2, rc.BRIDGE_STRUCT if not rail else 2])
            buf.add(v, f, mat=mats.astype(np.int32))
        # supports: every 10th vertex (~40 m) on generic spans where deck is high above ground
        if row.major:
            continue
        for i in np.flatnonzero(own)[::1]:
            if i % 10 != 5:
                continue
            h = C[i, 2] - thick - gz[i]
            if h < 4.0:
                continue
            cx, cy = C[i, 0] - ctx.wx, C[i, 1] - ctx.wy
            s = 0.8 if row.width < 10 else 1.3
            z0, z1 = gz[i] - 1.0, C[i, 2] - thick
            v = np.array([[cx - s, cy - s, z0], [cx + s, cy - s, z0], [cx + s, cy + s, z0], [cx - s, cy + s, z0],
                          [cx - s, cy - s, z1], [cx + s, cy - s, z1], [cx + s, cy + s, z1], [cx - s, cy + s, z1]])
            f = np.array([[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]])
            buf.add(v, f, mat=np.int32(rc.BRIDGE_STRUCT if not rail else 2))


def roughness(ctx, thresh=0.15):
    """rough(x0, y0, cell) for world-space 4 m cells: max deviation of the terrain at the cell's centre and
    edge midpoints from the bilinear interpolation of its corners."""
    def f(x0, y0, cell):
        lx, ly = x0 - ctx.wx, y0 - ctx.wy
        g = ctx.ground
        c00, c10 = g(lx, ly), g(lx + cell, ly)
        c01, c11 = g(lx, ly + cell), g(lx + cell, ly + cell)
        h = cell / 2
        dev = np.zeros(len(x0))
        for (ux, uy) in ((h, h), (h, 0), (0, h), (cell, h), (h, cell)):
            fx, fy = ux / cell, uy / cell
            lin = (1 - fx) * (1 - fy) * c00 + fx * (1 - fy) * c10 + (1 - fx) * fy * c01 + fx * fy * c11
            dev = np.maximum(dev, np.abs(g(lx + ux, ly + uy) - lin))
        return dev > thresh
    return f


def build(ctx) -> dict:
    net, wb = ground_network(ctx)
    out = {}
    for lod, cell, sampler, classes in (
            ("lod1", 4.0, ctx.ground, list(net)),
            ("lod0", 10.0, ctx.ground0, [rc.MOTORWAY, rc.ARTERIAL, rc.LOCAL])):
        buf = MeshBuf()
        for c in classes:
            if c not in net:
                continue
            v, t = drape_polygons(net[c], ctx, cell, sampler, rc.Z_OFF[c] + (0.3 if lod == "lod0" else 0.0),
                                  rough=roughness(ctx) if lod == "lod1" else None)
            buf.add(v, t, mat=np.int32(c))
        if lod == "lod1":
            pg = piers(ctx, wb)
            if pg is not None and not pg.is_empty:
                pg = pg.difference(shapely.union_all(list(net.values()))) if net else pg
                v, t = drape_polygons(pg, ctx, cell, sampler, rc.Z_OFF[rc.PIER])
                buf.add(v, t, mat=np.int32(rc.PIER))
        bridges(ctx, buf)
        out[lod] = (buf.arrays(), {"layer": "roads", "lod": lod})
    return out
