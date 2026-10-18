"""PianoHand demo on the MetaHuman hand.

    exec(open('<project>/Scripts/mh_hand_demo.py').read())          # Windows or macOS

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

Phase 5 helpers (individual hands):
    measure()                                    # the mesh's own palm / finger lengths, cm
    set_proportions(index=(1.1, 1.05, 1.0), ...) # per-finger (proximal, middle, distal) length scales
    set_proportions(palm_length=1.08, palm_width=0.95, thickness=0.9, overall=1.0)
    fit_measurements(palm_length=10.5, index=(4.6, 2.6, 2.3), ...)   # target cm -> scale factors
    reset_proportions()
    use_mask_groove(True)                        # geometric groove on the primary crease line (mask-driven)
    use_implicit(True, implicit_bulge=0.1)       # Phase 8 implicit skinning on/off (+ any implicit_* override)
    implicit_summary()                           # what was fitted (prims, centres, iso range)
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
    # the geometric groove is kept shallow and tight: a 0.5mm trench the width of the whole joint
    # band read as a cuff; the crease LOOK comes from the material's furrows
    crease_depth            = 0.0,      # the resting groove is a material job now; any geometric
    crease_sharpness        = 4.5,      # trench the width of the band reads as a cuff
    crease_compression_gain = 0.9,
    crease_stretch_relief   = 2.2,
    # geometric ripples are kept small: the fine folds are a normal-map job, and 0.35mm of
    # real displacement on a 77k mesh reads as lumps
    wrinkle_amplitude       = 0.012,
    wrinkle_frequency       = 6.0,
    volume_bulge            = 0.35,     # Phase 7: the roll-up at a bent joint IS this term (1/J thickness), see §1-M
    tensor_smooth_iterations = 3,       # Phase 7b: 1-ring Laplacian passes on the strain tensor (fist cobbles without it)
    bulge_gain              = 0.0,      # the capsule ring bulge reads as a ligature; contact push stays on
    # 0.45s is closer to real skin, but the fold it leaves is then gone before a
    # screenshot round-trip can catch it; 0.9s reads in motion and still stills.
    relax_gain              = 12.0,
    relax_tau               = 0.9,
    relax_crease_gain       = 0.03,
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

# Phase 5: the geometric groove follows the baked crease LINE instead of the whole joint band
MASK = '/Game/PianoHand/Textures/T_PH_WrinkleMask'
MASK_GROOVE = dict(mask_crease_depth=0.035, mask_crease_width=0.12,
                   dorsal_gather=0.045, dorsal_gather_spacing=0.24, dorsal_gather_reach=0.7, dorsal_gather_base=0.8, dorsal_gather_iron=8.0,
                   # 10-18 fold pile on the inside of a bending joint: pads bulge, secondary fold, primary crease deepens (sqrt of the drive)
                   palmar_pad_height=0.10, palmar_pad_dist=0.30, palmar_pad_width=0.22, palmar_fold2_depth=0.05, palmar_fold2_dist=0.55,
                   palmar_fold2_width=0.10, palmar_crease_deepen=0.08, palmar_fold_bend_full=1.2)


def use_mask_groove(on=True):
    deformer.set_editor_property('wrinkle_mask', unreal.load_asset(MASK) if on else None)
    for k, v in MASK_GROOVE.items():
        deformer.set_editor_property(k, v)
    print('mask groove ->', on)


use_mask_groove(True)

# Phase 8: implicit skinning (Vaillant et al. 2013) - HRBF field per bone part, Newton projection
# of the LBS/DQS pose back to each vertex's rest iso-value, contact stop at 55 deg, tangential
# relaxation, localised Laplacian smoothing, gradient-based bulge-in-contact. See
# Docs/ImplicitSkinning_Study.md. The capsule contact push is superseded by it.
IMPLICIT = dict(
    implicit_iterations=12, implicit_sigma=0.35, implicit_stop_angle=55.0, implicit_max_step=0.3,
    implicit_tolerance=0.002, implicit_relax=1.0, implicit_beta_diffusion=12, implicit_smooth_iterations=24,
    implicit_smooth_beta=1.0, implicit_bulge=0.0, implicit_bulge_start=15.0, implicit_bulge_full=70.0,
    implicit_bend_start=10.0, implicit_bend_full=40.0, implicit_contact_depth=0.25, implicit_stretch_keep=0.25,
    implicit_samples_per_bone=50, implicit_palm_samples=100,
)


def use_implicit(on=True, **kw):
    """Switch the implicit skinning stage; kw overrides any implicit_* property."""
    params = dict(IMPLICIT)
    params.update(kw)
    for k, v in params.items():
        deformer.set_editor_property(k, v)
    deformer.set_editor_property('implicit_skinning', bool(on))
    deformer.set_editor_property('contact_bulge', not on)   # capsule contact is the pre-implicit fallback
    # the implicit volume replaces most of the 1/J bulge; the strain pass would otherwise amplify every
    # contact push into a crushed knuckle. DQS is the paper's initial solution (LBS self-intersects deeper).
    deformer.set_editor_property('volume_bulge', 0.15 if on else DETAIL['volume_bulge'])
    deformer.set_editor_property('skin_mode', unreal.PianoHandSkinMode.DUAL_QUATERNION if on else MODE)
    print('implicit skinning ->', on)


def implicit_summary():
    s = unreal.PianoHandSkinningLibrary.get_implicit_skinning_summary(hand_comp)
    print('implicit:', s or '(not built yet - needs a rendered frame)')
    return s


use_implicit(True)

FINGERS = ('thumb', 'index', 'middle', 'ring', 'pinky')


def _finger_struct(spec, thickness=None):
    f = unreal.PianoHandFingerProportions()
    if spec is not None:
        p, m, d = spec
        f.set_editor_property('proximal', float(p)); f.set_editor_property('middle', float(m)); f.set_editor_property('distal', float(d))
    if thickness is not None:
        f.set_editor_property('thickness', float(thickness))
    return f


def set_proportions(palm_length=None, palm_width=None, palm_thickness=None, thickness=None, overall=None, **fingers):
    """Scale factors on the authored hand, applied per bone inside the deformer. Lengths move the
    joints downstream and stretch the segment's skin; the strain field is taken against the scaled
    rest pose, so a longer finger does not read as a stretched one. Omitted entries keep their value.
        set_proportions(index=(1.1, 1.05, 1.0), pinky=(0.9, 0.9, 0.9), thickness=0.95)"""
    P = deformer.get_editor_property('proportions')
    if palm_length is not None: P.set_editor_property('palm_length', float(palm_length))
    if palm_width is not None: P.set_editor_property('palm_width', float(palm_width))
    if palm_thickness is not None: P.set_editor_property('palm_thickness', float(palm_thickness))
    if overall is not None: P.set_editor_property('overall_scale', float(overall))
    for name in FINGERS:
        if name in fingers or thickness is not None:
            cur = P.get_editor_property(name)
            spec = fingers.get(name)
            if spec is not None:
                cur.set_editor_property('proximal', float(spec[0])); cur.set_editor_property('middle', float(spec[1])); cur.set_editor_property('distal', float(spec[2]))
            if thickness is not None:
                cur.set_editor_property('thickness', float(thickness))
            P.set_editor_property(name, cur)
    deformer.set_editor_property('proportions', P)
    print('proportions ->', {k: v for k, v in dict(palm_length=palm_length, palm_width=palm_width, thickness=thickness, overall=overall, **fingers).items() if v is not None})


def reset_proportions():
    deformer.set_editor_property('proportions', unreal.PianoHandProportions())
    print('proportions -> identity')


def measure():
    """Palm length / width and each finger's segment lengths of the mesh's reference pose, in cm."""
    m = unreal.PianoHandSkinningLibrary.measure_hand(hand_comp)
    print('palm  length %.2f  width %.2f' % (m.get_editor_property('palm_length'), m.get_editor_property('palm_width')))
    for name in FINGERS:
        f = m.get_editor_property(name)
        print('%-7s proximal %.2f  middle %.2f  distal %.2f' % (name, f.get_editor_property('proximal'), f.get_editor_property('middle'), f.get_editor_property('distal')))
    return m


def fit_measurements(palm_length=0.0, palm_width=0.0, **fingers):
    """Turn a real hand's measurements (cm; 0 = leave as authored) into proportions and apply them.
        fit_measurements(palm_length=10.5, palm_width=8.2, index=(4.6, 2.7, 2.3), pinky=(3.4, 2.0, 1.9))"""
    t = unreal.PianoHandMeasurements()
    t.set_editor_property('palm_length', float(palm_length)); t.set_editor_property('palm_width', float(palm_width))
    for name in FINGERS:
        if name in fingers:
            fl = unreal.PianoHandFingerLengths()
            p, m, d = fingers[name]
            fl.set_editor_property('proximal', float(p)); fl.set_editor_property('middle', float(m)); fl.set_editor_property('distal', float(d))
            t.set_editor_property(name, fl)
    P = unreal.PianoHandSkinningLibrary.proportions_from_measurements(hand_comp, t)
    deformer.set_editor_property('proportions', P)
    print('fitted proportions: palm %.3f x %.3f' % (P.get_editor_property('palm_length'), P.get_editor_property('palm_width')))
    for name in FINGERS:
        f = P.get_editor_property(name)
        print('  %-7s %.3f %.3f %.3f' % (name, f.get_editor_property('proximal'), f.get_editor_property('middle'), f.get_editor_property('distal')))
    return P


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
