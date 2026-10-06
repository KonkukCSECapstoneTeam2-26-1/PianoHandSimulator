import mido
import json
import os
import math
from itertools import combinations
from bisect import bisect_right

# 건반 3D 좌표 변환 공유 모듈 (01_Fingering <-> 02_IK 공용)
# 근거: 01_Design/09_Interface_Parameter_Decisions.md
try:
    import piano_keyboard
except ImportError:  # 다른 작업 디렉터리에서 임포트되는 경우 대비
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import piano_keyboard

# --- Constants & Anatomical Limits ---
BLACK_KEYS = {1, 3, 6, 8, 10}

# 피아노 88키 음역 (A0 ~ C8)
PIANO_MIN_PITCH, PIANO_MAX_PITCH = 21, 108

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
        # duration_ms(소리 지속)와 손가락 점유를 구분한다.
        # MIDI의 note_off는 Sustain 페달로 길게 늘어난 '소리'의 끝이지,
        # 손가락이 건반에서 떨어진 시점이 아니다. 아래 두 값은 운지 확정 후 채워진다.
        self.key_hold_ms = duration_ms   # 손가락이 실제로 건반을 누르고 있는 시간
        self.pedal_down = False          # 타건 시점에 Sustain 페달(CC64)이 눌려 있었는지
        self.required_hold_ms = duration_ms  # 페달을 고려한 최소 필수 점유 (운지와 무관)

    def to_dict(self):
        # 건반 중심 X / 타건 접점 Y / 누름 깊이 반영 Z (공유 모듈 위임)
        target_x, target_y, target_z = piano_keyboard.key_target_position(
            self.pitch, self.key_depth
        )
        return {
            "pitch": self.pitch,
            "start_ms": round(self.start_ms, 2),
            "duration_ms": round(self.duration_ms, 2),
            # IK는 건반 누름/해제에 key_hold_ms를 써야 한다 (duration_ms는 소리 지속)
            # 내림 처리: 반올림으로 점유 시간이 늘어나 겹침이 되살아나는 것을 방지
            "key_hold_ms": math.floor(self.key_hold_ms * 100) / 100,
            "pedal_down": self.pedal_down,
            "hand": "Left" if self.hand == 0 else "Right",
            "role": self.role,
            "finger": self.finger,
            "pressure": round(self.pressure, 3),
            "key_depth": round(self.key_depth, 3),
            "is_black": self.is_black,
            # 건반 3D 타겟 좌표(mm) — piano_keyboard 모듈이 유일한 산출 경로
            "target_x_mm": round(target_x, 2),
            "target_y_mm": round(target_y, 2),
            "target_z_mm": round(target_z, 2)
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

DEFAULT_TEMPO = 500000  # us/beat = 120 BPM

def _build_tempo_map(mid):
    """모든 트랙의 set_tempo를 절대 tick 기준으로 수집하여 [(tick, tempo)] 반환.

    Format 1 MIDI는 템포 이벤트가 별도 트랙(보통 track 0)에만 존재하므로,
    트랙마다 독립적으로 템포를 추적하면 음표 트랙이 템포 변화를 놓친다.
    """
    events = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == 'set_tempo':
                events.append((tick, msg.tempo))
    events.sort(key=lambda e: e[0])

    tempo_map = []
    for tick, tempo in events:
        if tempo_map and tempo_map[-1][0] == tick:
            tempo_map[-1] = (tick, tempo)  # 동일 tick이면 마지막 값 채택
        else:
            tempo_map.append((tick, tempo))

    if not tempo_map or tempo_map[0][0] > 0:
        tempo_map.insert(0, (0, DEFAULT_TEMPO))
    return tempo_map

def _make_tick_to_ms(tempo_map, ticks_per_beat):
    """템포맵 구간별 누적 시간을 선계산하여 tick → ms 변환 함수를 반환."""
    ticks = [t for t, _ in tempo_map]
    cum_ms = [0.0]
    for i in range(1, len(tempo_map)):
        prev_tick, prev_tempo = tempo_map[i - 1]
        cum_ms.append(cum_ms[-1] +
                      mido.tick2second(ticks[i] - prev_tick, ticks_per_beat, prev_tempo) * 1000)

    def tick_to_ms(tick):
        i = bisect_right(ticks, tick) - 1
        seg_tick, seg_tempo = tempo_map[i]
        return cum_ms[i] + mido.tick2second(tick - seg_tick, ticks_per_beat, seg_tempo) * 1000

    return tick_to_ms

def parse_pedal_spans(file_path):
    """Sustain 페달(CC64) 눌림 구간을 [(start_ms, end_ms)] 로 반환.

    CC64 값 >= 64 를 눌림으로 본다 (MIDI 표준 관례).
    페달이 눌린 동안에는 건반에서 손가락을 떼도 소리가 유지되므로,
    손가락 점유 시간(key_hold_ms)을 소리 지속(duration_ms)보다 짧게 잡을 근거가 된다.
    """
    mid = mido.MidiFile(file_path)
    tick_to_ms = _make_tick_to_ms(_build_tempo_map(mid), mid.ticks_per_beat)

    events = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == 'control_change' and msg.control == 64:
                events.append((tick, msg.value))
    events.sort(key=lambda e: e[0])

    spans, down_at = [], None
    last_ms = 0.0
    for tick, value in events:
        t_ms = tick_to_ms(tick)
        last_ms = max(last_ms, t_ms)
        if value >= 64 and down_at is None:
            down_at = t_ms
        elif value < 64 and down_at is not None:
            spans.append((down_at, t_ms))
            down_at = None
    if down_at is not None:          # 페달을 밟은 채 곡이 끝나는 경우
        spans.append((down_at, last_ms))
    return spans

# 타건 자체에 필요한 최소 점유 시간(ms).
# 페달이 처음부터 눌려 있어 건반을 즉시 떼도 되는 경우에도, 건반을 누르는 동작
# 자체에 시간이 걸리므로 하한을 둔다. (화음 그룹화 임계값과 동일한 30ms)
MIN_STRIKE_HOLD_MS = 30.0

def _merge_spans(spans):
    """겹치거나 맞닿는 구간을 병합해 정렬된 [(a, b)] 반환."""
    merged = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged

def compute_required_hold(all_notes, pedal_spans):
    """페달을 고려한 '필수 점유 구간'(ms)을 각 음표에 산출해 넣는다.

    소리는 건반 또는 Sustain 페달 중 하나가 유지한다. 따라서 건반은 발음 구간
    [start, start+duration) 중 **페달이 떠 있는 동안에만** 눌려 있으면 되고,
    페달이 눌린 뒤로는 손가락을 떼도 소리가 이어진다.

    required_hold = (발음 구간 안에서 페달이 떠 있는 마지막 시점) − start

    이 값은 MIDI 음표와 CC64 만으로 결정되므로 **운지 배정과 무관**하다.
    key_hold_ms 는 "같은 손가락/건반이 다시 필요한 시점"에 의존하므로 운지가
    정해져야 알 수 있는데, DP 는 그 운지를 정하는 중이라 순환 의존이 생긴다.
    required_hold 는 그 고리를 끊어, DP 가 시작 전에 "어떤 음표들이 반드시 함께
    눌려 있어야 하는가"를 알 수 있게 한다. (설계안 11번 문서 3.3절)
    """
    spans = _merge_spans(pedal_spans)
    starts = [a for a, _ in spans]

    for note in all_notes:
        s0 = note.start_ms
        e0 = s0 + note.duration_ms

        # 발음 구간과 겹치는 페달 구간을 훑으며 '페달이 떠 있는 마지막 시점'을 찾는다
        up_sup = s0
        cursor = s0
        i = bisect_right(starts, e0) - 1
        lo = max(0, bisect_right(starts, s0) - 1)
        for a, b in spans[lo:i + 1] if i >= lo else []:
            if b <= s0:
                continue
            if a >= e0:
                break
            if a > cursor:          # cursor ~ a 구간은 페달이 떠 있었다
                up_sup = a
            cursor = max(cursor, b)
        if cursor < e0:             # 끝까지 페달이 떠 있다
            up_sup = e0

        required = up_sup - s0
        required = max(required, min(MIN_STRIKE_HOLD_MS, note.duration_ms))
        note.required_hold_ms = min(required, note.duration_ms)

def apply_key_hold_and_pedal(all_notes, pedal_spans):
    """운지 확정 후, 손가락 점유 시간(key_hold_ms)과 페달 상태를 산출.

    같은 손·같은 손가락이 다음 음표에 다시 필요하면, 그 시점에 건반을 떼야 한다.
    따라서 key_hold_ms = min(duration_ms, 다음 동일 손가락 음표의 start - start).
    이로써 '한 손가락이 서로 다른 건반을 동시에 누르는' 물리적 모순을 구조적으로 제거한다.
    소리의 지속은 duration_ms 와 페달이 담당하므로 음악적 정보는 유실되지 않는다.
    """
    spans = sorted(pedal_spans)

    def is_pedal_down(t):
        lo, hi = 0, len(spans) - 1
        while lo <= hi:
            mid_i = (lo + hi) // 2
            a, b = spans[mid_i]
            if t < a:   hi = mid_i - 1
            elif t > b: lo = mid_i + 1
            else:       return True
        return False

    for note in all_notes:
        note.pedal_down = is_pedal_down(note.start_ms)

    clipped = 0

    def _clip_by(key_fn):
        """같은 키로 묶인 음표들에서, 다음 음표가 시작하면 이전 점유를 끝낸다."""
        nonlocal clipped
        buckets = {}
        for note in all_notes:
            if note.finger:
                buckets.setdefault(key_fn(note), []).append(note)
        for notes in buckets.values():
            notes.sort(key=lambda n: n.start_ms)
            for curr, nxt in zip(notes, notes[1:]):
                limit = nxt.start_ms - curr.start_ms
                if limit < curr.key_hold_ms:
                    curr.key_hold_ms = max(limit, 0.0)
                    clipped += 1

    # (1) 같은 손가락 재사용 — 손가락 하나는 한 번에 건반 하나만 누른다
    _clip_by(lambda n: (n.hand, n.finger))
    # (2) 같은 건반 재타격 — 건반 하나는 한 번에 손가락 하나만 누른다.
    #     손가락이 달라도 떼었다가 다시 누르는 것이므로 이전 점유가 끝나야 한다.
    _clip_by(lambda n: (n.hand, n.pitch))

    return clipped

def _chord_time(chord):
    """화음의 기준 시각 = 구성 음표 중 가장 이른 온셋.

    화음 리스트는 pitch 오름차순으로 정렬되어 있으므로 chord[0] 은 '최저음'이지
    '가장 먼저 눌린 음'이 아니다. chord[0].start_ms 를 화음의 시각으로 쓰면
    병합·이관 판정이 실제 시간 관계와 어긋난다.
    """
    return min(n.start_ms for n in chord)

def _dedupe_chord(chord):
    """화음 내 동일 pitch를 하나로 병합한다 (pitch 오름차순 정렬 결과 반환).

    두 트랙이 같은 음을 동시에 연주하는 중복 보이싱(doubling)은 MIDI에서 흔하지만,
    건반 하나는 손가락 하나로만 누른다. 중복을 남기면
      · Monotonicity: 같은 pitch에 서로 다른 손가락이 배정됨
      · Span: 간격 0인 쌍이 생겨 비정상 운지를 유도
      · 화음 크기 부풀림 → 5음 초과로 _trim_chord가 유효 음표를 버림
    이 세 가지가 연쇄적으로 발생한다.
    병합 시 velocity가 큰(더 또렷한) 음표를 남기고, 지속 시간은 가장 긴 값을 취한다.
    """
    best = {}
    for note in chord:
        prev = best.get(note.pitch)
        if prev is None:
            best[note.pitch] = note
        else:
            keep, drop = (note, prev) if note.velocity > prev.velocity else (prev, note)
            # 소리는 둘 중 늦게 끝나는 시점까지 유지된다
            keep.duration_ms = max(
                keep.start_ms + keep.duration_ms, drop.start_ms + drop.duration_ms
            ) - keep.start_ms
            keep.key_hold_ms = keep.duration_ms
            best[note.pitch] = keep
    return sorted(best.values(), key=lambda n: n.pitch)

def parse_midi_to_hand_chords(file_path):
    mid = mido.MidiFile(file_path)
    tick_to_ms = _make_tick_to_ms(_build_tempo_map(mid), mid.ticks_per_beat)
    all_notes = []

    # 트랙별로 처리하여 트랙 이름 힌트 활용
    for track in mid.tracks:
        hand_hint = _detect_hand_from_track_name(track.name)
        # pitch별 FIFO 큐: 떼기 전에 같은 음을 재타격하는 경우 선행 음이 유실되지 않도록 함
        active_notes = {}
        tick = 0
        for msg in track:
            tick += msg.time
            if msg.type == 'note_on' and msg.velocity > 0:
                active_notes.setdefault(msg.note, []).append((tick, msg.velocity))
            elif (msg.type == 'note_off') or (msg.type == 'note_on' and msg.velocity == 0):
                pending = active_notes.get(msg.note)
                if pending:
                    start_tick, vel = pending.pop(0)
                    start_ms = tick_to_ms(start_tick)
                    # 트랙 힌트가 없으면 -1로 보관 (후처리에서 pitch 기반 결정)
                    all_notes.append(NoteEvent(msg.note, vel, start_ms,
                                               tick_to_ms(tick) - start_ms,
                                               hand_hint if hand_hint is not None else -1))

        # note_off 없이 트랙이 끝난 음표는 트랙 종료 시점에서 닫아 유실을 막음
        end_ms = tick_to_ms(tick)
        for pitch, pending in active_notes.items():
            for start_tick, vel in pending:
                start_ms = tick_to_ms(start_tick)
                all_notes.append(NoteEvent(pitch, vel, start_ms, end_ms - start_ms,
                                           hand_hint if hand_hint is not None else -1))

    # 피아노 88키 범위(A0~C8) 밖 음표 제거.
    # MIDI에는 베이스·드럼 등 비피아노 트랙이 섞여 있을 수 있고, 그 음표는
    # 건반 좌표가 정의되지 않는다. (요구사항 2.3의 피아노 트랙 자동 선별은 미구현 상태)
    out_of_range = [n for n in all_notes if not (PIANO_MIN_PITCH <= n.pitch <= PIANO_MAX_PITCH)]
    if out_of_range:
        lo = min(n.pitch for n in out_of_range)
        hi = max(n.pitch for n in out_of_range)
        print(f"  [경고] 88키 범위 밖 음표 {len(out_of_range)}개 제외 "
              f"(pitch {lo}~{hi}, 허용 {PIANO_MIN_PITCH}~{PIANO_MAX_PITCH})")
        all_notes = [n for n in all_notes if PIANO_MIN_PITCH <= n.pitch <= PIANO_MAX_PITCH]

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
            # 동일 온셋 음표는 30ms 윈도우를 넘더라도 반드시 같은 화음에 둔다.
            # (같은 순간에 눌리는 음이 서로 다른 화음으로 갈라지면 물리 제약을
            #  화음 단위로 거는 의미가 사라진다)
            same_onset = h_notes[i].start_ms == curr_group[-1].start_ms
            if same_onset or h_notes[i].start_ms - curr_group[0].start_ms < 30:
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

def _finger_combinations(k, hand_id):
    """화음 음표 수 k에 대한 손가락 조합 (pitch 오름차순 기준)."""
    k = min(k, 5)
    combos = list(combinations(range(1, 6), k))
    if hand_id == 0:  # 왼손: 최저음이 5번, 최고음이 1번
        return [tuple(reversed(c)) for c in combos]
    return combos

def is_chord_playable(chord, hand_id):
    """이 화음을 한 손으로 실제 배정할 수 있는 손가락 조합이 하나라도 있는지 판정.

    span(최고음-최저음)만 보던 기존 기준으로는, 전체 폭은 (1,5)=17반음 이내여도
    내부 음 배치 때문에 어떤 조합으로도 MAX_SPAN을 만족할 수 없는 화음이 통과했다.
    (예: [43, 50, 53, 57, 60] — 폭 17은 허용이지만 f5-f4가 7반음(>6)이 되어 불가)
    그 경우 DP는 +5000 패널티를 물고 물리적으로 불가능한 운지를 출력한다.
    """
    if len(chord) < 2:
        return True
    if len(chord) > 5:
        return False
    for f_tuple in _finger_combinations(len(chord), hand_id):
        ok = True
        for i in range(len(f_tuple)):
            for j in range(i + 1, len(f_tuple)):
                pair = tuple(sorted((f_tuple[i], f_tuple[j])))
                if (chord[j].pitch - chord[i].pitch) > MAX_SPAN.get(pair, 12):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return True
    return False

def split_wide_chords_between_hands(hand_chords, max_span=17, max_iter=50):
    changed = True
    iters = 0
    while changed and iters < max_iter:   # 분리↔병합 진동 시 폭주 방지
        changed = False
        iters += 1

        # merge: 매 반복마다 30ms 이내 화음 합치기 (split 후 생긴 조각 포함)
        for h in [0, 1]:
            hand_chords[h].sort(key=_chord_time)
            merged = []
            for chord in hand_chords[h]:
                if merged and _chord_time(chord) - _chord_time(merged[-1]) < 30:
                    merged[-1] = _dedupe_chord(merged[-1] + chord)
                else:
                    merged.append(_dedupe_chord(chord))
            hand_chords[h] = merged

        # split: span 초과 화음을 반대 손으로 분리
        for h in [0, 1]:
            other = 1 - h
            new_chords = []
            for chord in hand_chords[h]:
                # span 한계와 '배정 가능한 손가락 조합 존재' 둘 다 만족해야 통과
                if len(chord) < 2 or (chord[-1].pitch - chord[0].pitch <= max_span
                                      and is_chord_playable(chord, h)):
                    new_chords.append(chord)
                    continue
                changed = True
                gaps = [chord[i+1].pitch - chord[i].pitch for i in range(len(chord)-1)]
                split_idx = gaps.index(max(gaps))
                lower, upper = chord[:split_idx+1], chord[split_idx+1:]
                keep, move = (lower, upper) if h == 0 else (upper, lower)
                new_chords.append(keep)

                # 반대 손에 같은 시간대 화음이 있으면 합쳤을 때 span 미리 체크
                move_time = _chord_time(move)
                existing = next((c for c in hand_chords[other]
                                 if abs(_chord_time(c) - move_time) < 30), None)
                if existing is None:
                    for n in move: n.hand = other
                    hand_chords[other].append(move)
                else:
                    combined = _dedupe_chord(existing + move)
                    if (combined[-1].pitch - combined[0].pitch <= max_span
                            and is_chord_playable(combined, other)):
                        for n in move: n.hand = other
                        hand_chords[other].append(move)
                    # span 초과 시 drop: 물리적으로 연주 불가능한 음표 제거

            hand_chords[h] = sorted(new_chords, key=_chord_time)

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
        # 인접 쌍만 보면 비인접 쌍(예: 2-5)의 한계 초과가 통과된다 → 모든 쌍을 검사
        for i in range(len(f_tuple)):
            for j in range(i+1, len(f_tuple)):
                f_pair = tuple(sorted((f_tuple[i], f_tuple[j])))
                if (first_chord[j].pitch - first_chord[i].pitch) > MAX_SPAN.get(f_pair, 12):
                    is_possible = False; break
            if not is_possible: break
        if is_possible:
            cost = sum(FINGER_DIFFICULTY[f] for f in f_tuple)
            first_states[f_tuple] = (cost, None)
    
    if not first_states:
        first_states[get_combinations(len(first_chord))[0]] = (0, None)
    dp.append(first_states)

    def calc_transition_cost(prev_notes, prev_f_tuple, curr_notes, curr_f_tuple):
        penalty = 0
        # 1. Span Check — 인접 쌍뿐 아니라 모든 손가락 쌍을 검사한다.
        #    인접만 보면 2-3(6) · 3-5(9)가 각각 통과하면서 2-5가 15반음(한계 12)이 되는
        #    물리적으로 불가능한 화음이 DP를 통과한다.
        for i in range(len(curr_f_tuple)):
            for j in range(i+1, len(curr_f_tuple)):
                f_pair = tuple(sorted((curr_f_tuple[i], curr_f_tuple[j])))
                if (curr_notes[j].pitch - curr_notes[i].pitch) > MAX_SPAN.get(f_pair, 12):
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

        # 5. 동시 누름 충돌 방지
        # 이전 음표가 아직 눌린 상태(duration 내)인데 현재 화음에서 같은 손가락 재사용 시 패널티
        curr_start = curr_notes[0].start_ms
        busy_fingers = {
            prev_f_tuple[i]
            for i, n in enumerate(prev_notes)
            if n.start_ms + n.duration_ms > curr_start
        }
        for f in curr_f_tuple:
            if f in busy_fingers:
                penalty += 2500  # 물리적으로 불가능에 가까움

        # 6. 아르페지오 롤링
        # 연속 단음에서 피치 방향과 손가락 방향이 일치해야 자연스러운 롤링
        if len(prev_notes) == 1 and len(curr_notes) == 1:
            p_f, c_f = prev_f_tuple[0], curr_f_tuple[0]
            pitch_dir = curr_notes[0].pitch - prev_notes[0].pitch
            if pitch_dir != 0:
                if p_f == c_f:
                    penalty += 60  # 단음 연속에서 같은 손가락 반복
                else:
                    # 오른손: 상행=손가락 증가, 하행=손가락 감소
                    # 왼손: 상행=손가락 감소(5→1 방향), 하행=손가락 증가
                    rh_mismatch = (hand_id == 1 and ((pitch_dir > 0 and c_f < p_f) or (pitch_dir < 0 and c_f > p_f)))
                    lh_mismatch = (hand_id == 0 and ((pitch_dir > 0 and c_f > p_f) or (pitch_dir < 0 and c_f < p_f)))
                    if rh_mismatch or lh_mismatch:
                        penalty += 35

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
    # 5음 초과 화음은 _trim_chord로 줄인 결과를 그대로 보관한다.
    # (기존에는 DP 내부에서만 잘라, 잘려나간 음표가 finger=0 으로 JSON에 새어나갔음)
    trimmed_out = 0
    for h in [0, 1]:
        kept = []
        for chord in hand_chords[h]:
            t = _trim_chord(chord, h)
            trimmed_out += len(chord) - len(t)
            kept.append(t)
        hand_chords[h] = kept
        solve_fingering_chord_dp(hand_chords[h], h)
    if trimmed_out:
        print(f"  [경고] 5음 초과 화음에서 음표 {trimmed_out}개 제외 (한 손 손가락 5개 한계)")

    # 운지 확정 후: 손가락 점유 시간(key_hold_ms)과 페달 상태 산출
    all_notes = [n for h in [0, 1] for group in hand_chords[h] for n in group]
    pedal_spans = parse_pedal_spans(file_path)
    compute_required_hold(all_notes, pedal_spans)
    clipped = apply_key_hold_and_pedal(all_notes, pedal_spans)
    print(f"  페달 구간 {len(pedal_spans)}개 / 손가락 점유 보정 {clipped}건")

    final_notes = []
    for h in [0, 1]:
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
    midi_name = os.path.splitext(os.path.basename(file_path))[0]
    output_path = os.path.join(output_dir, f"{midi_name}_polyphonic_result.json")
    with open(output_path, "w") as f: json.dump(final_notes, f, indent=4)
    print(f"\n--- POLYPHONIC ANALYSIS COMPLETE: {output_path} ---")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    midi_path = os.path.abspath(os.path.join(base_dir, "../assets/midi/deb_clai.mid"))
    
    if os.path.exists(midi_path): analyze_polyphonic(midi_path)
    else: print(f"Error: File not found at {midi_path}")
