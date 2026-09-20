"""Create M_PianoHandTension - visualises the Phase 2 tension vertex colour written by UPianoHandSkinDeformer.

Run inside the editor (Python console / unreal-mcp execute_python):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/create_tension_material.py').read())

Vertex Color layout (see CustomSkinningTension.usf):
    R = stretch (0..1), G = compression (0..1), B = signed strain (0.5 = rest), A = 1
Material: BaseColor = lerp(lerp(grey, red, R), blue, G); Roughness 0.6
"""
import unreal

PACKAGE = '/Game/PianoHand'
NAME = 'M_PianoHandTension'
PATH = PACKAGE + '/' + NAME

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
    print('reusing existing', PATH)
else:
    if not eal.does_directory_exist(PACKAGE):
        eal.make_directory(PACKAGE)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())
    print('created', PATH)

# Rebuild the graph from scratch so re-running the script is idempotent.
mel.delete_all_material_expressions(mat)

def const3(x, y, r, g, b):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionConstant3Vector, x, y)
    e.set_editor_property('constant', unreal.LinearColor(r, g, b, 1.0))
    return e

vc    = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -700, -100)
grey  = const3(-700, 100, 0.45, 0.42, 0.40)
red   = const3(-700, 250, 1.0, 0.03, 0.02)
blue  = const3(-700, 400, 0.02, 0.15, 1.0)
lerp1 = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -400, 0)
lerp2 = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -200, 0)
rough = mel.create_material_expression(mat, unreal.MaterialExpressionConstant, -200, 250)
rough.set_editor_property('r', 0.6)

mel.connect_material_expressions(grey, '', lerp1, 'A')
mel.connect_material_expressions(red,  '', lerp1, 'B')
mel.connect_material_expressions(vc,   'R', lerp1, 'Alpha')
mel.connect_material_expressions(lerp1, '', lerp2, 'A')
mel.connect_material_expressions(blue,  '', lerp2, 'B')
mel.connect_material_expressions(vc,    'G', lerp2, 'Alpha')
mel.connect_material_property(lerp2, '', unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)

mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat)
eal.save_asset(PATH)
print('M_PianoHandTension ready:', PATH)
