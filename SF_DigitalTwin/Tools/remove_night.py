"""Undo night mode: emissive back to black, delete MPC_SF."""
import unreal
mel = unreal.MaterialEditingLibrary
m = unreal.EditorAssetLibrary.load_asset("/Game/Materials/M_SF_Facade")
z = mel.create_material_expression(m, unreal.MaterialExpressionConstant3Vector, 0, 2000); z.set_editor_property("constant", unreal.LinearColor(0, 0, 0, 1))
mel.connect_material_property(z, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mel.recompile_material(m); unreal.EditorAssetLibrary.save_loaded_asset(m)
if unreal.EditorAssetLibrary.does_asset_exist("/Game/Materials/MPC_SF"): unreal.EditorAssetLibrary.delete_asset("/Game/Materials/MPC_SF")
print("SFNIGHT_REMOVED")
