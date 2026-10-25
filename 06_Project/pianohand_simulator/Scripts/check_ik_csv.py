"""Validate the IK -> Flesh/Skinning handoff CSVs (format spec: Docs/Kyungmin/IK_Handoff_Format.md).

No Unreal needed, so the IK side can self-check a file before sending it:

    python Scripts/check_ik_csv.py joints.csv [wrist.csv]

Exit code 0 = no errors (warnings are advisory), 1 = at least one error.
"""
import csv
import sys

FPS = 30
JOINT_HEADER = ['frame', 'time_ms', 'bone', 'flex_deg', 'abd_deg', 'twist_deg']
WRIST_HEADER = ['frame', 'time_ms', 'x_cm', 'y_cm', 'z_cm', 'yaw_deg', 'pitch_deg', 'roll_deg']
FINGERS = ['index', 'middle', 'ring', 'pinky']

BONES = ['thumb_01_r', 'thumb_02_r', 'thumb_03_r']
for _f in FINGERS:
    BONES += ['%s_metacarpal_r' % _f, '%s_01_r' % _f, '%s_02_r' % _f, '%s_03_r' % _f]

# generous advisory bounds (ROM in the requirements is tighter; these only catch sign/unit mistakes)
FLEX_RANGE = (-30.0, 120.0)
ABD_RANGE = (-45.0, 45.0)
TWIST_RANGE = (-30.0, 30.0)
THUMB_ABD_RANGE = (-60.0, 60.0)
THUMB_TWIST_RANGE = (-40.0, 40.0)
MAX_JOINT_STEP_DEG = 25.0     # per-frame change above this looks like a jump, not motion
MAX_WRIST_STEP_CM = 5.0
MAX_WRIST_STEP_DEG = 15.0
TIME_TOLERANCE_MS = 1.0


