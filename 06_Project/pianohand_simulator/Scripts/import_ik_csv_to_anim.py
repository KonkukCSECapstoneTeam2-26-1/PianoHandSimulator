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
    pitch = SIGN['abd']   * abd_deg       (spread, about the palm normal; -1 confirmed, thumb uses THUMB_ABD_SIGN)
    roll  = SIGN['twist'] * twist_deg     (about the finger axis)

The sign/axis table is the part to confirm against the IK program's own convention - it lives in one place (SIGN).
An existing asset of the same name is re-keyed instead of deleted, so levels that reference it keep working.
"""
import importlib
import math
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
# abd: IK abd > 0 turns a right-hand finger toward the THUMB (rotation about +y, thumb at -z), while a +pitch on a
# MetaHuman finger root turns it toward the PINKY (Scripts/check_ik_abd_sign.py, 2026-11-27: all four fingers) -> -1.
# The thumb keeps the old +1 until its bend plane is retargeted (IK_Handoff_Format.md open item 11).
SIGN = globals().get('IK_SIGN', {'flex': -1.0, 'abd': -1.0, 'twist': 1.0})
THUMB_ABD_SIGN = globals().get('IK_THUMB_ABD_SIGN', 1.0)
# Joint-angle speed limit (deg per frame, 0 = off). The IK CSV holds jumps of up to ~120 deg in one frame (a finger
# snapping between keys), which read as a stutter. Each channel is rate-limited forward and backward and the two are
# averaged, so a jump is spread evenly before and after its frame (no one-sided lag). 15 deg/frame = 450 deg/s at 30 fps:
# on deb_clai no jump above 20 deg is left and 99% of the samples stay within 1.2 deg of the IK (2026-11-27).
MAX_DEG_PER_FRAME = globals().get('IK_MAX_DEG_PER_FRAME', 15.0)
# Thumb retarget (IK_Handoff_Format.md item 11). The IK bends its thumb in the SAME plane as the fingers (toward the
# keys, about the hand's side-to-side axis) and spreads it about the palm normal. The MetaHuman thumb bones are rolled
# into opposition, so their local yaw curls the thumb ACROSS the palm toward the middle finger. True = apply the
# thumb's flex / abd about hand axes measured on the reference pose (flex + = toward the palm side, abd + = away from
# the fingers, as in the IK), twist stays a roll about the bone. False = the old local yaw / pitch mapping.
THUMB_RETARGET = globals().get('IK_THUMB_RETARGET', True)
# Which thumb bones get the hand-axis retarget. Retargeting all three (2026-11-27 first try) bent the MCP / IP hinges
# in a plane they cannot bend in (looked broken). Only the CMC (thumb_01, a saddle joint with two degrees of freedom)
# is aimed with the hand axes; MCP / IP (thumb_02 / 03) are hinges and keep bending about their own axis (local yaw).
THUMB_RETARGET_BONES = globals().get('IK_THUMB_RETARGET_BONES', ('thumb_01_r',))
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


def reference_bones():
    """name -> GeometryScriptBoneInfo, index -> info (reference pose)"""
    mesh = unreal.load_asset(REF_MESH)
    dyn = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property('lod_index', 0)
    dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
        mesh, dyn, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    _, infos = unreal.GeometryScript_BoneWeights.get_all_bones_info(dyn)
    return {str(b.name): b for b in infos}, {b.index: b for b in infos}


class ThumbRetarget(object):
    """component-space hand axes on the reference pose, turned into each thumb bone's local frame"""

    def __init__(self):
        self.by_name, self.by_index = reference_bones()
        self._g = {}
        self._axes = {}
        pos = lambda n: self.glob(self.by_name[n].index).translation
        f = ML.normal(pos('middle_02_r') - pos('middle_01_r'))                 # along the fingers (IK +x)
        lat = pos('pinky_01_r') - pos('index_01_r')                             # toward the pinky (IK +z)
        lat = ML.normal(lat - f * ML.dot_vector_vector(lat, f))
        # palm side: where a MetaHuman curl (negative local yaw, see SIGN['flex']) moves the middle finger
        d = self.child_move('middle_01_r', 'middle_02_r', unreal.Rotator(roll=0.0, pitch=0.0, yaw=-20.0))
        d = d - f * ML.dot_vector_vector(d, f) - lat * ML.dot_vector_vector(d, lat)
        self.palm = ML.normal(d)
        self.fwd, self.lat = f, lat
        normal = ML.cross_vector_vector(f, lat)
        # pick each axis' sign by trying it on the middle finger (independent of handedness conventions)
        self.flex_axis = lat if self.moves('middle_01_r', 'middle_02_r', lat, self.palm) else lat * -1.0
        self.abd_axis = normal if self.moves('middle_01_r', 'middle_02_r', normal, lat * -1.0) else normal * -1.0

    def glob(self, index):
        if index < 0:
            return unreal.Transform()
        if index not in self._g:
            b = self.by_index[index]
            self._g[index] = ML.compose_transforms(b.local_transform, self.glob(b.parent_index))
        return self._g[index]

    def child_move(self, bone, child, delta_rot):
        b = self.by_name[bone]
        local = b.local_transform
        rot = ML.compose_rotators(delta_rot, local.rotation.rotator())
        g = ML.compose_transforms(unreal.Transform(local.translation, rot, local.scale3d), self.glob(b.parent_index))
        moved = ML.compose_transforms(self.by_name[child].local_transform, g).translation
        return moved - self.glob(self.by_name[child].index).translation

    def axis_rot(self, bone, axis_c, deg):
        """local delta rotator = rotation by deg about the component-space axis, expressed in the bone's frame"""
        key = (bone, round(axis_c.x, 6), round(axis_c.y, 6), round(axis_c.z, 6))
        a = self._axes.get(key)
        if a is None:
            a = ML.normal(ML.inverse_transform_direction(self.glob(self.by_name[bone].index), axis_c))
            self._axes[key] = a
        h = math.radians(deg) * 0.5
        sh = math.sin(h)
        return unreal.Quat(a.x * sh, a.y * sh, a.z * sh, math.cos(h)).rotator()

    def moves(self, bone, child, axis_c, toward):
        d = self.child_move(bone, child, self.axis_rot(bone, axis_c, 10.0))
        return ML.dot_vector_vector(d, toward) > 0.0

    def delta(self, bone, flex, abd, twist):
        twist_rot = unreal.Rotator(roll=SIGN['twist'] * twist, pitch=0.0, yaw=0.0)
        r = ML.compose_rotators(twist_rot, self.axis_rot(bone, self.flex_axis, flex))
        if abd:
            r = ML.compose_rotators(r, self.axis_rot(bone, self.abd_axis, abd))
        return r

    def report(self):
        for label, rot in (('retarget', self.axis_rot('thumb_02_r', self.flex_axis, 30.0)),
                           ('old yaw', unreal.Rotator(roll=0.0, pitch=0.0, yaw=SIGN['flex'] * 30.0))):
            d = self.child_move('thumb_02_r', 'thumb_03_r', rot)
            unreal.log('[IK import] thumb_02 flex +30 (%s): thumb_03 moves %.2f cm palm-side, %.2f cm toward the pinky, '
                       '%.2f cm forward' % (label, ML.dot_vector_vector(d, self.palm), ML.dot_vector_vector(d, self.lat),
                                            ML.dot_vector_vector(d, self.fwd)))


