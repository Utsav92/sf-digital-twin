"""Phase 6: rail for one tile. f_mat -> materials.SLOTS["rail"]: 0 track/ballast, 1 embedded street track
(cable car / streetcar / surface light rail), 2 bridge structure.
Ground rail is clipped to the tile, densified every 3 m and draped as a ribbon; tunnels are omitted;
bridges reuse the global deck profiles (geom.roads.bridges with rail=True)."""
from __future__ import annotations

import numpy as np
import shapely

from geom import roadclass as rc
from geom.drape import densify_line, lines_of, ribbon
from geom.meshio import MeshBuf
from geom.roads import bridges

STYLE = {  # system/railway -> (width m, z offset, material)
    "cable_car": (1.7, 0.16, 1), "muni_streetcar": (1.7, 0.16, 1), "tram": (1.7, 0.16, 1),
    "light_rail": (1.9, 0.16, 1), "rail": (3.6, 0.25, 0), "subway": (3.6, 0.25, 0),
    "funicular": (2.0, 0.2, 0), "narrow_gauge": (3.0, 0.25, 0), "monorail": (1.5, 0.3, 0),
}


def build(ctx) -> dict:
    r = ctx.read("rail")
    out = {}
    for lod, step, sampler in (("lod1", 3.0, ctx.ground), ("lod0", 10.0, ctx.ground0)):
        buf = MeshBuf()
        for row in r.itertuples():
            if rc.tag(row.tunnel) not in (None, "no") or rc.tag(row.bridge) not in (None, "no"):
                continue
            if rc.tag(getattr(row, "covered", None)) == "yes" or (rc.tag(row.layer) or "").startswith("-"):
                continue
            key = row.system if row.system in STYLE else row.railway
            if key not in STYLE:
                continue
            w, zo, mat = STYLE[key]
            if lod == "lod0":
                w, zo = w * 2, zo + 0.4
            for ln in lines_of(row.geometry):
                p = densify_line(ln, step)
                if len(p) < 2:
                    continue
                xy = p - (ctx.wx, ctx.wy)
                v, q = ribbon(xy, w, sampler(xy[:, 0], xy[:, 1]) + zo)
                buf.add(v, q, mat=np.int32(mat))
        if lod == "lod1":
            bridges(ctx, buf, rail=True)
        out[lod] = (buf.arrays(), {"layer": "rail", "lod": lod})
    return out