def _read(path, header):
    errors = []
    with open(path, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return [], ['%s: empty file' % path]
    if [c.strip() for c in rows[0]] != header:
        errors.append('%s: header must be exactly %s, got %s' % (path, ','.join(header), ','.join(rows[0])))
        return [], errors
    return rows[1:], errors


def load_joints(path):
    """-> (tracks, errors, warnings); tracks[bone] = list of (flex, abd, twist) indexed by frame."""
    rows, errors = _read(path, JOINT_HEADER)
    warnings = []
    per_bone = {}
    for n, row in enumerate(rows, start=2):
        if len(row) != len(JOINT_HEADER):
            errors.append('%s:%d: expected %d columns, got %d' % (path, n, len(JOINT_HEADER), len(row)))
            continue
        try:
            frame = int(row[0])
            time_ms = float(row[1])
            flex, abd, twist = float(row[3]), float(row[4]), float(row[5])
        except ValueError:
            errors.append('%s:%d: non-numeric value in %s' % (path, n, ','.join(row)))
            continue
        bone = row[2].strip()
        if bone not in BONES:
            errors.append('%s:%d: unknown bone "%s"' % (path, n, bone))
            continue
        if abs(time_ms - frame * 1000.0 / FPS) > TIME_TOLERANCE_MS:
            errors.append('%s:%d: time_ms %.3f does not match frame %d at %d FPS (%.3f)'
                          % (path, n, time_ms, frame, FPS, frame * 1000.0 / FPS))
        per_bone.setdefault(bone, {})[frame] = (flex, abd, twist)

    tracks = {}
    counts = set()
    for bone, by_frame in per_bone.items():
        frames = sorted(by_frame)
        if frames != list(range(len(frames))):
            errors.append('%s: bone %s frames must run 0..N-1 without gaps or repeats' % (path, bone))
            continue
        tracks[bone] = [by_frame[i] for i in frames]
        counts.add(len(frames))
    if len(counts) > 1:
        errors.append('%s: bones have different frame counts: %s' % (path, sorted(counts)))
    missing = [b for b in BONES if b not in per_bone]
    if missing:
        warnings.append('%s: bones with no rows (will stay at the reference pose): %s' % (path, ', '.join(missing)))

    for bone, seq in tracks.items():
        thumb = bone.startswith('thumb')
        limits = (FLEX_RANGE, THUMB_ABD_RANGE if thumb else ABD_RANGE, THUMB_TWIST_RANGE if thumb else TWIST_RANGE)
        for axis, name in enumerate(('flex', 'abd', 'twist')):
            lo, hi = limits[axis]
            vals = [s[axis] for s in seq]
            if min(vals) < lo or max(vals) > hi:
                warnings.append('%s: %s %s_deg spans %.1f..%.1f, outside the advisory range %.0f..%.0f (sign or unit?)'
                                % (path, bone, name, min(vals), max(vals), lo, hi))
            step = max((abs(vals[i + 1] - vals[i]) for i in range(len(vals) - 1)), default=0.0)
            if step > MAX_JOINT_STEP_DEG:
                warnings.append('%s: %s %s_deg jumps %.1f deg in one frame (continuity?)' % (path, bone, name, step))
    return tracks, errors, warnings


def load_wrist(path):
    """-> (frames, errors, warnings); frames = list of (x, y, z, yaw, pitch, roll) indexed by frame."""
    rows, errors = _read(path, WRIST_HEADER)
    warnings = []
    by_frame = {}
    for n, row in enumerate(rows, start=2):
        if len(row) != len(WRIST_HEADER):
            errors.append('%s:%d: expected %d columns, got %d' % (path, n, len(WRIST_HEADER), len(row)))
            continue
        try:
            frame = int(row[0])
            time_ms = float(row[1])
            vals = tuple(float(v) for v in row[2:])
        except ValueError:
            errors.append('%s:%d: non-numeric value in %s' % (path, n, ','.join(row)))
            continue
        if abs(time_ms - frame * 1000.0 / FPS) > TIME_TOLERANCE_MS:
            errors.append('%s:%d: time_ms %.3f does not match frame %d at %d FPS' % (path, n, time_ms, frame, FPS))
        by_frame[frame] = vals
    frames = sorted(by_frame)
    if frames != list(range(len(frames))):
        errors.append('%s: frames must run 0..N-1 without gaps or repeats' % path)
        return [], errors, warnings
    seq = [by_frame[i] for i in frames]
    for i in range(len(seq) - 1):
        d_pos = max(abs(seq[i + 1][k] - seq[i][k]) for k in range(3))
        d_rot = max(abs(seq[i + 1][k] - seq[i][k]) for k in range(3, 6))
        if d_pos > MAX_WRIST_STEP_CM or d_rot > MAX_WRIST_STEP_DEG:
            warnings.append('%s: wrist jumps between frames %d and %d (%.1f cm / %.1f deg)' % (path, i, i + 1, d_pos, d_rot))
            break
    return seq, errors, warnings


def check(joints_path, wrist_path=None):
    tracks, errors, warnings = load_joints(joints_path)
    n_frames = len(next(iter(tracks.values()))) if tracks else 0
    if wrist_path:
        wrist, w_err, w_warn = load_wrist(wrist_path)
        errors += w_err
        warnings += w_warn
        if wrist and n_frames and len(wrist) != n_frames:
            errors.append('wrist file has %d frames but joints file has %d' % (len(wrist), n_frames))
    return tracks, errors, warnings


def main(argv):
    if not 2 <= len(argv) <= 3:
        print(__doc__)
        return 2
    tracks, errors, warnings = check(argv[1], argv[2] if len(argv) == 3 else None)
    n_frames = len(next(iter(tracks.values()))) if tracks else 0
    print('bones: %d / %d   frames: %d   (%.2f s at %d FPS)' % (len(tracks), len(BONES), n_frames, max(n_frames - 1, 0) / float(FPS), FPS))
    for w in warnings:
        print('WARN  ' + w)
    for e in errors:
        print('ERROR ' + e)
    print('RESULT: %s' % ('FAIL' if errors else 'OK'))
    return 1 if errors else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
