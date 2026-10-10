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
  detail  MetaHuman T_SkinMicroNormal, tiling tangent-space normal, always on. This is an authored
          skin micro-relief map that ships with the MetaHumanCharacter plugin; it replaced the
          procedurally baked T_PH_SkinDetail_N, which stays in the project as the fallback for
          anyone without the plugin.
          Under strain it is made ANISOTROPIC (Nagano et al. 2015): the micro grooves bunch up across
          the compressed axis and flatten along a stretched one.
  crease  procedural furrows, POSITION/DIRECTION from the baked wrinkle map, Bando et al. 2002
          cross-section, and a different pattern per joint type (MCP / PIP / DIP) from mask B
  veins   T_PH_Vein_N         tiling ridges + mask in alpha, gated by stretch

Maps
----
  T_PH_WrinkleMask  baked from the rig by Tools/bake_skin_maps.py, mesh UV space:
      R = weighted joint band (per-finger weights applied at bake time)
      G = signed distance along the bone from the joint pivot, +-CreaseRange cm
      B = joint type code (0 none, .2 MCP, .4 PIP, .6 DIP, .8 thumb MP, 1 other)
      A = which side of the joint - +1 stretches on flexion (back of hand), -1 compresses (palm)
  Vertex colour A carries the relax slack (released stretch, decaying) from the tension pass.
    CreaseRange here MUST match S_RANGE in the baker, or the crease spacing comes out wrong.
  Strain vertex colour from the deformer (strain tensor, CustomSkinningDetail.usf):
      R stretch (lambda_max - 1), G compression ALONG the bone, B compression ACROSS it.
