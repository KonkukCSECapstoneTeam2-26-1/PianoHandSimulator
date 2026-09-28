"""
V6 Pipeline — Fingering Engine
V5 piano_fingering_engine.py 기반, CLI 인수 지원 추가
  --midi   : MIDI 파일 경로 (생략 시 assets/midi/Super Mario 64 - Medley.mid)
  --output : 출력 JSON 경로 (생략 시 results/{stem}_fingering.json)

변경 이력:
  2026-09-21 (W04) : shared_constants 분리 적용 — 상수 중복 제거
"""
import mido
import json
import os
import argparse
from itertools import combinations

from shared_constants import (
    BLACK_KEY_PITCH_CLASSES as BLACK_KEYS,
    WHITE_KEY_PITCH_CLASSES,
    MAX_SPAN,
    FINGER_DIFFICULTY,
    POSITION_SHIFT_THRESHOLD,
    WRIST_YAW_MAX_DEG,
    WRIST_ROLL_MAX_DEG,
    FINGER_WRIST_OFFSET_R,
    FINGER_WRIST_OFFSET_L,
    MIDI_MIN,
    MIDI_MAX,
)


class NoteEvent:
    def __init__(self, pitch, velocity, start_ms, duration_ms, hand):
        self.pitch = pitch
        self.velocity = velocity
        self.start_ms = start_ms
        self.duration_ms = duration_ms
        self.hand = hand
        self.finger = 0
        self.role = "INNER"
        self.is_black = (pitch % 12) in BLACK_KEYS
        self.pressure = velocity / 127.0
        self.key_depth = self.pressure * 1.0

    def to_dict(self):
        return {
            "pitch": self.pitch,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "hand": "Left" if self.hand == 0 else "Right",
            "role": self.role,
            "finger": self.finger,
            "pressure": round(self.pressure, 3),
            "key_depth": round(self.key_depth, 3),
            "is_black": self.is_black
        }


# --- 1. MIDI Parser ---
def _detect_hand_from_track_name(name: str):
    import re
    words = set(re.split(r'[_\s\-]', name.lower()))
    if words & {'left', 'lh', 'l', 'bass', 'lower'}:
        return 0
    if words & {'right', 'rh', 'r', 'treble', 'upper', 'melody', 'lead'}:
        return 1
    return None

