"""평가 지표 측정 도구(tools/metrics.py) 검산 테스트.

지표가 "위반 0건"으로 보고될 때, 그것이 실제로 0인지 아니면 계산 코드가
돌지 않은 것인지 구분할 수 없다. 이 테스트는 **위반을 의도적으로 주입한
소형 샘플**을 만들어 각 지표가 그 위반을 정확히 검출하는지(그리고 정상
샘플에서는 0을 보고하는지) 확인한다.

실행: python tests/test_metrics.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../tools")))

import metrics as M  # noqa: E402

BLACK = {1, 3, 6, 8, 10}


def note(pitch, start, dur, hand, finger, role="INNER", yaw=0.0, roll=0.0):
    """결과 JSON 한 원소 생성 (알 수 없는 필드 하나를 섞어 견고성도 함께 검증)."""
    return {
        "pitch": pitch, "start_ms": float(start), "duration_ms": float(dur),
        "hand": hand, "role": role, "finger": finger,
        "pressure": 0.5, "key_depth": 0.5, "is_black": (pitch % 12) in BLACK,
        "wrist_pos_normalized": 0.5, "wrist_yaw_deg": yaw, "wrist_roll_deg": roll,
        "target_x_mm": 123.4,  # 다른 파트가 추가할 수 있는 미지의 필드
    }


def prep(raw_notes):
    notes = [M.Note(r, i) for i, r in enumerate(raw_notes)]
    return notes, M.group_chords(notes)


# ── 기준 샘플: 위반이 하나도 없어야 하는 정상 데이터 ──────────────
def sample_clean():
    """오른손 C-E-G 화음(f1/f3/f5) + 왼손 단음 하행, 중첩·초과 없음."""
    return [
        # 오른손 화음 3음: 60(f1) 64(f3) 67(f5) — 간격 4,3 (MAX_SPAN 1-3=14, 3-5=10 OK)
        note(60, 0, 400, "Right", 1), note(64, 5, 400, "Right", 3),
        note(67, 10, 400, "Right", 5, role="MELODY"),
        # 오른손 단음 상행: 손가락도 상행 (아르페지오 방향 일치)
        note(69, 500, 200, "Right", 2, role="MELODY"),
        note(71, 750, 200, "Right", 4, role="MELODY"),
        # 왼손 단음 하행: 손가락 상행 (왼손 규칙상 일치)
        note(48, 0, 400, "Left", 2, role="BASS"),
        note(45, 500, 200, "Left", 4, role="BASS"),
        note(43, 750, 200, "Left", 5, role="BASS"),
    ]


def run_all(raw):
    """모든 하드 지표를 한 번에 계산해 dict로 반환."""
    notes, chords = prep(raw)
    span_bad, span_total, _ = M.check_max_span(chords, adjacent_only=True)
    span2_bad, span2_total, _ = M.check_max_span(chords, adjacent_only=False)
    mono_bad, mono_total, _ = M.check_monotonicity(chords)
    conf_bad, conf_edge, _, _ = M.check_simultaneous_conflict(notes)
    dup_bad, _, _ = M.check_duplicate_in_chord(chords)
    un_bad, _ = M.check_unassigned(notes)
    yaw_bad, roll_bad, _, _, _ = M.check_rom(notes)
    rep, _ = M.single_note_runs(chords)
    arp, _, _ = M.arpeggio_mismatch(chords)
    hs = M.hand_separation(chords)
    i_span, i_dup, i_key, i_mono, i_inst, _ = M.check_instant_constraints(notes)
    return {
        "A7_span": i_span, "A8_dup": i_dup, "A8b_key": i_key,
        "A9_mono": i_mono, "A_instants": i_inst,
        "A1_span": span_bad, "A1_pairs": span_total,
        "A1b_span": span2_bad, "A1b_pairs": span2_total,
        "A2_mono": mono_bad, "A2_pairs": mono_total,
        "A3_conflict": conf_bad, "A3_edge": conf_edge,
        "A4_dup": dup_bad, "A5_unassigned": un_bad,
        "A6_yaw": yaw_bad, "A6_roll": roll_bad,
        "B9_repeat": rep, "B10_arp": arp, "B11_cross": hs["cross"],
        "notes": len(notes), "chords": sum(len(g) for g in chords.values()),
    }


# ── 각 케이스: (이름, 샘플 생성 함수, 기대값 dict) ────────────────
def case_clean():
    return sample_clean()


def case_span():
    """A1: 오른손 화음에서 f3-f5 간격을 10 → 13반음으로 늘려 초과 유발."""
    raw = sample_clean()
    raw[2]["pitch"] = 77  # 64(f3) → 77(f5): 13 > MAX_SPAN[(3,5)]=10
    return raw


def case_span_nonadjacent():
    """A1b: 인접 쌍은 모두 통과하지만 비인접 쌍(f2-f5)이 초과하는 화음.

    실제 엔진 출력(mario)에서 발견된 패턴: [p56:f2, p62:f3, p71:f5]
    인접 2-3 gap 6(≤6), 3-5 gap 9(≤10) → 통과. 비인접 2-5 gap 15 > 12 → 위반.
    """
    return [
        note(56, 0, 400, "Right", 2), note(62, 5, 400, "Right", 3),
        note(71, 10, 400, "Right", 5, role="MELODY"),
    ]


def case_mono():
    """A2: 오른손 화음의 손가락 순서를 뒤집어 단조성 위반 2쌍 유발."""
    raw = sample_clean()
    raw[0]["finger"], raw[2]["finger"] = 5, 1  # 60:f5, 64:f3, 67:f1 → 2쌍 위반
    return raw


def case_conflict():
    """A3: 오른손 f1 음을 길게 늘려 이후 화음의 f1과 시간 중첩 유발."""
    raw = sample_clean()
    raw[0]["duration_ms"] = 2000.0          # 60(f1) 0~2000ms
    raw[3]["finger"] = 1                     # 69 @500ms 를 f1으로 → 중첩
    raw[4]["finger"] = 1                     # 71 @750ms 도 f1 → 중첩 2쌍
    return raw


def case_edge():
    """A3b: 중첩이 0.01ms(반올림 오차 수준)인 경계 접촉 — 충돌로 세지 않아야 함."""
    raw = sample_clean()
    raw[0]["duration_ms"] = 500.01           # 60(f1) 종료 500.01ms
    raw[3]["finger"] = 1                     # 69 @500ms 시작 → 0.01ms 중첩
    return raw


def case_dup():
    """A4: 한 화음 안에서 같은 손가락(f3)을 2회 배정."""
    raw = sample_clean()
    raw[2]["finger"] = 3                     # 64:f3, 67:f3
    return raw


def case_unassigned():
    """A5: finger를 0으로 비워 미배정 유발."""
    raw = sample_clean()
    raw[1]["finger"] = 0
    return raw


def case_rom():
    """A6: yaw/roll을 ROM 한계 초과로 설정."""
    raw = sample_clean()
    raw[0]["wrist_yaw_deg"] = 40.0           # > 35
    raw[1]["wrist_roll_deg"] = -25.0         # |−25| > 20
    raw[2]["wrist_yaw_deg"] = -35.0          # 경계값 — 위반 아님
    return raw


def case_repeat():
    """B9: 단음 연속 구간에서 같은 손가락 반복(동음 아님)."""
    raw = sample_clean()
    raw[4]["finger"] = 2                     # 69:f2 → 71:f2 (상행, 같은 손가락)
    return raw


def case_arpeggio():
    """B10: 오른손 상행인데 손가락 번호 감소 → 방향성 불일치."""
    raw = sample_clean()
    raw[3]["finger"] = 4
    raw[4]["finger"] = 2                     # 69:f4 → 71:f2 (상행, 번호 감소)
    return raw


def case_cross():
    """B11: 동시 온셋에서 왼손 최고음 > 오른손 최저음 → 교차."""
    raw = sample_clean()
    raw[5]["pitch"] = 62                     # 왼손 62 vs 오른손 최저 60 @0ms
    raw[5]["finger"] = 2
    return raw


# ── 순간 단위 지표(A7~A9) 케이스 ──────────────────────────────────
# 핵심: 아래 음표들은 모두 **서로 다른 화음**(온셋 100ms 차이 > 30ms 윈도우)이다.
# 따라서 화음 단위 지표(A1/A2/A4)는 0을 보고하지만, 시간상으로는 겹쳐 있으므로
# 순간 단위 지표는 위반을 잡아내야 한다. 이 차이가 A7~A9 의 존재 이유다.

def case_instant_span():
    """지속음과 후속 단음이 겹치면서 손 범위를 초과 (화음 단위로는 안 보임)."""
    return [
        note(60, 0, 500, "Right", 1),     # 길게 유지
        note(90, 100, 100, "Right", 5),   # 30반음 떨어진 음을 그 위에 타건
    ]


def case_instant_finger_dup():
    """겹치는 두 음에 같은 손가락이 배정 — 한 손가락이 두 건반."""
    return [
        note(60, 0, 500, "Right", 3),
        note(62, 100, 100, "Right", 3),
    ]


def case_instant_key_dup():
    """같은 건반을 떼기 전에 다른 손가락으로 재타격 — 건반 하나에 손가락 둘."""
    return [
        note(60, 0, 500, "Left", 2),
        note(60, 100, 100, "Left", 4),
    ]


def case_instant_mono():
    """겹치는 두 음에서 pitch 순서와 손가락 순서가 어긋남."""
    return [
        note(60, 0, 500, "Right", 4),
        note(64, 100, 100, "Right", 2),
    ]


def case_instant_clean():
    """겹치지 않고 순차 타건 — 순간 단위 위반이 없어야 한다."""
    return [
        note(60, 0, 90, "Right", 1),
        note(90, 100, 100, "Right", 5),
    ]


CASES = [
    ("기준(정상) 샘플", case_clean, {
        "A1_span": 0, "A2_mono": 0, "A3_conflict": 0, "A3_edge": 0, "A4_dup": 0,
        "A5_unassigned": 0, "A6_yaw": 0, "A6_roll": 0,
        "B9_repeat": 0, "B10_arp": 0, "B11_cross": 0,
        # 인접쌍은 오른손 3음 화음에서만 2쌍 (왼손은 모두 단음 → 0쌍)
        "A1b_span": 0, "A1b_pairs": 1,
        "A1_pairs": 2, "A2_pairs": 2, "notes": 8, "chords": 6}),
    ("A1 MAX_SPAN 초과(인접) 주입", case_span, {"A1_span": 1, "A2_mono": 0}),
    ("A1b MAX_SPAN 초과(비인접) 주입", case_span_nonadjacent,
     {"A1_span": 0, "A1b_span": 1, "A1b_pairs": 1}),
    ("A2 Monotonicity 위반 주입", case_mono, {"A2_mono": 2}),
    ("A3 동시 누름 충돌 주입", case_conflict, {"A3_conflict": 2, "A3_edge": 0}),
    ("A3b 경계 접촉(0.01ms) 주입", case_edge, {"A3_conflict": 0, "A3_edge": 1}),
    ("A4 화음 내 손가락 중복 주입", case_dup, {"A4_dup": 1}),
    # 중간 음이 미배정이면 그 음을 포함한 인접쌍 2개가 span 평가에서 제외됨(2→0쌍)
    ("A5 미배정(finger=0) 주입", case_unassigned, {"A5_unassigned": 1, "A1_pairs": 0}),
    ("A6 ROM 초과 주입", case_rom, {"A6_yaw": 1, "A6_roll": 1}),
    ("B9 같은 손가락 반복 주입", case_repeat, {"B9_repeat": 1}),
    ("B10 아르페지오 불일치 주입", case_arpeggio, {"B10_arp": 1}),
    ("B11 손 교차 주입", case_cross, {"B11_cross": 1}),
    # 순간 단위 — 화음 단위 지표가 0인데도 위반이 잡혀야 한다
    ("A7 순간 손 범위 초과 주입", case_instant_span,
     {"A7_span": 1, "A_instants": 1, "A1_span": 0, "A1b_span": 0}),
    ("A8 순간 손가락 중복 주입", case_instant_finger_dup,
     {"A8_dup": 1, "A4_dup": 0}),
    ("A8b 순간 건반 중복 주입", case_instant_key_dup,
     {"A8b_key": 1, "A8_dup": 0}),
    ("A9 순간 Monotonicity 위반 주입", case_instant_mono,
     {"A9_mono": 1, "A2_mono": 0}),
    ("순간 단위 정상(겹침 없음)", case_instant_clean,
     {"A7_span": 0, "A8_dup": 0, "A8b_key": 0, "A9_mono": 0, "A_instants": 0}),
]


def test_robust_against_unknown_and_missing_fields():
    """미지 필드·결손 필드가 섞여도 예외 없이 집계되는지 확인."""
    raw = [
        {"pitch": 60, "start_ms": 0, "duration_ms": 100, "hand": "Right",
         "finger": 1, "unknown_field": {"nested": [1, 2]}},   # role/is_black/손목 없음
        {"pitch": 64, "start_ms": 5, "duration_ms": 100, "hand": "Right",
         "finger": 3, "wrist_yaw_deg": None},                  # 타입 이상
        {"pitch": 67, "start_ms": 10},                          # 대부분 결손
        "문자열이 섞인 경우",                                    # dict가 아닌 원소
    ]
    res = run_all(raw)
    assert res["notes"] == 4, res
    assert res["A5_unassigned"] == 2, res  # 결손 2건은 finger=0 으로 집계
    return True


def main():
    print(f"{M._pad('검산 케이스', 32)}{M._pad('지표', 16)}{M._pad('기대', 8)}{M._pad('실측', 8)}판정")
    print("-" * 74)

    failures = []
    for name, builder, expected in CASES:
        res = run_all(builder())
        for key, want in sorted(expected.items()):
            got = res[key]
            ok = got == want
            print(M._pad(name, 32) + M._pad(key, 16) + M._pad(want, 8)
                  + M._pad(got, 8) + ("PASS" if ok else "FAIL"))
            if not ok:
                failures.append(f"{name} / {key}: 기대 {want} vs 실측 {got}")
            name = ""  # 같은 케이스의 두 번째 줄부터는 이름 생략

    try:
        test_robust_against_unknown_and_missing_fields()
        print(M._pad("미지/결손 필드 견고성", 32) + M._pad("예외없음", 16)
              + M._pad("-", 8) + M._pad("-", 8) + "PASS")
    except Exception as exc:
        print(M._pad("미지/결손 필드 견고성", 32) + M._pad("예외", 16)
              + M._pad("-", 8) + M._pad("-", 8) + "FAIL")
        failures.append(f"미지/결손 필드 견고성: {type(exc).__name__}: {exc}")

    print("-" * 74)
    print(f"FAIL {len(failures)}건")
    for msg in failures:
        print(f"  - {msg}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
