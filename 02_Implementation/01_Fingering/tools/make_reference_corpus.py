"""연주 가능함이 보장된 기준 MIDI 코퍼스 생성기.

기존 테스트 코퍼스(게임 음악 MIDI 중심)는 애초에 두 손으로 연주할 수 없는 구간이
많아, 측정된 위반이 '엔진 결함'인지 '입력 자체가 불가능'인지 구분할 수 없었다.
(실측: 위반 시점의 81.6%가 어떤 손가락 조합으로도 해가 없음)

본 생성기는 각 순간에 한 손이 점유하는 음표 집합이 반드시 유효한 손가락 배정을
가지도록 구성한 곡을 만든다. 따라서 이 코퍼스에서 나온 위반은 전부 엔진 결함이며
목표값은 명확히 0이다.

엔진의 제약 모델을 전제로 한다.
  - 한 손 5손가락, 손가락 쌍별 MAX_SPAN
  - pitch 순서와 손가락 번호 순서가 단조 (엄지 넘기기 미지원)
따라서 '사람은 칠 수 있지만 이 모델로는 표현 불가'한 2옥타브 스케일 등은 넣지 않는다.

실행: python tools/make_reference_corpus.py
출력: assets/midi/reference/*.mid  (Format 1, track0=메타, track1=오른손, track2=왼손)
"""
import os
import sys

import mido

TPB = 480                 # ticks per beat
TEMPO = 500000            # us/beat = 120 BPM

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath(os.path.join(BASE_DIR, "../assets/midi/reference"))


class Piece:
    """음표와 페달 이벤트를 모아 Format 1 MIDI로 쓴다."""

    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.right = []    # (start_tick, dur_tick, pitch, velocity)
        self.left = []
        self.pedal = []    # (tick, value)

    def add(self, hand, start_beat, dur_beat, pitch, velocity=80):
        target = self.right if hand == "R" else self.left
        target.append((int(start_beat * TPB), int(dur_beat * TPB), pitch, velocity))

    def pedal_down(self, beat):
        self.pedal.append((int(beat * TPB), 127))

    def pedal_up(self, beat):
        self.pedal.append((int(beat * TPB), 0))

    def _track(self, notes, track_name, pedal=None):
        events = []
        for start, dur, pitch, vel in notes:
            events.append((start, 1, mido.Message("note_on", note=pitch, velocity=vel)))
            events.append((start + dur, 0, mido.Message("note_off", note=pitch, velocity=0)))
        for tick, value in (pedal or []):
            events.append((tick, 0, mido.Message("control_change", control=64, value=value)))
        # 같은 tick 에서는 note_off / CC 를 note_on 보다 먼저 처리
        events.sort(key=lambda e: (e[0], e[1]))

        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=track_name, time=0))
        prev = 0
        for tick, _order, msg in events:
            msg.time = tick - prev
            prev = tick
            track.append(msg)
        return track

    def write(self, out_dir):
        mid = mido.MidiFile(type=1, ticks_per_beat=TPB)
        meta = mido.MidiTrack()
        meta.append(mido.MetaMessage("track_name", name=self.name, time=0))
        meta.append(mido.MetaMessage("set_tempo", tempo=TEMPO, time=0))
        meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
        mid.tracks.append(meta)
        # 페달은 오른손 트랙에 실어 둔다 (양손 공용 — 파서는 전 트랙을 훑는다)
        mid.tracks.append(self._track(self.right, "Piano right", self.pedal))
        mid.tracks.append(self._track(self.left, "Piano left"))

        path = os.path.join(out_dir, self.name + ".mid")
        mid.save(path)
        return path, len(self.right) + len(self.left)


# 공통 원칙: 한 손이 동시에 점유하는 음은 5음 이하이며 손가락 쌍 간격이 한계 내.

def piece_five_finger():
    """고정 5지 포지션 - 양손이 각자 5음 범위를 벗어나지 않는 단선율."""
    p = Piece("ref_01_five_finger", "양손 고정 5지 포지션, 단선율 교대")
    rh = [60, 62, 64, 65, 67, 65, 64, 62]       # C4~G4
    lh = [48, 50, 52, 53, 55, 53, 52, 50]       # C3~G3
    t = 0.0
    for _ in range(4):
        for k, pitch in enumerate(rh):
            p.add("R", t + k * 0.5, 0.45, pitch)
        for k, pitch in enumerate(lh):
            p.add("L", t + k * 0.5, 0.45, pitch)
        t += 4.0
    return p


