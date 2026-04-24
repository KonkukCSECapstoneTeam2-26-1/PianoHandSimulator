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
# 약지(4): 해부학적으로 독립 운동이 가장 어려움
# 새끼(5): 짧고 힘이 약함
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
        self.is_black = (pitch % 12) in BLACK_KEYS
        self.pressure = velocity / 127.0
        self.key_depth = self.pressure * 1.0

    def to_dict(self):
        return {
            "pitch": self.pitch,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            "hand": "Left" if self.hand == 0 else "Right",
            "finger": self.finger,
            "pressure": round(self.pressure, 3),
            "key_depth": round(self.key_depth, 3),
            "is_black": self.is_black
        }

# --- 1. MIDI Parser ---
def parse_midi_to_hand_chords(file_path):
    mid = mido.MidiFile(file_path)
    all_notes = []
    active_notes = {}
    t_ms = 0.0
    tempo = 500000

    # merge_tracks로 모든 트랙을 절대 시간 순으로 병합 → 템포 변경이 올바르게 적용됨
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
                hand_chords[h].append(curr_group)
                curr_group = [h_notes[i]]
        curr_group.sort(key=lambda x: x.pitch)
        hand_chords[h].append(curr_group)
    return hand_chords

# --- 1b. Post-process: Split physically impossible wide chords between hands ---
def split_wide_chords_between_hands(hand_chords, max_span=17):
    """
    화음의 pitch span이 max_span(반음)을 초과하면 가장 큰 pitch 간격에서 분리하여
    한쪽을 반대 손으로 이동. 안정될 때까지 반복.
    """
    changed = True
    while changed:
        changed = False
        for h in [0, 1]:
            other = 1 - h
            new_chords = []
            for chord in hand_chords[h]:
                if len(chord) < 2 or chord[-1].pitch - chord[0].pitch <= max_span:
                    new_chords.append(chord)
                    continue
                # 가장 큰 pitch gap에서 분리
                changed = True
                gaps = [chord[i+1].pitch - chord[i].pitch for i in range(len(chord)-1)]
                split_idx = gaps.index(max(gaps))
                lower = chord[:split_idx+1]
                upper = chord[split_idx+1:]
                if h == 0:  # 왼손: 낮은 쪽 유지, 높은 쪽 → 오른손
                    new_chords.append(lower)
                    for n in upper: n.hand = 1
                    hand_chords[1].append(upper)
                else:       # 오른손: 높은 쪽 유지, 낮은 쪽 → 왼손
                    new_chords.append(upper)
                    for n in lower: n.hand = 0
                    hand_chords[0].append(lower)
            hand_chords[h] = sorted(new_chords, key=lambda c: c[0].start_ms)

    # split 후 같은 손·같은 시간대에 생긴 중복 chord 그룹 병합
    for h in [0, 1]:
        hand_chords[h].sort(key=lambda c: c[0].start_ms)
        merged = []
        for chord in hand_chords[h]:
            if merged and chord[0].start_ms - merged[-1][0].start_ms < 30:
                merged[-1] = sorted(merged[-1] + chord, key=lambda n: n.pitch)
            else:
                merged.append(chord)
        hand_chords[h] = merged

    return hand_chords

