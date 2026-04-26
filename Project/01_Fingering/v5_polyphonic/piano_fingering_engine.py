import mido
import json
import os
import math
from itertools import combinations

# --- Constants & Anatomical Limits ---
BLACK_KEYS = {1, 3, 6, 8, 10}

# Max semitones between finger pairs (Hard Limits)
MAX_SPAN = {
    (1, 2): 12, (2, 3): 6, (3, 4): 5, (4, 5): 6,
    (1, 3): 14, (1, 4): 15, (1, 5): 17, # Thumb to others
    (2, 4): 10, (2, 5): 12, (3, 5): 10
}

# Wrist Rotation Limits (Degrees)
WRIST_ROM = {
    "yaw_max": 35.0,
    "roll_max": 20.0
}

# 손가락별 손목 기준점 오프셋 (반음, 손목 중심 기준)
FINGER_WRIST_OFFSET_L = {1: 4,  2: 2,  3: 0, 4: -2, 5: -4}  # 왼손
FINGER_WRIST_OFFSET_R = {1: -4, 2: -2, 3: 0, 4:  2, 5:  4}  # 오른손

# ── 피아노 교육학 기반 손가락 비용 ───────────────────────────────
FINGER_DIFFICULTY = {1: 0, 2: 0, 3: 0, 4: 6, 5: 3}

# 포지션(5지 묶음) 전환 임계값 (반음)
POSITION_SHIFT_THRESHOLD = 5

class NoteEvent:
    def __init__(self, pitch, velocity, start_ms, duration_ms, hand):
        self.pitch = pitch
        self.velocity = velocity
        self.start_ms = start_ms
        self.duration_ms = duration_ms
        self.hand = hand
        self.finger = 0
        self.role = "INNER" # Default role
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

# --- 1. MIDI Parser with Voice Tagging ---
def parse_midi_to_hand_chords(file_path):
    mid = mido.MidiFile(file_path)
    all_notes = []
    active_notes = {}
    t_ms = 0.0
    tempo = 500000

    for msg in mido.merge_tracks(mid.tracks):
        t_ms += mido.tick2second(msg.time, mid.ticks_per_beat, tempo) * 1000
        if msg.type == 'set_tempo':
            tempo = msg.tempo
        elif msg.type == 'note_on' and msg.velocity > 0:
            active_notes[msg.note] = (t_ms, msg.velocity)
        elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
            if msg.note in active_notes:
                start_time, vel = active_notes.pop(msg.note)
                hand = 1 if msg.note >= 55 else 0
                all_notes.append(NoteEvent(msg.note, vel, start_time, t_ms - start_time, hand))

    all_notes.sort(key=lambda x: x.start_ms)
    hand_chords = {0: [], 1: []}
    for h in [0, 1]:
        h_notes = [n for n in all_notes if n.hand == h]
        if not h_notes: continue
        curr_group = [h_notes[0]]
        for i in range(1, len(h_notes)):
            if h_notes[i].start_ms - curr_group[0].start_ms < 30:
                curr_group.append(h_notes[i])
            else:
                curr_group.sort(key=lambda x: x.pitch)
                # Role Tagging
                if h == 1: # Right Hand: Top is Melody
                    for n in curr_group[:-1]: n.role = "INNER"
                    curr_group[-1].role = "MELODY"
                else: # Left Hand: Bottom is Bass
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
            new_chords = []
            for chord in hand_chords[h]:
                if len(chord) < 2 or chord[-1].pitch - chord[0].pitch <= max_span:
                    new_chords.append(chord)
                    continue
                changed = True
                gaps = [chord[i+1].pitch - chord[i].pitch for i in range(len(chord)-1)]
                split_idx = gaps.index(max(gaps))
                lower, upper = chord[:split_idx+1], chord[split_idx+1:]
                if h == 0:
                    new_chords.append(lower)
                    for n in upper: n.hand = 1
                    hand_chords[1].append(upper)
                else:
                    new_chords.append(upper)
                    for n in lower: n.hand = 0
                    hand_chords[0].append(lower)
            hand_chords[h] = sorted(new_chords, key=lambda c: c[0].start_ms)

    for h in [0, 1]:
        hand_chords[h].sort(key=lambda c: c[0].start_ms)
        merged = []
        for chord in hand_chords[h]:
            if merged and chord[0].start_ms - merged[-1][0].start_ms < 30:
                merged[-1] = sorted(merged[-1] + chord, key=lambda n: n.pitch)
            else: merged.append(chord)
        hand_chords[h] = merged
    return hand_chords

