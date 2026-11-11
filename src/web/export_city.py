"""Export the whole digital twin (LOD0, all 618 tiles) to a compact web format for the three.js viewer.

  .venv/bin/python src/web/export_city.py            -> web/data/manifest.json, web/data/tiles/<id>.bin.gz, web/data/paths.json

Per tile one gzip file: uint32 header length, JSON header (padded to 4 bytes), payload. Each layer (terrain, water,
roads, buildings) is an indexed mesh: positions int16 (0.05 m units, tile-local, three.js axes: x east, y up, z = -north),
vertex colour RGB uint8 (sRGB, per face colour copied to its vertices), kind uint8 (0 ground/road, 1 wall, 2 tall glass
wall, 3 roof; drives the shader's procedural windows), uint16/uint32 triangle indices. Trees are instance arrays.
"""
import gzip
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PROC = ROOT / "data/processed"
OUT = ROOT / "web/data"
Q = 0.05  # metres per int16 unit

TERRAIN = {  # materials.SLOTS["terrain"] order -> sRGB
    0: (150, 140, 125), 1: (60, 75, 70), 2: (205, 190, 150), 3: (110, 140, 80), 4: (95, 135, 75), 5: (60, 95, 55),
    6: (135, 140, 85), 7: (115, 150, 80), 8: (110, 135, 85), 9: (100, 140, 80), 10: (125, 125, 125),
    11: (130, 125, 120), 12: (110, 105, 100), 13: (150, 135, 115), 14: (125, 110, 95), 15: (95, 120, 95),
    16: (140, 135, 125), 17: (135, 135, 135)}
ROADS = {0: (58, 58, 62), 1: (62, 62, 66), 2: (70, 70, 72), 3: (78, 78, 78), 4: (150, 140, 125), 5: (160, 158, 152),
         6: (70, 70, 74), 7: (192, 57, 43), 8: (120, 105, 90)}
WATER = (35, 90, 120)
RAIL = (60, 55, 55)
PASTEL = np.array([(236, 226, 208), (222, 205, 180), (205, 215, 215), (226, 210, 190), (190, 160, 140),
                   (215, 190, 170), (200, 205, 190), (232, 220, 200), (180, 190, 200), (210, 170, 150)], np.uint8)
BRICK = (150, 70, 55)
GLASS = np.array([(70, 95, 120), (75, 110, 100), (120, 100, 75), (130, 135, 140), (45, 55, 70)], np.uint8)
ROOF = (115, 112, 108)
ROOF_PITCH = [(150, 85, 65), (105, 100, 98)]


def h01(a, salt=0):
    a = np.asarray(a, np.uint64) * np.uint64(2654435761) + np.uint64(salt * 40503)
    a ^= a >> np.uint64(13)
    a *= np.uint64(0x85EBCA6B)
    a ^= a >> np.uint64(16)
    return (a & np.uint64(0xFFFFFF)).astype(np.float64) / float(0x1000000)


def triangulate(sizes, loops):
    """General polygon list -> (T,3) triangles (fan) and the owning face of each triangle."""
    starts = np.cumsum(sizes) - sizes
    tris, own = [], []
    for k in (3, 4):
        f = np.flatnonzero(sizes == k)
        if not len(f):
            continue
        s = starts[f]
        t = np.stack([loops[s], loops[s + 1], loops[s + 2]], 1)
        tris.append(t)
        own.append(f)
        if k == 4:
            tris.append(np.stack([loops[s], loops[s + 2], loops[s + 3]], 1))
            own.append(f)
    for f in np.flatnonzero(sizes > 4):  # rare n-gons
        s, n = starts[f], sizes[f]
        for i in range(1, n - 1):
            tris.append(np.array([[loops[s], loops[s + i], loops[s + i + 1]]]))
            own.append(np.array([f]))
    return np.concatenate(tris), np.concatenate(own)


