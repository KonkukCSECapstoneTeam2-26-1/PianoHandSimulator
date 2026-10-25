"""Build an AnimSequence for the MetaHuman right hand from the IK handoff CSVs.

Format spec: Docs/Kyungmin/IK_Handoff_Format.md.  Run it inside the editor (Output Log > Python console, or
Tools > Execute Python Script):

    IK_JOINTS_CSV = r'C:/path/to/joints.csv'          # optional overrides; defaults to the sample files
    IK_WRIST_CSV  = r'C:/path/to/wrist.csv'
    IK_ANIM_NAME  = 'A_IK_Import'
    exec(open(r'<project>/Scripts/import_ik_csv_to_anim.py').read())

Each CSV angle is a DELTA from the bone's reference pose, composed onto the reference rotation exactly like
make_mh_hand_poses.py does. MetaHuman finger bones point down -X and bend on local yaw, so:

    yaw   = SIGN['flex']  * flex_deg      (IK flex is + when closing, MetaHuman curls with negative yaw -> -1)
    pitch = SIGN['abd']   * abd_deg       (spread, about the palm normal)
    roll  = SIGN['twist'] * twist_deg     (about the finger axis)

The sign/axis table is the part to confirm against the IK program's own convention - it lives in one place (SIGN).
An existing asset of the same name is re-keyed instead of deleted, so levels that reference it keep working.
"""
import importlib
import os
import sys

import unreal

SKELETON = '/MetaHumanCharacter/Female/Medium/NormalWeight/Body/metahuman_base_skel'
# same mesh make_mh_hand_poses.py reads reference-pose bone transforms from
REF_MESH = '/Game/Characters/MetaHumanHand/SKM_MH_Hand_R_Dense'
DST_DIR = globals().get('IK_DST_DIR', '/Game/Characters/MetaHumanHand')
ANIM_NAME = globals().get('IK_ANIM_NAME', 'A_IK_Import')
ANIM_PATH = DST_DIR + '/' + ANIM_NAME

PROJECT_DIR = unreal.Paths.project_dir()
SCRIPTS_DIR = os.path.join(PROJECT_DIR, 'Scripts')
SAMPLES_DIR = os.path.join(PROJECT_DIR, 'Docs', 'Kyungmin', 'samples')
JOINTS_CSV = globals().get('IK_JOINTS_CSV', os.path.join(SAMPLES_DIR, 'ik_sample_joints.csv'))
WRIST_CSV = globals().get('IK_WRIST_CSV', None)
SIGN = globals().get('IK_SIGN', {'flex': -1.0, 'abd': 1.0, 'twist': 1.0})
# The IK program's axes (x = depth, y = height, z = left-right) are not UE's, and how the wrist is placed (bone offset
# vs component move) is undecided - so wrist TRANSLATION stays off until both are settled. Wrist rotation is applied.
APPLY_WRIST_TRANSLATION = globals().get('IK_APPLY_WRIST_TRANSLATION', False)

if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)
import check_ik_csv as fmt  # noqa: E402
importlib.reload(fmt)

ML = unreal.MathLibrary
FPS = fmt.FPS


def reference_locals(names):
    """reference-pose parent-relative transform for each requested bone"""
    mesh = unreal.load_asset(REF_MESH)
    if mesh is None:
        raise RuntimeError('reference mesh not found: ' + REF_MESH)
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
        anim = unreal.load_asset(ANIM_PATH)
        anim.get_editor_property('controller').remove_all_bone_tracks()
        return anim
    factory = unreal.AnimSequenceFactory()
    factory.set_editor_property('target_skeleton', skel)
    return unreal.AssetToolsHelpers.get_asset_tools().create_asset(ANIM_NAME, DST_DIR, unreal.AnimSequence, factory)


def run():
    tracks, errors, warnings = fmt.check(JOINTS_CSV, WRIST_CSV)
    for w in warnings:
        unreal.log_warning('[IK import] ' + w)
    if errors:
        raise RuntimeError('invalid IK CSV:\n  ' + '\n  '.join(errors))

    wrist = None
    if WRIST_CSV:
        wrist, _, _ = fmt.load_wrist(WRIST_CSV)

    bones = list(tracks.keys()) + (['hand_r'] if wrist else [])
    refs = reference_locals(bones)
    n_keys = len(next(iter(tracks.values())))

    anim = create_anim()
    ctrl = anim.get_editor_property('controller')
    ctrl.open_bracket('import IK csv')
    ctrl.set_frame_rate(unreal.FrameRate(FPS, 1))
    ctrl.set_number_of_frames(unreal.FrameNumber(n_keys - 1))

    one = unreal.Vector(1.0, 1.0, 1.0)
    for bone in bones:
        ref = refs[bone]
        ref_rot = ref.rotation.rotator()
        pos, rot, scl = [], [], []
        for i in range(n_keys):
            if bone == 'hand_r':
                x, y, z, yaw, pitch, roll = wrist[i]
                delta = unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw)
                if APPLY_WRIST_TRANSLATION:
                    pos.append(ref.translation + unreal.Vector(x, y, z))   # offset in the parent bone's space (cm)
                else:
                    pos.append(ref.translation)
            else:
                flex, abd, twist = tracks[bone][i]
                delta = unreal.Rotator(roll=SIGN['twist'] * twist, pitch=SIGN['abd'] * abd, yaw=SIGN['flex'] * flex)
                pos.append(ref.translation)
            rot.append(ML.compose_rotators(delta, ref_rot).quaternion())
            scl.append(one)
        ctrl.add_bone_track(bone)
        ctrl.set_bone_track_keys(bone, pos, rot, scl)
    ctrl.close_bracket()
    unreal.EditorAssetLibrary.save_asset(ANIM_PATH)
    print('%s: %d bone tracks, %d keys @%dfps (%.2fs)  <- %s' % (
        ANIM_NAME, len(bones), n_keys, FPS, (n_keys - 1) / float(FPS), os.path.basename(JOINTS_CSV)))
    return anim


ik_anim = run()
