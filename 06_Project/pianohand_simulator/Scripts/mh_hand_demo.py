"""PianoHand demo on the MetaHuman hand.

    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/mh_hand_demo.py').read())

Mesh    /Game/Characters/MetaHumanHand/SKM_MH_Hand_R_Dense   (77k verts, PN tess level 3)
Anim    /Game/Characters/MetaHumanHand/A_MH_Hand_Cycle       (4s idle -> grasp -> release -> settle)

Both come from extract_metahuman_hand.py / make_mh_hand_poses.py. The MannyXR pose assets do not
apply here: metahuman_base_skel is a different skeleton.

One editor quirk worth knowing: the single-node anim instance is created lazily, so set_position()
in the SAME call that spawns the actor is dropped. Spawn first, pose in a later call - which is
exactly what set_t() below is for.

Helpers left in the global namespace:
    set_t(1.6)                   # scrub the cycle; MARKS names the interesting moments
    mark('released')             # set_t by name: idle | closing | grasp | released | settled
    use_material('skin'|'tension'|'clay')
    set_detail(crease_depth=0.06, relax_gain=8.0, ...)
    set_skin(DorsalBase=0.65, DorsalIron=6.0, ...)
    skin_params()
    view('dorsal', 16)           # repeatable camera, derived from the rig's own flexion axis
    shot('name')                 # HighResShot; must be its own call, after the pose settles
"""
import unreal

MESH = '/Game/Characters/MetaHumanHand/SKM_MH_Hand_R_Dense'
ANIM = '/Game/Characters/MetaHumanHand/A_MH_Hand_Cycle'
MATERIALS = {
    'skin':    '/Game/PianoHand/MI_PianoHandSkin',
    'tension': '/Game/PianoHand/M_PianoHandTension',
    'clay':    '/Game/PianoHand/M_PianoHandClay',
}
MARKS = {'idle': 0.25, 'closing': 0.85, 'grasp': 1.60, 'released': 2.55, 'settled': 3.60}

LABEL = 'PH_MH_Hand'
SPAWN_AT = unreal.Vector(0, -60, 120)
MODE = unreal.PianoHandSkinMode.LINEAR_BLEND
TENSION_SCALE = 8.0
START_MAT = 'skin'

# Same displacement tuning the MannyXR hand ended Phase 3d on. The MetaHuman hand is a similar
# vertex count (77k vs 92k) and the same physical size, so these carry over; the one thing that
# does change is the material's DetailTiling, because the UVs were repacked.
DETAIL = dict(
    crease_depth            = 0.055,
    crease_sharpness        = 3.0,
    crease_compression_gain = 0.9,
    crease_stretch_relief   = 2.2,
    wrinkle_amplitude       = 0.035,
    wrinkle_frequency       = 6.0,
    volume_bulge            = 0.15,
    # 0.45s is closer to real skin, but the fold it leaves is then gone before a
    # screenshot round-trip can catch it; 0.9s reads in motion and still stills.
    relax_gain              = 12.0,
    relax_tau               = 0.9,
    relax_crease_gain       = 0.06,
)

ELL = unreal.EditorLevelLibrary


def _spawn():
    for a in ELL.get_all_level_actors():
        if a.get_actor_label() == LABEL:
            ELL.destroy_actor(a)
    actor = ELL.spawn_actor_from_class(unreal.SkeletalMeshActor, SPAWN_AT, unreal.Rotator(0, 0, 0))
    actor.set_actor_label(LABEL)
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(unreal.load_asset(MESH))
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    comp.set_animation(unreal.load_asset(ANIM))
    comp.set_update_animation_in_editor(True)
    comp.play(False)
    return actor, comp


hand_actor, hand_comp = _spawn()

deformer = unreal.PianoHandSkinningLibrary.apply_custom_skinning(hand_comp, MODE, True, TENSION_SCALE, True)
for _k, _v in DETAIL.items():
    deformer.set_editor_property(_k, _v)


