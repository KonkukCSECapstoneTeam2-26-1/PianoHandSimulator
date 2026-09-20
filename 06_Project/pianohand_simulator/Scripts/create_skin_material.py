"""Create M_PianoHandSkin / MI_PianoHandSkin - Phase 3c.

Run inside the editor (after import_skin_textures.py):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/create_skin_material.py').read())

The shading itself lives in HLSL, not in this script
-----------------------------------------------------
`Shaders/Private/PianoHandSkin.ush` (virtual path `/PianoHand/Private/PianoHandSkin.ush`) holds the
whole surface model. Each Custom node here lists that file in IncludeFilePaths and its body is a
single call - so the graph is wiring only, and the code is a real source file you can diff and edit
without opening the material editor. Edit the .ush, then `RecompileShaders changed` in the console
(or re-run this script) to see it.

GLSL is not an option in UE: material shaders are authored in HLSL and cross-compiled per platform.

Layers
------
  detail  T_PH_SkinDetail_N   tiling tangent-space normal, always on
  crease  procedural lines, DIRECTION from the baked wrinkle map, amplitude from band x compression
  veins   T_PH_Vein_N         tiling ridges + mask in alpha, gated by stretch

Maps
----
  T_PH_WrinkleMask  baked from the rig by Tools/bake_skin_maps.py, mesh UV space:
      R = weighted joint band (per-finger weights applied at bake time)
      G = signed distance along the bone from the joint pivot, +-CreaseRange cm
      B = raw joint band
    CreaseRange here MUST match S_RANGE in the baker, or the crease spacing comes out wrong.
  Tension vertex colour from CustomSkinningTension.usf: R stretch, G compression, B signed.
"""
import unreal

PACKAGE = '/Game/PianoHand'
NAME = 'M_PianoHandSkin'
PATH = PACKAGE + '/' + NAME
MI_PATH = PACKAGE + '/MI_' + NAME[2:]
TEXDIR = PACKAGE + '/Textures'
INCLUDE = '/PianoHand/Private/PianoHandSkin.ush'

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary

if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
else:
    if not eal.does_directory_exist(PACKAGE):
        eal.make_directory(PACKAGE)
    mat = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())
mel.delete_all_material_expressions(mat)


def scalar(name, value, x, y, group='Skin'):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', value)
    e.set_editor_property('group', group)
    return e


def vector(name, color, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', color)
    return e


def tex_object(name, path, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureObjectParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('texture', unreal.load_asset(path))
    e.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    return e


def custom(desc, body, out_type, input_names, x, y):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionCustom, x, y)
    e.set_editor_property('description', desc)
    e.set_editor_property('code', body)
    e.set_editor_property('output_type', out_type)
    e.set_editor_property('include_file_paths', [INCLUDE])
    ins = []
    for n in input_names:
        ci = unreal.CustomInput()
        ci.set_editor_property('input_name', n)
        ins.append(ci)
    e.set_editor_property('inputs', ins)
    return e


# --- shared inputs ------------------------------------------------------------------------------
uv = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -1700, -400)
vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1700, -300)

mask_tex = tex_object('WrinkleMaskTex', TEXDIR + '/T_PH_WrinkleMask', -1700, -20)

detail_tex = tex_object('SkinDetailTex', TEXDIR + '/T_PH_SkinDetail_N', -1700, 120)
detail_tex.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
vein_tex = tex_object('VeinTex', TEXDIR + '/T_PH_Vein_N', -1700, 260)

PARAMS = [
    ('DetailTiling',     4.0),   # skin micro-relief repeats per UV unit
    ('DetailStrength',   1.0),
    ('CreaseFrequency',  1.5),   # creases per CENTIMETRE along the bone (the map is in cm)
    ('CreaseSharpness',  2.6),   # higher = narrower grooves
    ('CreaseWarp',      0.25),   # fbm meander in cm, so the lines are not parallel rulings
    ('CreaseDepth',     0.055),
    ('CreaseRange',      3.0),   # MUST match S_RANGE in Tools/bake_skin_maps.py
    ('VeinTiling',       4.0),
    ('VeinStrength',     1.0),
    ('WrinkleBase',      0.35),  # crease amount kept at rest - extended fingers still show knuckles
    ('CompressGain',     2.2),   # how fast creases deepen under compression
    ('MaskGain',         1.6),   # widens/narrows the baked concentration band
    ('MaskSharpness',    3.0),   # tightens the band around the joint (1 = the raw baked band)
    ('Eps',            0.0020),  # finite-difference step in UV; a few texels of the 2k mask
]
p = {n: scalar(n, v, -1700, 400 + i * 80) for i, (n, v) in enumerate(PARAMS)}

NORMAL_ARGS = ['DetailTiling', 'DetailStrength', 'CreaseFrequency', 'CreaseSharpness', 'CreaseWarp',
               'CreaseDepth', 'CreaseRange', 'VeinTiling', 'VeinStrength', 'WrinkleBase',
               'CompressGain', 'MaskGain', 'MaskSharpness', 'Eps']

