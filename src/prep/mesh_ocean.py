"""Far-ocean plane for distant views: 60 x 60 km square at sea level - 0.05 m, minus all built tiles
(built tiles carry their own water at sea level). City frame coordinates.
Writes data/processed/city_ocean.npz"""
import json, sys
from pathlib import Path
import numpy as np, shapely
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa
from geom import meshio  # noqa
from geom.polytri import triangulate  # noqa
PROC = crs.ROOT / "data/processed"
idx = json.loads((PROC / "tile_index.json").read_text())
sea = json.loads((PROC / "dem/dem_meta.json").read_text())["sea_level_navd88"]
built = shapely.union_all([shapely.box(*t["bounds_city"]) for t in idx["tiles"].values() if t["status"] == "build"])
far = shapely.box(-30000, -30000, 30000, 30000).difference(built)
v, f = triangulate(far)
arr = {"verts": np.c_[v, np.full(len(v), sea - 0.05)].astype(np.float32), "loops": f.ravel().astype(np.int32),
       "sizes": np.full(len(f), 3, np.int32), "f_mat": np.zeros(len(f), np.int32)}
print(meshio.save(PROC / "city_ocean.npz", arr, {"layer": "ocean"}))
