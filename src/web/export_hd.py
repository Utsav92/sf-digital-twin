"""High-detail web export of the 16 PILOT tiles from the Blender LOD1 meshes (the standard web export uses LOD0).
  .venv/bin/python src/web/export_hd.py   -> web/data_hd/manifest.json, web/data_hd/tiles/<id>.bin.gz
Same container as export_city.py, plus: LOD1 terrain/roads/buildings, a 'details' layer (curbs, markings, crosswalks,
trim, balcony slabs, railings, sills), position quantisation 0.04 m (header field "q")."""
import gzip
import json
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import export_city as E  # noqa: E402

E.Q = 0.04
PROC, ROOT = E.PROC, E.ROOT
OUT = ROOT / "web/data_hd"
DETAIL = np.array([(150, 148, 142), (205, 205, 200), (210, 170, 50), (205, 205, 200), (165, 160, 152), (172, 167, 160),
                   (60, 62, 66), (190, 185, 175)], np.uint8)


def clip_far(d, limit=1250.0):
    """Drop faces with any vertex beyond +/-limit m of the tile centre (stray far-away detail geometry would overflow int16)."""
    v = d["verts"]
    ok_v = (np.abs(v[:, :2]) < limit).all(1)
    sizes, loops = d["sizes"], d["loops"].astype(np.int64)
    rep = np.repeat(np.arange(len(sizes)), sizes)
    face_ok = np.bincount(rep, weights=(~ok_v[loops]).astype(float), minlength=len(sizes)) == 0
    if face_ok.all():
        return d
    keep_loop = face_ok[rep]
    new_loops = loops[keep_loop]
    used, inv = np.unique(new_loops, return_inverse=True)
    out = {k: d[k] for k in d.files}
    out.update(verts=v[used], loops=inv, sizes=sizes[face_ok], f_mat=d["f_mat"][face_ok], uv=d["uv"][keep_loop])
    print(f"  clipped {int((~face_ok).sum())} far-away detail faces", flush=True)
    return out


def layers_lod1(tdir):
    out = {}
    d = np.load(tdir / "mesh_terrain_lod1.npz")
    if len(d["sizes"]):
        tab = np.array([E.TERRAIN[i] for i in range(18)], np.uint8)
        cls = np.clip(d["f_cls"], 0, 17)
        out["terrain"] = E.layer_arrays(d, tab[cls], np.zeros(len(cls), np.uint8))
    d = np.load(tdir / "mesh_water_lod1.npz")
    if len(d["sizes"]):
        n = len(d["sizes"])
        out["water"] = E.layer_arrays(d, np.tile(np.array(E.WATER, np.uint8), (n, 1)), np.zeros(n, np.uint8))
    d = np.load(tdir / "mesh_roads_lod1.npz")
    if len(d["sizes"]):
        tab = np.array([E.ROADS[i] for i in range(9)], np.uint8)
        out["roads"] = E.layer_arrays(d, tab[np.clip(d["f_mat"], 0, 8)], np.zeros(len(d["sizes"]), np.uint8))
    d = np.load(tdir / "mesh_buildings_lod1.npz")
    if len(d["sizes"]):
        bid, mat = d["f_bid"].astype(np.int64), d["f_mat"]
        r = E.h01(bid)
        rgb = np.zeros((len(bid), 3), np.uint8); kd = np.zeros(len(bid), np.uint8)
        wall, tall, roof, pitch = mat == 0, mat == 2, mat == 1, mat == 3
        pal = E.PASTEL[(E.h01(bid, 3) * len(E.PASTEL)).astype(int) % len(E.PASTEL)]
        rgb[wall] = pal[wall]
        brick = wall & (E.h01(bid, 5) < 0.22)
        rgb[brick] = E.BRICK
        rgb[tall] = E.GLASS[(E.h01(bid, 7) * len(E.GLASS)).astype(int) % len(E.GLASS)][tall]
        rgb[roof] = E.ROOF
        rgb[pitch] = np.array(E.ROOF_PITCH, np.uint8)[(r > 0.5).astype(int)][pitch]
        kd[wall] = 1; kd[tall] = 2; kd[roof | pitch] = 3
        out["buildings"] = E.layer_arrays(d, rgb, kd)
    d = np.load(tdir / "mesh_details_lod1.npz")
    d = clip_far(d) if len(d["sizes"]) else d
    if len(d["sizes"]):
        out["details"] = E.layer_arrays(d, DETAIL[np.clip(d["f_mat"], 0, 7)], np.zeros(len(d["sizes"]), np.uint8))
    return out


def write_tile(tid):
    tdir = PROC / "tiles" / tid
    layers = layers_lod1(tdir)
    blobs, head, off = [], {"layers": [], "trees": None, "q": E.Q}, 0

    def add(arr):
        nonlocal off
        b = E.pad4(arr.tobytes()); blobs.append(b); o = off; off += len(b); return o
    for name, L in layers.items():
        head["layers"].append({"name": name, "nv": int(L["nv"]), "ni": int(len(L["idx"])), "idx": "u16" if L["idt"] == np.uint16 else "u32",
                               "pos": add(L["pos"].ravel()), "col": add(L["col"].ravel()), "kind": add(L["kind"]), "ind": add(L["idx"])})
    t = np.load(tdir / "mesh_trees_lod1.npz")
    if len(t["verts"]):
        v = t["verts"].astype(np.float32)
        head["trees"] = {"n": int(len(v)), "pos": add(np.c_[v[:, 0], v[:, 2], -v[:, 1]].astype(np.float32).ravel()),
                         "scale": add(t["p_scale"].astype(np.float32).ravel()), "cls": add(t["p_cls"].astype(np.uint8))}
    hb = E.pad4(json.dumps(head).encode())
    raw = struct.pack("<I", len(hb)) + hb + b"".join(blobs)
    path = OUT / "tiles" / f"{tid}.bin.gz"
    with gzip.GzipFile(path, "wb", compresslevel=6, mtime=0) as fh:
        fh.write(raw)
    return len(raw), path.stat().st_size, {k: len(L["idx"]) // 3 for k, L in layers.items()}


def main():
    from multiprocessing import Pool
    (OUT / "tiles").mkdir(parents=True, exist_ok=True)
    idx = json.loads((PROC / "tile_index.json").read_text())
    tiles = [t for t in idx["tiles"].values() if t["status"] == "build" and t["pilot"]]
    with Pool(4) as pool:
        res = pool.map(write_tile, [t["id"] for t in tiles])
    man = {"scale": 1.0, "axes": "three.js: x east, y up, z = -north (metres, origin Ferry Building)", "q": E.Q, "tiles": []}
    for t, (raw, gz, tr) in zip(tiles, res):
        cx, cy, cz = t["offset_city"]
        man["tiles"].append({"id": t["id"], "c": [cx, cz, -cy], "bytes": gz, "tris": sum(tr.values()), "layers": tr})
    (OUT / "manifest.json").write_text(json.dumps(man))
    print(f"{len(tiles)} pilot tiles, {sum(sum(r[2].values()) for r in res):,} triangles, raw {sum(r[0] for r in res) / 1e6:.0f} MB, gz {sum(r[1] for r in res) / 1e6:.0f} MB")


if __name__ == "__main__":
    main()
