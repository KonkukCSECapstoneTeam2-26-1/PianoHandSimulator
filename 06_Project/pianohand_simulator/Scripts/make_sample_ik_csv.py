"""Write a synthetic IK handoff sample (format spec: Docs/Kyungmin/IK_Handoff_Format.md).

The motion is the same closing/opening cycle as A_MH_Hand_Cycle (Scripts/make_mh_hand_poses.py), expressed as
per-joint angles in the handoff convention, so importing the CSV must reproduce that animation. That makes the
importer testable before real IK data exists, and shows the IK side exactly what a file should look like.

    python Scripts/make_sample_ik_csv.py [out_dir]       # default: Docs/Kyungmin/samples

Convention used here (the IK side must confirm theirs): flex_deg is POSITIVE when the finger closes.
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_ik_csv as fmt  # noqa: E402

FPS = fmt.FPS
DURATION = 4.0

# mirrors make_mh_hand_poses.py (curl = 0 at rest, 1 at full grasp), with flex sign flipped to "closing = +"
KEYFRAMES = [(0.0, 0.0), (0.5, 0.0), (1.2, 1.0), (2.0, 1.0), (2.5, 0.0), (4.0, 0.0)]
FLEX_AT_FULL_CURL = {'01': 62.0, '02': 72.0, '03': 32.0}
METACARPAL_CUP = {'index': 0.0, 'middle': 0.0, 'ring': 7.0, 'pinky': 13.0}
THUMB_FLEX = {'thumb_01_r': 16.0, 'thumb_02_r': 24.0, 'thumb_03_r': 28.0}
THUMB_SWING = {'thumb_01_r': (-12.0, -10.0)}      # (abd_deg, twist_deg) at full curl


def curl_at(t):
    for i in range(len(KEYFRAMES) - 1):
        t0, v0 = KEYFRAMES[i]
        t1, v1 = KEYFRAMES[i + 1]
        if t0 <= t <= t1:
            if t1 <= t0:
                return v1
            a = (t - t0) / (t1 - t0)
            a = a * a * (3.0 - 2.0 * a)           # smoothstep, same as the original
            return v0 + (v1 - v0) * a
    return KEYFRAMES[-1][1]


def full_curl_angles():
    """bone -> (flex, abd, twist) at curl = 1"""
    out = {}
    for finger in fmt.FINGERS:
        out['%s_metacarpal_r' % finger] = (METACARPAL_CUP[finger], 0.0, 0.0)
        for joint, flex in FLEX_AT_FULL_CURL.items():
            out['%s_%s_r' % (finger, joint)] = (flex, 0.0, 0.0)
    for bone, flex in THUMB_FLEX.items():
        abd, twist = THUMB_SWING.get(bone, (0.0, 0.0))
        out[bone] = (flex, abd, twist)
    return out


def write(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    full = full_curl_angles()
    frames = int(round(DURATION * FPS))
    joints_path = os.path.join(out_dir, 'ik_sample_joints.csv')
    wrist_path = os.path.join(out_dir, 'ik_sample_wrist.csv')
    with open(joints_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(fmt.JOINT_HEADER)
        for frame in range(frames + 1):
            c = curl_at(frame / float(FPS))
            for bone in fmt.BONES:
                flex, abd, twist = full[bone]
                # "+ 0.0" turns -0.0 into 0.0 so the file never contains "-0.0000"
                w.writerow([frame, '%.3f' % (frame * 1000.0 / FPS), bone,
                            '%.4f' % (flex * c + 0.0), '%.4f' % (abd * c + 0.0), '%.4f' % (twist * c + 0.0)])
    with open(wrist_path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh)
        w.writerow(fmt.WRIST_HEADER)
        for frame in range(frames + 1):
            w.writerow([frame, '%.3f' % (frame * 1000.0 / FPS), '0.0000', '0.0000', '0.0000', '0.0000', '0.0000', '0.0000'])
    return joints_path, wrist_path


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', 'Docs', 'Kyungmin', 'samples')
    j, w = write(os.path.normpath(out))
    print('wrote', j)
    print('wrote', w)