def layer_arrays(d, face_rgb, face_kind):
    sizes, loops = d["sizes"], d["loops"].astype(np.int64)
    v = d["verts"].astype(np.float64)
    nv = len(v)
    tri, own = triangulate(sizes, loops)
    pos = np.round(np.c_[v[:, 0], v[:, 2], -v[:, 1]] / Q)
    assert np.abs(pos).max() < 32000, "position overflow"
    col = np.zeros((nv, 3), np.uint8)
    kind = np.zeros(nv, np.uint8)
    rep = np.repeat(np.arange(len(sizes)), sizes)
    col[loops] = face_rgb[rep]
    kind[loops] = face_kind[rep]
    idt = np.uint16 if nv < 65535 else np.uint32
    return dict(nv=nv, pos=pos.astype(np.int16), col=col, kind=kind, idx=tri.astype(idt).ravel(), idt=idt)


def build_layers(tdir):
    out = {}
    d = np.load(tdir / "mesh_terrain_lod0.npz")
    if len(d["sizes"]):
        tab = np.array([TERRAIN[i] for i in range(18)], np.uint8)
        cls = np.clip(d["f_cls"], 0, 17)
        out["terrain"] = layer_arrays(d, tab[cls], np.zeros(len(cls), np.uint8))
    d = np.load(tdir / "mesh_water_lod0.npz")
    if len(d["sizes"]):
        n = len(d["sizes"])
        out["water"] = layer_arrays(d, np.tile(np.array(WATER, np.uint8), (n, 1)), np.zeros(n, np.uint8))
    parts = []
    d = np.load(tdir / "mesh_roads_lod0.npz")
    if len(d["sizes"]):
        tab = np.array([ROADS[i] for i in range(9)], np.uint8)
        parts.append((d, tab[np.clip(d["f_mat"], 0, 8)], np.zeros(len(d["sizes"]), np.uint8)))
    out["roads"] = None
    for d, rgb, kd in parts:
        out["roads"] = layer_arrays(d, rgb, kd)
    d = np.load(tdir / "mesh_buildings_lod0.npz")
    if len(d["sizes"]):
        bid, mat = d["f_bid"].astype(np.int64), d["f_mat"]
        r = h01(bid)
        rgb = np.zeros((len(bid), 3), np.uint8)
        kd = np.zeros(len(bid), np.uint8)
        wall = mat == 0
        tall = mat == 2
        roof = mat == 1
        pitch = mat == 3
        pal = PASTEL[(h01(bid, 3) * len(PASTEL)).astype(int) % len(PASTEL)]
        rgb[wall] = pal[wall]
        brick = wall & (h01(bid, 5) < 0.22)
        rgb[brick] = BRICK
        rgb[tall] = GLASS[(h01(bid, 7) * len(GLASS)).astype(int) % len(GLASS)][tall]
        rgb[roof] = ROOF
        pr = np.array(ROOF_PITCH, np.uint8)[(r > 0.5).astype(int)]
        rgb[pitch] = pr[pitch]
        kd[wall] = 1
        kd[tall] = 2
        kd[roof | pitch] = 3
        out["buildings"] = layer_arrays(d, rgb, kd)
    d = np.load(tdir / "mesh_rail_lod0.npz")
    if len(d["sizes"]) and out.get("roads") is not None:
        pass  # rail ribbons are tiny; the road layer already carries bridge/rail context
    return {k: v for k, v in out.items() if v is not None}


def pad4(b):
    return b + b"\0" * (-len(b) % 4)


