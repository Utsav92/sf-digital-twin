"""Mesh interchange between prep (numpy/shapely) and Blender builders (numpy only).

npz layout (all tile-local meters, Z up):
  verts       float32 (V, 3)
  loops       int32   (L,)       vertex index per face corner
  sizes       int32   (P,)       corners per polygon (3 or 4 or n)
  f_<name>    (P,)               per-face attribute (int32 / float32)
  v_<name>    (V,)               per-vertex attribute
  meta        json string
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np


class MeshBuf:
    """Accumulates polygons from many parts; vertex indices are offset automatically."""

    def __init__(self):
        self.v, self.l, self.s, self.fa, self.uv = [], [], [], {}, []
        self.nv = 0

    def add(self, verts, faces, uv=None, **face_attrs):
        """verts (n,3); faces either (m,k) array or list of index lists; uv optional (L,2) per corner."""
        verts = np.asarray(verts, np.float64)
        if len(verts) == 0:
            return
        if isinstance(faces, np.ndarray) and faces.ndim == 2:
            loops = faces.ravel() + self.nv
            sizes = np.full(len(faces), faces.shape[1], np.int32)
        else:
            loops = np.concatenate([np.asarray(f) for f in faces]) + self.nv
            sizes = np.array([len(f) for f in faces], np.int32)
        self.v.append(verts)
        self.uv.append(None if uv is None else np.asarray(uv, np.float32).reshape(-1, 2))
        self.l.append(loops.astype(np.int32))
        self.s.append(sizes)
        for k, val in face_attrs.items():
            self.fa.setdefault(k, []).append(np.broadcast_to(np.asarray(val), (len(sizes),)).copy())
        self.nv += len(verts)

    @property
    def npoly(self):
        return int(sum(len(s) for s in self.s))

    def arrays(self):
        if not self.v:
            return None
        out = {"verts": np.concatenate(self.v).astype(np.float32),
               "loops": np.concatenate(self.l), "sizes": np.concatenate(self.s)}
        for k, parts in self.fa.items():
            out["f_" + k] = np.concatenate(parts)
        if any(u is not None for u in self.uv):  # corners without explicit UVs get planar XY
            uv = []
            for v, l, u in zip(self.v, self.l, self.uv):
                uv.append(u if u is not None else np.zeros((len(l), 2), np.float32) * np.nan)
            out["uv"] = np.concatenate(uv)
        return out


def planar_uv(arrays: dict, offset_xy) -> None:
    """Fill missing per-corner UVs with city-frame XY (metres) so textures run continuously across tiles."""
    loops = arrays["loops"]
    if not len(loops):
        return
    xy = arrays["verts"][loops, :2].astype(np.float64) + np.asarray(offset_xy[:2])
    uv = arrays.get("uv")
    if uv is None:
        arrays["uv"] = xy.astype(np.float32)
    else:
        bad = ~np.isfinite(uv).all(1)
        uv[bad] = xy[bad]
        arrays["uv"] = uv.astype(np.float32)


def save(path: Path, arrays: dict | None, meta: dict) -> dict:
    path = Path(path)
    if arrays is None:
        arrays = {"verts": np.zeros((0, 3), np.float32), "loops": np.zeros(0, np.int32),
                  "sizes": np.zeros(0, np.int32)}
    meta = {**meta, "nverts": int(len(arrays["verts"])), "npolys": int(len(arrays["sizes"])),
            "ntris": int(np.maximum(arrays["sizes"] - 2, 0).sum())}
    tmp = path.with_name(f".{path.stem}.{os.getpid()}.tmp.npz")
    np.savez_compressed(tmp, meta=np.array(json.dumps(meta)), **arrays)
    os.replace(tmp, path)
    return meta