# --- 2. Advanced Solver with Hard Constraints ---
def solve_fingering_chord_dp(chord_sequence, hand_id):
    if not chord_sequence: return
    
    def get_combinations(k):
        return list(combinations(range(1, 6), k))

    dp = []
    # Initialize
    first_chord = chord_sequence[0]
    first_states = {}
    for f_tuple in get_combinations(len(first_chord)):
        # Check if first chord itself is possible
        is_possible = True
        for i in range(len(f_tuple)-1):
            pair = (f_tuple[i], f_tuple[i+1])
            if (first_chord[i+1].pitch - first_chord[i].pitch) > MAX_SPAN.get(pair, 12):
                is_possible = False; break
        if is_possible:
            cost = sum(
                FINGER_DIFFICULTY[f] +
                (25 if (f == 1 and first_chord[i].is_black) else
                 10 if (f == 5 and first_chord[i].is_black) else 0)
                for i, f in enumerate(f_tuple)
            )
            first_states[f_tuple] = (cost, None)
    
    if not first_states:  # 모든 조합이 span 위반 → 최소 위반 조합 선택
        best_combo, best_viol = None, float('inf')
        for f_tuple in get_combinations(len(first_chord)):
            total_viol = sum(
                max(0, (first_chord[i+1].pitch - first_chord[i].pitch) - MAX_SPAN.get((f_tuple[i], f_tuple[i+1]), 12))
                for i in range(len(f_tuple)-1)
            )
            if total_viol < best_viol:
                best_viol, best_combo = total_viol, f_tuple
        first_states[best_combo] = (0, None)
    dp.append(first_states)

    def calc_transition_cost(prev_notes, prev_f_tuple, curr_notes, curr_f_tuple):
        penalty = 0
        # 1. Monotonicity & Span Check (Hard Constraints as high penalties)
        for i in range(len(curr_f_tuple)-1):
            span = curr_notes[i+1].pitch - curr_notes[i].pitch
            pair = (curr_f_tuple[i], curr_f_tuple[i+1])
            if span > MAX_SPAN.get(pair, 12): penalty += 5000 # Serious penalty

        # 2. 크로싱 룰 + 4-5번 전환 추가 패널티
        p_diff = curr_notes[0].pitch - prev_notes[-1].pitch
        if hand_id == 1: # 오른손
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and curr_f_tuple[0] != 1: penalty += 2000
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and prev_f_tuple[0] != 1: penalty += 2000
        else: # 왼손
            if p_diff < 0 and curr_f_tuple[-1] > prev_f_tuple[0] and curr_f_tuple[-1] != 1: penalty += 2000
            if p_diff > 0 and curr_f_tuple[0] < prev_f_tuple[-1] and prev_f_tuple[-1] != 1: penalty += 2000

        # 약지-새끼(4-5) 전환: 해부학적으로 매우 어려움
        if len(curr_notes) == 1 and len(prev_notes) == 1:
            if {prev_f_tuple[0], curr_f_tuple[0]} == {4, 5}:
                penalty += 30

        # 3. 손목 이동 비용 (단일 노트: 손가락 기반 손목 위치 역산)
        if len(curr_notes) == 1 and len(prev_notes) == 1:
            off = FINGER_WRIST_OFFSET_R if hand_id == 1 else FINGER_WRIST_OFFSET_L
            prev_wrist = prev_notes[0].pitch - off[prev_f_tuple[0]]
            curr_wrist = curr_notes[0].pitch - off[curr_f_tuple[0]]
            wrist_move = abs(curr_wrist - prev_wrist)
        else:
            prev_avg_p = sum(n.pitch for n in prev_notes) / len(prev_notes)
            curr_avg_p = sum(n.pitch for n in curr_notes) / len(curr_notes)
            wrist_move = abs(curr_avg_p - prev_avg_p)

        # 포지션 전환 추가 비용: 5반음 이상 손목 이동 = 포지션 시프트
        if wrist_move > POSITION_SHIFT_THRESHOLD:
            penalty += (wrist_move - POSITION_SHIFT_THRESHOLD) * 2

        # 4. 손가락별 비용 (난이도 + 흑건 패널티)
        note_penalty = 0
        for i, f in enumerate(curr_f_tuple):
            note = curr_notes[i]
            note_penalty += FINGER_DIFFICULTY[f]
            if note.is_black:
                if f == 1:   note_penalty += 25   # 엄지 흑건: 손목 꺾임 발생
                elif f == 5: note_penalty += 10   # 새끼 흑건

        # 5. 엄지 통과법(Thumb Under) 보너스
        #    교과서 패턴: 오른손 상행 3→1, 하행 1→3
        if len(curr_notes) == 1 and len(prev_notes) == 1:
            pf, cf = prev_f_tuple[0], curr_f_tuple[0]
            if hand_id == 1:
                if pf == 3 and cf == 1 and p_diff > 0: penalty -= 10  # 상행 엄지 통과
                if pf == 1 and cf == 3 and p_diff < 0: penalty -= 10  # 하행 손가락 넘기기
            else:
                if pf == 3 and cf == 1 and p_diff < 0: penalty -= 10
                if pf == 1 and cf == 3 and p_diff > 0: penalty -= 10

        # 6. 같은 손가락 반복 타이브레이커
        if len(curr_notes) == 1 and len(prev_notes) == 1:
            if curr_f_tuple[0] == prev_f_tuple[0]:
                penalty += 8

        return wrist_move * 2.0 + note_penalty + penalty

    # DP Forward
    for c_idx in range(1, len(chord_sequence)):
        curr_chord = chord_sequence[c_idx]
        prev_chord = chord_sequence[c_idx-1]
        curr_states = {}
        curr_combos = get_combinations(len(curr_chord))
        prev_states = dp[c_idx-1]
        
        for curr_f_tuple in curr_combos:
            min_c = float('inf')
            best_prev = None
            for prev_f_tuple, (prev_cost, _) in prev_states.items():
                t_cost = calc_transition_cost(prev_chord, prev_f_tuple, curr_chord, curr_f_tuple)
                if prev_cost + t_cost < min_c:
                    min_c = prev_cost + t_cost
                    best_prev = prev_f_tuple
            curr_states[curr_f_tuple] = (min_c, best_prev)
        dp.append(curr_states)

    # Backtrack
    last_states = dp[-1]
    best_last_f_tuple = min(last_states.keys(), key=lambda k: last_states[k][0])
        
    curr_f_tuple = best_last_f_tuple
    for i in range(len(chord_sequence)-1, -1, -1):
        if curr_f_tuple is None: break # Safety
        for j, finger in enumerate(curr_f_tuple):
            if j < len(chord_sequence[i]):
                chord_sequence[i][j].finger = finger
        curr_f_tuple = dp[i][curr_f_tuple][1]

