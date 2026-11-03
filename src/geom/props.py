"""Street props for one tile: street lamps, parked cars, moving traffic (instance points).

Generated from the global ground road network by arclength along each OSM way, so a point's position never
depends on tiling; a tile keeps the points that fall inside it. Deterministic hashes, no RNG state.
- lamps   : sidewalked streets, every 32 m, staggered on both sides, 0.6 m inside the curb, facing the road
- parked  : arterial/local streets with parking lanes, both curbs, 6.3 m pitch, 60% occupancy, not within
            12 m of a way's ends (intersections)
- traffic : right-hand lanes (both directions unless oneway), density by class
npz: verts (points), p_kind (0 lamp, 1 car), p_cls (proto index), p_rot (yaw rad), p_paint (0..1 hash),
     p_moving (0/1)
"""
from __future__ import annotations

import numpy as np
import shapely

from geom import roadclass as rc
from geom import roads as R

PROTO = {"lamp": 0, "sedan": 1, "suv": 2, "van": 3}
N_PAINT = 8  # car prototypes = 3 body types x 8 paints (colour baked per proto: robust under nested instancing)
SPACING = {rc.MOTORWAY: 40.0, rc.ARTERIAL: 55.0, rc.LOCAL: 110.0}


def _h(a, b, c=0):
    a = np.asarray(a, np.int64)
    b = np.asarray(b, np.int64)
    h = (a * 73856093) ^ (b * 19349663) ^ (c * 83492791)
    h = (h ^ (h >> 13)) * 1274126177
    return ((h ^ (h >> 16)) & 0xFFFFFF) / float(0x1000000)


def _along(line, step, start):
    L = line.length
    if L < 2 * start:
        return np.zeros(0), np.zeros((0, 2)), np.zeros((0, 2))
    s = np.arange(start, L - start, step)
    p = shapely.get_coordinates(shapely.line_interpolate_point(line, s))
    q = shapely.get_coordinates(shapely.line_interpolate_point(line, np.minimum(s + 1.0, L)))
    t = q - p
    t /= np.linalg.norm(t, axis=1, keepdims=True) + 1e-9
    return s, p, t


