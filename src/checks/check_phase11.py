"""Phase 11: verify the Unreal export with pxr (Unreal itself is not installed on this machine, so the
in-engine import check is deferred; this checks everything the USD files themselves must guarantee).
- stage: metersPerUnit == 1, upAxis Z
- every mesh triangulated (Nanite-friendly, no n-gons), has UVs; buildings carry the 'Col' primvar
- every bound material name is an Unreal master-material name from config/unreal_materials.json
- tile geometry bounds == source mesh bounds (npz) within 1 cm
- hero landmarks: pivot + USD extent reproduces the in-city landmark top (Salesforce 326 m) within 10 cm,
  and manifest unreal_location_cm == (x*100, -y*100, z*100) of the pivot
"""
import json
import sys
from pathlib import Path

import numpy as np
from pxr import Usd, UsdGeom, UsdShade

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import crs  # noqa: E402

ROOT = crs.ROOT
PROC = ROOT / "data/processed"
man = json.loads((ROOT / "out/city/manifest.json").read_text())
MATS = set(v for k, v in json.loads((ROOT / "config/unreal_materials.json").read_text()).items() if k != "comment")
fails = []


def check(ok, msg):
    print(("PASS " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


def stage_info(path):
    st = Usd.Stage.Open(str(path))
    meshes, ngon, nouv, mats, pts = 0, 0, 0, set(), []
    col = 0
    for prim in st.Traverse():
        if prim.IsA(UsdGeom.Mesh):
            m = UsdGeom.Mesh(prim)
            meshes += 1
            c = np.array(m.GetFaceVertexCountsAttr().Get())
            ngon += int((c != 3).sum())
            pv = UsdGeom.PrimvarsAPI(prim)
            nouv += not any(p.GetTypeName().role == "TextureCoordinate" for p in pv.GetPrimvars())
            col += pv.HasPrimvar("Col")
            xf = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            p = np.array(m.GetPointsAttr().Get())
            p = np.c_[p, np.ones(len(p))] @ np.array(xf)
            pts.append(p[:, :3])
            b = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
            if b:
                mats.add(b.GetPrim().GetName())
            for sub in prim.GetChildren():  # GeomSubsets carry per-face material bindings
                sb = UsdShade.MaterialBindingAPI(sub).ComputeBoundMaterial()[0]
                if sb:
                    mats.add(sb.GetPrim().GetName())
    P = np.concatenate(pts) if pts else np.zeros((0, 3))
    return st, meshes, ngon, nouv, col, mats, P


tiles = {k: t for k, t in man["tiles"].items() if t["files"]["usd"]}
bad_units = bad_tri = bad_uv = bad_mat = bad_bbox = no_col = 0
unknown = set()
for k, t in tiles.items():
    st, nm, ngon, nouv, col, mats, P = stage_info(ROOT / t["files"]["usd"])
    bad_units += not (abs(UsdGeom.GetStageMetersPerUnit(st) - 1.0) < 1e-9 and UsdGeom.GetStageUpAxis(st) == "Z")
    bad_tri += ngon > 0
    bad_uv += nouv > 0
    unknown |= mats - MATS
    # source bounds from the LOD1 npz layers that were exported
    src = []
    for layer in ("terrain", "water", "roads", "rail", "buildings", "landmarks"):
        f = PROC / "tiles" / k / f"mesh_{layer}_lod1.npz"
        if f.exists():
            v = np.load(f)["verts"]
            if len(v):
                src.append(v)
    S = np.concatenate(src)
    if len(P) == 0 or np.abs(P.min(0) - S.min(0)).max() > 0.01 or np.abs(P.max(0) - S.max(0)).max() > 0.01:
        bad_bbox += 1
        print(f"   bbox mismatch {k}: usd {P.min(0).round(2)}..{P.max(0).round(2)} src {S.min(0).round(2)}.."
              f"{S.max(0).round(2)}")
    no_col += col == 0
n = len(tiles)
check(bad_units == 0, f"tile stages metersPerUnit=1, upAxis=Z: {n - bad_units}/{n}")
check(bad_tri == 0, f"tiles fully triangulated (no n-gons): {n - bad_tri}/{n}")
check(bad_uv == 0, f"every mesh has UVs: {n - bad_uv}/{n}")
check(not unknown, f"all material names are Unreal master materials (unknown: {sorted(unknown)[:6]})")
check(bad_bbox == 0, f"tile geometry bounds match source within 1 cm: {n - bad_bbox}/{n}")
check(no_col == 0, f"vertex colour primvar 'Col' present in every tile: {n - no_col}/{n}")

# hero landmark placement
lm = man["landmarks"]
st, nm, ngon, nouv, col, mats, P = stage_info(ROOT / lm["salesforce"]["usd"])
piv = np.array(lm["salesforce"]["pivot_city_m"])
top_world = piv[2] + P[:, 2].max()
x, y = crs.lonlat_to_city(-122.39694, 37.78977)
V = []
rep = json.loads((PROC / "landmarks_report.json").read_text())
idx = json.loads((PROC / "tile_index.json").read_text())
for k in rep["tiles"]:
    d = np.load(PROC / "tiles" / k / "mesh_landmarks_lod1.npz")["verts"] + np.array(idx["tiles"][k]["offset_city"])
    V.append(d)
V = np.concatenate(V)
near = np.hypot(V[:, 0] - float(x), V[:, 1] - float(y)) < 40
check(abs(top_world - V[near, 2].max()) < 0.10, f"Salesforce hero asset top {top_world:.2f} m vs in-city mesh "
      f"{V[near, 2].max():.2f} m (<10 cm)")
cxy = piv[:2] + (P[:, :2].min(0) + P[:, :2].max(0)) / 2
check(np.hypot(*(cxy - V[near, :2].mean(0))) < 1.0, f"Salesforce hero asset XY centre offset "
      f"{np.hypot(*(cxy - V[near, :2].mean(0))):.2f} m")
ue = lm["salesforce"]["unreal_location_cm"]
check(np.allclose(ue, [piv[0] * 100, -piv[1] * 100, piv[2] * 100], atol=0.2), f"manifest UE location {ue} cm")
check(ngon == 0 and nouv == 0, "landmark asset triangulated with UVs")
print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
