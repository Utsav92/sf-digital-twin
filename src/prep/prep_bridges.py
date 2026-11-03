"""Phase 6a: city-wide 3D deck profiles for every road/rail bridge way.

Graph model (per connected bridge network, 4 m densified vertices):
  anchors  : bridge endpoints shared with a ground (non-bridge, non-tunnel) way or a tunnel portal;
             deck z there = terrain z (so decks meet the street exactly)
  target T : terrain + 6.5 m x layer (rail 7 m), floored at sea level over water;
             named major spans over water: Golden Gate 67 m, Bay Bridge 50 m (+9 m per layer above 2)
  z_up     : max over u of T(u) - G*dist(u, v)  (decks rise early towards high targets, grade G=5%)
  z        : min(z_up, z_anchor_nearest + G*dist_to_anchor)  (decks come down to meet anchors)
Each way gets centre/left/right 3D polylines (vertex normals averaged -> continuous ribbons across tiles).
Writes data/processed/bridges3d.parquet (+ report)
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
import shapely
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from geom import roadclass as rc  # noqa: E402

PROC = crs.ROOT / "data/processed"
STEP = 4.0
GRADE = 0.05
WATER_CLR = {"golden gate": 67.0, "bay bridge": 50.0, "eisenhower": 50.0}


def dem_sampler():
    r = rasterio.open(PROC / "dem/dem_1m.tif")
    a = r.read(1)
    inv = ~r.transform

    def f(x, y):
        c, rr = inv * (np.asarray(x), np.asarray(y))
        c = np.clip(c - 0.5, 0, a.shape[1] - 2)
        rr = np.clip(rr - 0.5, 0, a.shape[0] - 2)
        i, j = np.floor(c).astype(int), np.floor(rr).astype(int)
        tx, ty = c - i, rr - j
        return ((1 - tx) * (1 - ty) * a[j, i] + tx * (1 - ty) * a[j, i + 1]
                + (1 - tx) * ty * a[j + 1, i] + tx * ty * a[j + 1, i + 1])
    return f


def key(x, y):
    return (round(x, 1), round(y, 1))


def main():
    t0 = time.time()
    sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
    roads = gpd.read_parquet(PROC / "osm/roads.parquet")
    rails = gpd.read_parquet(PROC / "osm/rail.parquet")
    for df in (roads, rails):
        for c in ("covered", "surface", "sidewalk", "bridge:name", "lanes", "width", "oneway"):
            if c not in df:
                df[c] = None
    roads = roads[roads.highway.isin(rc.CLASS) & ~roads.footway.isin(rc.SKIP_FOOTWAY)]
    roads = roads.assign(kind="road")
    rails = rails.assign(kind="rail", highway=None)
    allw = pd.concat([roads, rails], ignore_index=True)
    allw = allw[allw.geom_type == "LineString"]
    isb = np.array([rc.is_bridge(r) for r in allw.itertuples()])
    ist = np.array([rc.tag(t) not in (None, "no") for t in allw.tunnel])
    br = allw[isb].copy()
    ground_nodes = set()
    for g in allw[~isb & ~ist].geometry:  # ground ways
        for x, y in shapely.get_coordinates(g):
            ground_nodes.add(key(x, y))
    tunnel_ends = set()
    for g in allw[ist].geometry:
        c = shapely.get_coordinates(g)
        tunnel_ends.update({key(*c[0]), key(*c[-1])})
    ground = dem_sampler()
    surface_lo = 0.0

    # --- densify each bridge way, build global vertex table
    verts, way_of, edges, way_slices = [], [], [], []
    node_id = {}
    for wi, row in enumerate(br.itertuples()):
        g = row.geometry
        n = max(2, int(np.ceil(g.length / STEP)) + 1)
        d = np.linspace(0, g.length, n)
        pts = shapely.get_coordinates(shapely.line_interpolate_point(g, d))
        ids = []
        for k, (x, y) in enumerate(pts):
            kk = key(x, y)
            if k in (0, n - 1) and kk in node_id:  # junctions between bridge ways share a vertex
                ids.append(node_id[kk])
                continue
            vid = len(verts)
            verts.append((x, y))
            way_of.append(wi)
            if k in (0, n - 1):
                node_id[kk] = vid
            ids.append(vid)
        for a, b, L in zip(ids[:-1], ids[1:], np.diff(d)):
            edges.append((a, b, max(L, 0.01)))
        way_slices.append(ids)
    V = np.array(verts)
    E = np.array(edges)
    nv = len(V)
    A = coo_matrix((np.r_[E[:, 2], E[:, 2]], (np.r_[E[:, 0], E[:, 1]].astype(int),
                                               np.r_[E[:, 1], E[:, 0]].astype(int))), shape=(nv, nv)).tocsr()
    ncomp, comp = connected_components(A, directed=False)

    # --- targets
    gz = ground(V[:, 0], V[:, 1])
    layer = np.array([max(1.0, rc.num(br.layer.iloc[w]) if not np.isnan(rc.num(br.layer.iloc[w])) else 1.0)
                      for w in way_of])
    kind = br.kind.values[way_of]
    clr = np.where(kind == "rail", 7.0, 6.5) * layer
    T = np.maximum(gz, sea) + clr
    names = np.array([f"{rc.tag(a) or ''} {rc.tag(b) or ''}".lower()
                      for a, b in zip(br.name, br["bridge:name"])], dtype=str)[way_of]
    over_water = gz < sea + 0.5
    for k, c in WATER_CLR.items():
        sel = over_water & (np.char.find(names, k) >= 0)
        extra = np.where(k == "golden gate", 0.0, 9.0 * np.maximum(layer - 2, 0))
        T[sel] = np.maximum(T[sel], sea + c + extra[sel])
    # anchors
    anchor = np.zeros(nv, bool)
    for ids in way_slices:
        for vid in (ids[0], ids[-1]):
            kk = key(*V[vid])
            if kk in ground_nodes or kk in tunnel_ends:
                anchor[vid] = True
    T[anchor] = gz[anchor]

    # z_up: max-plus relaxation along edges (rise at most GRADE towards high targets)
    zu = T.copy()
    a, b, L = E[:, 0].astype(int), E[:, 1].astype(int), E[:, 2]
    for it in range(5000):
        old = zu.copy()
        np.maximum.at(zu, a, zu[b] - GRADE * L)
        np.maximum.at(zu, b, zu[a] - GRADE * L)
        if np.allclose(old, zu, atol=1e-4):
            break
    # descend to anchors
    z = zu.copy()
    if anchor.any():
        dist, _, src = dijkstra(A, directed=False, indices=np.flatnonzero(anchor), min_only=True,
                                return_predecessors=True)
        reach = np.isfinite(dist)
        z[reach] = np.minimum(zu[reach], gz[src[reach]] + GRADE * dist[reach])
    z = np.maximum(z, gz + 0.3)  # never below terrain
    z[anchor] = gz[anchor]

    # --- per-way 3D ribbons
    rows = []
    for wi, (row, ids) in enumerate(zip(br.itertuples(), way_slices)):
        p = np.c_[V[ids], z[ids]]
        if row.kind == "road":
            c = rc.CLASS[row.highway]
            w = rc.width(row) if c != rc.PATH else rc.width(row)
        else:
            c, w = -1, 4.5
        t = np.gradient(p[:, :2], axis=0)
        t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-12
        nrm = np.c_[-t[:, 1], t[:, 0]]
        left = np.c_[p[:, :2] + nrm * w / 2, p[:, 2]]
        right = np.c_[p[:, :2] - nrm * w / 2, p[:, 2]]
        nm = names[ids[0]]
        rows.append({"osm_id": row.osm_id, "kind": row.kind, "cls": c, "width": w, "name": row.name,
                     "major": any(k in nm for k in WATER_CLR),
                     "center": p.astype(np.float64).tobytes(), "left": left.tobytes(), "right": right.tobytes(),
                     "ground": gz[ids].tobytes(), "n": len(ids), "comp": int(comp[ids[0]]),
                     "geometry": shapely.LineString(p[:, :2])})
    out = gpd.GeoDataFrame(rows, geometry="geometry", crs=26910)
    out.to_parquet(PROC / "bridges3d.parquet")
    rep = {"bridge_ways": len(out), "networks": int(ncomp), "vertices": nv, "anchors": int(anchor.sum()),
           "relax_iterations": it + 1, "max_deck_above_ground_m": float((z - gz).max()),
           "seconds": round(time.time() - t0, 1)}
    for nmk in ("golden gate", "eisenhower"):
        sel = np.char.find(names, nmk) >= 0
        if sel.any():
            rep[f"deck_max_{nmk}"] = round(float(z[sel].max()), 1)
    (PROC / "bridges_report.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
