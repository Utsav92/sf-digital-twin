"""Phase 4: terrain mesh assertions (mesh space, after stitching).
- every build tile has LOD0/LOD1 terrain npz, finite z, full grid (no holes)
- shared edges: neighbour edge vertices identical in world space (both LODs), incl. fine/coarse stitches
- landmark elevations on the LOD1 mesh: Twin Peaks ~280, Ferry Building 0-3 (+-1)
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
T = {k: t for k, t in idx["tiles"].items() if t["status"] == "build"}
pilot = "--pilot" in sys.argv
if pilot:
    T = {k: t for k, t in T.items() if t["pilot"]}
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


cache = {}


def mesh(k, lod):
    if (k, lod) not in cache:
        d = np.load(PROC / "tiles" / k / f"mesh_terrain_{lod}.npz")
        v = d["verts"].astype(np.float64)
        n = int(round(np.sqrt(len(v))))
        g = v.reshape(n, n, 3).copy()
        g[..., 0] += T[k]["offset_city"][0]
        g[..., 1] += T[k]["offset_city"][1]
        cache[(k, lod)] = g
    return cache[(k, lod)]


bad, tot, holes = 0, 0, 0
for k, t in T.items():
    for lod in ("lod1", "lod0"):
        g = mesh(k, lod)
        if not np.isfinite(g).all():
            holes += 1
        for d, (mine, theirs) in {"E": (np.s_[:, -1], np.s_[:, 0]), "N": (np.s_[-1, :], np.s_[0, :])}.items():
            nb = t["neighbors"].get(d)
            if nb not in T:
                continue
            a, b = g[mine], mesh(nb, lod)[theirs]
            tot += 1
            if a.shape == b.shape:
                ok = np.allclose(a, b, atol=1e-3)
            else:  # fine vs coarse: every coarse vertex must lie on the fine edge polyline
                fine, coarse = (a, b) if len(a) > len(b) else (b, a)
                r = (len(fine) - 1) // (len(coarse) - 1)
                ok = np.allclose(fine[::r], coarse, atol=1e-3)
                # intermediate fine vertices collinear (linear interp) with coarse segment ends
                zi = np.interp(np.arange(len(fine)), np.arange(0, len(fine), r), coarse[:, 2])
                ok = ok and np.allclose(fine[:, 2], zi, atol=1e-3)
            bad += not ok
check(holes == 0, f"terrain meshes finite & complete ({len(T)} tiles x 2 LODs)")
check(bad == 0, f"mesh seams watertight: {tot - bad}/{tot}")


def zat(lon, lat, rad=0.0):
    x, y = crs.lonlat_to_city(lon, lat)
    x, y = float(x), float(y)
    best = -1e9
    for k, t in T.items():
        b = t["bounds_city"]
        if b[0] - rad <= x <= b[2] + rad and b[1] - rad <= y <= b[3] + rad:
            g = mesh(k, "lod1")
            d = np.hypot(g[..., 0] - x, g[..., 1] - y)
            m = d <= max(rad, 1.5)
            if m.any():
                best = max(best, float(g[..., 2][m].max() if rad else g[..., 2][d == d.min()][0]))
    return best


L = crs.config()["landmarks_check"]
if not pilot:
    tp = zat(L["twin_peaks"]["lon"], L["twin_peaks"]["lat"], 40)
    check(270 <= tp <= 290, f"Twin Peaks summit on mesh: {tp:.1f} m (~280)")
    md = zat(L["mt_davidson"]["lon"], L["mt_davidson"]["lat"], 40)
    check(270 <= md <= 292, f"Mt Davidson summit on mesh: {md:.1f} m (~283)")
fb = zat(L["ferry_building"]["lon"], L["ferry_building"]["lat"])
check(0 <= fb <= 4, f"Ferry Building ground on mesh: {fb:.2f} m (0-3, tolerance +1)")
lod1 = sum(int(np.load(PROC / "tiles" / k / "mesh_terrain_lod1.npz")["sizes"].size) for k in T) * 2
print(f"terrain LOD1 triangles: {lod1:,}")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
