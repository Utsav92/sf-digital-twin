"""Build out/city/sf_materials.blend: every material (procedural + CC0-textured PBR) and shared node group
in ONE file. Tile builders link materials from it, so a city render loads each texture exactly once.
blender -b --factory-startup -P src/blender/build_material_library.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from bpy_common import ROOT, reset_scene, save_blend_atomic  # noqa: E402
import materials  # noqa: E402

reset_scene()
names = sorted(set(materials.LIB) | set(materials.SPECIAL))
for n in names:
    m = materials.get_mat(n, local=True)
    m.use_fake_user = True
materials.globals_group().use_fake_user = True
out = ROOT / "out/city/sf_materials.blend"
save_blend_atomic(out)
print(f"MATLIB {len(names)} materials, {len(bpy.data.images)} images -> {out.relative_to(ROOT)}")
