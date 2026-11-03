"""Phase 11 (prep side): instance transform CSVs + city manifest for Unreal (and the master .blend).

Coordinate conventions (also written into the manifest):
  city frame  : metres, x = east, y = north, z = up (NAVD88), origin = Ferry Building
  Unreal      : centimetres, left-handed: UE.X = east*100, UE.Y = -north*100, UE.Z = up*100
                (identical to what Unreal's USD importer does with a Z-up, metersPerUnit=1 stage)
  world       : EPSG:26910 UTM metres = city + origin_world_xy
Outputs:
  out/unreal/instances/<tile>_trees.csv   x_cm,y_cm,z_cm,yaw_deg,scale_x,scale_y,scale_z,species,source
  out/city/manifest.json                  per tile: bounds, offsets, files, counts, triangle budgets
python src/prep/export_manifest.py [--pilot|--tiles ..]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from prep.prep_tiles import select_tiles  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"
SPECIES = ["broadleaf", "conifer", "palm"]


def ue(xyz):
    xyz = np.asarray(xyz, float)
    return np.c_[xyz[..., 0] * 100, -xyz[..., 1] * 100, xyz[..., 2] * 100]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tiles")
    a = ap.parse_args()
    idx = json.loads((PROC / "tile_index.json").read_text())
    T = select_tiles(idx, a.pilot, a.tiles)
    ox, oy = crs.origin_world()
    man = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S"), "crs": idx["crs"],
           "origin": idx["origin"], "tile_size_m": idx["tile_size_m"],
           "conventions": {"city": "m, x east, y north, z up NAVD88, origin Ferry Building",
                           "unreal": "cm, UE.X=east*100, UE.Y=-north*100, UE.Z=up*100",
                           "world": "EPSG:26910 = city + origin.world_xy"},
           "tiles": {}, "landmarks": {}}
    idir = ROOT / "out/unreal/instances"
    idir.mkdir(parents=True, exist_ok=True)
    tot_trees = 0
    for t in T:
        k = t["id"]
        off = np.array(t["offset_city"])
        d = np.load(PROC / "tiles" / k / "mesh_trees_lod1.npz")
        n = len(d["verts"])
        if n:
            p = d["verts"] + off
            u = ue(p)
            yaw = np.degrees(d["p_rot"])
            sc = d["p_scale"]
            rows = np.c_[u.round(1), yaw.round(1), sc.round(2)]
            with open(idir / f"{k}_trees.csv", "w") as f:
                f.write("x_cm,y_cm,z_cm,yaw_deg,crown_radius_m,crown_radius_m2,height_m,species,source\n")
                for r, c, s in zip(rows, d["p_cls"], d["p_src"]):
                    f.write(",".join(f"{v:g}" for v in r) + f",{SPECIES[c]},{'procedural' if s else 'data'}\n")
        tot_trees += n
        build = json.loads((ROOT / "out/tiles" / k / "build.json").read_text()) \
            if (ROOT / "out/tiles" / k / "build.json").exists() else {}
        usd = ROOT / "out/unreal/tiles" / k / f"{k}.usdc"
        man["tiles"][k] = {
            "name": t["name"], "i": t["i"], "j": t["j"], "bounds_city_m": t["bounds_city"],
            "offset_city_m": t["offset_city"], "offset_world_utm": [off[0] + ox, off[1] + oy, 0.0],
            "unreal_location_cm": ue(off)[0].round(1).tolist(), "pilot": t["pilot"],
            "files": {"blend": f"out/tiles/{k}/{k}.blend", "usd": f"out/unreal/tiles/{k}/{k}.usdc"
                      if usd.exists() else None, "trees_csv": f"out/unreal/instances/{k}_trees.csv" if n else None},
            "counts": {"trees": n, "buildings": json.loads((PROC / "tiles" / k / "mesh_buildings.done.json")
                                                           .read_text())["lod1"].get("count", 0)},
            "triangles": {o: v["tris"] for o, v in build.get("objects", {}).items()},
            "lods": ["LOD0", "LOD1"],
        }
    assets = json.loads((PROC / "landmarks/assets.json").read_text())
    for name, v in assets.items():
        piv = np.array(v["pivot_city_m"])
        f = ROOT / "out/unreal/landmarks" / f"SM_Landmark_{name}.usdc"
        man["landmarks"][name] = {**v, "unreal_location_cm": ue(piv)[0].round(1).tolist(),
                                  "usd": str(f.relative_to(ROOT)) if f.exists() else None}
    out = ROOT / "out/city/manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(man, indent=1))
    print(f"manifest: {len(man['tiles'])} tiles, {len(man['landmarks'])} landmarks, {tot_trees} tree instances "
          f"-> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
