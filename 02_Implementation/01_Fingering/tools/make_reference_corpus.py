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


PIECES = [piece_five_finger, piece_block_chords, piece_alberti,
          piece_pedal_arpeggio, piece_sustained_bass, piece_position_shift,
          piece_inner_voice, piece_scale]


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