def write_tile(tid, tile):
    tdir = PROC / "tiles" / tid
    layers = build_layers(tdir)
    blobs, head = [], {"layers": [], "trees": None}
    off = 0

    def add(arr):
        nonlocal off
        b = pad4(arr.tobytes())
        blobs.append(b)
        o = off
        off += len(b)
        return o
    for name, L in layers.items():
        head["layers"].append({"name": name, "nv": int(L["nv"]), "ni": int(len(L["idx"])),
                               "idx": "u16" if L["idt"] == np.uint16 else "u32", "pos": add(L["pos"].ravel()),
                               "col": add(L["col"].ravel()), "kind": add(L["kind"]), "ind": add(L["idx"])})
    t = np.load(tdir / "mesh_trees_lod0.npz")
    if len(t["verts"]):
        v = t["verts"].astype(np.float32)
        p3 = np.c_[v[:, 0], v[:, 2], -v[:, 1]].astype(np.float32)
        sc = t["p_scale"].astype(np.float32)
        head["trees"] = {"n": int(len(v)), "pos": add(p3.ravel()), "scale": add(sc.ravel()),
                         "cls": add(t["p_cls"].astype(np.uint8))}
    hb = pad4(json.dumps(head).encode())
    raw = struct.pack("<I", len(hb)) + hb + b"".join(blobs)
    path = OUT / "tiles" / f"{tid}.bin.gz"
    with gzip.GzipFile(path, "wb", compresslevel=6, mtime=0) as fh:
        fh.write(raw)
    return len(raw), path.stat().st_size, sum(len(L["idx"]) // 3 for L in layers.values())


def main():
    from multiprocessing import Pool
    (OUT / "tiles").mkdir(parents=True, exist_ok=True)
    idx = json.loads((PROC / "tile_index.json").read_text())
    tiles = [t for t in idx["tiles"].values() if t["status"] == "build"]
    ids = [t["id"] for t in tiles]
    with Pool() as pool:
        res = pool.starmap(write_tile, [(t["id"], t) for t in tiles], chunksize=4)
    man = {"scale": 1.0, "axes": "three.js: x east, y up, z = -north (metres, origin Ferry Building)",
           "sea_level": 0.95, "tiles": []}
    for t, (raw, gz, ntri) in zip(tiles, res):
        cx, cy, cz = t["offset_city"]
        man["tiles"].append({"id": t["id"], "c": [cx, cz, -cy], "pilot": bool(t["pilot"]), "bytes": gz, "tris": ntri})
    (OUT / "manifest.json").write_text(json.dumps(man))
    print(f"{len(tiles)} tiles, {sum(r[2] for r in res):,} triangles, raw {sum(r[0] for r in res) / 1e6:.0f} MB, "
          f"gz {sum(r[1] for r in res) / 1e6:.0f} MB")
    # ---- flythrough paths (drone keys from the Blender rig; car route with terrain heights)
    keys = json.loads((PROC / "cine_drone_keys_180.json").read_text())
    fr = np.array(keys["frames"], float)
    eye, look = np.array(keys["eye"]), np.array(keys["look"])
    conv = lambda a: np.c_[a[:, 0], a[:, 2], -a[:, 1]].round(2).tolist()  # noqa: E731
    route = np.array(json.loads((PROC / "hero_route.json").read_text())["xy"])
    # terrain height under the route from the pilot terrain lattice (nearest vertex, then smoothed)
    pv = []
    for t in tiles:
        if t["pilot"]:
            d = np.load(PROC / "tiles" / t["id"] / "mesh_terrain_lod0.npz")
            pv.append(d["verts"] + np.array(t["offset_city"]))
    pv = np.concatenate(pv)
    cell = 8.0
    key = np.floor(pv[:, :2] / cell).astype(np.int64)
    kk = key[:, 0] * 100003 + key[:, 1]
    order = np.argsort(kk)
    kk_s, z_s = kk[order], pv[order, 2]
    def zat(p):
        k = np.floor(p / cell).astype(np.int64)
        best = None
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                q = (k[0] + dx) * 100003 + (k[1] + dy)
                lo, hi = np.searchsorted(kk_s, q), np.searchsorted(kk_s, q, "right")
                if hi > lo:
                    zz = z_s[lo:hi].mean()
                    if best is None:
                        best = []
                    best.append(zz)
        return float(np.mean(best)) if best else 0.0
    z = np.array([zat(p) for p in route])
    kz = np.exp(-0.5 * (np.arange(-12, 13) / 4.0) ** 2)
    kz /= kz.sum()
    z = np.convolve(np.pad(z, 12, mode="edge"), kz, mode="valid") + 0.12
    paths = {"drone": {"t": ((fr - 1) / 24.0).tolist(), "eye": conv(eye), "look": conv(look)},
             "car": {"xz": np.c_[route[:, 0], -route[:, 1]].round(2).tolist(), "y": z.round(2).tolist(), "step": 2.0}}
    (OUT / "paths.json").write_text(json.dumps(paths))
    print("paths: drone keys", len(fr), "car route points", len(route))


if __name__ == "__main__":
    main()
