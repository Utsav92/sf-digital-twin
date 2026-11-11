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
# kinds: 0 lamp, 1 car, 2 hydrant, 3 bench, 4 bin, 5 traffic signal, 6 pedestrian
# absolute prototype indices (props_instancing.protos order): 25 hydrant, 26 bench, 27 bin, 28 signal, 29-34 pedestrians
P_HYDRANT, P_BENCH, P_BIN, P_SIGNAL, P_PED0, N_PED = 25, 26, 27, 28, 29, 6
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
    ends = {}
    for row in sub.itertuples():
        c0 = shapely.get_coordinates(row.geometry)
        for e in (c0[0], c0[-1]):
            k_ = (round(e[0] / 0.5), round(e[1] / 0.5))
            ends[k_] = ends.get(k_, 0) + 1

    def push(q, yaw, kd, cl):
        pts.append(q)
        kind.extend([kd] * len(q))
        cls.extend(list(cl) if hasattr(cl, "__len__") else [cl] * len(q))
        rot.append(yaw)
        paint.append(np.zeros(len(q)))
        moving.extend([0] * len(q))

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
        if row.sw:  # sidewalk furniture + pedestrians
            for step, start, salt, off, p_cls, occ in ((70.0, 20.0, 40, 0.5, P_HYDRANT, 0.45),
                                                       (60.0, 15.0, 50, 1.9, P_BENCH, 0.18 if c == rc.ARTERIAL else 0.05),
                                                       (45.0, 10.0, 60, 1.35, P_BIN, 0.3 if c == rc.ARTERIAL else 0.1)):
                ss, p, t = _along(g, step, start)
                if not len(ss):
                    continue
                k = np.arange(len(ss))
                keep = _h(wid, k, salt) < occ
                n = np.c_[-t[:, 1], t[:, 0]]
                side = np.where(_h(wid, k, salt + 1) < 0.5, 1.0, -1.0)
                q = (p + n * (side * (hw + off))[:, None])[keep]
                yaw = np.arctan2(-n[:, 1] * side, -n[:, 0] * side)[keep]  # faces the road
                if len(q):
                    push(q, yaw, {P_HYDRANT: 2, P_BENCH: 3, P_BIN: 4}[p_cls], p_cls)
            pocc = 0.55 if c == rc.ARTERIAL else 0.22
            for sgn, salt in ((1.0, 70), (-1.0, 71)):
                ss, p, t = _along(g, 7.5, 9.0)
                if not len(ss):
                    continue
                k = np.arange(len(ss))
                keep = _h(wid, k, salt) < pocc
                n = np.c_[-t[:, 1], t[:, 0]]
                lat = hw + 0.8 + 1.5 * _h(wid, k, salt + 1)
                q = (p + n * (sgn * lat)[:, None])[keep]
                walk = np.where(_h(wid, k, salt + 2) < 0.5, 0.0, np.pi) + (_h(wid, k, salt + 3) - 0.5) * 0.4
                yaw = (np.arctan2(t[:, 1], t[:, 0]) + walk)[keep]
                pc = (P_PED0 + np.minimum((_h(wid, k, salt + 4) * N_PED).astype(np.int32), N_PED - 1))[keep]
                if len(q):
                    push(q, yaw, 6, pc)
            if c == rc.ARTERIAL:  # traffic signals: mast arm on the right-hand corner of each approach
                gc = shapely.get_coordinates(g)
                for end, sgn in ((0, 1.0), (1, -1.0)):
                    e = gc[0] if end == 0 else gc[-1]
                    if ends.get((round(e[0] / 0.5), round(e[1] / 0.5)), 0) < 3 or g.length < 40:
                        continue
                    s_ = 8.5 if end == 0 else g.length - 8.5
                    pp = np.array(shapely.get_coordinates(shapely.line_interpolate_point(g, s_))[0])
                    p2 = np.array(shapely.get_coordinates(shapely.line_interpolate_point(g, s_ + sgn))[0])
                    tout = (p2 - pp) / (np.linalg.norm(p2 - pp) + 1e-9)
                    right = np.array([-tout[1], tout[0]])
                    q = (pp + right * (hw + 0.9))[None, :]
                    push(q, np.array([np.arctan2(-right[1], -right[0])]), 5, P_SIGNAL)
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
        kind_all = np.array(kind, np.int32)
        net, _ = R.ground_network(ctx)  # furniture + pedestrians must stand on a sidewalk polygon
        sw = net.get(rc.SIDEWALK)
        onsw = np.ones(len(P), bool)
        furn = np.isin(kind_all, (2, 3, 4, 6))
        if sw is not None and furn.any():
            onsw[furn] = shapely.contains_xy(sw, P[furn, 0], P[furn, 1])
        elif furn.any():
            onsw[furn] = False
        sig = kind_all == 5
        if sig.any():
            reach = sw.buffer(2.0) if sw is not None else None
            onsw[sig] = shapely.contains_xy(reach, P[sig, 0], P[sig, 1]) if reach is not None else True
        inside &= onsw
        rp = ctx.dir.parents[1] / "hero_route.json"  # cinematic hero-car route: no instanced cars on it
        if rp.exists():
            import json
            rxy = np.array(json.loads(rp.read_text())["xy"]) + (ctx.ox, ctx.oy)
            line = shapely.LineString(rxy)
            near = shapely.dwithin(shapely.points(P), line, 4.2) & (kind_all == 1)
            inside &= ~near
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
        z = sampler(lx, ly) + np.where(kind == 1, 0.12, 0.26) if len(P) else np.zeros(0)
        sel = np.ones(len(P), bool) if lod == "lod1" else (kind == 0)  # far view: lamps only
        arr = {"verts": np.c_[lx, ly, z].astype(np.float32)[sel], "loops": np.zeros(0, np.int32),
               "sizes": np.zeros(0, np.int32), "p_kind": kind[sel], "p_cls": cls[sel], "p_rot": rot[sel],
               "p_paint": paint[sel], "p_moving": moving[sel]}
        out[lod] = (arr, {"layer": "props", "lod": lod, "lamps": int((kind[sel] == 0).sum()),
                          "cars": int((kind[sel] == 1).sum()), "peds": int((kind[sel] == 6).sum()),
                          "signals": int((kind[sel] == 5).sum())})
    return out
