"""PianoHand Phase 3b demo: dense hand mesh + geometric creases + procedural skin wrinkles/veins.

Run inside the editor (Python console / unreal-mcp execute_python):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/hand_tension_demo.py').read())

Meshes
  base  : /Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right         (5787 verts)
  dense : /Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right_Dense   (91752 verts, PN tess level 3)
          built by subdivide_hand.py - the extra vertices are what the Phase 3 crease/wrinkle
          displacement pass actually needs to resolve per-knuckle folds.

Materials
  skin    : M_PianoHandSkin     procedural wrinkles + veins + detail normal, driven by the tension
                                vertex colour (compression -> creases, stretch -> veins)
  tension : M_PianoHandTension  raw strain debug view (red stretch / blue compression)
  clay    : M_PianoHandClay     matte grey, for judging the geometry alone

Spawns two hands side by side:
  PH_Hand_Custom  (Y=0)  -> UPianoHandSkinDeformer: skinning + tension + detail displacement
  PH_Hand_Engine  (Y=25) -> engine GPU skin cache, original materials (reference)

Helpers left in the global namespace:
    set_pose('Grasp')            # Idle | IndexCurl | Point | ThumbUp | Grasp
    set_scale(8.0)               # tension colour gain
    use_mesh('dense'|'base')
    use_material('skin'|'tension'|'clay')
    set_detail(crease_depth=0.08, wrinkle_amplitude=0.06, ...)   # deformer displacement tuning
    set_skin(WrinkleDepth=0.012, WrinkleTiling=70, ...)          # MI_PianoHandSkin scalars
    skin_params()                # print every material scalar and its current value
    look_at_hand(dist)
    compare_with_engine(True/False)
"""
import unreal

MESHES = {
    'base':  '/Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right',
    'dense': '/Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right_Dense',
}
MATERIALS = {
    'skin':    '/Game/PianoHand/MI_PianoHandSkin',   # instance, so set_skin() needs no recompile
    'tension': '/Game/PianoHand/M_PianoHandTension',
    'clay':    '/Game/PianoHand/M_PianoHandClay',
}
ANIM  = '/Game/Characters/MannequinsXR/Animations/A_MannequinsXR_%s_Right'
POSES = ['Idle', 'IndexCurl', 'Point', 'ThumbUp', 'Grasp']

MODE          = unreal.PianoHandSkinMode.LINEAR_BLEND
TENSION_SCALE = 8.0
START_MESH    = 'dense'
START_MAT     = 'skin'

# Deformer displacement tuning that reads well on the dense mesh. The C++ defaults were set for the
# 5.8k-vert base mesh; at 92k verts the same crease depth over-shoots and tears the surface where
# the fingers fold hardest, so the compression gain comes down and the depths come with it.
DETAIL = dict(
    crease_depth            = 0.05,
    crease_sharpness        = 3.0,
    crease_compression_gain = 0.6,
    wrinkle_amplitude       = 0.035,
    wrinkle_frequency       = 6.0,
    volume_bulge            = 0.15,
)

ELL = unreal.EditorLevelLibrary


def _destroy(label):
    for a in ELL.get_all_level_actors():
        if a.get_actor_label() == label:
            ELL.destroy_actor(a)


def spawn(label, y, mesh_key):
    _destroy(label)
    actor = ELL.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, y, 120), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(label)
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(unreal.load_asset(MESHES[mesh_key]))
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    comp.set_animation(unreal.load_asset(ANIM % 'Idle'))
    comp.set_update_animation_in_editor(True)
    comp.play(False)          # hold the single pose frame
    return actor, comp


custom_actor, custom_comp = spawn('PH_Hand_Custom', 0, START_MESH)
engine_actor, engine_comp = spawn('PH_Hand_Engine', 25, START_MESH)

# bComputeTension=True, bDetailDisplacement=True -> creases/volume/wrinkles in the compute pass
deformer = unreal.PianoHandSkinningLibrary.apply_custom_skinning(custom_comp, MODE, True, TENSION_SCALE, True)
for _k, _v in DETAIL.items():
    deformer.set_editor_property(_k, _v)


def use_material(key='skin'):
    mat = unreal.load_asset(MATERIALS[key])
    if mat is None:
        print('WARNING: %s not found' % MATERIALS[key])
        return
    for slot in range(custom_comp.get_num_materials()):
        custom_comp.set_material(slot, mat)
    print('material ->', key)


