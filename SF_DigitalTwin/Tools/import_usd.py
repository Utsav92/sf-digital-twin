"""Import sf_twin USD tiles/landmarks into /Game/Geo. Usage (editor): -ExecutePythonScript="import_usd.py" with env SF_IDS=t-03_-02,... SF_LANDMARKS=salesforce,..."""
import os, json, time, unreal
SF = os.path.expanduser("~/sf_twin")
ids = [i for i in os.environ.get("SF_IDS", "").split(",") if i]
lms = [i for i in os.environ.get("SF_LANDMARKS", "").split(",") if i]

def import_usd(path, dest):
    opts = unreal.UsdStageImportOptions()
    opts.import_actors = False
    opts.import_geometry = True
    opts.import_skeletal_animations = False
    opts.import_level_sequences = False
    opts.import_materials = True
    opts.prim_path_folder_structure = False
    opts.merge_identical_material_slots = True
    t = unreal.AssetImportTask()
    t.filename, t.destination_path, t.automated, t.save, t.replace_existing = path, dest, True, True, True
    t.factory = unreal.UsdStageImportFactory()
    t.options = opts
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([t])
    print("SFIMPORT", path, "->", dest, "objects:", [str(o) for o in (t.imported_object_paths or [])][:4], len(t.imported_object_paths or []))

def nanite(root):
    sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
    for a in unreal.AssetRegistryHelpers.get_asset_registry().get_assets_by_path(root, recursive=True):
        if str(a.asset_class_path.asset_name) == "StaticMesh":
            m = a.get_asset(); ns = sub.get_nanite_settings(m); ns.enabled = True; sub.set_nanite_settings(m, ns, True)
            unreal.EditorAssetLibrary.save_loaded_asset(m)

t0 = time.time()
for k, i in enumerate(ids):
    if unreal.EditorAssetLibrary.does_directory_exist(f"/Game/Geo/Tiles/{i}") and os.environ.get("SF_SKIP_EXISTING", "1") == "1":
        continue
    import_usd(f"{SF}/out/unreal/tiles/{i}/{i}.usdc", f"/Game/Geo/Tiles/{i}")
    nanite(f"/Game/Geo/Tiles/{i}")
    print("SFTIME", k + 1, len(ids), round(time.time() - t0, 1), "s", flush=True)
for n in lms:
    import_usd(f"{SF}/out/unreal/landmarks/SM_Landmark_{n}.usdc", f"/Game/Landmarks/{n}")
print("SFIMPORT_DONE")