def _rate_limit(seq, step):
    out = [seq[0]]
    for x in seq[1:]:
        p = out[-1]
        out.append(p + max(-step, min(step, x - p)))
    return out


def limit_speed(tracks, step):
    """zero-phase joint speed limit: average of a forward and a backward rate-limited pass, per bone and channel"""
    if not step or step <= 0:
        return tracks, 0
    out, touched = {}, 0
    for bone, keys in tracks.items():
        chans = []
        for c in range(3):
            s = [k[c] for k in keys]
            f = _rate_limit(s, step)
            b = _rate_limit(s[::-1], step)[::-1]
            z = [(u + v) * 0.5 for u, v in zip(f, b)]
            touched += sum(1 for u, v in zip(s, z) if abs(u - v) > 0.5)
            chans.append(z)
        out[bone] = [tuple(ch[i] for ch in chans) for i in range(len(keys))]
    return out, touched


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

    tracks, touched = limit_speed(tracks, MAX_DEG_PER_FRAME)
    if MAX_DEG_PER_FRAME:
        unreal.log('[IK import] speed limit %.1f deg/frame: %d channel samples changed by > 0.5 deg' % (MAX_DEG_PER_FRAME, touched))
    bones = list(tracks.keys()) + (['hand_r'] if wrist else [])
    refs = reference_locals(bones)
    n_keys = len(next(iter(tracks.values())))

    thumb = None
    if THUMB_RETARGET:
        thumb = ThumbRetarget()
        thumb.report()
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
                if thumb is not None and bone in THUMB_RETARGET_BONES:
                    delta = thumb.delta(bone, flex, abd, twist)
                else:
                    abd_sign = THUMB_ABD_SIGN if bone.startswith('thumb') else SIGN['abd']
                    delta = unreal.Rotator(roll=SIGN['twist'] * twist, pitch=abd_sign * abd, yaw=SIGN['flex'] * flex)
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