def piece_block_chords():
    """블록 화음 - 3화음만 사용. 각 화음은 5지 범위 내이고 화음끼리 겹치지 않는다."""
    p = Piece("ref_02_block_chords", "3화음 블록, 페달 없음")
    chords_r = [(60, 64, 67), (62, 65, 69), (64, 67, 71), (60, 64, 67)]
    chords_l = [(48, 52, 55), (50, 53, 57), (52, 55, 59), (48, 52, 55)]
    t = 0.0
    for i in range(6):
        for pitch in chords_r[i % len(chords_r)]:
            p.add("R", t, 0.9, pitch)
        for pitch in chords_l[i % len(chords_l)]:
            p.add("L", t, 0.9, pitch)
        t += 1.0
    return p


def piece_alberti():
    """알베르티 베이스 - 왼손 분산 반주(5지 범위), 오른손 선율."""
    p = Piece("ref_03_alberti", "알베르티 베이스 + 단선율 멜로디")
    alberti = [48, 55, 52, 55]                 # C3 G3 E3 G3 (5지 범위 내)
    melody = [67, 65, 64, 62, 60, 62, 64, 65]
    t = 0.0
    for bar in range(6):
        for k in range(8):
            p.add("L", t + k * 0.25, 0.22, alberti[k % 4])
        p.add("R", t, 0.95, melody[(bar * 2) % len(melody)])
        p.add("R", t + 1.0, 0.95, melody[(bar * 2 + 1) % len(melody)])
        t += 2.0
    return p


def piece_pedal_arpeggio():
    """페달 아르페지오 - duration 은 서로 겹치지만 페달이 소리를 유지한다.

    페달을 고려하지 않으면 한 손이 2옥타브를 동시에 짚어야 하므로 연주 불가다.
    required_hold 를 올바로 쓰면 각 건반은 다음 음 전에 떨어지므로 연주 가능하다.
    페달 처리 메커니즘을 직접 겨냥한 곡이다.
    """
    p = Piece("ref_04_pedal_arpeggio", "페달로 유지되는 아르페지오 (required_hold 검증용)")
    t = 0.0
    for bar in range(4):
        root = [60, 65, 67, 60][bar]
        notes = [root, root + 4, root + 7, root + 12, root + 7, root + 4]
        p.pedal_down(t)
        for k, pitch in enumerate(notes):
            # 소리는 마디 끝까지 이어지지만(페달), 손가락은 다음 음 전에 뗀다
            p.add("R", t + k * 0.25, 2.0 - k * 0.25, pitch)
        bass = [36, 41, 43, 36][bar]
        p.add("L", t, 1.9, bass)
        p.add("L", t + 1.0, 0.9, bass + 7)
        p.pedal_up(t + 1.95)
        t += 2.0
    return p


def piece_sustained_bass():
    """지속 베이스 + 이동 선율 - 왼손이 길게 누른 상태에서 오른손이 움직인다.

    왼손 베이스는 페달 구간에 들어 있어 손가락을 떼도 소리가 유지된다.
    점유가 여러 화음에 걸치는 상황을 만든다.
    """
    p = Piece("ref_05_sustained_bass", "페달 하 지속 베이스 + 이동 선율")
    melody = [72, 71, 69, 67, 69, 71, 72, 74]
    t = 0.0
    for bar in range(4):
        p.pedal_down(t)
        p.add("L", t, 3.8, [36, 38, 41, 43][bar])        # 길게 울리는 베이스
        p.add("L", t + 2.0, 1.8, [43, 45, 48, 50][bar])
        for k in range(8):
            p.add("R", t + k * 0.5, 0.45, melody[(bar * 2 + k) % len(melody)])
        p.pedal_up(t + 3.95)
        t += 4.0
    return p


def piece_position_shift():
    """포지션 이동 - 쉼표로 분리된 서로 다른 5지 포지션."""
    p = Piece("ref_06_position_shift", "쉼표로 분리된 5지 포지션 이동")
    positions_r = [60, 67, 72, 65]
    positions_l = [48, 43, 36, 41]
    t = 0.0
    for i in range(6):
        base_r = positions_r[i % len(positions_r)]
        base_l = positions_l[i % len(positions_l)]
        for k, step in enumerate([0, 2, 4, 5, 4, 2]):
            p.add("R", t + k * 0.25, 0.22, base_r + step)
            p.add("L", t + k * 0.25, 0.22, base_l + step)
        t += 2.0          # 뒤쪽 공백 = 포지션 이동 시간
    return p


