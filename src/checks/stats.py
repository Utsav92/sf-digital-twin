"""City-wide totals: tiles, triangles per layer/LOD, file sizes, build times -> out/city/stats.json"""
import glob, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa
ROOT = crs.ROOT
idx = json.loads((ROOT / "data/processed/tile_index.json").read_text())
tot, tsec, maxtile = {}, 0.0, (0, "")
for f in glob.glob(str(ROOT / "data/processed/tiles/*/mesh_*.done.json")):
    layer = Path(f).name.split("_")[1].split(".")[0]
    d = json.loads(Path(f).read_text())
    tsec += d.get("seconds", 0)
    for lod in ("lod1", "lod0"):
        if lod in d:
            tot[f"{layer}_{lod}"] = tot.get(f"{layer}_{lod}", 0) + d[lod].get("ntris", 0)
bsec, blend_bytes = 0.0, 0
for f in glob.glob(str(ROOT / "out/tiles/*/build.json")):
    d = json.loads(Path(f).read_text())
    bsec += d["seconds"]
    blend_bytes += d.get("blend_bytes", 0)
    if d["tris_total"] > maxtile[0]:
        maxtile = (d["tris_total"], d["id"])
lm = json.loads((ROOT / "data/processed/landmarks_report.json").read_text())
lm_tris = sum(json.loads(str(__import__("numpy").load(f)["meta"]))["ntris"]
              for f in glob.glob(str(ROOT / "data/processed/tiles/*/mesh_landmarks_lod1.npz")))
du = lambda p: sum(f.stat().st_size for f in Path(p).rglob("*") if f.is_file())
st = {"tiles_total": len(idx["tiles"]), "tiles_built": sum(t["status"] == "build" for t in idx["tiles"].values()),
      "tiles_skipped_water": sum(t["status"] == "skip_water" for t in idx["tiles"].values()),
      "triangles": {**tot, "landmarks_lod1": lm_tris},
      "triangles_lod1_total": sum(v for k, v in tot.items() if k.endswith("lod1")) + lm_tris,
      "triangles_lod0_total": sum(v for k, v in tot.items() if k.endswith("lod0")) + lm_tris,
      "heaviest_tile": {"id": maxtile[1], "tris": maxtile[0]},
      "mesh_cpu_seconds": round(tsec, 1), "blender_build_cpu_seconds": round(bsec, 1),
      "bytes": {"data_raw": du(ROOT / "data/raw"), "data_processed": du(ROOT / "data/processed"),
                "out_tiles": du(ROOT / "out/tiles"), "out_unreal": du(ROOT / "out/unreal")},
      "landmarks": {k: v for k, v in lm.items() if k != "tiles"}}
(ROOT / "out/city/stats.json").write_text(json.dumps(st, indent=1))
print(json.dumps(st, indent=1))
