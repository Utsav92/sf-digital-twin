"""Audit and enable Nanite on every imported tile and landmark mesh; print counts and triangle totals."""
import unreal
ar = unreal.AssetRegistryHelpers.get_asset_registry()
sub = unreal.get_editor_subsystem(unreal.StaticMeshEditorSubsystem)
on = off = fixed = tris = 0; per = {}
for root in ("/Game/Geo/Tiles", "/Game/Landmarks"):
    for a in ar.get_assets_by_path(root, recursive=True):
        if str(a.asset_class_path.asset_name) != "StaticMesh": continue
        m = a.get_asset(); ns = sub.get_nanite_settings(m)
        if ns.enabled: on += 1
        else:
            ns.enabled = True; sub.set_nanite_settings(m, ns, True); unreal.EditorAssetLibrary.save_loaded_asset(m); fixed += 1; off += 1
        tris += sub.get_number_triangles(m, 0) if hasattr(sub, "get_number_triangles") else 0
        per[root] = per.get(root, 0) + 1
print("SFNANITE already_on", on, "enabled_now", fixed, "meshes", per, "LOD0_triangles", tris)
print("SFNANITE_DONE")
