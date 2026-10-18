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

# 공유 상수 (01/02/03 파트 공용) — 수치의 단일 출처
try:
    import shared_constants
except ImportError:
    import sys as _sys
    _sys.path.insert(0, os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")))
    import shared_constants

# --- Constants & Anatomical Limits ---
# 수치는 `02_Implementation/01_Fingering/shared_constants.py` 가 단일 출처다.
# 아래 이름들은 기존 소비측(metrics.py·테스트)과의 호환을 위해 그대로 노출한다.
BLACK_KEYS = set(shared_constants.BLACK_KEY_PITCH_CLASSES)

# 피아노 88키 음역 (A0 ~ C8)
PIANO_MIN_PITCH = shared_constants.MIDI_MIN
PIANO_MAX_PITCH = shared_constants.MIDI_MAX

# 손가락 쌍별 최대 허용 반음 간격 (하드 제약)
MAX_SPAN = shared_constants.MAX_SPAN

# 손목 가동 범위 (도)
WRIST_ROM = {
    "yaw_max": shared_constants.WRIST_YAW_MAX_DEG,
    "roll_max": shared_constants.WRIST_ROLL_MAX_DEG,
}

# 손가락별 손목 기준점 오프셋 (반음, 손목 중심 기준)
FINGER_WRIST_OFFSET_L = shared_constants.FINGER_WRIST_OFFSET_L
FINGER_WRIST_OFFSET_R = shared_constants.FINGER_WRIST_OFFSET_R

# ── 피아노 교육학 기반 손가락 비용 ───────────────────────────────
FINGER_DIFFICULTY = shared_constants.FINGER_DIFFICULTY

# 포지션(5지 묶음) 전환 임계값 (반음)
POSITION_SHIFT_THRESHOLD = shared_constants.POSITION_SHIFT_THRESHOLD

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
        self.dropped = False             # 순간 단위 충돌 해소에서 제외된 음표

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
MIN_STRIKE_HOLD_MS = shared_constants.MIN_STRIKE_HOLD_MS

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

def split_wide_chords_between_hands(hand_chords, max_span=17, max_iter=50, report=None):
    """report: dict 를 넘기면 버려진 음표 수/예시를 기록한다."""
    dropped = []
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
                    def _fits(chord, hand):
                        return (chord[-1].pitch - chord[0].pitch <= max_span
                                and is_chord_playable(chord, hand))

                    combined = _dedupe_chord(existing + move)
                    if _fits(combined, other):
                        for n in move: n.hand = other
                        hand_chords[other].append(move)
                    else:
                        # 통째로 버리지 않고 최대한 살린다.
                        # 1) 반대 손에 성부 중요도 순으로 한 음씩 넣어 본다
                        order = {"MELODY": 0, "BASS": 1, "INNER": 2}
                        ranked = sorted(move, key=lambda n: (order.get(n.role, 2), -n.velocity))
                        accepted = []
                        for note in ranked:
                            if _fits(_dedupe_chord(existing + accepted + [note]), other):
                                accepted.append(note)
                        if accepted:
                            for n in accepted: n.hand = other
                            hand_chords[other].append(sorted(accepted, key=lambda n: n.pitch))

                        # 2) 반대 손이 받지 못한 음은 원래 손에 되돌릴 수 있는지 본다.
                        #    분리 지점은 '최대 간격'으로 정해지므로, 연주 가능성 기준으로는
                        #    남은 음 일부가 원래 손에 들어갈 여지가 있다.
                        leftover = [n for n in ranked if n not in accepted]
                        returned = []
                        for note in leftover:
                            if _fits(_dedupe_chord(keep + returned + [note]), h):
                                returned.append(note)
                        if returned:
                            keep.extend(returned)
                            keep.sort(key=lambda n: n.pitch)

                        # 3) 그래도 남으면 버린다 (편곡이 두 손 연주 범위를 넘는 경우)
                        dropped.extend(n for n in leftover if n not in returned)

            hand_chords[h] = sorted(new_chords, key=_chord_time)

    if report is not None:
        report["dropped"] = len(dropped)
        report["examples"] = [
            f"t={n.start_ms:.0f}ms pitch={n.pitch} ({n.role})" for n in dropped[:5]]
    return hand_chords

# --- 2. Polyphonic DP Solver ---
def _trim_chord(chord, hand_id):
    """화음이 5음 초과일 때 중요 성부(MELODY/BASS) 우선으로 5개만 남김."""
    if len(chord) <= 5:
        return chord
    priority = {"MELODY": 0, "BASS": 1, "INNER": 2}
    sorted_chord = sorted(chord, key=lambda n: (priority[n.role], n.pitch if hand_id == 0 else -n.pitch))
    return sorted(sorted_chord[:5], key=lambda n: n.pitch)

# --- 순간 단위(점유 기반) 제약 파라미터 -----------------------------------
# 설계안: 01_Design/11_Temporal_Constraint_Design.md (3단계)
HELD_DEPTH_LIMIT = 4        # 점유 정보를 기억할 최대 화음 거리 (실측상 96.8% 커버)
DP_BEAM_WIDTH = 120         # 화음당 유지할 최대 상태 수 (상태 폭발 방지)
OCCUPANCY_TOL_MS = 1.0      # 점유 종료 판정 허용오차 (반올림 경계)

OCCUPANCY_SPAN_PENALTY = 5000    # 순간 손 범위 초과 (화음 내 SpanPenalty와 동일 수준)
OCCUPANCY_FINGER_PENALTY = 4000  # 한 손가락이 두 건반
OCCUPANCY_ORDER_PENALTY = 1500   # pitch 순 ↔ 손가락 순 어긋남

def _occupies_at(note, t_ms):
    """음표가 시각 t 에 아직 건반을 점유하고 있는가.

    점유 길이는 required_hold_ms(페달을 고려한 최소 의무)를 쓴다. key_hold_ms 는
    운지가 정해져야 알 수 있어 DP 중에는 사용할 수 없다. (설계안 3.3절)
    """
    return note.start_ms + note.required_hold_ms > t_ms + OCCUPANCY_TOL_MS

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

    chord_times = [_chord_time(c) for c in chord_sequence]
    EMPTY_HELD = frozenset()

    def advance_held(held, prev_idx, prev_f, t_now, curr_idx):
        """이전 상태의 점유 집합을 현재 화음 시점으로 갱신.

        - 아직 점유 중이고
        - 화음 거리가 HELD_DEPTH_LIMIT 이내인
        항목만 남기고, 직전 화음에서 새로 이어지는 점유를 더한다.
        항목은 (화음 인덱스, 화음 내 위치, 손가락).
        """
        out = []
        for entry in held:
            ci, pos, fg = entry
            if curr_idx - ci <= HELD_DEPTH_LIMIT and _occupies_at(chord_sequence[ci][pos], t_now):
                out.append(entry)
        prev_chord = chord_sequence[prev_idx]
        for pos, note in enumerate(prev_chord):
            if pos < len(prev_f) and _occupies_at(note, t_now):
                out.append((prev_idx, pos, prev_f[pos]))
        return frozenset(out)

    def occupancy_penalty(curr_chord, curr_f, held):
        """현재 화음 + 아직 눌려 있는 음표를 합쳐 순간 단위 제약을 검사.

        화음 단위 검사만으로는 지속음과의 충돌을 볼 수 없다. 이 함수가 설계안의
        C1(손가락 유일) · C2(손 범위) · C3(순서)를 한 순간에 대해 평가한다.
        """
        if not held:
            return 0
        items = [(n.pitch, f) for n, f in zip(curr_chord, curr_f)]
        items += [(chord_sequence[ci][pos].pitch, fg) for ci, pos, fg in held]
        items.sort()
        fingers = [f for _, f in items]

        penalty = (len(fingers) - len(set(fingers))) * OCCUPANCY_FINGER_PENALTY

        for a in range(len(items)):
            for b in range(a + 1, len(items)):
                limit = MAX_SPAN.get(tuple(sorted((items[a][1], items[b][1]))), 12)
                if items[b][0] - items[a][0] > limit:
                    penalty += OCCUPANCY_SPAN_PENALTY

        # 엄지(1번)는 순서 판정에서 제외한다. 엄지 넘기기 중에는 엄지가 다른 손가락보다
        # 높은(오른손) 또는 낮은(왼손) 건반에 놓이는 것이 정상이며, 이는 손바닥 아래로
        # 지나가는 동작이라 2~5번의 상호 순서만 유지되면 물리적으로 가능하다.
        others = [f for f in fingers if f != 1]
        for k in range(len(others) - 1):
            if hand_id == 1:
                if others[k] >= others[k + 1]:
                    penalty += OCCUPANCY_ORDER_PENALTY
            else:
                if others[k] <= others[k + 1]:
                    penalty += OCCUPANCY_ORDER_PENALTY
        return penalty

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
            first_states[(f_tuple, EMPTY_HELD)] = (cost, None)

    if not first_states:
        first_states[(get_combinations(len(first_chord))[0], EMPTY_HELD)] = (0, None)
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
                    # 엄지 넘기기(thumb-under)와 손가락 넘어가기(cross-over)는 스케일·
                    # 아르페지오의 표준 주법이다. 방향이 역전되어 보이지만 정상이므로
                    # 패널티 대상에서 제외하고, 포지션을 다 쓴 뒤에 일어나면 보상한다.
                    #   오른손: 상행 중 엄지로 내려오기 / 하행 중 엄지 위로 넘어가기
                    #   왼손  : 하행 중 엄지로 올라가기 / 상행 중 엄지 아래로 넘어가기
                    if hand_id == 1:
                        thumb_turn = (pitch_dir > 0 and c_f == 1) or (pitch_dir < 0 and p_f == 1)
                    else:
                        thumb_turn = (pitch_dir < 0 and c_f == 1) or (pitch_dir > 0 and p_f == 1)

                    if thumb_turn:
                        # 엄지를 넘기는 '상대 손가락'이 무엇이냐로 자연스러움이 갈린다.
                        # 보상하지 않는다 — 넘기기 자체를 보상하면 1-4-1-4 처럼 두 음마다
                        # 넘기는 운지가 최적이 되어 버린다. 자연스러운 음계는 아래의
                        # '순차 진행 보상'으로 1-2-3 을 쌓은 뒤 넘기도록 유도한다.
                        pivot = p_f if c_f == 1 else c_f
                        if pivot == 5:
                            penalty += 40   # 5번 밑으로 엄지를 넘기는 것은 과도한 비틀림
                        elif pivot == 2:
                            penalty += 20   # 2번에서 넘기면 포지션을 낭비한다
                    else:
                        # 오른손: 상행=손가락 증가, 하행=손가락 감소
                        # 왼손: 상행=손가락 감소(5→1 방향), 하행=손가락 증가
                        rh_mismatch = (hand_id == 1 and ((pitch_dir > 0 and c_f < p_f) or (pitch_dir < 0 and c_f > p_f)))
                        lh_mismatch = (hand_id == 0 and ((pitch_dir > 0 and c_f > p_f) or (pitch_dir < 0 and c_f < p_f)))
                        if rh_mismatch or lh_mismatch:
                            penalty += 35

                    # 순차 진행(반음~온음)에서 손가락이 한 칸씩 이동하면 자연스럽다.
                    # 오른손 상행/왼손 하행은 +1, 그 반대는 -1 방향이 자연스러운 진행이며,
                    # 이 보상이 쌓여야 1-2-3 을 거친 뒤 엄지를 넘기는 표준 음계 운지가 된다.
                    if abs(pitch_dir) <= 2:
                        natural = 1 if ((hand_id == 1) == (pitch_dir > 0)) else -1
                        if c_f - p_f == natural:
                            penalty -= 20

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
        t_now = chord_times[c_idx]
        prev_states = dp[c_idx-1]
        curr_states = {}

        # 이전 상태별로 점유 집합을 한 번만 갱신해 재사용
        advanced = {}
        for (prev_f, prev_held) in prev_states:
            key = (prev_f, prev_held)
            advanced[key] = advance_held(prev_held, c_idx - 1, prev_f, t_now, c_idx)

        for curr_f in get_combinations(len(curr_chord)):
            for prev_state, (prev_c, _) in prev_states.items():
                prev_f, _prev_held = prev_state
                held_now = advanced[prev_state]
                cost = (prev_c
                        + calc_transition_cost(prev_chord, prev_f, curr_chord, curr_f)
                        + occupancy_penalty(curr_chord, curr_f, held_now))
                state = (curr_f, held_now)
                known = curr_states.get(state)
                if known is None or cost < known[0]:
                    curr_states[state] = (cost, prev_state)

        # 빔 가지치기: 비용 상위 DP_BEAM_WIDTH 개만 유지해 상태 폭발을 막는다.
        # 점유 집합이 상태에 포함되면서 경로마다 서로 다른 상태가 생기므로,
        # 제한하지 않으면 긴 곡에서 상태 수가 급격히 늘어난다.
        if len(curr_states) > DP_BEAM_WIDTH:
            kept = sorted(curr_states.items(), key=lambda kv: kv[1][0])[:DP_BEAM_WIDTH]
            curr_states = dict(kept)

        dp.append(curr_states)

    # 역추적
    state = min(dp[-1], key=lambda k: dp[-1][k][0])
    for i in range(len(chord_sequence) - 1, -1, -1):
        curr_f = state[0]
        for j, finger in enumerate(curr_f):
            if j < len(chord_sequence[i]):
                chord_sequence[i][j].finger = finger
        state = dp[i][state][1]

def _instant_violation(held, hand_id):
    """이 순간의 점유 집합이 물리 제약을 위반하는가 (C1 유일 / C2 범위 / C3 순서)."""
    items = sorted(((n.pitch, n.finger) for n in held))
    fingers = [f for _, f in items]
    if len(set(fingers)) != len(fingers):
        return True
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            limit = MAX_SPAN.get(tuple(sorted((items[a][1], items[b][1]))), 12)
            if items[b][0] - items[a][0] > limit:
                return True
    # 엄지(1번)는 순서 판정에서 제외 — 엄지 넘기기는 정상 주법이다 (위 주석 참조)
    others = [f for f in fingers if f != 1]
    for k in range(len(others) - 1):
        if hand_id == 1 and others[k] >= others[k + 1]:
            return True
        if hand_id == 0 and others[k] <= others[k + 1]:
            return True
    return False

def resolve_instant_conflicts(all_notes):
    """순간 단위 물리 제약 위반을 해소한다 (설계안 11번 문서 4단계).

    DP(3단계)는 운지 배정만 바꿀 수 있어, 그 순간의 음표 집합 자체가 연주 불가능한
    경우에는 손을 쓸 수 없다. 실측상 위반의 81.6% 가 그런 경우였다.
    여기서는 '무엇을 눌러야 하는가' 자체를 조정한다.

    처리 순서 (음악적 손실이 적은 것부터):
      1) 점유 단축 — 앞서 눌린 음의 건반을 지금 뗀다. 연주자가 실제로 하는 동작이며
         페달이 눌려 있으면 소리도 유지되므로 손실이 없다.
      2) 소리 희생을 동반한 단축 — 페달이 없으면 건반을 떼는 순간 소리도 끊긴다.
         연주 불가 상태를 유지하는 것보다는 낫다고 보고 허용하되 별도로 집계한다.
      3) drop — 동시에 타건되는 음끼리 충돌해 단축으로 풀 수 없을 때. 성부 중요도가
         낮은 음(INNER → BASS → MELODY)부터 버리며, 버린 사실을 반드시 보고한다.

    점유 단축은 이후 시점의 점유 집합을 줄이기만 하므로 새로운 위반을 만들지 않는다.
    따라서 온셋을 시간순으로 한 번만 훑으면 충분하다.
    """
    stats = {"released": 0, "released_cutting_sound": 0, "sound_cut_ms": 0.0,
             "dropped": 0, "unresolved": 0, "drop_examples": []}

    for hand_id in (0, 1):
        notes = sorted((n for n in all_notes if n.hand == hand_id and n.finger),
                       key=lambda n: n.start_ms)
        if not notes:
            continue
        for t in sorted({n.start_ms for n in notes}):
            held = [n for n in notes
                    if not n.dropped and n.start_ms <= t
                    and n.start_ms + max(n.key_hold_ms, 1e-9) > t + OCCUPANCY_TOL_MS]

            guard = 0
            while len(held) >= 2 and _instant_violation(held, hand_id) and guard < 10:
                guard += 1
                # 단축으로 풀 수 있으려면 '이미 충분히 눌려 있던' 음이어야 한다.
                # 타건 후 MIN_STRIKE_HOLD_MS 도 지나지 않은 음을 떼는 것은 물리적으로
                # 불가능하므로(누르고 떼는 동작 자체에 시간이 든다), 그런 음은
                # 사실상 동시 타건으로 보고 아래 drop 경로로 보낸다.
                carried = [n for n in held
                           if t - n.start_ms >= min(MIN_STRIKE_HOLD_MS, n.duration_ms)]

                if carried:
                    # 1·2) 지금 타건되는 음들의 음역에서 가장 먼 '유지음'을 뗀다
                    fresh = [n.pitch for n in held if n not in carried]  # 방금 눌린 음들
                    center = (sum(fresh) / len(fresh) if fresh
                              else sum(n.pitch for n in held) / len(held))
                    victim = max(carried, key=lambda n: (abs(n.pitch - center), n.start_ms))
                    new_hold = max(0.0, t - victim.start_ms)
                    if new_hold < victim.required_hold_ms - OCCUPANCY_TOL_MS:
                        stats["released_cutting_sound"] += 1
                        stats["sound_cut_ms"] += victim.required_hold_ms - new_hold
                    victim.key_hold_ms = new_hold
                    stats["released"] += 1
                else:
                    # 3) 전부 동시 타건 → 단축으로 풀 수 없으므로 버린다
                    priority = {"INNER": 0, "BASS": 1, "MELODY": 2}
                    center = sum(n.pitch for n in held) / len(held)
                    victim = min(held, key=lambda n: (priority.get(n.role, 0),
                                                      -abs(n.pitch - center)))
                    victim.dropped = True
                    stats["dropped"] += 1
                    if len(stats["drop_examples"]) < 5:
                        stats["drop_examples"].append(
                            f"{'왼손' if hand_id == 0 else '오른손'} "
                            f"t={t:.0f}ms pitch={victim.pitch} ({victim.role}) "
                            f"점유={[n.pitch for n in held]}")

                held = [n for n in held if not n.dropped
                        and n.start_ms + max(n.key_hold_ms, 1e-9) > t + OCCUPANCY_TOL_MS]

            if len(held) >= 2 and _instant_violation(held, hand_id):
                stats["unresolved"] += 1

    return stats

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
    split_report = {}
    hand_chords = split_wide_chords_between_hands(
        parse_midi_to_hand_chords(file_path), report=split_report)
    if split_report.get("dropped"):
        print(f"  [경고] 양손 어디에도 배정할 수 없어 제외한 음표 "
              f"{split_report['dropped']}개 (편곡이 두 손 연주 범위를 넘음)")
        for ex in split_report["examples"]:
            print(f"    [제외] {ex}")
    # 5음 초과 화음은 _trim_chord로 줄인 결과를 그대로 보관한다.
    # (기존에는 DP 내부에서만 잘라, 잘려나간 음표가 finger=0 으로 JSON에 새어나갔음)
    # DP 가 점유 제약을 평가하려면 required_hold 가 먼저 있어야 한다 (설계안 3.3절)
    pedal_spans = parse_pedal_spans(file_path)
    compute_required_hold(
        [n for h in [0, 1] for chord in hand_chords[h] for n in chord], pedal_spans)

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
    compute_required_hold(all_notes, pedal_spans)
    clipped = apply_key_hold_and_pedal(all_notes, pedal_spans)
    print(f"  페달 구간 {len(pedal_spans)}개 / 손가락 점유 보정 {clipped}건")

    # 순간 단위 충돌 해소 (4단계)
    rs = resolve_instant_conflicts(all_notes)
    print(f"  순간 충돌 해소: 점유 단축 {rs['released']}건"
          f" (소리 희생 {rs['released_cutting_sound']}건, {rs['sound_cut_ms']/1000:.1f}s)"
          f" / 음표 제외 {rs['dropped']}개 / 미해결 {rs['unresolved']}시점")
    for ex in rs["drop_examples"]:
        print(f"    [제외] {ex}")

    final_notes = []
    for h in [0, 1]:
        for group in hand_chords[h]:
            group = [n for n in group if not n.dropped]   # 4단계에서 제외된 음표
            if not group:
                continue
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
