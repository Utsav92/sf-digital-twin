import unreal
L = unreal.EditorStaticMeshLibrary
for sp in ("Broadleaf","Conifer","Palm"):
    path = f"/Game/Props/SM_Tree_{sp}/SM_Tree_{sp}/StaticMeshes/SM_Tree_{sp}"
    m = unreal.EditorAssetLibrary.load_asset(path)
    bs = L.get_lod_build_settings(m, 0)
    print("SFTN before", sp, bs.recompute_normals, bs.recompute_tangents, bs.use_mikk_t_space, "tris", L.get_number_triangles(m, 0) if hasattr(L,"get_number_triangles") else "?")
    bs.recompute_normals = True; bs.recompute_tangents = True; bs.use_mikk_t_space = True
    L.set_lod_build_settings(m, 0, bs)
    unreal.EditorAssetLibrary.save_loaded_asset(m)
print("SFTN_DONE")