def _find_split_pitch(all_notes):
    if not all_notes:
        return 55
    from collections import Counter
    hist = Counter(n.pitch // 1 for n in all_notes)
    min_density, best_pitch = float('inf'), 55
    for p in range(40, 80):
        density = sum(hist.get(q, 0) for q in range(p - 2, p + 3))
        if density < min_density:
            min_density, best_pitch = density, p
    return best_pitch

def parse_midi_to_hand_chords(file_path):
    mid = mido.MidiFile(file_path)
    all_notes = []
    tempo = 500000

    for t_idx, track in enumerate(mid.tracks):
        hand_hint = _detect_hand_from_track_name(track.name)
        active_notes = {}
        t_ms = 0.0
        for msg in track:
            t_ms += mido.tick2second(msg.time, mid.ticks_per_beat, tempo) * 1000
            if msg.type == 'set_tempo':
                tempo = msg.tempo
            elif msg.type == 'note_on' and msg.velocity > 0:
                active_notes[msg.note] = (t_ms, msg.velocity, hand_hint)
            elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                if msg.note in active_notes:
                    start_time, vel, hint = active_notes.pop(msg.note)
                    all_notes.append(NoteEvent(msg.note, vel, start_time, t_ms - start_time,
                                               hint if hint is not None else -1))

    all_notes.sort(key=lambda x: x.start_ms)

    unassigned = [n for n in all_notes if n.hand == -1]
    if unassigned:
        split_pitch = _find_split_pitch(all_notes)
        for n in unassigned:
            n.hand = 1 if n.pitch >= split_pitch else 0

    hand_chords = {0: [], 1: []}
    for h in [0, 1]:
        h_notes = [n for n in all_notes if n.hand == h]
        if not h_notes:
            continue
        curr_group = [h_notes[0]]
        for i in range(1, len(h_notes)):
            if h_notes[i].start_ms - curr_group[0].start_ms < 30:
                curr_group.append(h_notes[i])
            else:
                curr_group.sort(key=lambda x: x.pitch)
                if h == 1:
                    for n in curr_group[:-1]: n.role = "INNER"
                    curr_group[-1].role = "MELODY"
                else:
                    curr_group[0].role = "BASS"
                    for n in curr_group[1:]: n.role = "INNER"
                hand_chords[h].append(curr_group)
                curr_group = [h_notes[i]]

        curr_group.sort(key=lambda x: x.pitch)
        if h == 1:
            for n in curr_group[:-1]: n.role = "INNER"
            curr_group[-1].role = "MELODY"
        else:
            curr_group[0].role = "BASS"
            for n in curr_group[1:]: n.role = "INNER"
        hand_chords[h].append(curr_group)
    return hand_chords

def split_wide_chords_between_hands(hand_chords, max_span=17):
    changed = True
    while changed:
        changed = False
        for h in [0, 1]:
            hand_chords[h].sort(key=lambda c: c[0].start_ms)
            merged = []
            for chord in hand_chords[h]:
                if merged and chord[0].start_ms - merged[-1][0].start_ms < 30:
                    merged[-1] = sorted(merged[-1] + chord, key=lambda n: n.pitch)
                else:
                    merged.append(chord)
            hand_chords[h] = merged

        for h in [0, 1]:
            other = 1 - h
            new_chords = []
            for chord in hand_chords[h]:
                if len(chord) < 2 or chord[-1].pitch - chord[0].pitch <= max_span:
                    new_chords.append(chord)
                    continue
                changed = True
                gaps = [chord[i+1].pitch - chord[i].pitch for i in range(len(chord)-1)]
                split_idx = gaps.index(max(gaps))
                lower, upper = chord[:split_idx+1], chord[split_idx+1:]
                keep, move = (lower, upper) if h == 0 else (upper, lower)
                new_chords.append(keep)
                move_time = move[0].start_ms
                existing = next((c for c in hand_chords[other]
                                 if abs(c[0].start_ms - move_time) < 30), None)
                if existing is None:
                    for n in move: n.hand = other
                    hand_chords[other].append(move)
                else:
                    combined = sorted(existing + move, key=lambda n: n.pitch)
                    if combined[-1].pitch - combined[0].pitch <= max_span:
                        for n in move: n.hand = other
                        hand_chords[other].append(move)
            hand_chords[h] = sorted(new_chords, key=lambda c: c[0].start_ms)
    return hand_chords


# --- 2. Polyphonic DP Solver ---
def _trim_chord(chord, hand_id):
    if len(chord) <= 5:
        return chord
    priority = {"MELODY": 0, "BASS": 1, "INNER": 2}
    sorted_chord = sorted(chord, key=lambda n: (priority[n.role], n.pitch if hand_id == 0 else -n.pitch))
    return sorted(sorted_chord[:5], key=lambda n: n.pitch)

def solve_fingering_chord_dp(chord_sequence, hand_id):
    if not chord_sequence:
        return
    chord_sequence = [_trim_chord(c, hand_id) for c in chord_sequence]

    def get_combinations(k):
        if k > 5:
            k = 5
        combos = list(combinations(range(1, 6), k))
        if hand_id == 0:
            return [tuple(reversed(c)) for c in combos]
        return combos

    dp = []
    first_chord = chord_sequence[0]
    first_states = {}
    for f_tuple in get_combinations(len(first_chord)):
        is_possible = True
        for i in range(len(f_tuple)-1):
            f_pair = tuple(sorted((f_tuple[i], f_tuple[i+1])))
            if (first_chord[i+1].pitch - first_chord[i].pitch) > MAX_SPAN.get(f_pair, 12):
                is_possible = False; break
        if is_possible:
            cost = sum(FINGER_DIFFICULTY[f] for f in f_tuple)
            first_states[f_tuple] = (cost, None)

    if not first_states:
        first_states[get_combinations(len(first_chord))[0]] = (0, None)
    dp.append(first_states)

    def calc_transition_cost(prev_notes, prev_f_tuple, curr_notes, curr_f_tuple):
        penalty = 0
        for i in range(len(curr_f_tuple)-1):
            f_pair = tuple(sorted((curr_f_tuple[i], curr_f_tuple[i+1])))
            if (curr_notes[i+1].pitch - curr_notes[i].pitch) > MAX_SPAN.get(f_pair, 12):
                penalty += 5000

        role_penalty = 0
        for i, f in enumerate(curr_f_tuple):
            note = curr_notes[i]
            if note.role == "MELODY":
                if hand_id == 1:
                    if f == 4:      role_penalty -= 12
                    elif f == 5:    role_penalty -= 6
                    elif f == 1:    role_penalty += 20
                else:
                    if f == 1:      role_penalty -= 12
                    elif f == 2:    role_penalty -= 6
                    elif f == 5:    role_penalty += 15
            elif note.role == "BASS":
                if hand_id == 1:
                    if f == 1:      role_penalty -= 10
                else:
                    if f == 5:      role_penalty -= 12
            elif note.role == "INNER":
                if f in [2, 3]:     role_penalty -= 5

        prev_m_idx = next((i for i, n in enumerate(prev_notes) if n.role == "MELODY"), None)
        curr_m_idx = next((i for i, n in enumerate(curr_notes) if n.role == "MELODY"), None)
        if prev_m_idx is not None and curr_m_idx is not None:
            pm_note, cm_note = prev_notes[prev_m_idx], curr_notes[curr_m_idx]
            pm_f, cm_f = prev_f_tuple[prev_m_idx], curr_f_tuple[curr_m_idx]
            p_dist = abs(cm_note.pitch - pm_note.pitch)
            if 0 < p_dist <= 2 and pm_f == cm_f: penalty -= 20
            if p_dist >= 3 and pm_f == cm_f:     penalty += 30

        curr_start = curr_notes[0].start_ms
        busy_fingers = {
            prev_f_tuple[i]
            for i, n in enumerate(prev_notes)
            if n.start_ms + n.duration_ms > curr_start
        }
        for f in curr_f_tuple:
            if f in busy_fingers:
                penalty += 2500

        if len(prev_notes) == 1 and len(curr_notes) == 1:
            p_f, c_f = prev_f_tuple[0], curr_f_tuple[0]
            pitch_dir = curr_notes[0].pitch - prev_notes[0].pitch
            if pitch_dir != 0:
                if p_f == c_f:
                    penalty += 60
                else:
                    rh_mismatch = (hand_id == 1 and ((pitch_dir > 0 and c_f < p_f) or (pitch_dir < 0 and c_f > p_f)))
                    lh_mismatch = (hand_id == 0 and ((pitch_dir > 0 and c_f > p_f) or (pitch_dir < 0 and c_f < p_f)))
                    if rh_mismatch or lh_mismatch:
                        penalty += 35

        p_diff = curr_notes[0].pitch - prev_notes[-1].pitch
        if hand_id == 1:
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and curr_f_tuple[0] != 1: penalty += 2000
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and prev_f_tuple[0] != 1: penalty += 2000
        else:
            if p_diff < 0 and curr_f_tuple[-1] < prev_f_tuple[0] and curr_f_tuple[-1] != 1: penalty += 2000
            if p_diff > 0 and curr_f_tuple[0] > prev_f_tuple[-1] and prev_f_tuple[-1] != 1: penalty += 2000

        wrist_move = abs((sum(n.pitch for n in curr_notes)/len(curr_notes)) - (sum(n.pitch for n in prev_notes)/len(prev_notes)))
        if wrist_move > POSITION_SHIFT_THRESHOLD: penalty += (wrist_move - POSITION_SHIFT_THRESHOLD) * 2

        note_penalty = sum(FINGER_DIFFICULTY[f] for f in curr_f_tuple)
        for i, f in enumerate(curr_f_tuple):
            if curr_notes[i].is_black and f == 1: note_penalty += 25
            if curr_notes[i].is_black and f == 5: note_penalty += 10

        return wrist_move * 2.0 + note_penalty + penalty + role_penalty

    for c_idx in range(1, len(chord_sequence)):
        curr_chord, prev_chord = chord_sequence[c_idx], chord_sequence[c_idx-1]
        curr_states, prev_states = {}, dp[c_idx-1]
        for curr_f in get_combinations(len(curr_chord)):
            min_c, best_p = float("inf"), None
            for prev_f, (prev_c, _) in prev_states.items():
                t_c = calc_transition_cost(prev_chord, prev_f, curr_chord, curr_f)
                if prev_c + t_c < min_c: min_c, best_p = prev_c + t_c, prev_f
            curr_states[curr_f] = (min_c, best_p)
        dp.append(curr_states)

    curr_f = min(dp[-1].keys(), key=lambda k: dp[-1][k][0])
    for i in range(len(chord_sequence)-1, -1, -1):
        for j, finger in enumerate(curr_f): chord_sequence[i][j].finger = finger
        curr_f = dp[i][curr_f][1]


# --- 3. Wrist Physics ---
def calculate_wrist_rotation_rom(chord_group, hand_id):
    if not chord_group: return 0, 0
    avg_pitch = sum(n.pitch for n in chord_group) / len(chord_group)
    offsets = FINGER_WRIST_OFFSET_R if hand_id == 1 else FINGER_WRIST_OFFSET_L
    yaw_score = sum((n.pitch - avg_pitch) - offsets.get(n.finger, 0) for n in chord_group)
    yaw_deg = max(min(yaw_score * 2.5 * (-1 if hand_id == 0 else 1),
                      WRIST_YAW_MAX_DEG), -WRIST_YAW_MAX_DEG)
    roll_deg = 0
    thumb = next((n for n in chord_group if n.finger == 1), None)
    pinky = next((n for n in chord_group if n.finger == 5), None)
    if thumb and thumb.is_black: roll_deg += 12
    if pinky and pinky.is_black: roll_deg -= 12
    roll_deg = max(min(roll_deg * (-1 if hand_id == 0 else 1),
                       WRIST_ROLL_MAX_DEG), -WRIST_ROLL_MAX_DEG)
    return round(yaw_deg, 2), round(roll_deg, 2)


# --- 4. Main Analysis ---
def analyze_polyphonic(file_path, output_path=None):
    print(f"  Analyzing: {os.path.basename(file_path)}")
    hand_chords = split_wide_chords_between_hands(parse_midi_to_hand_chords(file_path))
    final_notes = []
    for h in [0, 1]:
        solve_fingering_chord_dp(hand_chords[h], h)
        for group in hand_chords[h]:
            wrist_pos = round((sum(n.pitch for n in group)/len(group) - MIDI_MIN) / (MIDI_MAX - MIDI_MIN), 3)
            yaw, roll = calculate_wrist_rotation_rom(group, h)
            for n in group:
                d = n.to_dict()
                d.update({"wrist_pos_normalized": wrist_pos, "wrist_yaw_deg": yaw, "wrist_roll_deg": roll})
                final_notes.append(d)
    final_notes.sort(key=lambda x: x["start_ms"])

    if output_path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.abspath(os.path.join(base_dir, "../results"))
        stem = os.path.splitext(os.path.basename(file_path))[0]
        output_path = os.path.join(results_dir, f"{stem}_fingering.json")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final_notes, f, indent=4, ensure_ascii=False)

    note_count = len(final_notes)
    left  = sum(1 for n in final_notes if n["hand"] == "Left")
    right = sum(1 for n in final_notes if n["hand"] == "Right")
    duration_s = max(n["start_ms"] + n["duration_ms"] for n in final_notes) / 1000
    print(f"  -> {note_count} notes ({left}L / {right}R), {duration_s:.1f}s")
    print(f"  -> Saved: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PianoHandSimulator — Fingering Engine V6")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    default_midi = os.path.abspath(os.path.join(base_dir, "../assets/midi/Super Mario 64 - Medley.mid"))

    parser.add_argument("--midi",   default=default_midi, help="MIDI 파일 경로")
    parser.add_argument("--output", default=None,          help="출력 JSON 경로 (생략 시 results/{stem}_fingering.json)")
    args = parser.parse_args()

    if not os.path.exists(args.midi):
        print(f"Error: MIDI file not found — {args.midi}")
        raise SystemExit(1)

    analyze_polyphonic(args.midi, args.output)
