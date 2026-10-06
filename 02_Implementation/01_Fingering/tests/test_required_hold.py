"""페달 기반 '필수 점유 구간'(required_hold) 검증 테스트.

소리는 건반 또는 Sustain 페달 중 하나가 유지한다. 따라서 건반은 발음 구간 중
페달이 떠 있는 동안에만 눌려 있으면 되고, 페달이 눌린 뒤로는 떼도 된다.

    required_hold = (발음 구간 안에서 페달이 떠 있는 마지막 시점) − start

이 값은 MIDI 음표와 CC64 만으로 결정되어 운지와 무관하므로, DP 가 시작 전에
"어떤 음표들이 반드시 함께 눌려 있어야 하는가"를 알 수 있게 한다.
(설계안 01_Design/11_Temporal_Constraint_Design.md 3.3절 / 2단계)

실행: python tests/test_required_hold.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../v5_polyphonic")))

import piano_fingering_engine as engine  # noqa: E402

TOL = 1e-6

# (이름, 페달 구간, (start, duration), 기대 required_hold)
CASES = [
    ("페달 없음 → 발음 구간 전체를 눌러야 함",
     [], (0, 1000), 1000),
    ("페달이 음표 내내 눌려 있음 → 최소 타건 시간만",
     [(0, 2000)], (0, 1000), engine.MIN_STRIKE_HOLD_MS),
    ("페달이 300ms 에 ON → 그때까지만 점유",
     [(300, 2000)], (0, 1000), 300),
    ("페달이 음표 끝 전에 OFF → 끝까지 점유해야 함",
     [(100, 800)], (0, 1000), 1000),
    ("페달이 음표 시작 전에 끝남 → 전 구간 점유",
     [(0, 50)], (100, 900), 900),
    ("페달 구간 둘 사이에 틈 → 마지막 틈이 끝나는 시점까지",
     [(100, 300), (500, 2000)], (0, 1000), 500),
    ("발음 구간이 최소 타건 시간보다 짧음 → duration 이 상한",
     [(0, 2000)], (0, 20), 20),
    ("페달이 음표가 끝난 뒤 시작 → 전 구간 점유",
     [(1500, 2000)], (0, 1000), 1000),
    ("겹치는 페달 구간이 병합되어 처리됨",
     [(200, 600), (400, 2000)], (0, 1000), 200),
]


def make_note(start, duration):
    return engine.NoteEvent(60, 80, float(start), float(duration), 1)


def check_invariants(path_notes):
    """실데이터 불변식: min(30, dur) ≤ required_hold ≤ duration."""
    bad = []
    for n in path_notes:
        lower = min(engine.MIN_STRIKE_HOLD_MS, n.duration_ms)
        if not (lower - TOL <= n.required_hold_ms <= n.duration_ms + TOL):
            bad.append(n)
    return bad


def main():
    print(f"{'케이스':46s} {'기대':>8s} {'실제':>8s}  판정")
    print("-" * 78)
    failures = []
    for name, spans, (start, duration), want in CASES:
        note = make_note(start, duration)
        engine.compute_required_hold([note], spans)
        got = note.required_hold_ms
        ok = abs(got - want) < TOL
        print(f"{name[:45]:46s} {want:8.1f} {got:8.1f}  {'PASS' if ok else 'FAIL'}")
        if not ok:
            failures.append(name)

    # 실데이터 불변식 검사
    midi_dir = os.path.abspath(os.path.join(BASE_DIR, "../assets/midi"))
    checked = 0
    if os.path.isdir(midi_dir):
        for fname in sorted(os.listdir(midi_dir)):
            if not fname.lower().endswith((".mid", ".midi")):
                continue
            path = os.path.join(midi_dir, fname)
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                hand_chords = engine.parse_midi_to_hand_chords(path)
                spans = engine.parse_pedal_spans(path)
            notes = [n for h in (0, 1) for c in hand_chords[h] for n in c]
            engine.compute_required_hold(notes, spans)
            bad = check_invariants(notes)
            checked += len(notes)
            if bad:
                failures.append(f"{fname}: 불변식 위반 {len(bad)}건")
                print(f"{fname[:45]:46s} {'-':>8s} {'-':>8s}  FAIL ({len(bad)}건)")

    print("-" * 78)
    print(f"합성 케이스 {len(CASES)}건 · 실데이터 음표 {checked}개 불변식 검사")
    print(f"FAIL {len(failures)}건")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
