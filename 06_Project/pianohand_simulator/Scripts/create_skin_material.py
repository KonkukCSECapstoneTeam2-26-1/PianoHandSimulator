"""Create M_PianoHandSkin / MI_PianoHandSkin - v3 (Subsurface Profile + crease shape + palm lines).

Run inside the editor (after import_skin_textures.py):
    exec(open('<project>/Scripts/create_skin_material.py').read())

The shading itself lives in HLSL, not in this script
-----------------------------------------------------
`Shaders/Private/PianoHandSkin.ush` (virtual path `/PianoHand/Private/PianoHandSkin.ush`) holds the
whole surface model. Each Custom node here lists that file in IncludeFilePaths and its body is a
single call - so the graph is wiring only, and the code is a real source file you can diff and edit
without opening the material editor. Edit the .ush, then `RecompileShaders changed` in the console
(or re-run this script) to see it.

v3 (2026-10-12)
---------------
  shading model   Subsurface Profile (SSP_PianoHandSkin, created here). Light scatters under the
                  surface, so the edges of a furrow soften and the normal relief reads as folded
                  skin instead of scratched plastic. Opacity = subsurface amount.
  surface         one Custom node (PH_SkinSurface) returns cavity / blanch / flush / vein; base
                  colour, roughness, specular, AO and opacity are all functions of it, so the
                  colour and the relief can never disagree. Furrows are darker, rougher and less
                  specular; stretched knuckles blanch, compressed skin flushes.
  crease shape    the primary crease bows around the finger, tapers out at the sides, forks at its
                  ends, and every joint is seeded differently (mask 2 R).
  regional relief three fixed tilings of the micro-relief map (knuckle / base / side) and papillary
                  ridges (T_PH_PalmRidge_N) on the palmar side, blended by region weight.
  palm lines      distal / proximal palmar and thenar creases from the distance field in mask 2 G/B.
  distance fade   DDX/DDY of the UV -> cm per pixel; the fine lines fade first, the primary
                  crease and palm lines later, so nothing shimmers at a distance.

Maps
----
  T_PH_WrinkleMask   baked from the rig by Tools/bake_skin_maps.py, mesh UV space:
      R = weighted joint band (per-finger weights applied at bake time)
      G = unsigned distance along the bone to the nearest joint band centre, 0..CreaseRange cm
      B = joint type code (0 none, .2 MCP, .4 PIP, .6 DIP, .8 thumb MP, 1 other)
      A = which side of the joint - +1 stretches on flexion (back of hand), -1 compresses (palm)
  T_PH_WrinkleMask2  R = joint seed + distal/proximal side, G = palm crease distance 0..PalmRange,
                     B = palm crease depth, A = along-hand coordinate (its gradient gives the side of the joint)
  T_PH_PalmRidge_N   tiling papillary ridges (palmar side micro relief)
  Vertex colour A carries the relax slack (released stretch, decaying) from the tension pass.
    CreaseRange / PalmRange here MUST match S_RANGE / PALM_RANGE in the baker.
  Strain vertex colour from the deformer (strain tensor, CustomSkinningDetail.usf):
      R stretch (lambda_max - 1), G compression ALONG the bone, B compression ACROSS it.
"""
import unreal

PACKAGE = '/Game/PianoHand'
NAME = 'M_PianoHandSkin'
PATH = PACKAGE + '/' + NAME
MI_PATH = PACKAGE + '/MI_' + NAME[2:]
SSP_NAME = 'SSP_PianoHandSkin'
SSP_PATH = PACKAGE + '/' + SSP_NAME
TEXDIR = PACKAGE + '/Textures'
INCLUDE = '/PianoHand/Private/PianoHandSkin.ush'
# authored skin micro-relief from the MetaHumanCharacter plugin; falls back to our procedural bake
DETAIL_TEX = '/MetaHumanCharacter/Lookdev_UHM/Skin/Textures/T_SkinMicroNormal'
DETAIL_TEX_FALLBACK = PACKAGE + '/Textures/T_PH_SkinDetail_N'

mel = unreal.MaterialEditingLibrary
eal = unreal.EditorAssetLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()

if eal.does_asset_exist(PATH):
    mat = unreal.load_asset(PATH)