# --- 3. Wrist Physics with ROM Clamping ---
def calculate_wrist_rotation_rom(chord_group, hand_id):
    if not chord_group: return 0, 0
    avg_pitch = sum(n.pitch for n in chord_group) / len(chord_group)
    
    # Yaw Calculation
    yaw_score = 0
    for n in chord_group:
        expected_rel_pitch = (n.finger - 3) * 2.5 # Adjusted natural spacing
        actual_rel_pitch = n.pitch - avg_pitch
        yaw_score += (actual_rel_pitch - expected_rel_pitch)
    
    yaw_deg = yaw_score * 2.5
    if hand_id == 0: yaw_deg = -yaw_deg
    
    # Roll Calculation
    roll_deg = 0
    thumb = next((n for n in chord_group if n.finger == 1), None)
    pinky = next((n for n in chord_group if n.finger == 5), None)
    if thumb and thumb.is_black: roll_deg += 12
    if pinky and pinky.is_black: roll_deg -= 12
    if hand_id == 0: roll_deg = -roll_deg
    
    # --- Hard ROM Clamping ---
    yaw_deg = max(min(yaw_deg, WRIST_ROM["yaw_max"]), -WRIST_ROM["yaw_max"])
    roll_deg = max(min(roll_deg, WRIST_ROM["roll_max"]), -WRIST_ROM["roll_max"])
    
    return round(yaw_deg, 2), round(roll_deg, 2)

# --- 4. Main Analysis ---
def analyze_rom(file_path):
    print(f"Analyzing with Anatomical ROM: {file_path}...")
    hand_chords = parse_midi_to_hand_chords(file_path)
    hand_chords = split_wide_chords_between_hands(hand_chords)
    final_notes = []
    
    for h in [0, 1]:
        solve_fingering_chord_dp(hand_chords[h], h)
        for group in hand_chords[h]:
            avg_p = sum(n.pitch for n in group) / len(group)
            wrist_pos = round((avg_p - 21) / (108 - 21), 3)
            yaw, roll = calculate_wrist_rotation_rom(group, h)
            for n in group:
                d = n.to_dict()
                d["wrist_pos_normalized"] = wrist_pos
                d["wrist_yaw_deg"] = yaw
                d["wrist_roll_deg"] = roll
                final_notes.append(d)

    final_notes.sort(key=lambda x: x["start_ms"])
    output_filename = "mario_rom_result.json"
    with open(output_filename, 'w') as f:
        json.dump(final_notes, f, indent=4)
        
    print(f"\n--- ROM ANALYSIS COMPLETE ---")
    print(f"Results constrained by human limits saved to {output_filename}")

if __name__ == "__main__":
    midi_path = "D:\\Git\\PianoHandSimulator\\Super Mario 64 - Medley.mid"
    if os.path.exists(midi_path):
        analyze_rom(midi_path)
    else:
        print("Error: File not found.")
