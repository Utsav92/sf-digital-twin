import unreal
mel = unreal.MaterialEditingLibrary
for n in ("M_SF_Master","M_SF_Facade"):
    m = unreal.EditorAssetLibrary.load_asset("/Game/Materials/"+n)
    for flag in ("used_with_instanced_static_meshes","used_with_nanite"):
        try: print("SFMU", n, flag, "before", m.get_editor_property(flag)); m.set_editor_property(flag, True)
        except Exception as e: print("SFMU skip", n, flag, str(e)[:100])
    mel.recompile_material(m); unreal.EditorAssetLibrary.save_loaded_asset(m)
print("SFMU_DONE")
