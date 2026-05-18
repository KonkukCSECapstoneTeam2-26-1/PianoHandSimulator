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
def _detect_hand_from_track_name(name: str):
    """트랙 이름에서 왼손/오른손 힌트 추출. 0=Left, 1=Right, None=불명확"""
    import re
    words = set(re.split(r'[_\s\-]', name.lower()))
    if words & {'left', 'lh', 'l', 'bass', 'lower'}:
        return 0
    if words & {'right', 'rh', 'r', 'treble', 'upper', 'melody', 'lead'}:
        return 1
    return None

def _find_split_pitch(all_notes):
    """전체 음표 피치 분포에서 밀도가 가장 낮은 지점을 손 분리 기준으로 반환."""
    if not all_notes:
        return 55
    from collections import Counter
    hist = Counter(n.pitch // 1 for n in all_notes)
    # 피아노 연주 범위(40~80)에서 탐색
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

    # 트랙별로 처리하여 트랙 이름 힌트 활용
    track_time = [0.0] * len(mid.tracks)
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
                    # 트랙 힌트가 없으면 일단 None으로 보관 (후처리에서 pitch 기반 결정)
                    all_notes.append(NoteEvent(msg.note, vel, start_time, t_ms - start_time, hint if hint is not None else -1))

    all_notes.sort(key=lambda x: x.start_ms)

    # 트랙 힌트가 없는 음표(-1)는 피치 기반 동적 분리
    unassigned = [n for n in all_notes if n.hand == -1]
    if unassigned:
        split_pitch = _find_split_pitch(all_notes)
        for n in unassigned:
            n.hand = 1 if n.pitch >= split_pitch else 0

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

        # merge: 매 반복마다 30ms 이내 화음 합치기 (split 후 생긴 조각 포함)
        for h in [0, 1]:
            hand_chords[h].sort(key=lambda c: c[0].start_ms)
            merged = []
            for chord in hand_chords[h]:
                if merged and chord[0].start_ms - merged[-1][0].start_ms < 30:
                    merged[-1] = sorted(merged[-1] + chord, key=lambda n: n.pitch)
                else:
                    merged.append(chord)
            hand_chords[h] = merged

        # split: span 초과 화음을 반대 손으로 분리
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

                # 반대 손에 같은 시간대 화음이 있으면 합쳤을 때 span 미리 체크
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
                    # span 초과 시 drop: 물리적으로 연주 불가능한 음표 제거

            hand_chords[h] = sorted(new_chords, key=lambda c: c[0].start_ms)

    return hand_chords

# --- 2. Polyphonic DP Solver ---
def _trim_chord(chord, hand_id):
    """화음이 5음 초과일 때 중요 성부(MELODY/BASS) 우선으로 5개만 남김."""
    if len(chord) <= 5:
        return chord
    priority = {"MELODY": 0, "BASS": 1, "INNER": 2}
    sorted_chord = sorted(chord, key=lambda n: (priority[n.role], n.pitch if hand_id == 0 else -n.pitch))
    return sorted(sorted_chord[:5], key=lambda n: n.pitch)

def solve_fingering_chord_dp(chord_sequence, hand_id):
    if not chord_sequence: return
    chord_sequence = [_trim_chord(c, hand_id) for c in chord_sequence]

    def get_combinations(k):
        if k > 5:
            k = 5
        combos = list(combinations(range(1, 6), k))
        if hand_id == 0: # Left Hand: Lowest pitch gets highest finger number (5 -> 1)
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
        # 1. Span Check
        for i in range(len(curr_f_tuple)-1):
            f_pair = tuple(sorted((curr_f_tuple[i], curr_f_tuple[i+1])))
            if (curr_notes[i+1].pitch - curr_notes[i].pitch) > MAX_SPAN.get(f_pair, 12):
                penalty += 5000

        # 2. Role Affinity (손마다 해부학적으로 다르게 적용)
        role_penalty = 0
        for i, f in enumerate(curr_f_tuple):
            note = curr_notes[i]
            if note.role == "MELODY":
                # 오른손: 4번(약지) 선호, 5번은 소폭 선호, 1번은 기피
                # 왼손: 1번(엄지=가장 높은 음) 선호
                if hand_id == 1:
                    if f == 4:      role_penalty -= 12
                    elif f == 5:    role_penalty -= 6
                    elif f == 1:    role_penalty += 20
                else:
                    if f == 1:      role_penalty -= 12
                    elif f == 2:    role_penalty -= 6
                    elif f == 5:    role_penalty += 15
            elif note.role == "BASS":
                # 오른손 베이스: 1번(엄지) 선호
                # 왼손 베이스: 5번(새끼=가장 낮은 음) 선호
                if hand_id == 1:
                    if f == 1:      role_penalty -= 10
                else:
                    if f == 5:      role_penalty -= 12
            elif note.role == "INNER":
                if f in [2, 3]:     role_penalty -= 5

        # 3. Melody Continuity
        # step motion(반음~온음)에서 같은 손가락을 유지하면 레가토에 유리 → 보상
        # 반대로 도약(3반음 이상)에서 같은 손가락을 고집하면 손목 이동이 큼 → 패널티
        prev_m_idx = next((i for i, n in enumerate(prev_notes) if n.role == "MELODY"), None)
        curr_m_idx = next((i for i, n in enumerate(curr_notes) if n.role == "MELODY"), None)
        if prev_m_idx is not None and curr_m_idx is not None:
            pm_note, cm_note = prev_notes[prev_m_idx], curr_notes[curr_m_idx]
            pm_f, cm_f = prev_f_tuple[prev_m_idx], curr_f_tuple[curr_m_idx]
            p_dist = abs(cm_note.pitch - pm_note.pitch)
            if 0 < p_dist <= 2 and pm_f == cm_f: penalty -= 20  # step motion + 같은 손가락 → 보상
            if p_dist >= 3 and pm_f == cm_f:     penalty += 30  # 도약 + 같은 손가락 → 패널티

        # 4. Wrist & Crossing (Standard V4 logic updated for LH)
        p_diff = curr_notes[0].pitch - prev_notes[-1].pitch
        if hand_id == 1: # Right Hand
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and curr_f_tuple[0] != 1: penalty += 2000
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and prev_f_tuple[0] != 1: penalty += 2000
        else: # Left Hand (Fingers 5->1)
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
    
    # Use proper finger-to-wrist offsets
    offsets = FINGER_WRIST_OFFSET_R if hand_id == 1 else FINGER_WRIST_OFFSET_L
    yaw_score = sum((n.pitch - avg_pitch) - offsets.get(n.finger, 0) for n in chord_group)
    
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