def piece_inner_voice():
    """내성 유지 - 페달 없이 손가락으로 한 음을 길게 누른 채 다른 음이 움직인다.

    페달이 없으므로 required_hold == duration 이고, 유지음의 점유가 후속 화음까지
    실제로 걸친다. 3단계 DP 의 점유 상태 확장이 겨냥한 바로 그 상황이며,
    유지음과 이동음이 항상 한 손 범위 안에 있도록 구성해 연주 가능성을 보장한다.

    오른손: C5(72)를 2박 유지 + 그 아래 E4~G4 가 이동 (최대 간격 12반음)
    왼손  : C3(48)를 2박 유지 + 그 위 G3~B3 가 이동 (최대 간격 11반음)
    """
    p = Piece("ref_07_inner_voice", "페달 없이 유지되는 내성 (점유 상태 검증용)")
    t = 0.0
    for bar in range(5):
        # 오른손: 상성 유지음 + 하성 이동
        p.add("R", t, 1.9, 72)
        for k, pitch in enumerate([64, 65, 67, 65]):
            p.add("R", t + k * 0.5, 0.45, pitch)
        # 왼손: 하성 유지음 + 상성 이동
        p.add("L", t, 1.9, 48)
        for k, pitch in enumerate([55, 57, 59, 57]):
            p.add("L", t + k * 0.5, 0.45, pitch)
        t += 2.0
    return p


def piece_scale():
    """2옥타브 음계 - 엄지 넘기기(thumb-under)가 반드시 필요한 곡.

    5지 포지션으로는 5음까지만 칠 수 있으므로, 2옥타브를 이어 치려면 엄지가 다른
    손가락 아래로 지나가야 한다. 음표끼리 시간이 겹치지 않아 물리 제약 자체는
    자명하게 만족하며, 이 곡의 관심사는 **운지의 음악적 타당성**이다.
    (표준 운지: 오른손 상행 1-2-3-1-2-3-4-5, 왼손 상행 5-4-3-2-1-3-2-1)
    """
    p = Piece("ref_08_scale", "2옥타브 다장조 음계 (엄지 넘기기 검증용)")
    major = [0, 2, 4, 5, 7, 9, 11]
    up_r = [60 + 12 * o + st for o in range(2) for st in major] + [84]
    up_l = [36 + 12 * o + st for o in range(2) for st in major] + [60]
    seq_r = up_r + up_r[-2::-1]        # 상행 후 하행
    seq_l = up_l + up_l[-2::-1]
    for k, pitch in enumerate(seq_r):
        p.add("R", k * 0.25, 0.22, pitch)
    for k, pitch in enumerate(seq_l):
        p.add("L", k * 0.25, 0.22, pitch)
    return p


# ── 코스트 구조 압박용 (13_Cost_Function_Design.md 5.4) ────────────────────
# 기존 8곡은 짧고 쉬워 가산 코스트의 교환 현상을 재현하지 못한다. 아래 네 곡은
# 곡을 길게 하고 선호도 항(흑건 엄지, 손목 이동)을 반복 누적시켜 압박한다.
# 모두 한 손 점유 집합에 유효한 손가락 배정이 존재하도록 구성했다.

def piece_long_inner_voice():
    """ref_09 — 긴 내성 유지. 점유가 계속 겹치면서 선호도가 길게 누적된다.

    ref_07 과 같은 구조이되 40마디로 늘리고, 이동음이 흑건을 자주 지나도록 했다.
    유지음(1번 또는 5번 고정)과 이동음 사이 간격은 항상 MAX_SPAN 안이다.
      오른손: C5(72) 유지 + 그 아래 E4~A4(64~69) 이동  → 최대 8반음, (1,5)=17 이내
      왼손  : C3(48) 유지 + 그 위 G3~C4(55~60) 이동     → 최대 12반음, (1,5)=17 이내
    """
    p = Piece("ref_09_long_inner_voice",
              "긴 내성 유지 (40마디) — 점유 누적과 선호도 누적을 동시에")
    move_r = [64, 66, 67, 69, 67, 66, 64, 65]    # 흑건 66 포함
    move_l = [55, 57, 58, 60, 58, 57, 55, 56]    # 흑건 58, 56 포함
    t = 0.0
    for bar in range(40):
        p.add("R", t, 1.9, 72)
        p.add("L", t, 1.9, 48)
        for k in range(4):
            p.add("R", t + k * 0.5, 0.45, move_r[(bar * 4 + k) % len(move_r)])
            p.add("L", t + k * 0.5, 0.45, move_l[(bar * 4 + k) % len(move_l)])
        t += 2.0
    return p