NORMAL_BODY = """return PH_SkinNormal(
    UV, Tension,
    WrinkleMaskTex, WrinkleMaskTexSampler,
    SkinDetailTex, SkinDetailTexSampler,
    VeinTex, VeinTexSampler,
    DetailTiling, DetailStrength,
    CreaseFrequency, CreaseSharpness, CreaseWarp, CreaseDepth, CreaseRange,
    VeinTiling, VeinStrength,
    WrinkleBase, CompressGain, MaskGain, MaskSharpness, Eps);"""

nrm_inputs = ['UV', 'Tension', 'WrinkleMaskTex', 'SkinDetailTex', 'VeinTex'] + NORMAL_ARGS
nrm = custom('PH_SkinNormal', NORMAL_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT3, nrm_inputs, -1000, -300)

VEIN_BODY = """return PH_VeinMask(UV, Tension, WrinkleMaskTex, WrinkleMaskTexSampler,
    VeinTex, VeinTexSampler, VeinTiling, MaskGain, MaskSharpness);"""
vein_inputs = ['UV', 'Tension', 'WrinkleMaskTex', 'VeinTex', 'VeinTiling', 'MaskGain', 'MaskSharpness']
vein = custom('PH_VeinMask', VEIN_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT1, vein_inputs, -1000, 300)

CREASE_BODY = """return PH_CreaseMask(UV, Tension, WrinkleMaskTex, WrinkleMaskTexSampler,
    CreaseFrequency, CreaseSharpness, CreaseWarp, CreaseRange, WrinkleBase, CompressGain,
    MaskGain, MaskSharpness);"""
crease_inputs = ['UV', 'Tension', 'WrinkleMaskTex', 'CreaseFrequency', 'CreaseSharpness', 'CreaseWarp',
                 'CreaseRange', 'WrinkleBase', 'CompressGain', 'MaskGain', 'MaskSharpness']
crease = custom('PH_CreaseMask', CREASE_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT1, crease_inputs, -1000, 560)


def wire(node, names):
    for n in names:
        if n == 'UV':
            mel.connect_material_expressions(uv, '', node, 'UV')
        elif n == 'Tension':
            mel.connect_material_expressions(vc, '', node, 'Tension')
        elif n == 'WrinkleMaskTex':
            mel.connect_material_expressions(mask_tex, '', node, 'WrinkleMaskTex')
        elif n == 'SkinDetailTex':
            mel.connect_material_expressions(detail_tex, '', node, 'SkinDetailTex')
        elif n == 'VeinTex':
            mel.connect_material_expressions(vein_tex, '', node, 'VeinTex')
        else:
            mel.connect_material_expressions(p[n], '', node, n)


wire(nrm, nrm_inputs)
wire(vein, vein_inputs)
wire(crease, crease_inputs)

# --- base colour --------------------------------------------------------------------------------
skin = vector('SkinColor', unreal.LinearColor(0.80, 0.60, 0.52, 1.0), -1000, 800)
# the colour layers stay close to the skin tone - the relief should read from the NORMAL,
# not from painted-on dark bands, which look like dirt the moment the light moves
flush = vector('CompressionFlush', unreal.LinearColor(0.74, 0.50, 0.43, 1.0), -1000, 920)
veincol = vector('VeinColor', unreal.LinearColor(0.70, 0.55, 0.56, 1.0), -1000, 1040)
creasecol = vector('CreaseShadow', unreal.LinearColor(0.68, 0.48, 0.41, 1.0), -1000, 1160)

l1 = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -600, 860)
mel.connect_material_expressions(skin, '', l1, 'A')
mel.connect_material_expressions(flush, '', l1, 'B')
mel.connect_material_expressions(vc, 'G', l1, 'Alpha')

l2 = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -420, 860)
mel.connect_material_expressions(l1, '', l2, 'A')
mel.connect_material_expressions(veincol, '', l2, 'B')
mel.connect_material_expressions(vein, '', l2, 'Alpha')

l3 = mel.create_material_expression(mat, unreal.MaterialExpressionLinearInterpolate, -240, 860)
mel.connect_material_expressions(l2, '', l3, 'A')
mel.connect_material_expressions(creasecol, '', l3, 'B')
mel.connect_material_expressions(crease, '', l3, 'Alpha')

rough = scalar('Roughness', 0.55, -600, 1300, 'Surface')
spec = scalar('Specular', 0.32, -600, 1380, 'Surface')

mel.connect_material_property(nrm, '', unreal.MaterialProperty.MP_NORMAL)
mel.connect_material_property(l3, '', unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rough, '', unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(spec, '', unreal.MaterialProperty.MP_SPECULAR)

mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat)
eal.save_asset(PATH)

# --- MI, the tuning handle (scalar defaults on the Material itself need a full recompile) --------
if eal.does_asset_exist(MI_PATH):
    mi = unreal.load_asset(MI_PATH)
else:
    mi = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        'MI_' + NAME[2:], PACKAGE, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
mi.set_editor_property('parent', mat)
mel.clear_all_material_instance_parameters(mi)
eal.save_asset(MI_PATH)

print('M_PianoHandSkin ready:', PATH)
print('MI_PianoHandSkin ready:', MI_PATH)