else:
    if not eal.does_directory_exist(PACKAGE):
        eal.make_directory(PACKAGE)
    mat = tools.create_asset(NAME, PACKAGE, unreal.Material, unreal.MaterialFactoryNew())
mel.delete_all_material_expressions(mat)


# --- subsurface profile -------------------------------------------------------------------------
# Burley normalised diffusion, the parameters Epic uses for their own skin lookdev, in cm. The
# profile is an asset so the lighting team can tune it without touching the material.
def make_profile():
    if eal.does_asset_exist(SSP_PATH):
        prof = unreal.load_asset(SSP_PATH)
    else:
        factory = None
        for fname in ('SubsurfaceProfileFactory',):
            factory = getattr(unreal, fname, None)
        if factory is None:
            print('WARNING: no SubsurfaceProfile factory in this build; the engine default profile will be used')
            return None
        prof = tools.create_asset(SSP_NAME, PACKAGE, unreal.SubsurfaceProfile, factory())
    try:
        s = prof.get_editor_property('settings')
        wanted = dict(
            enable_burley=False,     # Burley came out as speckle on Metal (editor viewport, 5.6.1); separable is clean
            surface_albedo=unreal.LinearColor(0.867, 0.603, 0.447, 1.0),
            mean_free_path_color=unreal.LinearColor(0.98, 0.9, 0.86, 1.0),
            mean_free_path_distance=0.6,     # cm - a hand is thinner-skinned than a cheek
            world_unit_scale=1.0,
            scatter_radius=0.5,
            subsurface_color=unreal.LinearColor(0.48, 0.36, 0.40, 1.0),
            falloff_color=unreal.LinearColor(1.0, 0.37, 0.30, 1.0),
            boundary_color_bleed=unreal.LinearColor(1.0, 0.8, 0.8, 1.0),
            extinction_scale=1.0,
            normal_scale=0.25,       # 0.08 is Epic's face value; at 0.25 the fine crease normals survive the SSS blur
            scattering_distribution=0.93,
            ior=1.55,
            roughness0=0.75,
            roughness1=1.30,
            lobe_mix=0.85,
        )
        for k, v in wanted.items():
            try:
                s.set_editor_property(k, v)
            except Exception as e:   # a field renamed between engine versions is not fatal
                print('  (profile field %s skipped: %s)' % (k, e))
        prof.set_editor_property('settings', s)
    except Exception as e:
        print('WARNING: could not set profile settings:', e)
    eal.save_asset(SSP_PATH)
    return prof


profile = make_profile()


def scalar(name, value, x, y, group='Skin'):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionScalarParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', value)
    e.set_editor_property('group', group)
    return e


def vector(name, color, x, y, group='Colour'):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionVectorParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('default_value', color)
    e.set_editor_property('group', group)
    return e


