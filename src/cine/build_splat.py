"""Build a 3D Gaussian splat of the digital twin from Blender capture views (no training needed: the twin
gives exact geometry and a calibrated, depth-exact render for every view).

  blender ... render_city.py -- --splat-capture data/splat   (writes views/*.npz, images/*.png, transforms.json)
  .venv/bin/python src/cine/build_splat.py data/splat out/splat/sf_twin_pilot

Per view: decode the hi/lo depth, back-project every pixel to a world point (colour = the lit AgX render),
estimate normals from the depth image, drop silhouette/grazing pixels, then merge all views by voxel
(aerial views 1.0 m, street views 0.3 m by default). Each voxel becomes one Gaussian: a flat disc oriented to the
surface normal (scale 0.6 v in-plane, 0.08 v along the normal), opacity 0.92, SH DC colour. Writes a standard
3DGS .ply (Y-down, like COLMAP-trained splats) and the compact antimatter15 .splat format.
"""
import json
import sys
from pathlib import Path

import numpy as np

C0 = 0.28209479177387814
BOX = (-1560.0, -1060.0, 560.0, 1060.0)  # pilot extent + margin (city frame, m)
Z_RANGE = (-30.0, 420.0)


def view_points(f, vox_aerial, vox_street, vox_fill=0.5):
    d = np.load(f)
    code = d["code"].astype(np.float32)
    H, W = int(d["H"]), int(d["W"])
    fx, eye, Rm, rgb = float(d["fx"]), d["eye"], d["R"], d["rgb"]
    tag = str(d["tag"])
    vox = vox_street if tag.startswith("street") else (vox_fill if tag.startswith("fill") else vox_aerial)
    alpha = code[:, :, 3] > 0.5
    dist = 32.0 * (code[:, :, 0] + code[:, :, 1])
    jj, ii = np.mgrid[0:H, 0:W]
    dc = np.stack([(ii + 0.5 - W / 2) / fx, (jj + 0.5 - H / 2) / fx, -np.ones_like(dist)], -1)
    dc /= np.linalg.norm(dc, axis=-1, keepdims=True)
    dw = dc @ Rm.T
    P = eye + dist[..., None] * dw
    # normals from the depth image (central differences), oriented towards the camera
    dxv = P[1:-1, 2:] - P[1:-1, :-2]
    dyv = P[2:, 1:-1] - P[:-2, 1:-1]
    n = np.cross(dxv, dyv)
    nl = np.linalg.norm(n, axis=-1, keepdims=True)
    n = n / np.maximum(nl, 1e-12)
    inner = (slice(1, -1), slice(1, -1))
    toward = (eye - P[inner])
    flip = (n * toward).sum(-1) < 0
    n[flip] *= -1
    cosv = np.abs((n * dw[inner]).sum(-1))
    dd = dist
    jump = np.zeros_like(dd, bool)
    for a_, b_ in (((slice(1, -1), slice(2, None)), inner), ((slice(1, -1), slice(None, -2)), inner),
                   ((slice(2, None), slice(1, -1)), inner), ((slice(None, -2), slice(1, -1)), inner)):
        jump[b_] |= np.abs(dd[a_] - dd[b_]) > 0.06 * dd[b_] + 0.05
    ok = np.zeros_like(alpha)
    ok[inner] = alpha[inner] & ~jump[inner] & (cosv > 0.14) & (nl[..., 0] > 0)
    ok &= (dist < 1800.0)
    pts = P[ok]
    m = (pts[:, 0] > BOX[0]) & (pts[:, 0] < BOX[2]) & (pts[:, 1] > BOX[1]) & (pts[:, 1] < BOX[3]) & \
        (pts[:, 2] > Z_RANGE[0]) & (pts[:, 2] < Z_RANGE[1])
    pts = pts[m]
    nn = np.zeros_like(P)
    nn[inner] = n
    nrm = nn[ok][m]
    col = rgb[ok][m].astype(np.float32)
    return pts, nrm, col, vox


def quantize(pts, vox):
    q = np.floor(pts / vox).astype(np.int64) + (1 << 20)
    return (q[:, 0] << 42) | (q[:, 1] << 21) | q[:, 2]


class Acc:
    """Voxel accumulator: running sums of position, normal and colour per voxel key."""

    def __init__(self):
        self.k = np.zeros(0, np.int64)
        self.s = np.zeros((0, 10))  # pos3, nrm3, col3, count

    def add(self, keys, pts, nrm, col):
        u, inv = np.unique(keys, return_inverse=True)
        cols = np.concatenate([pts, nrm, col, np.ones((len(pts), 1))], 1)
        s = np.stack([np.bincount(inv, weights=cols[:, c], minlength=len(u)) for c in range(10)], 1)
        self.k = np.concatenate([self.k, u])
        self.s = np.concatenate([self.s, s])
        if len(self.k) > 6_000_000:
            self.compact()

    def compact(self):
        u, inv = np.unique(self.k, return_inverse=True)
        s = np.stack([np.bincount(inv, weights=self.s[:, c], minlength=len(u)) for c in range(10)], 1)
        self.k, self.s = u, s


