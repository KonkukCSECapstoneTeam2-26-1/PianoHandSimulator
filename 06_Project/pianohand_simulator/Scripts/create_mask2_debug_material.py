"""M_PH_Mask2Debug - unlit: R = joint seed (mask 2 R, nearest-filtered look), G = joint type (mask 1 B), B = band (mask 1 R)."""
import unreal
PACKAGE = '/Game/PianoHand'; NAME = 'M_PH_Mask2Debug'; PATH = PACKAGE + '/' + NAME
mel = unreal.MaterialEditingLibrary; eal = unreal.EditorAssetLibrary
if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
else:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())
mel.delete_all_material_expressions(mat)
mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
t2 = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -600, 0)
t2.set_editor_property('texture', unreal.load_asset('/Game/PianoHand/Textures/T_PH_WrinkleMask2'))
t1 = mel.create_material_expression(mat, unreal.MaterialExpressionTextureSample, -600, 300)
t1.set_editor_property('texture', unreal.load_asset('/Game/PianoHand/Textures/T_PH_WrinkleMask'))
ap = mel.create_material_expression(mat, unreal.MaterialExpressionAppendVector, -300, 0)
ap2 = mel.create_material_expression(mat, unreal.MaterialExpressionAppendVector, -100, 0)
mel.connect_material_expressions(t2, 'R', ap, 'A')
mel.connect_material_expressions(t1, 'B', ap, 'B')
mel.connect_material_expressions(ap, '', ap2, 'A')
mel.connect_material_expressions(t1, 'R', ap2, 'B')
mel.connect_material_property(ap2, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat); eal.save_asset(PATH)
print('M_PH_Mask2Debug ready:', PATH)
