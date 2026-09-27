"""Author a flexion cycle for the MetaHuman hand so the Phase 3 tension pipeline has a real pose
TRANSITION to react to.

    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/make_mh_hand_poses.py').read())

The MannyXR pose assets do not apply here - metahuman_base_skel is a different skeleton - so the
cycle is generated directly on the bone tracks. MetaHuman finger bones point down -X and bend on
local yaw (the reference pose already carries yaw -24 / -20 / -4 on middle_01/02/03), so a curl is
just a negative yaw delta composed onto each joint's reference rotation.

Why a cycle rather than static poses: the relax/hysteresis term only exists while strain is
CHANGING. A held grasp shows creases; the wrinkles that appear as a knuckle straightens out need
the release itself. The cycle holds idle, closes, holds, opens, then holds long enough for the
slack to decay.

Produces /Game/Characters/MetaHumanHand/A_MH_Hand_Cycle.
"""
import unreal

SKELETON = '/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel'
DST_DIR = '/Game/Characters/MetaHumanHand'
ANIM_NAME = 'A_MH_Hand_Cycle'
ANIM_PATH = DST_DIR + '/' + ANIM_NAME

FPS = 30
DURATION = 4.0

# curl = 0 at rest, 1 at full grasp
KEYFRAMES = [(0.0, 0.0), (0.5, 0.0), (1.2, 1.0), (2.0, 1.0), (2.5, 0.0), (4.0, 0.0)]

# named sample times for screenshots / A-B shots
MARKS = {'idle': 0.25, 'closing': 0.85, 'grasp': 1.60, 'released': 2.55, 'settled': 3.60}

# degrees of yaw at curl = 1, per joint
CURL = {
    '%s_metacarpal_r': 0.0,
    '%s_01_r': -68.0,
    '%s_02_r': -82.0,
    '%s_03_r': -46.0,
}
FINGERS = ['index', 'middle', 'ring', 'pinky']
# the palm cups as the outer fingers close
METACARPAL_CUP = {'index': 0.0, 'middle': 0.0, 'ring': -7.0, 'pinky': -13.0}
THUMB = {'thumb_01_r': -22.0, 'thumb_02_r': -30.0, 'thumb_03_r': -34.0}

ML = unreal.MathLibrary


def curl_at(t):
    for i in range(len(KEYFRAMES) - 1):
        t0, v0 = KEYFRAMES[i]
        t1, v1 = KEYFRAMES[i + 1]
        if t0 <= t <= t1:
            if t1 <= t0:
                return v1
            a = (t - t0) / (t1 - t0)
            a = a * a * (3.0 - 2.0 * a)          # smoothstep: no velocity step at the corners
            return v0 + (v1 - v0) * a
    return KEYFRAMES[-1][1]


def bone_curl_degrees():
    """bone name -> yaw degrees at curl = 1"""
    out = {}
    for f in FINGERS:
        for pattern, deg in CURL.items():
            name = pattern % f
            d = METACARPAL_CUP[f] if 'metacarpal' in pattern else deg
            if d != 0.0:
                out[name] = d
    out.update(THUMB)
    return out


def reference_locals(names):
    """reference-pose parent-relative transform for each requested bone"""
    mesh = unreal.load_asset(DST_DIR + '/SKM_MH_Hand_R_Dense')
    dyn = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property('lod_index', 0)
    dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
        mesh, dyn, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    _, bones = unreal.GeometryScript_BoneWeights.get_all_bones_info(dyn)
    table = {str(b.name): b.local_transform for b in bones}
    missing = [n for n in names if n not in table]
    if missing:
        raise RuntimeError('bones not on the mesh: %s' % missing)
    return {n: table[n] for n in names}


def create_anim():
    skel = unreal.load_asset(SKELETON)
    if skel is None:
        raise RuntimeError('skeleton not found: ' + SKELETON)
    if unreal.EditorAssetLibrary.does_asset_exist(ANIM_PATH):
        unreal.EditorAssetLibrary.delete_asset(ANIM_PATH)
    factory = unreal.AnimSequenceFactory()
    factory.set_editor_property('target_skeleton', skel)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(ANIM_NAME, DST_DIR, unreal.AnimSequence, factory)


def run():
    degrees = bone_curl_degrees()
    refs = reference_locals(list(degrees.keys()))
    anim = create_anim()
    frames = int(round(DURATION * FPS))
    times = [i / float(FPS) for i in range(frames + 1)]
    curls = [curl_at(t) for t in times]

    ctrl = anim.get_editor_property('controller')
    ctrl.open_bracket('build hand cycle')
    ctrl.set_frame_rate(unreal.FrameRate(FPS, 1))
    ctrl.set_number_of_frames(unreal.FrameNumber(frames))
    for name, deg in degrees.items():
        ref = refs[name]
        ref_rot = ref.rotation.rotator()
        pos, rot, scl = [], [], []
        for c in curls:
            delta = unreal.Rotator(roll=0.0, pitch=0.0, yaw=deg * c)
            pos.append(ref.translation)
            rot.append(ML.compose_rotators(delta, ref_rot).quaternion())
            scl.append(unreal.Vector(1.0, 1.0, 1.0))
        ctrl.add_bone_track(name)
        ctrl.set_bone_track_keys(name, pos, rot, scl)
    ctrl.close_bracket()
    unreal.EditorAssetLibrary.save_asset(ANIM_PATH)
    print('%s: %d bone tracks, %d frames @%dfps (%.1fs)' % (ANIM_NAME, len(degrees), frames, FPS, DURATION))
    print('marks:', ', '.join('%s=%.2fs' % kv for kv in sorted(MARKS.items(), key=lambda kv: kv[1])))
    return anim


anim_cycle = run()