def quat_mul(a, b):
    w1, x1, y1, z1 = a.T
    w2, x2, y2, z2 = b.T
    return np.stack([w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
                     w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2, w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2], 1)


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    va = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    vs = float(sys.argv[4]) if len(sys.argv) > 4 else 0.3
    files = sorted((src / "views").glob("*.npz"))
    vf = float(sys.argv[5]) if len(sys.argv) > 5 else 0.5
    acc = {va: Acc(), vs: Acc(), vf: Acc()} if vf not in (va, vs) else {va: Acc(), vs: Acc()}
    raw = 0
    for i, f in enumerate(files):
        pts, nrm, col, vox = view_points(f, va, vs, vf)
        raw += len(pts)
        if len(pts):
            acc[vox].add(quantize(pts, vox), pts, nrm, col)
        if i % 20 == 0:
            print(f"view {i}/{len(files)} raw={raw:,}", flush=True)
    P, N, Cc, V = [], [], [], []
    for vox, a in acc.items():
        a.compact()
        c = a.s[:, 9:10]
        P.append(a.s[:, 0:3] / c)
        n = a.s[:, 3:6]
        N.append(n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9))
        Cc.append(a.s[:, 6:9] / c)
        V.append(np.full(len(c), vox))
    P, N, Cc, V = (np.concatenate(x) for x in (P, N, Cc, V))
    G = len(P)
    print(f"{G:,} Gaussians from {raw:,} pixels ({len(files)} views)", flush=True)
    # orientation: +Z axis of the disc -> surface normal
    z = np.array([0, 0, 1.0])
    ax = np.cross(z, N)
    an = np.linalg.norm(ax, axis=1)
    ang = np.arccos(np.clip(N[:, 2], -1, 1))
    axu = ax / np.maximum(an, 1e-9)[:, None]
    q = np.c_[np.cos(ang / 2), axu * np.sin(ang / 2)[:, None]]
    flat = an < 1e-6
    q[flat] = np.where((N[flat, 2:3] > 0), np.array([1.0, 0, 0, 0]), np.array([0.0, 1, 0, 0]))
    # Z-up city frame -> Y-down (COLMAP-like) viewer frame: rotation +90 deg about X
    s2 = np.sqrt(0.5)
    qm = np.tile(np.array([s2, s2, 0, 0]), (G, 1))
    q = quat_mul(qm, q)
    q /= np.linalg.norm(q, axis=1, keepdims=True)
    Pv = np.c_[P[:, 0], -P[:, 2], P[:, 1]]
    Nv = np.c_[N[:, 0], -N[:, 2], N[:, 1]]
    rgb = np.clip(Cc / 255.0, 0, 1)
    f_dc = (rgb - 0.5) / C0
    op = np.full(G, np.log(0.92 / 0.08))
    sc = np.log(np.c_[0.6 * V, 0.6 * V, 0.08 * V])
    out.parent.mkdir(parents=True, exist_ok=True)
    dt = np.dtype([(n, "<f4") for n in ("x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2", "opacity",
                                         "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3")])
    arr = np.empty(G, dt)
    for k, v in zip(dt.names, np.c_[Pv, Nv, f_dc, op, sc, q].T):
        arr[k] = v
    ply = out.with_suffix(".ply")
    with open(ply, "wb") as fh:
        fh.write(("ply\nformat binary_little_endian 1.0\nelement vertex %d\n" % G +
                  "".join(f"property float {n}\n" for n in dt.names) + "end_header\n").encode())
        fh.write(arr.tobytes())
    # .splat (antimatter15): pos f32x3, scale f32x3 (linear), rgba u8x4, rot u8x4 ; sorted by size/opacity
    order = np.argsort(-(np.exp(sc).sum(1)))
    sp = np.empty(G, np.dtype([("p", "<f4", 3), ("s", "<f4", 3), ("c", "u1", 4), ("r", "u1", 4)]))
    sp["p"], sp["s"] = Pv[order], np.exp(sc)[order]
    sp["c"] = np.c_[np.round(rgb * 255), np.full(G, 235)][order].astype(np.uint8)
    sp["r"] = np.clip(np.round(q[order] * 128 + 128), 0, 255).astype(np.uint8)
    sp_path = out.with_suffix(".splat")
    sp_path.write_bytes(sp.tobytes())
    # quick top-down preview straight from the Gaussians (colour of the highest point per pixel)
    S = 2400
    x0, y0, x1, y1 = BOX
    ix = np.clip(((P[:, 0] - x0) / (x1 - x0) * (S - 1)).astype(int), 0, S - 1)
    iy = np.clip(((P[:, 1] - y0) / (y1 - y0) * (S - 1)).astype(int), 0, S - 1)
    o = np.argsort(P[:, 2])
    img = np.zeros((S, S, 3), np.uint8)
    img[iy[o], ix[o]] = np.clip(Cc[o], 0, 255).astype(np.uint8)
    np.save(out.with_name(out.name + "_topdown.npy"), img[::-1])
    print(f"wrote {ply} ({ply.stat().st_size / 1e6:.0f} MB), {sp_path} ({sp_path.stat().st_size / 1e6:.0f} MB)")
    json.dump({"gaussians": int(G), "views": len(files), "voxel_aerial_m": va, "voxel_street_m": vs,
               "frame": "Y-down (COLMAP-like): x=east, y=-up, z=north; origin = Ferry Building",
               "bounds_city_m": BOX}, open(out.with_suffix(".json"), "w"), indent=1)


if __name__ == "__main__":
    main()
