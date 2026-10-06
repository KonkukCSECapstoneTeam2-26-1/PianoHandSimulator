"""기준 코퍼스 회귀 테스트 — 연주 가능한 입력에서 위반이 0인지 검증.

기존 테스트 코퍼스(게임 음악 MIDI)는 애초에 두 손으로 연주할 수 없는 구간이 많아,
측정된 위반이 '엔진 결함'인지 '입력 자체가 불가능'인지 구분할 수 없었다
(실측: 위반 시점의 81.6%가 어떤 손가락 조합으로도 해가 없음).

본 테스트는 두 단계로 동작한다.

  1단계 — 기준 코퍼스가 정말로 연주 가능한지 **엔진을 거치지 않고** 독립 검증한다.
          이 단계가 실패하면 기준 자체가 틀린 것이므로 생성기를 고쳐야 한다.
  2단계 — 엔진을 돌려 순간 단위 위반을 센다. 입력이 연주 가능함이 보장되었으므로
          **여기서 나온 위반은 전부 엔진 결함**이며 목표값은 0이다.

실행: python tests/test_reference_corpus.py
"""
import contextlib
import io
import os
import sys
from itertools import combinations

import mido

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../v5_polyphonic")))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../tools")))

import piano_fingering_engine as engine  # noqa: E402

REF_DIR = os.path.abspath(os.path.join(BASE_DIR, "../assets/midi/reference"))
OCCUPANCY_TOL_MS = 1.0


def has_valid_assignment(pitches, hand):
    """이 pitch 집합을 한 손으로 짚을 수 있는 손가락 조합이 존재하는가.

    hand: 1=오른손(피치 오름차순 ↔ 손가락 오름차순), 0=왼손(반대)
    """
    uniq = sorted(set(pitches))
    if len(uniq) < 2:
        return True
    if len(uniq) > 5:
        return False
    for combo in combinations(range(1, 6), len(uniq)):
        fingers = combo if hand == 1 else tuple(reversed(combo))
        ok = True
        for a in range(len(uniq)):
            for b in range(a + 1, len(uniq)):
                pair = tuple(sorted((fingers[a], fingers[b])))
                if uniq[b] - uniq[a] > engine.MAX_SPAN.get(pair, 12):
                    ok = False
                    break
            if not ok:
                break
        if ok:
            return True
    return False


def held_sets(notes, hand, hold_of):
    """해당 손의 각 온셋 시점에서 동시에 점유 중인 음표 집합을 순서대로 반환."""
    hand_notes = [n for n in notes if n["hand"] == hand]
    for t in sorted({n["start"] for n in hand_notes}):
        held = [n for n in hand_notes
                if n["start"] <= t and n["start"] + max(hold_of(n), 1e-9) > t + OCCUPANCY_TOL_MS]
        if len(held) >= 2:
            yield t, held


def load_reference(path):
    """기준 MIDI 를 트랙 이름 기준으로 읽어 (음표, 페달 구간) 반환 — 엔진 비의존."""
    mid = mido.MidiFile(path)
    tick_to_ms = engine._make_tick_to_ms(engine._build_tempo_map(mid), mid.ticks_per_beat)

    notes, pedal_events = [], []
    for track in mid.tracks:
        lowered = track.name.lower()
        hand = 1 if "right" in lowered else (0 if "left" in lowered else None)
        tick, active = 0, {}
        for msg in track:
            tick += msg.time
            if msg.type == "control_change" and msg.control == 64:
                pedal_events.append((tick, msg.value))
            elif msg.type == "note_on" and msg.velocity > 0:
                active.setdefault(msg.note, []).append(tick)
            elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
                pending = active.get(msg.note)
                if pending and hand is not None:
                    start = pending.pop(0)
                    notes.append({"hand": hand, "pitch": msg.note,
                                  "start": tick_to_ms(start),
                                  "duration": tick_to_ms(tick) - tick_to_ms(start)})

    pedal_events.sort()
    spans, down_at = [], None
    for tick, value in pedal_events:
        t = tick_to_ms(tick)
        if value >= 64 and down_at is None:
            down_at = t
        elif value < 64 and down_at is not None:
            spans.append((down_at, t))
            down_at = None
    return notes, spans


def required_hold(note, spans):
    """페달을 고려한 최소 필수 점유 (엔진 구현과 동일한 정의, 독립 계산)."""
    start = note["start"]
    end = start + note["duration"]
    up_sup, cursor = start, start
    for a, b in sorted(spans):
        if b <= start or a >= end:
            continue
        if a > cursor:
            up_sup = a
        cursor = max(cursor, b)
    if cursor < end:
        up_sup = end
    return max(up_sup - start, min(engine.MIN_STRIKE_HOLD_MS, note["duration"]))


