"""Driver (prep venv): run headless Blender tile builders in parallel, batching tiles per process.

python src/blender/build_tiles.py [--pilot|--tiles ..] [--procs N] [--batch 8] [--force]
Skips tiles whose build.json is newer than all their mesh_*.npz inputs (unless --force).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402
from prep.prep_tiles import select_tiles  # noqa: E402

ROOT = crs.ROOT
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")


def stale(t) -> bool:
    b = ROOT / "out/tiles" / t["id"] / "build.json"
    if not b.exists():
        return True
    newest = max((p.stat().st_mtime for p in (ROOT / "data/processed/tiles" / t["id"]).glob("mesh_*.npz")),
                 default=0)
    srcs = [ROOT / "src/blender" / f for f in ("build_tile.py", "materials.py", "bpy_common.py",
                                                  "trees_instancing.py")]
    newest = max([newest] + [p.stat().st_mtime for p in srcs if p.exists()])
    return b.stat().st_mtime < newest


def run(batch, k):
    log = ROOT / "logs/build" / f"batch_{k:04d}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with open(log, "w") as f:
        rc = subprocess.call([BLENDER, "-b", "--factory-startup", "-P", str(ROOT / "src/blender/build_tile.py"),
                              "--", "--tiles", ",".join(t["id"] for t in batch)], stdout=f, stderr=subprocess.STDOUT)
    return rc, batch, time.time() - t0, log


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", action="store_true")
    ap.add_argument("--tiles")
    ap.add_argument("--procs", type=int, default=crs.config()["parallel"]["blender_procs"])
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    index = json.loads((ROOT / "data/processed/tile_index.json").read_text())
    T = select_tiles(index, a.pilot, a.tiles)
    todo = [t for t in T if a.force or stale(t)]
    batches = [todo[i:i + a.batch] for i in range(0, len(todo), a.batch)]
    print(f"build {len(todo)}/{len(T)} tiles in {len(batches)} batches, {a.procs} Blender procs", flush=True)
    t0, fails = time.time(), []
    with ThreadPoolExecutor(a.procs) as ex:
        for k, (rc, batch, dt, log) in enumerate(ex.map(lambda kb: run(kb[1], kb[0]), enumerate(batches))):
            ok = [t["id"] for t in batch if (ROOT / "out/tiles" / t["id"] / "build.json").exists()]
            if rc != 0:
                fails.append(str(log))
            print(f"  batch {k + 1}/{len(batches)} rc={rc} {dt:.0f}s ({len(ok)}/{len(batch)} ok)", flush=True)
    print(f"done in {time.time() - t0:.0f} s; failed batches: {fails}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