def piece_black_thumb_trap():
    """ref_10 — 흑건 엄지 비용(+25)이 반복 누적되는 배치.

    각 마디는 흑건 하나와 그 위 백건 넷으로 이뤄진다. 흑건이 가장 낮으므로
    오른손에서는 1번(엄지)이 흑건을 맡는 배정이 자연스럽고, 그때마다 +25 가 붙는다.
    피하려면 포지션을 통째로 올려야 해 손목 이동 비용이 대신 든다.
    두 비용 모두 선호도 항이므로, 60마디 동안 어느 쪽을 고르든 비용이 크게 쌓인다.

    각 화음은 5음이고 1-5 간격이 최대 11반음으로 (1,5)=17 안이다.
    """
    p = Piece("ref_10_black_thumb_trap",
              "흑건 엄지 반복 (60마디) — 선호도 누적 유도")
    # (흑건 시작음, 위 백건 4개 오프셋)
    bases_r = [61, 63, 66, 68, 70]              # C#4 D#4 F#4 G#4 A#4
    offs = [0, 3, 5, 8, 11]
    bases_l = [37, 39, 42, 44, 46]              # 한 옥타브 반 아래
    t = 0.0
    for bar in range(60):
        br = bases_r[bar % len(bases_r)]
        bl = bases_l[bar % len(bases_l)]
        for k, o in enumerate(offs):
            p.add("R", t + k * 0.25, 0.22, br + o)
            p.add("L", t + k * 0.25, 0.22, bl + o)
        t += 1.5
    return p


def piece_position_grind():
    """ref_11 — 포지션 이동이 끊임없이 일어나는 곡.

    POSITION_SHIFT_THRESHOLD(5반음)을 넘는 이동이 마디마다 생기고, 초과분 × 2 가
    가산된다. 쉼표를 두지 않아 손목 이동 비용이 계속 쌓인다.
    각 포지션 안에서는 5지 범위를 넘지 않으므로 연주 가능하다.
    """
    p = Piece("ref_11_position_grind",
              "쉼표 없는 포지션 이동 반복 (80마디) — 손목 이동 비용 누적")
    anchors_r = [60, 72, 64, 76, 67, 79, 62, 74]
    anchors_l = [48, 36, 45, 33, 43, 31, 46, 34]
    steps = [0, 2, 4, 2]
    t = 0.0
    for bar in range(80):
        ar = anchors_r[bar % len(anchors_r)]
        al = anchors_l[bar % len(anchors_l)]
        for k, s in enumerate(steps):
            p.add("R", t + k * 0.25, 0.22, ar + s)
            p.add("L", t + k * 0.25, 0.22, al + s)
        t += 1.0
    return p


def piece_wide_sustain():
    """ref_12 — 넓게 벌어진 화음을 페달로 유지하며 그 사이를 선율이 지난다.

    빔 포화를 노린다. 점유 집합이 커지면 DP 상태가 급격히 늘어 가지치기가 자주 일어나고,
    3.2(무위반 상태가 잘려 나감)가 재현되기 쉽다. ref_04 가 같은 성격이지만 30화음뿐이다.

    오른손 유지 화음은 (60, 71) = 11반음으로 (1,5)=17 안이고, 그 사이 선율 음도
    두 유지음과의 간격이 모두 한계 내다. 페달이 있어 소리는 이어지되 점유는
    key_hold_ms 로 따로 계산된다.
    """
    p = Piece("ref_12_wide_sustain",
              "페달 아래 넓은 유지 화음 + 사이 선율 (50마디) — 빔 포화 유도")
    inner_r = [62, 64, 65, 67, 69, 67, 65, 64]
    inner_l = [50, 52, 53, 55, 57, 55, 53, 52]
    t = 0.0
    for bar in range(50):
        p.pedal_down(t)
        p.add("R", t, 3.8, 60)
        p.add("R", t, 3.8, 71)
        p.add("L", t, 3.8, 36)
        p.add("L", t, 3.8, 47)
        for k in range(8):
            p.add("R", t + 0.5 + k * 0.4, 0.35, inner_r[(bar * 2 + k) % len(inner_r)])
            p.add("L", t + 0.5 + k * 0.4, 0.35, inner_l[(bar * 2 + k) % len(inner_l)])
        p.pedal_up(t + 3.9)
        t += 4.0
    return p


PIECES = [piece_five_finger, piece_block_chords, piece_alberti,
          piece_pedal_arpeggio, piece_sustained_bass, piece_position_shift,
          piece_inner_voice, piece_scale,
          piece_long_inner_voice, piece_black_thumb_trap,
          piece_position_grind, piece_wide_sustain]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("출력 경로: " + OUT_DIR)
    print()
    print("{:28s} {:>5s}  설명".format("파일", "음표"))
    print("-" * 84)
    for build in PIECES:
        piece = build()
        path, count = piece.write(OUT_DIR)
        print("{:28s} {:5d}  {}".format(os.path.basename(path), count, piece.description))
    print("-" * 84)
    print("{}곡 생성 완료".format(len(PIECES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