def use_material(key='skin'):
    mat = unreal.load_asset(MATERIALS[key])
    if mat is None:
        print('WARNING: %s not found' % MATERIALS[key])
        return
    for slot in range(hand_comp.get_num_materials()):
        hand_comp.set_material(slot, mat)
    print('material ->', key)


def set_t(seconds):
    hand_comp.set_position(float(seconds), False)
    print('t -> %.2fs' % seconds)


def mark(name):
    set_t(MARKS[name])


def set_detail(**kw):
    for k, v in kw.items():
        deformer.set_editor_property(k, float(v) if not isinstance(v, bool) else v)
    print('detail ->', kw)


def set_skin(**kw):
    mi = unreal.load_asset(MATERIALS['skin'])
    for k, v in kw.items():
        unreal.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(mi, k, float(v))
    unreal.EditorAssetLibrary.save_asset(MATERIALS['skin'])
    print('skin ->', kw)


def set_skin_texture(param, path):
    mi = unreal.load_asset(MATERIALS['skin'])
    unreal.MaterialEditingLibrary.set_material_instance_texture_parameter_value(mi, param, unreal.load_asset(path))
    unreal.EditorAssetLibrary.save_asset(MATERIALS['skin'])
    print('skin texture %s -> %s' % (param, path))


def skin_params():
    mi = unreal.load_asset(MATERIALS['skin'])
    mel = unreal.MaterialEditingLibrary
    for n in sorted(str(x) for x in mel.get_scalar_parameter_names(unreal.load_asset('/Game/PianoHand/M_PianoHandSkin'))):
        print('  %-16s %s' % (n, mel.get_material_instance_scalar_parameter_value(mi, n)))


def look_at_hand(dist=18.0, height=4.0, pitch=-8.0, side=3.0):
    p = hand_comp.get_socket_transform('middle_01_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
    ELL.set_level_viewport_camera_info(p + unreal.Vector(-dist, side, height),
                                       unreal.Rotator(roll=0.0, pitch=pitch, yaw=0.0))


def view(side='dorsal', dist=17.0, lift=0.0):
    """Frame the hand from the back or the palm, derived from the rig rather than eyeballed.

    Flexion is a negative rotation about the bone's local +Z, and a point offset along
    cross(flexAxis, boneDir) stretches when the joint bends - so that direction IS the back of the
    hand. Bones run down local -X, so it works out to the bone's -Y. Same derivation the wrinkle
    mask's alpha channel is baked from, which is what makes these views line up with it.

    The direction comes from hand_r and nothing else. Take it from a finger bone instead and the
    camera swings with the curl, so a 'dorsal' view set while the fist is closed lands on the palm
    once the hand opens. hand_r is never animated here, so it is the stable frame.
    """
    ML = unreal.MathLibrary
    wrist = hand_comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
    knuck = hand_comp.get_socket_transform('middle_02_r', unreal.RelativeTransformSpace.RTS_WORLD)
    target = (wrist.translation + knuck.translation) * 0.5 + unreal.Vector(0, 0, lift)
    rot = wrist.rotation.rotator()
    dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)     # -Y
    d = dorsal if side == 'dorsal' else (
        ML.multiply_vector_float(dorsal, -1.0) if side == 'palmar' else ML.get_up_vector(rot))
    eye = target + ML.multiply_vector_float(d, dist)
    ELL.set_level_viewport_camera_info(eye, ML.find_look_at_rotation(eye, target))
    print('view -> %s, %.0fcm' % (side, dist))


def shot(name, width=1920, height=1080):
    """One HighResShot. It only fires when the editor TICKS, and a blocking python call is not a
    tick, so this has to be its own call - and the call that changed the pose has to be an earlier
    one, or the previous pose is what lands in the file."""
    unreal.SystemLibrary.execute_console_command(
        ELL.get_editor_world(), 'HighResShot %dx%d filename="%s"' % (width, height, name))
    print('shot ->', name)


use_material(START_MAT)
print('MetaHuman hand ready: %d bones, %d material slot(s)' % (hand_comp.get_num_bones(), hand_comp.get_num_materials()))
print("pose with mark('grasp') / set_t(2.55) - NOT in this same call, the anim instance is not up yet")