def tex_object(name, path, x, y, normal=False):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionTextureObjectParameter, x, y)
    e.set_editor_property('parameter_name', name)
    e.set_editor_property('texture', unreal.load_asset(path))
    e.set_editor_property('sampler_type', unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL if normal
                          else unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
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


def mask(src, x, y, r=False, g=False, b=False, a=False):
    e = mel.create_material_expression(mat, unreal.MaterialExpressionComponentMask, x, y)
    e.set_editor_property('r', r)
    e.set_editor_property('g', g)
    e.set_editor_property('b', b)
    e.set_editor_property('a', a)
    mel.connect_material_expressions(src, '', e, '')
    return e


# --- shared inputs ------------------------------------------------------------------------------
uv = mel.create_material_expression(mat, unreal.MaterialExpressionTextureCoordinate, -1900, -500)
vc = mel.create_material_expression(mat, unreal.MaterialExpressionVertexColor, -1900, -400)
ddx = mel.create_material_expression(mat, unreal.MaterialExpressionDDX, -1700, -560)
ddy = mel.create_material_expression(mat, unreal.MaterialExpressionDDY, -1700, -480)
mel.connect_material_expressions(uv, '', ddx, '')
mel.connect_material_expressions(uv, '', ddy, '')

mask_tex = tex_object('WrinkleMaskTex', TEXDIR + '/T_PH_WrinkleMask', -1900, -200)
mask2_tex = tex_object('WrinkleMask2Tex', TEXDIR + '/T_PH_WrinkleMask2', -1900, -60)

_detail_path = DETAIL_TEX if unreal.load_asset(DETAIL_TEX) is not None else DETAIL_TEX_FALLBACK
if _detail_path != DETAIL_TEX:
    print('MetaHuman skin micro-normal not available, using', _detail_path)
detail_tex = tex_object('SkinDetailTex', _detail_path, -1900, 80, normal=True)
ridge_tex = tex_object('PalmRidgeTex', TEXDIR + '/T_PH_PalmRidge_N', -1900, 220, normal=True)
vein_tex = tex_object('VeinTex', TEXDIR + '/T_PH_Vein_N', -1900, 360)
# Phase 6: the crease graph tables (data textures, read with Load)
graph_cells = tex_object('GraphCellsTex', TEXDIR + '/T_PH_WrinkleGraph_Cells', -1900, 440)
graph_e0 = tex_object('GraphEdges0Tex', TEXDIR + '/T_PH_WrinkleGraph_Edges0', -1900, 480)
graph_e1 = tex_object('GraphEdges1Tex', TEXDIR + '/T_PH_WrinkleGraph_Edges1', -1900, 520)

PARAMS = [
    # T_SkinMicroNormal is authored at MetaHuman body texel density; the hand's UVs are repacked
    # to fill 0..1, so it needs many more repeats than our own 1k tile did (that one was 4.0).
    ('DetailTiling',    14.0),   # skin micro-relief repeats per UV unit
    ('DetailStrength',  0.45),
    ('MicroAniso',       1.0),   # micro-groove slope gain per unit compression (Nagano: up to ~2.5x)
    ('MicroFlatten',     0.5),   # micro-groove slope loss per unit stretch
    ('VSign',            1.0),   # -1 if the mask's V gradient runs against the normal map's y
    # regional relief (v3): the knuckle mesh is wider and deeper, the finger sides finer and fainter
    ('KnuckleTilingMul',   0.70),
    ('KnuckleStrengthMul', 1.5),
    ('SideTilingMul',      1.5),
    ('SideStrengthMul',    0.5),
    ('RidgeTiling',       12.0),  # ~0.05cm ridge spacing at 25cm/UV with 40 ridges per tile
    ('RidgeStrength',      0.45),
    ('CreaseFrequency',  1.3),   # furrows per CENTIMETRE along the bone, before the per-joint multiplier
    ('CreaseSharpness',  3.2),   # legacy: narrows the furrow (3.2 = the Bando width as-is)
    ('CreaseWarp',      0.25),   # fbm meander as a fraction of the furrow spacing
    ('CreaseDepth',     0.35),   # cm-equivalent depth of the PRIMARY crease; relief has no AO so it is exaggerated
    ('UVScaleCm',       25.0),   # cm per UV unit of the hand mesh (median edge ratio, see Tools)
    ('CreaseRange',      2.0),   # MUST match S_RANGE in Tools/bake_skin_maps.py
    ('FurrowWidth',     0.25),   # Bando w of the fine folds, as a fraction of their spacing
    ('PrimaryWidth',    0.14),   # cm, Bando w of the primary crease (v3; was tied to the spacing, ~0.27cm)
    ('Irregularity',     1.0),   # how unevenly the secondary folds are spaced / weighted
    ('SecondaryDepth',   0.4),   # fine fold family depth relative to the primary crease
    ('JointReach',       1.2),   # cm from the band centre where the folds have faded out
    ('CompressNarrow',   2.0),   # furrows narrow under compression across them (Weiss 2024)
    ('StretchWiden',     2.0),   # and widen / flatten under stretch
    # per-joint pattern (mask B says which joint a texel belongs to)
    ('FoldsMCP',         1.1),   # frequency multipliers, back of the hand
    ('FoldsPIP',         2.2),   #   PIP: 3-6 fine irregular folds
    ('FoldsDIP',         0.8),   #   DIP: one or two clean lines
    ('DepthMCP',        0.55),   # depth multipliers, both sides (10-16: 0.55 still drew a dark dash on the extended index MCP; now also scales the graph primaries)
    ('DepthPIP',         1.0),
    ('DepthDIP',        0.75),
    ('PalmSplit',        0.3),   # cm, half-distance of the palmar PIP double crease
    ('SideFolds',       0.25),   # oblique folds at the sides of a flexed joint (Bando's crossing family)
    # crease shape (v3)
    ('CreaseBow',      -0.20),   # cm: knuckle crease ends drift proximally -> the line arcs over the joint
    ('PalmBow',         0.15),   # palmar digital creases bow the other way, gently
    ('SideTaper',       0.20),   # |cos around the finger| below which the primary crease is gone
    ('ForkStrength',    0.55),   # the Y branch at each end, relative to the primary depth
    ('ForkAngle',       0.35),   # cm along the bone the branch drifts over its length
    ('SeedVariation',   0.8),    # per-joint variation of fold count / phase / bow (0 = identical joints)
    ('FoldFlattenStart', 0.55),  # 10-16: compression past which a closing fold presses secondary folds / lattice / micro relief flat
    ('FoldFlattenFull',  0.95),
    # palm lines (v3)
    ('PalmRange',        2.0),   # MUST match PALM_RANGE in Tools/bake_skin_maps.py
    ('PalmLineDepth',    0.9),   # relative to the primary knuckle crease (1.3 read as carved trenches - 10-14 palm sweep)
    ('PalmLineWidth',   0.24),   # cm, Bando w: wider and shallower than the finger creases, soft shoulders
    ('PalmLineBase',    0.55),   # standing depth on an open hand
    ('PalmLineCompress', 2.0),   # deepening as the palm cups
    ('PalmLineIron',    0.8),    # opening up as the hand is spread flat
    # distance fade (v3): cm of skin per screen pixel
    ('FadeStartCm',    0.050),
    ('FadeEndCm',      0.180),
    # crease graph (Phase 6, Weiss 2023/2024): 1 = draw the creases from the simulated graph tables,
    # 0 = the v3 procedural furrows
    ('GraphCreases',      1.0),
    ('GraphDepth',       0.16),   # cm depth of a full-weight primary trail at full gate (~0.06 cm at the resting dorsal gate). 10-15: p-norm max returns it undiluted (was 0.30 under the 16-slot mellow-max, ~0.04 cm effective)
    ('GraphSecondaryDepth', 0.3),  # secondary trails relative to primary
    ('GraphFineDepth',      5.0),  # 10-16: lattice for close-ups only; 5 read as crumpled old skin at play distance (PH_LatticeFade hides it past ~0.02 cm/px)
    ('GraphAlphaW',       1.0),   # Weiss 2024 alpha_w: width response to stretch along the wrinkle's normal
    ('GraphAlphaD',       3.0),   # alpha_d: depth response (deeper under compression)
    ('GraphBeta',         8.0),   # p of the p-norm smooth max over overlapping fragments (10-15, was mellow-max sharpness 20)
    ('GraphGrid',       512.0),   # MUST match GRID in Tools/simulate_wrinkle_graph.py
    ('GraphTableWidth', 4096.0),  # MUST match TABLE_WIDTH
    ('GraphRelRange',     6.0),   # MUST match REL_RANGE
    ('GraphWidthRange',   0.5),   # MUST match WIDTH_RANGE (cm)
    ('VeinTiling',       4.0),
    ('VeinStrength',     0.2),
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
p = {n: scalar(n, v, -1900, 520 + i * 70) for i, (n, v) in enumerate(PARAMS)}

# surface response knobs (v3)
SURFACE = [
    ('Roughness',       0.50),
    ('Specular',        0.32),
    ('CavityRough',     0.35),   # roughness added at the bottom of a furrow
    ('StretchSmooth',   0.12),   # roughness lost on taut skin
    ('CavitySpecLoss',  0.60),   # specular lost inside a furrow
    ('CavityAO',        0.7),    # occlusion inside a furrow (10-16: 0.7 read as a scar at play distance)
    ('StretchThin',     0.15),   # subsurface amount lost over a blanched knuckle
    ('BlanchGain',      0.9),
    ('FlushGain',       0.7),
    ('CavityDarken',    0.10),   # pigment darkening at the furrow bottom (AO is separate)
]
sp = {n: scalar(n, v, -1300, 900 + i * 70, 'Surface') for i, (n, v) in enumerate(SURFACE)}

# everything the crease model needs, packed into FPHSkinParams inside the node body
STRUCT_ARGS = ['CreaseFrequency', 'CreaseSharpness', 'CreaseWarp', 'CreaseRange', 'FurrowWidth', 'PrimaryWidth', 'Irregularity',
               'SecondaryDepth', 'JointReach', 'CompressNarrow', 'StretchWiden',
               'FoldsMCP', 'FoldsPIP', 'FoldsDIP', 'DepthMCP', 'DepthPIP', 'DepthDIP', 'PalmSplit', 'SideFolds',
               'PalmarBase', 'PalmarCompress', 'PalmarIron', 'PalmarRelax',
               'DorsalBase', 'DorsalIron', 'DorsalRelax', 'SideSharpness', 'SideFlip',
               'MaskGain', 'MaskSharpness',
               'CreaseBow', 'PalmBow', 'SideTaper', 'ForkStrength', 'ForkAngle', 'SeedVariation', 'FoldFlattenStart', 'FoldFlattenFull',
               'PalmRange', 'PalmLineDepth', 'PalmLineWidth', 'PalmLineBase', 'PalmLineCompress', 'PalmLineIron',
               'FadeStartCm', 'FadeEndCm']

FILL_STRUCT = 'FPHSkinParams P;\n' + ''.join('P.%s = %s;\n' % (n, n) for n in STRUCT_ARGS)

GRAPH_ARGS = ['GraphCreases', 'GraphDepth', 'GraphSecondaryDepth', 'GraphFineDepth', 'GraphAlphaW', 'GraphAlphaD', 'GraphBeta',
              'GraphGrid', 'GraphTableWidth', 'GraphRelRange', 'GraphWidthRange']
NORMAL_ARGS = (['DetailTiling', 'DetailStrength', 'MicroAniso', 'MicroFlatten', 'VSign',
                'KnuckleTilingMul', 'KnuckleStrengthMul', 'SideTilingMul', 'SideStrengthMul',
                'RidgeTiling', 'RidgeStrength',
                'CreaseDepth', 'UVScaleCm', 'VeinTiling', 'VeinStrength', 'Eps'] + GRAPH_ARGS + STRUCT_ARGS)

NORMAL_BODY = FILL_STRUCT + """return PH_SkinNormal(
    UV, DUVx, DUVy, Tension, Relax,
    WrinkleMaskTex, WrinkleMaskTexSampler,
    WrinkleMask2Tex, WrinkleMask2TexSampler,
    SkinDetailTex, SkinDetailTexSampler,
    PalmRidgeTex, PalmRidgeTexSampler,
    VeinTex, VeinTexSampler,
    GraphCellsTex, GraphEdges0Tex, GraphEdges1Tex,
    DetailTiling, DetailStrength, MicroAniso, MicroFlatten, VSign,
    KnuckleTilingMul, KnuckleStrengthMul, SideTilingMul, SideStrengthMul, RidgeTiling, RidgeStrength,
    CreaseDepth, UVScaleCm, VeinTiling, VeinStrength, Eps,
    GraphCreases, GraphDepth, GraphSecondaryDepth, GraphFineDepth, GraphAlphaW, GraphAlphaD, GraphBeta,
    GraphGrid, GraphTableWidth, GraphRelRange, GraphWidthRange, P);"""

nrm_inputs = ['UV', 'DUVx', 'DUVy', 'Tension', 'Relax', 'WrinkleMaskTex', 'WrinkleMask2Tex', 'SkinDetailTex',
              'PalmRidgeTex', 'VeinTex', 'GraphCellsTex', 'GraphEdges0Tex', 'GraphEdges1Tex'] + NORMAL_ARGS
nrm = custom('PH_SkinNormal', NORMAL_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT3, nrm_inputs, -1000, -300)

SURF_BODY = FILL_STRUCT + """return PH_SkinSurface(UV, DUVx, DUVy, Tension, Relax,
    WrinkleMaskTex, WrinkleMaskTexSampler, WrinkleMask2Tex, WrinkleMask2TexSampler,
    VeinTex, VeinTexSampler, GraphCellsTex, GraphEdges0Tex, GraphEdges1Tex,
    UVScaleCm, VeinTiling, Eps,
    GraphCreases, GraphDepth, GraphSecondaryDepth, GraphFineDepth, GraphAlphaW, GraphAlphaD, GraphBeta,
    GraphGrid, GraphTableWidth, GraphRelRange, GraphWidthRange, CreaseDepth, P);"""
surf_inputs = ['UV', 'DUVx', 'DUVy', 'Tension', 'Relax', 'WrinkleMaskTex', 'WrinkleMask2Tex', 'VeinTex',
               'GraphCellsTex', 'GraphEdges0Tex', 'GraphEdges1Tex',
               'UVScaleCm', 'VeinTiling', 'Eps'] + GRAPH_ARGS + ['CreaseDepth'] + STRUCT_ARGS
surf = custom('PH_SkinSurface', SURF_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT4, surf_inputs, -1000, 500)

COLOR_BODY = """return PH_SkinBaseColor(Surface, SkinColor.rgb, FlushColor.rgb, BlanchColor.rgb, VeinColor.rgb, CreaseColor.rgb,
    BlanchGain, FlushGain, CavityDarken);"""
color_inputs = ['Surface', 'SkinColor', 'FlushColor', 'BlanchColor', 'VeinColor', 'CreaseColor',
                'BlanchGain', 'FlushGain', 'CavityDarken']
color = custom('PH_SkinBaseColor', COLOR_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT3, color_inputs, -500, 500)

RESP_BODY = """return PH_SkinResponse(Surface, Tension, Roughness, Specular,
    CavityRough, StretchSmooth, CavitySpecLoss, CavityAO, StretchThin);"""
resp_inputs = ['Surface', 'Tension', 'Roughness', 'Specular', 'CavityRough', 'StretchSmooth',
               'CavitySpecLoss', 'CavityAO', 'StretchThin']
resp = custom('PH_SkinResponse', RESP_BODY, unreal.CustomMaterialOutputType.CMOT_FLOAT4, resp_inputs, -500, 900)

# --- colours ------------------------------------------------------------------------------------
# the colour layers stay close to the skin tone - the relief should read from the NORMAL, not from
# painted-on dark bands, which look like dirt the moment the light moves
colours = {
    'SkinColor':   vector('SkinColor',   unreal.LinearColor(0.74, 0.50, 0.40, 1.0), -1300, 400),
    'FlushColor':  vector('FlushColor',  unreal.LinearColor(0.76, 0.40, 0.34, 1.0), -1300, 500),
    'BlanchColor': vector('BlanchColor', unreal.LinearColor(0.84, 0.66, 0.58, 1.0), -1300, 600),
    'VeinColor':   vector('VeinColor',   unreal.LinearColor(0.70, 0.55, 0.56, 1.0), -1300, 700),
    'CreaseColor': vector('CreaseColor', unreal.LinearColor(0.72, 0.40, 0.36, 1.0), -1300, 800),   # reference: furrows read pink, not dark
}


def wire(node, names):
    for n in names:
        if n == 'UV':
            mel.connect_material_expressions(uv, '', node, 'UV')
        elif n == 'DUVx':
            mel.connect_material_expressions(ddx, '', node, 'DUVx')
        elif n == 'DUVy':
            mel.connect_material_expressions(ddy, '', node, 'DUVy')
        elif n == 'Tension':
            mel.connect_material_expressions(vc, '', node, 'Tension')
        elif n == 'Relax':
            # the tension pass writes the relax slack into vertex-colour ALPHA
            mel.connect_material_expressions(vc, 'A', node, 'Relax')
        elif n == 'Surface':
            mel.connect_material_expressions(surf, '', node, 'Surface')
        elif n == 'WrinkleMaskTex':
            mel.connect_material_expressions(mask_tex, '', node, n)
        elif n == 'WrinkleMask2Tex':
            mel.connect_material_expressions(mask2_tex, '', node, n)
        elif n == 'SkinDetailTex':
            mel.connect_material_expressions(detail_tex, '', node, n)
        elif n == 'PalmRidgeTex':
            mel.connect_material_expressions(ridge_tex, '', node, n)
        elif n == 'VeinTex':
            mel.connect_material_expressions(vein_tex, '', node, n)
        elif n == 'GraphCellsTex':
            mel.connect_material_expressions(graph_cells, '', node, n)
        elif n == 'GraphEdges0Tex':
            mel.connect_material_expressions(graph_e0, '', node, n)
        elif n == 'GraphEdges1Tex':
            mel.connect_material_expressions(graph_e1, '', node, n)
        elif n in colours:
            mel.connect_material_expressions(colours[n], '', node, n)
        elif n in sp:
            mel.connect_material_expressions(sp[n], '', node, n)
        else:
            mel.connect_material_expressions(p[n], '', node, n)


wire(nrm, nrm_inputs)
wire(surf, surf_inputs)
wire(color, color_inputs)
wire(resp, resp_inputs)

# every Custom input has to be driven, or the whole material falls back to the default one
for node, names in ((nrm, nrm_inputs), (surf, surf_inputs), (color, color_inputs), (resp, resp_inputs)):
    have = [str(n) for n in mel.get_material_expression_input_names(node)]
    srcs = list(mel.get_inputs_for_material_expression(mat, node))
    missing = [n for n, src in zip(have, srcs) if src is None]
    if missing or len(have) != len(names) or len(srcs) != len(have):
        print('WARNING: %s has %d inputs (expected %d), %d sources, unconnected: %s'
              % (node.get_editor_property('description'), len(have), len(names), len(srcs), missing))

rough_out = mask(resp, -200, 900, r=True)
spec_out = mask(resp, -200, 980, g=True)
ao_out = mask(resp, -200, 1060, b=True)
opac_out = mask(resp, -200, 1140, a=True)

mel.connect_material_property(nrm, '', unreal.MaterialProperty.MP_NORMAL)
mel.connect_material_property(color, '', unreal.MaterialProperty.MP_BASE_COLOR)
mel.connect_material_property(rough_out, '', unreal.MaterialProperty.MP_ROUGHNESS)
mel.connect_material_property(spec_out, '', unreal.MaterialProperty.MP_SPECULAR)
mel.connect_material_property(ao_out, '', unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
mel.connect_material_property(opac_out, '', unreal.MaterialProperty.MP_OPACITY)

mat.set_editor_property('shading_model', unreal.MaterialShadingModel.MSM_SUBSURFACE_PROFILE)
if profile is not None:
    mat.set_editor_property('subsurface_profile', profile)
mat.set_editor_property('used_with_skeletal_mesh', True)
mel.recompile_material(mat)
eal.save_asset(PATH)
# 10-15: the parameter defaults the engine reports (and the MI inherits) lagged one run behind the
# values written into the ScalarParameter nodes - a second recompile after the save settles them.
stale = [n for n, v in PARAMS if abs(mel.get_material_default_scalar_parameter_value(mat, n) - v) > 1e-5]
if stale:
    print('defaults stale after first compile (%s) - recompiling once more' % ', '.join(stale[:6]))
    mel.recompile_material(mat)
    eal.save_asset(PATH)
    stale = [n for n, v in PARAMS if abs(mel.get_material_default_scalar_parameter_value(mat, n) - v) > 1e-5]
    print('defaults still stale: %s' % (stale or 'none'))

# --- MI, the tuning handle (scalar defaults on the Material itself need a full recompile) --------
if eal.does_asset_exist(MI_PATH):
    mi = unreal.load_asset(MI_PATH)
else:
    mi = tools.create_asset('MI_' + NAME[2:], PACKAGE, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
mi.set_editor_property('parent', mat)
mel.clear_all_material_instance_parameters(mi)
# 10-15: the defaults the engine reports for the base material lag one script run behind the node
# values (see above), so the MI carries every scalar explicitly - what set_skin() reads and writes.
for n, v in PARAMS:
    mel.set_material_instance_scalar_parameter_value(mi, n, float(v))
eal.save_asset(MI_PATH)

print('M_PianoHandSkin ready:', PATH, '(shading model: Subsurface Profile ->', SSP_PATH if profile else 'engine default', ')')
print('MI_PianoHandSkin ready:', MI_PATH)
