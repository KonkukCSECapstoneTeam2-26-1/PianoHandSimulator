"""Check the CSV importer against a known answer: the sample CSV is the A_MH_Hand_Cycle motion written as joint angles,
so the animation it produces must match A_MH_Hand_Cycle pose for pose.

    exec(open(r'<project>/Scripts/test_ik_import.py').read())

Headless (editor closed):
    UnrealEditor-Cmd.exe <uproject> -run=pythonscript -script="<project>/Scripts/test_ik_import.py" -unattended -nosplash
Writes the verdict to Saved/ik_import_test.txt as well as the log.
"""
import os

import unreal

PROJECT_DIR = unreal.Paths.project_dir()
SAMPLES = os.path.join(PROJECT_DIR, 'Docs', 'Kyungmin', 'samples')
IK_ANIM_NAME = 'A_IK_SampleCheck'
IK_JOINTS_CSV = os.path.join(SAMPLES, 'ik_sample_joints.csv')
IK_WRIST_CSV = os.path.join(SAMPLES, 'ik_sample_wrist.csv')
exec(open(os.path.join(PROJECT_DIR, 'Scripts', 'import_ik_csv_to_anim.py')).read())

REFERENCE_ANIM = DST_DIR + '/A_MH_Hand_Cycle'
TIMES = [0.0, 0.25, 0.5, 0.85, 1.2, 1.6, 2.0, 2.3, 2.55, 3.6, 4.0]
TOLERANCE_DEG = 0.05

lines = []


def emit(msg):
    lines.append(msg)
    print(msg)


def angle_between(a, b):
    """smallest rotation (deg) taking quaternion a to b"""
    dot = abs(a.x * b.x + a.y * b.y + a.z * b.z + a.w * b.w)
    dot = min(1.0, dot)
    import math
    return math.degrees(2.0 * math.acos(dot))


ref_anim = unreal.load_asset(REFERENCE_ANIM)
new_anim = unreal.load_asset(DST_DIR + '/' + IK_ANIM_NAME)
verdict = 'FAIL'
try:
    lib = unreal.AnimationLibrary
    bone_names = [b for b in fmt.BONES]
    worst = (0.0, None, None)
    for bone in bone_names:
        for t in TIMES:
            pa = lib.get_bone_pose_for_time(ref_anim, bone, t, False)
            pb = lib.get_bone_pose_for_time(new_anim, bone, t, False)
            d = angle_between(pa.rotation, pb.rotation)
            if d > worst[0]:
                worst = (d, bone, t)
    emit('compared %d bones x %d times against %s' % (len(bone_names), len(TIMES), REFERENCE_ANIM))
    emit('worst rotation difference: %.4f deg (bone=%s, t=%s)' % worst)
    verdict = 'PASS' if worst[0] <= TOLERANCE_DEG else 'FAIL'
except Exception as exc:  # the pose query API changed between engine versions; say so instead of guessing
    emit('could not compare poses: %s: %s' % (type(exc).__name__, exc))
    verdict = 'ERROR'

emit('RESULT: ' + verdict)
out_path = os.path.join(unreal.Paths.project_saved_dir(), 'ik_import_test.txt')
with open(out_path, 'w', encoding='utf-8') as fh:
    fh.write('\n'.join(lines) + '\n')
