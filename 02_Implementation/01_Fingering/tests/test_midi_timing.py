"""MIDI 파싱 타이밍 회귀 테스트.

운지법 엔진이 산출한 음표의 절대 시각(start_ms)을 mido의 템포맵 기준 정답과 비교한다.

검증 항목
  1. 음표 수 일치      — 재타격·미종료 음표가 유실되지 않는지
  2. 타이밍 오차 < 1ms — Format 1에서 템포 트랙(set_tempo)이 음표 트랙에 올바로 적용되는지

실행: python tests/test_midi_timing.py
"""
import os
import sys

import mido

TOLERANCE_MS = 1.0

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MIDI_DIR = os.path.abspath(os.path.join(BASE_DIR, "../assets/midi"))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../v5_polyphonic")))

import piano_fingering_engine as engine  # noqa: E402


def reference_note_starts(path):
    """mido의 템포맵 적용 이터레이션으로 note_on 절대 시각(ms)을 산출 — 정답.

    이 테스트가 보는 것은 **시각 변환**이므로, 음표 집합은 엔진과 같은 기준으로
    맞춘다. 두 단계를 정답에도 적용한다.

      1. 피아노 트랙 자동 선별 (요구사항 2.3) — 타악 채널·효과음 음색 제외 및
         피아노 편곡 판정. 판정 자체는 `tests/test_track_selection.py` 가 따로
         검증하므로, 여기서는 엔진의 선별 함수를 그대로 불러 기준만 공유한다.
      2. 피아노 88키 음역(A0~C8) 밖 음표 제외.

    시각은 mido 의 템포맵 이터레이션으로 독립 산출하므로, 엔진의 tick→ms 변환과
    비교하는 의미는 그대로 유지된다.
    """
    mid = mido.MidiFile(path)
    abs_sec = 0.0
    # mido 의 평탄화 이터레이션은 파일 전체를 시간 순으로 주므로, 채널별 음색을
    # 그대로 따라가면 엔진의 program 귀속(채널 단위·시간 순)과 같은 기준이 된다.
    channel_program = {}
    candidates = []
    for msg in mid:
        abs_sec += msg.time
        if msg.type == "program_change":
            channel_program[msg.channel] = msg.program
        elif msg.type == "note_on" and msg.velocity > 0:
            candidates.append(engine.NoteEvent(
                msg.note, msg.velocity, abs_sec * 1000, 1.0, -1,
                channel=msg.channel,
                program=channel_program.get(msg.channel, 0)))

    selected = engine.select_piano_sources(candidates)
    return sorted(n.start_ms for n in selected
                  if engine.PIANO_MIN_PITCH <= n.pitch <= engine.PIANO_MAX_PITCH)


def engine_note_starts(path):
    hand_chords = engine.parse_midi_to_hand_chords(path)
    return sorted(n.start_ms for h in (0, 1) for chord in hand_chords[h] for n in chord)


def check(path):
    """(통과여부, 음표수, 최대오차ms, 메시지) 반환."""
    expected = reference_note_starts(path)
    actual = engine_note_starts(path)

    if len(expected) != len(actual):
        return False, len(expected), None, f"음표 수 불일치: 정답 {len(expected)} vs 엔진 {len(actual)}"

    max_err = max((abs(a - b) for a, b in zip(expected, actual)), default=0.0)
    if max_err >= TOLERANCE_MS:
        return False, len(expected), max_err, f"타이밍 오차 {max_err:.3f} ms >= {TOLERANCE_MS} ms"
    return True, len(expected), max_err, ""


def main():
    if not os.path.isdir(MIDI_DIR):
        print(f"MIDI 디렉터리를 찾을 수 없음: {MIDI_DIR}")
        return 1

    files = sorted(f for f in os.listdir(MIDI_DIR) if f.lower().endswith((".mid", ".midi")))
    if not files:
        print(f"MIDI 파일이 없음: {MIDI_DIR}")
        return 1

    print(f"{'파일':34s} {'음표':>6s} {'최대오차(ms)':>13s}  판정")
    print("-" * 66)

    failures = []
    for name in files:
        try:
            ok, count, max_err, msg = check(os.path.join(MIDI_DIR, name))
        except Exception as exc:  # 손상 파일 등
            print(f"{name[:33]:34s} {'-':>6s} {'-':>13s}  ERROR {type(exc).__name__}: {exc}")
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            continue

        err_text = f"{max_err:13.5f}" if max_err is not None else f"{'-':>13s}"
        print(f"{name[:33]:34s} {count:6d} {err_text}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append((name, msg))

    print("-" * 66)
    print(f"PASS {len(files) - len(failures)} / FAIL {len(failures)}")
    for name, msg in failures:
        print(f"  - {name}: {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