# --- 2. Polyphonic DP Solver ---
def solve_fingering_chord_dp(chord_sequence, hand_id):
    if not chord_sequence: return
    def get_combinations(k): return list(combinations(range(1, 6), k))

    dp = []
    first_chord = chord_sequence[0]
    first_states = {}
    for f_tuple in get_combinations(len(first_chord)):
        is_possible = True
        for i in range(len(f_tuple)-1):
            if (first_chord[i+1].pitch - first_chord[i].pitch) > MAX_SPAN.get((f_tuple[i], f_tuple[i+1]), 12):
                is_possible = False; break
        if is_possible:
            cost = sum(FINGER_DIFFICULTY[f] for f in f_tuple)
            first_states[f_tuple] = (cost, None)
    
    if not first_states:
        first_states[get_combinations(len(first_chord))[0]] = (0, None)
    dp.append(first_states)

    def calc_transition_cost(prev_notes, prev_f_tuple, curr_notes, curr_f_tuple):
        penalty = 0
        # 1. Span Check
        for i in range(len(curr_f_tuple)-1):
            if (curr_notes[i+1].pitch - curr_notes[i].pitch) > MAX_SPAN.get((curr_f_tuple[i], curr_f_tuple[i+1]), 12):
                penalty += 5000

        # 2. Role Affinity
        role_penalty = 0
        for i, f in enumerate(curr_f_tuple):
            note = curr_notes[i]
            if note.role == "MELODY":
                if f in [4, 5]: role_penalty -= 15
                if f == 1:     role_penalty += 20
            elif note.role == "BASS":
                if f == 5:     role_penalty -= 15
            elif note.role == "INNER":
                if f in [2, 3]: role_penalty -= 5

        # 3. Melody Continuity
        prev_m_idx = next((i for i, n in enumerate(prev_notes) if n.role == "MELODY"), None)
        curr_m_idx = next((i for i, n in enumerate(curr_notes) if n.role == "MELODY"), None)
        if prev_m_idx is not None and curr_m_idx is not None:
            pm_note, cm_note = prev_notes[prev_m_idx], curr_notes[curr_m_idx]
            pm_f, cm_f = prev_f_tuple[prev_m_idx], curr_f_tuple[curr_m_idx]
            p_dist = cm_note.pitch - pm_note.pitch
            if 0 < abs(p_dist) <= 2 and pm_f == cm_f: penalty += 40

        # 4. Wrist & Crossing (Standard V4 logic)
        p_diff = curr_notes[0].pitch - prev_notes[-1].pitch
        if hand_id == 1:
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and curr_f_tuple[0] != 1: penalty += 2000
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and prev_f_tuple[0] != 1: penalty += 2000
        else:
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and curr_f_tuple[-1] != 1: penalty += 2000
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and prev_f_tuple[-1] != 1: penalty += 2000

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
    yaw_score = sum((n.pitch - avg_pitch) - (n.finger - 3) * 2.5 for n in chord_group)
    yaw_deg = max(min(yaw_score * 2.5 * (-1 if hand_id == 0 else 1), WRIST_ROM["yaw_max"]), -WRIST_ROM["yaw_max"])
    roll_deg = 0
    thumb, pinky = next((n for n in chord_group if n.finger == 1), None), next((n for n in chord_group if n.finger == 5), None)
    if thumb and thumb.is_black: roll_deg += 12
    if pinky and pinky.is_black: roll_deg -= 12
    roll_deg = max(min(roll_deg * (-1 if hand_id == 0 else 1), WRIST_ROM["roll_max"]), -WRIST_ROM["roll_max"])
    return round(yaw_deg, 2), round(roll_deg, 2)

# --- 4. Main Analysis ---
def analyze_polyphonic(file_path):
    print(f"Analyzing with Polyphonic Voice Leading (V5): {file_path}...")
    hand_chords = split_wide_chords_between_hands(parse_midi_to_hand_chords(file_path))
    final_notes = []
    for h in [0, 1]:
        solve_fingering_chord_dp(hand_chords[h], h)
        for group in hand_chords[h]:
            wrist_pos = round((sum(n.pitch for n in group)/len(group) - 21) / (108 - 21), 3)
            yaw, roll = calculate_wrist_rotation_rom(group, h)
            for n in group:
                d = n.to_dict()
                d.update({"wrist_pos_normalized": wrist_pos, "wrist_yaw_deg": yaw, "wrist_roll_deg": roll})
                final_notes.append(d)
    final_notes.sort(key=lambda x: x["start_ms"])
    
    # 스크립트 위치 기준으로 상위 폴더(01_Fingering) 내의 결과 폴더 지정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.abspath(os.path.join(base_dir, "../results"))
    
    if not os.path.exists(output_dir): os.makedirs(output_dir)
    output_path = os.path.join(output_dir, "mario_polyphonic_result.json")
    with open(output_path, "w") as f: json.dump(final_notes, f, indent=4)
    print(f"\n--- POLYPHONIC ANALYSIS COMPLETE: {output_path} ---")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    midi_path = os.path.abspath(os.path.join(base_dir, "../assets/midi/Super Mario 64 - Medley.mid"))
    
    if os.path.exists(midi_path): analyze_polyphonic(midi_path)
    else: print(f"Error: File not found at {midi_path}")
