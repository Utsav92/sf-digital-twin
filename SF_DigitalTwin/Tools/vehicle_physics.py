import unreal
sk = unreal.EditorAssetLibrary.load_asset("/Game/Vehicle/SK_Vehicle")
print("SFPHYS existing", sk.get_editor_property("physics_asset"))
if not sk.get_editor_property("physics_asset"):
    f = unreal.PhysicsAssetFactory()
    try: f.set_editor_property("target_skeletal_mesh", sk)
    except Exception as e: print("SFPHYS factory prop", e)
    pa = unreal.AssetToolsHelpers.get_asset_tools().create_asset("PA_Vehicle", "/Game/Vehicle", unreal.PhysicsAsset, f)
    print("SFPHYS created", pa)
    if pa:
        sk.set_editor_property("physics_asset", pa)
        unreal.EditorAssetLibrary.save_loaded_asset(pa); unreal.EditorAssetLibrary.save_loaded_asset(sk)
pa = sk.get_editor_property("physics_asset")
print("SFPHYS final", pa, [str(b) for b in (pa.get_editor_property("skeletal_body_setups") if pa else [])][:8])
