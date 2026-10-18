"""Create M_PianoHandVColor - unlit material that shows the raw vertex colour (deformer debug output)."""
import unreal
PACKAGE = '/Game/PianoHand'; NAME = 'M_PianoHandVColor'; PATH = PACKAGE + '/' + NAME
mel = unreal.MaterialEditingLibrary; eal = unreal.EditorAssetLibrary
if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
else:
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())
mel.delete_all_material_expressions(mat)
mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_UNLIT)
vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -400, 0)
mel.connect_material_property(vc, '', unreal.MaterialProperty.MP_EMISSIVE_COLOR)
mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat); eal.save_asset(PATH)
print('M_PianoHandVColor ready:', PATH)