def build(ctx) -> dict:
    G = R._globals(ctx.dir.parents[1])
    roads = G["roads"]
    bx0, by0, bx1, by1 = ctx.tile["bounds_city"]
    wb = (bx0 + ctx.ox, by0 + ctx.oy, bx1 + ctx.ox, by1 + ctx.oy)
    sub = roads.iloc[G["roads_sidx"].query(shapely.box(*wb), predicate="intersects")]
    pts, kind, cls, rot, paint, moving = [], [], [], [], [], []
    for row in sub.itertuples():
        c = row.cls
        if c not in (rc.MOTORWAY, rc.ARTERIAL, rc.LOCAL):
            continue
        g = row.geometry
        wid = int(str(row.osm_id).lstrip("wr")) % 10_000_019  # stable per-way id (no salted str hash)
        hw = row.w / 2
        parking = c in (rc.ARTERIAL, rc.LOCAL) and not row.highway.endswith("_link")
        if row.sw:  # lamps
            s, p, t = _along(g, 32.0, 6.0)
            n = np.c_[-t[:, 1], t[:, 0]]
            side = np.where(np.arange(len(s)) % 2 == 0, 1.0, -1.0)
            q = p + n * (side * (hw + 0.6))[:, None]
            yaw = np.arctan2(-n[:, 1] * side, -n[:, 0] * side)  # arm faces the road
            pts.append(q)
            kind += [0] * len(q)
            cls += [PROTO["lamp"]] * len(q)
            rot.append(yaw)
            paint.append(np.zeros(len(q)))
            moving += [0] * len(q)
        if parking:  # parked cars at both curbs
            for sgn, salt in ((1.0, 1), (-1.0, 2)):
                s, p, t = _along(g, 6.3, 12.0)
                if not len(s):
                    continue
                k = np.arange(len(s))
                occ = _h(wid, k, salt) < 0.6
                n = np.c_[-t[:, 1], t[:, 0]]
                q = (p + n * sgn * (hw - 1.15))[occ]
                yaw = np.arctan2(t[:, 1], t[:, 0])[occ] + (0 if sgn < 0 else np.pi) * 0
                ph = _h(wid, k, salt + 10)[occ]
                pts.append(q)
                kind += [1] * len(q)
                cls += list(np.where(ph < 0.6, PROTO["sedan"], np.where(ph < 0.88, PROTO["suv"], PROTO["van"])))
                rot.append(yaw + np.where(sgn > 0, 0.0, np.pi))
                paint.append(_h(wid, k, salt + 20)[occ])
                moving += [0] * len(q)
        # moving traffic
        lanes = rc.num(row.lanes)
        lanes = int(lanes) if lanes == lanes and 0 < lanes < 13 else rc.DEFAULT_LANES.get(row.highway, 2)
        oneway = rc.tag(row.oneway) == "yes" or c == rc.MOTORWAY
        lw = rc.LANE_W[c]
        dirs = [1.0] if oneway else [1.0, -1.0]
        per_dir = max(1, lanes if oneway else lanes // 2)
        for di, d in enumerate(dirs):
            for ln in range(per_dir):
                s, p, t = _along(g, SPACING[c] / 4, 8.0)
                if not len(s):
                    continue
                k = np.arange(len(s))
                keep = _h(wid, k, 100 + 7 * di + ln) < 0.25  # ~1 car per SPACING per lane
                n = np.c_[-t[:, 1], t[:, 0]]
                # right-hand traffic: forward lanes on the right of the way direction
                off = (lw * (ln + 0.5)) if oneway else (lw * (ln + 0.5))
                off = off - (per_dir * lw / 2 if oneway else 0)
                q = (p - n * d * off if not oneway else p + n * off)[keep]
                yaw = np.arctan2(t[:, 1] * d, t[:, 0] * d)[keep]
                ph = _h(wid, k, 200 + ln)[keep]
                pts.append(q)
                kind += [1] * len(q)
                cls += list(np.where(ph < 0.55, PROTO["sedan"], np.where(ph < 0.85, PROTO["suv"], PROTO["van"])))
                rot.append(yaw)
                paint.append(_h(wid, k, 300 + ln)[keep])
                moving += [1] * len(q)
    if pts:
        P = np.concatenate(pts)
        inside = (P[:, 0] >= wb[0]) & (P[:, 0] < wb[2]) & (P[:, 1] >= wb[1]) & (P[:, 1] < wb[3])
        b = ctx.read("buildings")
        if len(b):  # nothing inside buildings
            inside &= ~shapely.contains_xy(shapely.union_all(b.geometry.values), P[:, 0], P[:, 1])
        P = P[inside]
        kind = np.array(kind, np.int32)[inside]
        cls = np.array(cls, np.int32)[inside]
        rot = np.concatenate(rot).astype(np.float32)[inside]
        paint = np.concatenate(paint).astype(np.float32)[inside]
        moving = np.array(moving, np.int32)[inside]
        car = kind == 1
        cls[car] = 1 + (cls[car] - 1) * N_PAINT + np.minimum((paint[car] * N_PAINT).astype(np.int32), N_PAINT - 1)
    else:
        P = np.zeros((0, 2))
        kind = cls = moving = np.zeros(0, np.int32)
        rot = paint = np.zeros(0, np.float32)
    out = {}
    for lod, sampler in (("lod1", ctx.ground), ("lod0", ctx.ground0)):
        lx, ly = P[:, 0] - ctx.wx, P[:, 1] - ctx.wy
        z = sampler(lx, ly) + np.where(kind == 1, 0.12, 0.22) if len(P) else np.zeros(0)
        sel = np.ones(len(P), bool) if lod == "lod1" else (kind == 0)  # far view: lamps only
        arr = {"verts": np.c_[lx, ly, z].astype(np.float32)[sel], "loops": np.zeros(0, np.int32),
               "sizes": np.zeros(0, np.int32), "p_kind": kind[sel], "p_cls": cls[sel], "p_rot": rot[sel],
               "p_paint": paint[sel], "p_moving": moving[sel]}
        out[lod] = (arr, {"layer": "props", "lod": lod, "lamps": int((kind[sel] == 0).sum()),
                          "cars": int((kind[sel] == 1).sum())})
    return out
