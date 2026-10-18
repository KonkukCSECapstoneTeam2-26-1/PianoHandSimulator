"""Create M_PianoHandClay - a flat matte surface so pure geometry (creases, bulges) is readable.

Run inside the editor:
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/create_clay_material.py').read())
"""
import unreal

PACKAGE = '/Game/PianoHand'
NAME = 'M_PianoHandClay'
PATH = PACKAGE + '/' + NAME

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
else:
    if not eal.does_directory_exist(PACKAGE):
        eal.make_directory(PACKAGE)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())

mel.delete_all_material_expressions(mat)

base = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, -400, 0)
base.set_editor_property('constant', unreal.LinearColor(0.62, 0.58, 0.55, 1.0))
rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 200)
rough.set_editor_property('r', 0.55)
metal = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -400, 320)
metal.set_editor_property('r', 0.0)

mel.connect_material_property(base, '', unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(metal, '', unreal.MaterialProperty.MP_METALLIC)

mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat)
eal.save_asset(PATH)
print('M_PianoHandClay ready:', PATH)
