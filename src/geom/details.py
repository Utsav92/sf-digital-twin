"""Street + facade detail layer (LOD1 only; LOD0 stays empty).

Street: curbs (vertical face + top lip between carriageway and sidewalk), lane markings (double yellow centre
lines, dashed lane dividers, solid parking/edge lines) and zebra crosswalks at junctions.
Facade: plinth, cornice and parapet rings, balconies (slab + railing) and window sills. Balconies/sills are
placed on the SAME metre grid the facade shader uses for its windows (u = metres along the ring from the first
vertex, bay 2.8 m / floor 3.3 m, window zone v in 0.30..0.85 of the floor), so they line up with the glass.
f_mat -> materials.SLOTS["details"]: 0 curb, 1 marking_white, 2 marking_yellow, 3 crosswalk, 4 bldg_trim,
5 balcony_slab, 6 railing_metal, 7 sill. Deterministic (hash of building id / way id), tile-independent.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import shapely
from shapely.geometry.polygon import orient

from geom import roadclass as rc
from geom import roads as R
from geom.buildings import _exclude, polys, walls
from geom.drape import ribbon
from geom.meshio import MeshBuf
from geom.polytri import triangulate
from geom.props import _h

CURB, M_WHITE, M_YELLOW, CROSS, TRIM, BALC, RAIL, SILL = range(8)
BAY, FLOOR_H = 2.8, 3.3          # must match materials.facade_material (low-rise)
LIFT = 0.045                     # markings sit this far above the road surface
_CUBE = np.array([[0, 1, 3, 2], [4, 6, 7, 5], [0, 4, 5, 1], [2, 3, 7, 6], [0, 2, 6, 4], [1, 5, 7, 3]])


def boxes(c, u, nrm, w, d, h, z0, centered=False):
    """Vectorised boxes. c (n,2) wall points, u (n,2) unit along wall, nrm (n,2) unit outward; w along u
    (centred), d along nrm from the wall (0..d), height h from z0 (n,). -> verts (8n,3), faces (6n,4)."""
    n = len(c)
    ia, ib, ic = [np.array(x) for x in zip(*[(a, b, k) for a in (0, 1) for b in (0, 1) for k in (0, 1)])]
    su = (ia * 2 - 1) * (np.asarray(w).reshape(-1, 1) / 2)
    sn = ib * (np.asarray(d).reshape(-1, 1)) if not centered else (ib * 2 - 1) * np.asarray(d).reshape(-1, 1) / 2
    xy = c[:, None, :] + u[:, None, :] * su[:, :, None] + nrm[:, None, :] * sn[:, :, None]
    z = np.asarray(z0).reshape(-1, 1) + ic[None, :] * np.asarray(h).reshape(-1, 1)
    v = np.concatenate([xy, z[:, :, None]], axis=2).reshape(-1, 3)
    f = (_CUBE[None, :, :] + (np.arange(n) * 8)[:, None, None])[:, :, ::-1].reshape(-1, 4)  # left-handed frame
    return v, f


def ring_slab(buf, poly, z0, z1, mat, ox, oy, cap=True):
    """Extrude a polygon (with holes) as walls + optional top cap."""
    poly = orient(poly, 1.0)
    for ring in [poly.exterior, *poly.interiors]:
        xy = shapely.get_coordinates(ring) - (ox, oy)
        if len(xy) < 4:
            continue
        v, q, uv = walls(xy, z0, z1)
        buf.add(v, q, uv=uv, mat=np.int32(mat))
    if cap:
        v2, t = triangulate(poly, ox, oy)
        if len(t):
            buf.add(np.c_[v2, np.full(len(v2), z1)], t, mat=np.int32(mat))


# ------------------------------------------------------------------------------------------ facades
def facades(ctx, buf):
    f = ctx.dir / "buildings_meta.parquet"
    if not f.exists():
        return {"buildings": 0, "balconies": 0, "sills": 0}
    meta = pd.read_parquet(f).set_index("bid")
    b = ctx.read("buildings")
    excl = _exclude(ctx.dir.parents[1])
    ox, oy = ctx.wx, ctx.wy
    n_b = n_bal = n_sill = 0
    for row in b.itertuples():
        if row.bid in excl or row.bid not in meta.index:
            continue
        m = meta.loc[row.bid]
        base, roof, h, kind = float(m["base"]), float(m["roof"]), float(m["height_m"]), m["roof_kind"]
        parts = polys(row.geometry)
        if not parts:
            continue
        n_b += 1
        for p in parts:
            if p.area < 25:
                continue
            outer = type(p)(p.exterior)
            if h >= 6:  # plinth, cornice, parapet (flat roofs only get a parapet)
                ring_slab(buf, outer.buffer(0.12, join_style=2, mitre_limit=2.0), base, base + 1.0, TRIM, ox, oy, cap=False)
                ring_slab(buf, outer.buffer(0.32, join_style=2, mitre_limit=2.0).difference(outer.buffer(0.0)),
                          roof - 0.5, roof - 0.02, TRIM, ox, oy, cap=True) if kind == "flat" else None
                if kind == "flat":
                    inner = outer.buffer(-0.35, join_style=2)
                    if not inner.is_empty:
                        for q in polys(outer.difference(inner)):
                            ring_slab(buf, q, roof, roof + 0.8, TRIM, ox, oy, cap=True)
            if h < 8 or h > 120 or p.area < 60:
                continue
            xy = shapely.get_coordinates(orient(p, 1.0).exterior) - (ox, oy)
            if len(xy) < 4:
                continue
            P0, P1 = xy[:-1], xy[1:]
            seg = P1 - P0
            L = np.linalg.norm(seg, axis=1)
            u = seg / (L[:, None] + 1e-9)
            nrm = np.c_[u[:, 1], -u[:, 0]]  # outward = right of travel
            s0 = np.r_[0, np.cumsum(L)[:-1]]
            nf = int((roof - base) // FLOOR_H)
            balc_bld = h <= 45 and _h(row.bid, 7, 3) < 0.45
            cc, uu, nn, zz = [], [], [], []
            for i in range(len(L)):
                if L[i] < 4.0:
                    continue
                k0 = int(np.ceil((s0[i] + 1.2) / BAY - 0.5))
                k1 = int(np.floor((s0[i] + L[i] - 1.2) / BAY - 0.5))
                if k1 < k0:
                    continue
                ks = np.arange(k0, min(k1, k0 + 11) + 1)
                uc = (ks + 0.5) * BAY
                for j in range(1, max(nf, 1)):
                    sel = _h(row.bid * 131 + i, ks * 17 + j, 5) < (0.5 if balc_bld else 0.0)
                    if not balc_bld:
                        continue
                    pts = P0[i] + u[i] * (uc[sel] - s0[i])[:, None]
                    cc.append(pts)
                    uu.append(np.repeat(u[i][None], len(pts), 0))
                    nn.append(np.repeat(nrm[i][None], len(pts), 0))
                    zz.append(np.full(len(pts), base + j * FLOOR_H + 0.9))
            if balc_bld and cc:
                c, uv_, nv, z0 = (np.concatenate(a) for a in (cc, uu, nn, zz))
                if len(c) > 150:
                    pick = np.arange(0, len(c), int(np.ceil(len(c) / 150)))
                    c, uv_, nv, z0 = c[pick], uv_[pick], nv[pick], z0[pick]
                n = len(c)
                v, fq = boxes(c, uv_, nv, np.full(n, 2.2), np.full(n, 1.05), np.full(n, 0.13), z0)  # slab
                buf.add(v, fq, mat=np.int32(BALC))
                z1 = z0 + 0.13
                v, fq = boxes(c + nv * 1.02, uv_, nv, np.full(n, 2.2), np.full(n, 0.04), np.full(n, 0.05), z1 + 0.95)
                buf.add(v, fq, mat=np.int32(RAIL))                                                       # top rail
                v, fq = boxes(c + nv * 1.02, uv_, nv, np.full(n, 2.2), np.full(n, 0.04), np.full(n, 0.04), z1 + 0.05)
                buf.add(v, fq, mat=np.int32(RAIL))                                                       # bottom rail
                for off in (-1.05, -0.35, 0.35, 1.05):                                                   # posts
                    v, fq = boxes(c + uv_ * off + nv * 1.02, uv_, nv, np.full(n, 0.04), np.full(n, 0.04),
                                  np.full(n, 0.95), z1)
                    buf.add(v, fq, mat=np.int32(RAIL))
                n_bal += n
            elif not balc_bld and h <= 40:  # window sills on a hashed subset of walls
                cs, us, ns, zs = [], [], [], []
                for i in range(len(L)):
                    if L[i] < 4.0:
                        continue
                    k0 = int(np.ceil((s0[i] + 1.0) / BAY - 0.5))
                    k1 = int(np.floor((s0[i] + L[i] - 1.0) / BAY - 0.5))
                    if k1 < k0:
                        continue
                    ks = np.arange(k0, min(k1, k0 + 15) + 1)
                    uc = (ks + 0.5) * BAY
                    pts = P0[i] + u[i] * (uc - s0[i])[:, None]
                    for j in range(1, max(nf, 1)):
                        cs.append(pts)
                        us.append(np.repeat(u[i][None], len(pts), 0))
                        ns.append(np.repeat(nrm[i][None], len(pts), 0))
                        zs.append(np.full(len(pts), base + j * FLOOR_H + 0.30 * FLOOR_H - 0.08))
                if cs:
                    c, uv_, nv, z0 = (np.concatenate(a) for a in (cs, us, ns, zs))
                    if len(c) > 200:
                        pick = np.arange(0, len(c), int(np.ceil(len(c) / 200)))
                        c, uv_, nv, z0 = c[pick], uv_[pick], nv[pick], z0[pick]
                    n = len(c)
                    v, fq = boxes(c, uv_, nv, np.full(n, 1.45), np.full(n, 0.14), np.full(n, 0.08), z0)
                    buf.add(v, fq, mat=np.int32(SILL))
                    n_sill += n
    return {"buildings": n_b, "balconies": n_bal, "sills": n_sill}


# ------------------------------------------------------------------------------------------ streets
def _longest(g):
    parts = [p for p in shapely.get_parts(g) if p.geom_type == "LineString" and p.length > 0.5]
    return max(parts, key=lambda p: p.length) if parts else None


def _strip(buf, ctx, g, trim, width, mat, z_off, dash=None, step=1.5):
    """Marking strip along line g between `trim` from each end; dash=(on, period) metres or None (solid)."""
    if g is None or g.length < 2 * trim + 3:
        return 0
    s = np.arange(trim, g.length - trim + 1e-6, step)
    if len(s) < 2:
        return 0
    p = shapely.get_coordinates(shapely.line_interpolate_point(g, s))
    on = np.ones(len(s), bool) if dash is None else (s % dash[1]) < dash[0]
    # runs of consecutive `on` samples
    idx = np.flatnonzero(on)
    if not len(idx):
        return 0
    runs = np.split(idx, np.flatnonzero(np.diff(idx) > 1) + 1)
    n = 0
    for r in runs:
        if len(r) < 2:
            continue
        xy = p[r] - (ctx.wx, ctx.wy)
        z = ctx.ground(xy[:, 0], xy[:, 1]) + z_off + LIFT
        v, q = ribbon(xy, width, z)
        buf.add(v, q, mat=np.int32(mat))
        n += len(q)
    return n


def streets(ctx, buf):
    net, wb = R.ground_network(ctx)
    G = R._globals(ctx.dir.parents[1])
    roads = G["roads"]
    sub = roads.iloc[G["roads_sidx"].query(shapely.box(*wb), predicate="intersects")]
    sub = sub[sub.cls.isin([rc.MOTORWAY, rc.ARTERIAL, rc.LOCAL])]
    stats = {"curb_m": 0.0, "marking_quads": 0, "crosswalks": 0}
    # ---- curbs: boundary of the carriageway where it meets the sidewalk
    cw = [net[c] for c in (rc.ARTERIAL, rc.LOCAL) if c in net]
    if cw and rc.SIDEWALK in net:
        carr = shapely.union_all(cw)
        sw = net[rc.SIDEWALK]
        curb = shapely.intersection(shapely.boundary(carr), shapely.buffer(sw, 0.2))
        zr, zt = rc.Z_OFF[rc.LOCAL], rc.Z_OFF[rc.SIDEWALK] + 0.04
        for ln in R_lines(curb):
            if ln.length < 1.0:
                continue
            m = max(2, int(np.ceil(ln.length / 1.5)) + 1)
            pts = shapely.get_coordinates(shapely.line_interpolate_point(ln, np.linspace(0, ln.length, m)))
            tg = np.gradient(pts, axis=0)
            tg /= np.linalg.norm(tg, axis=1, keepdims=True) + 1e-9
            nrm = np.c_[-tg[:, 1], tg[:, 0]]
            probe = pts + nrm * 0.4
            into_sw = shapely.contains_xy(sw, probe[:, 0], probe[:, 1]).mean() >= 0.5
            nrm = nrm if into_sw else -nrm  # points onto the sidewalk
            lx, ly = pts[:, 0] - ctx.wx, pts[:, 1] - ctx.wy
            g0 = ctx.ground(lx, ly)
            inner = pts + nrm * 0.18
            ilx, ily = inner[:, 0] - ctx.wx, inner[:, 1] - ctx.wy
            gi = ctx.ground(ilx, ily)
            n = len(pts)
            V = np.r_[np.c_[lx, ly, g0 + zr], np.c_[lx, ly, g0 + zt], np.c_[ilx, ily, gi + zt]]
            i = np.arange(n - 1)
            face = np.c_[i, i + 1, n + i + 1, n + i]
            top = np.c_[n + i, n + i + 1, 2 * n + i + 1, 2 * n + i]
            buf.add(V, np.r_[face, top], mat=np.int32(CURB))
            stats["curb_m"] += ln.length
    # ---- lane markings + crosswalks
    ends = {}
    for row in sub.itertuples():
        c0 = shapely.get_coordinates(row.geometry)
        for e in (c0[0], c0[-1]):
            ends[(round(e[0] / 0.5), round(e[1] / 0.5))] = ends.get((round(e[0] / 0.5), round(e[1] / 0.5)), 0) + 1
    for row in sub.itertuples():
        g, c, hw = row.geometry, row.cls, row.w / 2
        if g.geom_type != "LineString" or g.length < 12:
            continue
        lanes = rc.num(row.lanes)
        lanes = int(lanes) if lanes == lanes and 0 < lanes < 13 else rc.DEFAULT_LANES.get(row.highway, 2)
        oneway = rc.tag(row.oneway) == "yes" or c == rc.MOTORWAY
        lw = rc.LANE_W[c]
        per_dir = max(1, lanes if oneway else lanes // 2)
        trim = (9.5 if c == rc.ARTERIAL else 7.0) if c != rc.MOTORWAY else 4.0
        zo = rc.Z_OFF[c]
        link = row.highway.endswith("_link")
        parking = c in (rc.ARTERIAL, rc.LOCAL) and not link and rc.tag(row.surface) not in ("paving_stones", "sett")

        def off(d):
            return _longest(shapely.offset_curve(g, d))
        q = 0
        if not oneway and not link:
            if c == rc.ARTERIAL or (c == rc.LOCAL and hw >= 5.5):
                if c == rc.ARTERIAL:
                    q += _strip(buf, ctx, off(0.14), trim, 0.11, M_YELLOW, zo)
                    q += _strip(buf, ctx, off(-0.14), trim, 0.11, M_YELLOW, zo)
                else:
                    q += _strip(buf, ctx, g, trim, 0.12, M_YELLOW, zo, dash=(3.0, 12.0))
        for k in range(1, per_dir):  # lane dividers
            offs = [(k * lw) if not oneway else (k - per_dir / 2) * lw]
            if not oneway:
                offs.append(-k * lw)
            for d in offs:
                q += _strip(buf, ctx, off(d), trim, 0.12, M_WHITE, zo, dash=(3.0, 12.0))
        edge = (hw - rc.PARKING_W) if parking else (hw - 1.0 if c == rc.MOTORWAY else None)
        if edge is not None and edge > 2.4:
            for sgn in (1, -1):
                q += _strip(buf, ctx, off(sgn * edge), trim * 0.6, 0.11, M_WHITE, zo)
        stats["marking_quads"] += q
        # zebra crosswalks at junction ends (arterial/local with sidewalks, junction of >= 3 ways)
        if row.sw and c in (rc.ARTERIAL, rc.LOCAL) and hw < 14:
            for end, sgn in ((0, 1), (1, -1)):
                pt = shapely.get_coordinates(g)[0 if end == 0 else -1]
                if ends.get((round(pt[0] / 0.5), round(pt[1] / 0.5)), 0) < 3:
                    continue
                dist = trim - 1.2
                s = dist if end == 0 else g.length - dist
                p = np.array(shapely.get_coordinates(shapely.line_interpolate_point(g, s))[0])
                q2 = np.array(shapely.get_coordinates(shapely.line_interpolate_point(g, s + sgn * 1.0))[0])
                t = (q2 - p) / (np.linalg.norm(q2 - p) + 1e-9)
                nv = np.array([-t[1], t[0]])
                vs = np.arange(-(hw - 0.5), hw - 0.5 + 1e-6, 0.95)
                cc = p[None, :] + vs[:, None] * nv[None, :] - (ctx.wx, ctx.wy)
                inside = (cc[:, 0] + ctx.wx > wb[0]) & (cc[:, 0] + ctx.wx < wb[2]) & \
                         (cc[:, 1] + ctx.wy > wb[1]) & (cc[:, 1] + ctx.wy < wb[3])
                cc = cc[inside]
                if not len(cc):
                    continue
                z = ctx.ground(cc[:, 0], cc[:, 1]) + zo + LIFT
                n = len(cc)
                # bars: 2.8 m along t, 0.45 m across (u along n)
                bu = np.repeat(nv[None], n, 0)
                bn = np.repeat(t[None], n, 0)
                v, fq = boxes(cc - bn * 1.4, bu, bn, np.full(n, 0.45), np.full(n, 2.8), np.full(n, 0.012), z)
                buf.add(v, fq, mat=np.int32(CROSS))
                stats["crosswalks"] += 1
    return stats


def R_lines(g):
    from geom.drape import lines_of
    return lines_of(g)


def build(ctx) -> dict:
    buf = MeshBuf()
    st = streets(ctx, buf)
    fa = facades(ctx, buf)
    arrays = buf.arrays()
    return {"lod1": (arrays, {"layer": "details", "lod": "lod1", **st, **fa}),
            "lod0": (None, {"layer": "details", "lod": "lod0"})}