def verify_playable(path):
    """1단계 — 기준 곡이 연주 가능한지 독립 검증. (동시타건 시점 수, 불가 시점 수)"""
    notes, spans = load_reference(path)
    hold_of = lambda n: required_hold(n, spans)  # noqa: E731
    instants = impossible = 0
    for hand in (0, 1):
        for _t, held in held_sets(notes, hand, hold_of):
            instants += 1
            if not has_valid_assignment([n["pitch"] for n in held], hand):
                impossible += 1
    return instants, impossible


def engine_violations(path):
    """2단계 — 엔진 결과의 순간 단위 위반 수. (시점, span위반, 중복, 순서위반)"""
    with contextlib.redirect_stdout(io.StringIO()):
        hand_chords = engine.split_wide_chords_between_hands(
            engine.parse_midi_to_hand_chords(path))
        spans = engine.parse_pedal_spans(path)
        notes0 = [n for h in (0, 1) for c in hand_chords[h] for n in c]
        engine.compute_required_hold(notes0, spans)
        for h in (0, 1):
            hand_chords[h] = [engine._trim_chord(c, h) for c in hand_chords[h]]
            engine.solve_fingering_chord_dp(hand_chords[h], h)
        notes = [n for h in (0, 1) for c in hand_chords[h] for n in c]
        engine.compute_required_hold(notes, spans)
        engine.apply_key_hold_and_pedal(notes, spans)

    records = [{"hand": n.hand, "pitch": n.pitch, "finger": n.finger,
                "start": n.start_ms, "hold": n.key_hold_ms} for n in notes]
    instants = span_bad = dup_bad = mono_bad = 0
    for hand in (0, 1):
        for _t, held in held_sets(records, hand, lambda n: n["hold"]):
            instants += 1
            held = sorted(held, key=lambda n: (n["pitch"], n["finger"]))
            for a in range(len(held)):
                for b in range(a + 1, len(held)):
                    pair = tuple(sorted((held[a]["finger"], held[b]["finger"])))
                    if held[b]["pitch"] - held[a]["pitch"] > engine.MAX_SPAN.get(pair, 12):
                        span_bad += 1
                        break
                else:
                    continue
                break
            fingers = [n["finger"] for n in held]
            if len(set(fingers)) != len(fingers):
                dup_bad += 1
            ordered = (all(fingers[k] < fingers[k + 1] for k in range(len(fingers) - 1))
                       if hand == 1 else
                       all(fingers[k] > fingers[k + 1] for k in range(len(fingers) - 1)))
            if not ordered:
                mono_bad += 1
    return instants, span_bad, dup_bad, mono_bad


def main():
    if not os.path.isdir(REF_DIR):
        print("기준 코퍼스가 없습니다. 먼저 생성하세요:")
        print("  python tools/make_reference_corpus.py")
        return 1

    files = sorted(f for f in os.listdir(REF_DIR) if f.lower().endswith((".mid", ".midi")))
    if not files:
        print("기준 코퍼스가 비어 있습니다. python tools/make_reference_corpus.py")
        return 1

    print("[1단계] 기준 코퍼스 연주 가능성 — 엔진 비의존 독립 검증")
    print("{:30s} {:>8s} {:>10s}  판정".format("곡", "동시타건", "연주불가"))
    print("-" * 62)
    failures = []
    for name in files:
        instants, impossible = verify_playable(os.path.join(REF_DIR, name))
        ok = impossible == 0
        print("{:30s} {:8d} {:10d}  {}".format(
            name[:29], instants, impossible, "PASS" if ok else "FAIL"))
        if not ok:
            failures.append("{}: 기준 곡 자체가 연주 불가 {}시점 — 생성기 수정 필요"
                            .format(name, impossible))

    print()
    print("[2단계] 엔진 결과 순간 단위 위반 — 입력이 연주 가능하므로 목표는 0")
    print("{:30s} {:>6s} {:>6s} {:>6s} {:>6s}  판정".format("곡", "시점", "범위", "중복", "순서"))
    print("-" * 66)
    for name in files:
        instants, span_bad, dup_bad, mono_bad = engine_violations(os.path.join(REF_DIR, name))
        total = span_bad + dup_bad + mono_bad
        print("{:30s} {:6d} {:6d} {:6d} {:6d}  {}".format(
            name[:29], instants, span_bad, dup_bad, mono_bad, "PASS" if total == 0 else "FAIL"))
        if total:
            failures.append("{}: 엔진 위반 {}건 (연주 가능한 입력이므로 엔진 결함)"
                            .format(name, total))

    print("-" * 66)
    print("FAIL {}건".format(len(failures)))
    for f in failures:
        print("  - " + f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
