"""Import the original props: static USD (trees, car, pedestrian) -> /Game/Props, rigged FBX -> /Game/Vehicle/SK_Vehicle (+ physics asset)."""
import os, unreal
P = os.path.expanduser("~/sf_twin/out/unreal/props")
tools = unreal.AssetToolsHelpers.get_asset_tools()
def usd(name):
    o = unreal.UsdStageImportOptions(); o.import_actors = False; o.import_geometry = True; o.import_skeletal_animations = False; o.import_level_sequences = False
    o.import_materials = True; o.prim_path_folder_structure = False; o.merge_identical_material_slots = True
    t = unreal.AssetImportTask(); t.filename, t.destination_path, t.automated, t.save, t.replace_existing = f"{P}/{name}.usdc", f"/Game/Props/{name}", True, True, True
    t.factory = unreal.UsdStageImportFactory(); t.options = o; tools.import_asset_tasks([t]); print("SFPROP", name, [str(x) for x in (t.imported_object_paths or [])][:3])
for n in ("SM_Tree_Broadleaf", "SM_Tree_Conifer", "SM_Tree_Palm", "SM_Car", "SM_Pedestrian"): usd(n)
ui = unreal.FbxImportUI(); ui.set_editor_property("import_mesh", True); ui.set_editor_property("import_as_skeletal", True); ui.set_editor_property("import_materials", True)
ui.set_editor_property("import_textures", False); ui.set_editor_property("create_physics_asset", True); ui.set_editor_property("import_animations", False)
ui.set_editor_property("mesh_type_to_import", unreal.FBXImportType.FBXIT_SKELETAL_MESH)
t = unreal.AssetImportTask(); t.filename, t.destination_path, t.destination_name, t.automated, t.save, t.replace_existing, t.options = f"{P}/SK_Vehicle.fbx", "/Game/Vehicle", "SK_Vehicle", True, True, True, ui
tools.import_asset_tasks([t]); print("SFPROP vehicle", [str(x) for x in (t.imported_object_paths or [])])
ar = unreal.AssetRegistryHelpers.get_asset_registry()
print("SFPROP vehicle assets", [str(a.asset_name) + ":" + str(a.asset_class_path.asset_name) for a in ar.get_assets_by_path("/Game/Vehicle", recursive=True)])
print("SFPROPS_DONE")