"""
import unreal

PACKAGE = '/Game/PianoHand'
NAME = 'M_PianoHandSkin'
PATH = PACKAGE + '/' + NAME
MI_PATH = PACKAGE + '/MI_' + NAME[2:]
TEXDIR = PACKAGE + '/Textures'
INCLUDE = '/PianoHand/Private/PianoHandSkin.ush'
# authored skin micro-relief from the MetaHumanCharacter plugin; falls back to our procedural bake
DETAIL_TEX = '/MetaHumanCharacter/Lookdev_UHM/Skin/Textures/T_SkinMicroNormal'
DETAIL_TEX_FALLBACK = PACKAGE + '/Textures/T_PH_SkinDetail_N'

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

_detail_path = DETAIL_TEX if unreal.load_asset(DETAIL_TEX) is not None else DETAIL_TEX_FALLBACK
if _detail_path != DETAIL_TEX:
    print('MetaHuman skin micro-normal not available, using', _detail_path)
detail_tex = tex_object('SkinDetailTex', _detail_path, -1700, 120)
detail_tex.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
vein_tex = tex_object('VeinTex', TEXDIR + '/T_PH_Vein_N', -1700, 260)

PARAMS = [
    # T_SkinMicroNormal is authored at MetaHuman body texel density; the hand's UVs are repacked
    # to fill 0..1, so it needs many more repeats than our own 1k tile did (that one was 4.0).
    ('DetailTiling',    14.0),   # skin micro-relief repeats per UV unit
    ('DetailStrength',  0.55),
    ('MicroAniso',       1.0),   # micro-groove slope gain per unit compression (Nagano: up to ~2.5x)
    ('MicroFlatten',     0.5),   # micro-groove slope loss per unit stretch
    ('VSign',            1.0),   # -1 if the mask's V gradient runs against the normal map's y
    ('CreaseFrequency',  1.3),   # furrows per CENTIMETRE along the bone, before the per-joint multiplier
    ('CreaseSharpness',  3.2),   # legacy: narrows the furrow (3.2 = the Bando width as-is)
    ('CreaseWarp',      0.25),   # fbm meander as a fraction of the furrow spacing
    ('CreaseDepth',     0.35),   # cm-equivalent depth of the PRIMARY crease; relief has no AO so it is exaggerated
    ('UVScaleCm',       25.0),   # cm per UV unit of the hand mesh (median edge ratio, see Tools)
    ('CreaseRange',      2.0),   # MUST match S_RANGE in Tools/bake_skin_maps.py
    ('FurrowWidth',     0.25),   # Bando w as a fraction of the furrow spacing
    ('Irregularity',     1.0),   # how unevenly the secondary folds are spaced / weighted
    ('SecondaryDepth',   0.4),   # fine fold family depth relative to the primary crease
    ('JointReach',       1.2),   # cm from the band centre where the folds have faded out
    ('CompressNarrow',   2.0),   # furrows narrow under compression across them (Weiss 2024)
    ('StretchWiden',     2.0),   # and widen / flatten under stretch
    # per-joint pattern (mask B says which joint a texel belongs to)
    ('FoldsMCP',         1.1),   # frequency multipliers, back of the hand
    ('FoldsPIP',         2.2),   #   PIP: 3-6 fine irregular folds
    ('FoldsDIP',         0.8),   #   DIP: one or two clean lines
    ('DepthMCP',        0.55),   # depth multipliers, both sides
    ('DepthPIP',         1.0),
    ('DepthDIP',        0.75),
    ('PalmSplit',        0.3),   # cm, half-distance of the palmar PIP double crease
    ('SideFolds',       0.25),   # oblique folds at the sides of a flexed joint (Bando's crossing family)
    ('VeinTiling',       4.0),
    ('VeinStrength',     0.6),
    # Two crease regimes, because the joint band wraps all the way around a joint and the two
    # sides of it do OPPOSITE things. Mask alpha says which side a texel is on.
    #   palm    rest creases deepen as the hand CLOSES
    ('PalmarBase',      0.45),   # standing creases on an open palm
    ('PalmarCompress',   2.6),   # how fast they deepen under compression
    ('PalmarIron',       1.2),   # how fast stretch irons them flat
    ('PalmarRelax',      0.8),   # released-stretch slack, palm side
    #   knuckle the skin over the back of a joint carries slack, so it is gathered at REST and
    #           pulls taut as the hand closes - the reverse of the palm
    ('DorsalBase',      0.40),   # folds standing over an extended knuckle
    ('DorsalIron',       5.0),   # how fast flexion spends that slack and the surface goes taut
    ('DorsalRelax',      4.0),   # the folds that come back just after a fist opens
    ('SideSharpness',    3.0),   # how narrow the palm/back transition is around the sides
    ('SideFlip',         1.0),   # -1 if a rig curls the other way; avoids a re-bake
    ('MaskGain',         1.0),   # widens/narrows the baked concentration band
    ('MaskSharpness',    3.0),   # tightens the band around the joint (1 = the raw baked band)
    ('Eps',            0.0008),  # finite-difference step in UV; ~0.02cm, a quarter of the finest furrow
]
p = {n: scalar(n, v, -1700, 400 + i * 80) for i, (n, v) in enumerate(PARAMS)}

# everything the crease model needs, packed into FPHSkinParams inside the node body
STRUCT_ARGS = ['CreaseFrequency', 'CreaseSharpness', 'CreaseWarp', 'CreaseRange', 'FurrowWidth', 'Irregularity',
               'SecondaryDepth', 'JointReach', 'CompressNarrow', 'StretchWiden',
               'FoldsMCP', 'FoldsPIP', 'FoldsDIP', 'DepthMCP', 'DepthPIP', 'DepthDIP', 'PalmSplit', 'SideFolds',
               'PalmarBase', 'PalmarCompress', 'PalmarIron', 'PalmarRelax',
               'DorsalBase', 'DorsalIron', 'DorsalRelax', 'SideSharpness', 'SideFlip',
               'MaskGain', 'MaskSharpness']

FILL_STRUCT = 'FPHSkinParams P;\n' + ''.join('P.%s = %s;\n' % (n, n) for n in STRUCT_ARGS)

NORMAL_ARGS = (['DetailTiling', 'DetailStrength', 'MicroAniso', 'MicroFlatten', 'VSign',
                'CreaseDepth', 'UVScaleCm', 'VeinTiling', 'VeinStrength', 'Eps'] + STRUCT_ARGS)

NORMAL_BODY = FILL_STRUCT + """return PH_SkinNormal(
    UV, Tension, Relax,
    WrinkleMaskTex, WrinkleMaskTexSampler,
    SkinDetailTex, SkinDetailTexSampler,
    VeinTex, VeinTexSampler,
    DetailTiling, DetailStrength, MicroAniso, MicroFlatten, VSign,
    CreaseDepth, UVScaleCm, VeinTiling, VeinStrength, Eps, P);"""

nrm_inputs = ['UV', 'Tension', 'Relax', 'WrinkleMaskTex', 'SkinDetailTex', 'VeinTex'] + NORMAL_ARGS
nrm = custom('PH_SkinNormal', NORMAL_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT3, nrm_inputs, -1000, -300)

VEIN_BODY = """return PH_VeinMask(UV, Tension, WrinkleMaskTex, WrinkleMaskTexSampler,
    VeinTex, VeinTexSampler, VeinTiling, SideSharpness, SideFlip, MaskGain, MaskSharpness);"""
vein_inputs = ['UV', 'Tension', 'WrinkleMaskTex', 'VeinTex', 'VeinTiling', 'SideSharpness',
               'SideFlip', 'MaskGain', 'MaskSharpness']
vein = custom('PH_VeinMask', VEIN_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT1, vein_inputs, -1000, 300)

CREASE_BODY = FILL_STRUCT + """return PH_CreaseMask(UV, Tension, Relax, WrinkleMaskTex, WrinkleMaskTexSampler, P);"""
crease_inputs = ['UV', 'Tension', 'Relax', 'WrinkleMaskTex'] + STRUCT_ARGS
crease = custom('PH_CreaseMask', CREASE_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT1, crease_inputs, -1000, 560)


def wire(node, names):
    for n in names:
        if n == 'UV':
            mel.connect_material_expressions(uv, '', node, 'UV')
        elif n == 'Tension':
            mel.connect_material_expressions(vc, '', node, 'Tension')
        elif n == 'Relax':
            # the tension pass writes the relax slack into vertex-colour ALPHA
            mel.connect_material_expressions(vc, 'A', node, 'Relax')
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
skin = vector('SkinColor', unreal.LinearColor(0.74, 0.50, 0.40, 1.0), -1000, 800)
# the colour layers stay close to the skin tone - the relief should read from the NORMAL,
# not from painted-on dark bands, which look like dirt the moment the light moves
flush = vector('CompressionFlush', unreal.LinearColor(0.70, 0.42, 0.36, 1.0), -1000, 920)
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

rough = scalar('Roughness', 0.5, -600, 1300, 'Surface')
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