def use_mesh(key='dense'):
    """Swap both hands onto a different source mesh and re-apply the deformer."""
    global deformer
    asset = unreal.load_asset(MESHES[key])
    if asset is None:
        print('WARNING: %s not found - run subdivide_hand.py first' % MESHES[key])
        return
    unreal.PianoHandSkinningLibrary.remove_custom_skinning(custom_comp)
    for c in (custom_comp, engine_comp):
        c.set_skeletal_mesh_asset(asset)
        c.play(False)
        c.set_position(0.0, False)
    deformer = unreal.PianoHandSkinningLibrary.apply_custom_skinning(custom_comp, MODE, True, TENSION_SCALE, True)
    for k, v in DETAIL.items():
        deformer.set_editor_property(k, v)
    use_material(START_MAT)
    print('mesh -> %s (%d verts)' % (key, unreal.EditorSkeletalMeshLibrary.get_num_verts(asset, 0)))


def set_pose(name):
    anim = unreal.load_asset(ANIM % name)
    for c in (custom_comp, engine_comp):
        c.set_animation(anim)
        c.play(False)
        c.set_position(0.0, False)
    print('pose ->', name)


def set_scale(v):
    deformer.set_editor_property('tension_scale', float(v))
    print('tension_scale ->', v)


def set_detail(**kw):
    """Deformer displacement tuning, e.g.
       set_detail(crease_depth=0.09, crease_sharpness=2.2, wrinkle_amplitude=0.07, wrinkle_frequency=14)"""
    for k, v in kw.items():
        deformer.set_editor_property(k, float(v) if not isinstance(v, bool) else v)
    print('detail ->', kw)


def set_skin(**kw):
    """Live material tuning on MI_PianoHandSkin - no shader recompile, e.g.
       set_skin(WrinkleDepth=0.012, WrinkleTiling=70, MicroDepth=0.002, NormalStrength=0.7)"""
    mi = unreal.load_asset(MATERIALS['skin'])
    mel = unreal.MaterialEditingLibrary
    for k, v in kw.items():
        mel.set_material_instance_scalar_parameter_value(mi, k, float(v))
    unreal.EditorAssetLibrary.save_asset(MATERIALS['skin'])
    print('skin ->', kw)


def skin_params():
    """Every scalar parameter M_PianoHandSkin exposes, with its current instance value."""
    mi = unreal.load_asset(MATERIALS['skin'])
    mel = unreal.MaterialEditingLibrary
    for n in mel.get_scalar_parameter_names(unreal.load_asset('/Game/PianoHand/M_PianoHandSkin')):
        print('  %-16s %s' % (n, mel.get_material_instance_scalar_parameter_value(mi, n)))


def look_at_hand(dist=20.0, height=5.0, pitch=-8.0):
    # NOTE: unreal.Rotator(a, b, c) is (roll, pitch, yaw) in Python - always pass pitch by keyword.
    p = custom_comp.get_socket_transform('middle_02_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
    ELL.set_level_viewport_camera_info(p + unreal.Vector(-dist, 6, height),
                                       unreal.Rotator(roll=0.0, pitch=pitch, yaw=0.0))


def compare_with_engine(show_custom=True):
    """A/B the skinning itself: same frozen pose + the mesh's own material on both, tension off."""
    orig = custom_comp.get_skinned_asset().get_editor_property('materials')[0].material_interface
    engine_actor.set_actor_location(custom_actor.get_actor_location(), False, False)
    for c in (custom_comp, engine_comp):
        c.play(False)
        c.set_position(0.0, False)      # freeze frame 0 - a looping 2-frame pose asset drifts otherwise
        c.set_material(0, orig)
    deformer.set_editor_property('compute_tension', False)
    custom_comp.set_visibility(show_custom)
    engine_comp.set_visibility(not show_custom)
    print('showing', 'custom' if show_custom else 'engine')


use_material(START_MAT)

bones = [str(custom_comp.get_bone_name(i)) for i in range(custom_comp.get_num_bones())]
print('hand spawned: mesh=%s  %d bones, %d material slot(s)' % (START_MESH, len(bones), custom_comp.get_num_materials()))
print("use set_pose('Grasp') / set_detail(crease_depth=0.09) / set_skin(WrinkleDepth=0.012) / skin_params() / look_at_hand()")
