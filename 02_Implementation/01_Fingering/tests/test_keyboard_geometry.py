"""건반 3D 좌표 변환 모듈(piano_keyboard) 기하 검증 테스트.

근거 문서: `01_Design/09_Interface_Parameter_Decisions.md` (3장 / 4.2절 / 5.1절 / 5.2절)

검증 항목
  1. 백건 인덱스 경계      — white_key_index(21)=0, white_key_index(108)=51
  2. 백건 52개 전단사       — 21~108 백건이 인덱스 0~51을 빠짐없이 1:1로 덮는지
  3. 옥타브 X 중심 간격     — C4→C5 = 7 × 백건폭
  4. 흑건 X 중앙 배치       — 인접 두 백건 중심의 정확한 중앙인지
  5. 흑건/백건 접점 Y 차    — 85.0 - 30.0 = 55.0 mm
  6. 목표 Z (key_depth 0/1) — 문서 5.1절 식과 일치
  7. 범위 밖 pitch          — ValueError 발생

실행: python tests/test_keyboard_geometry.py
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(BASE_DIR, "../v5_polyphonic")))

import piano_keyboard as kb  # noqa: E402

EPS = 1e-9

# 문서 3장: 옥타브 폭(백건 7개) 164.0mm가 1차 규격값이고 백건 폭은 거기서 파생된다.
# 백건 폭을 23.4로 반올림하면 옥타브 간격이 163.8mm가 되어 88키에서 약 1.5mm
# 누적 오차가 생기므로, 모듈은 WHITE_KEY_WIDTH_MM = OCTAVE_WIDTH_MM / 7로 정의한다.
OCTAVE_PITCH_MM = 7 * kb.WHITE_KEY_WIDTH_MM

results = []


def record(name, ok, detail):
    """검증 결과 1건 기록."""
    results.append((name, ok, detail))


def near(a, b):
    return abs(a - b) < 1e-6


# ── 1. 백건 인덱스 경계 (문서 4.2절 검증 문구) ──────────────────
def test_index_bounds():
    i_low, i_high = kb.white_key_index(21), kb.white_key_index(108)
    ok = (i_low == 0) and (i_high == 51)
    record("백건 인덱스 경계 A0=0 / C8=51", ok, f"A0={i_low}, C8={i_high}")


# ── 2. 백건 52개가 인덱스 0~51을 1:1로 덮는지 ───────────────────
def test_white_key_bijection():
    whites = [p for p in range(kb.MIN_PITCH, kb.MAX_PITCH + 1) if not kb.is_black_key(p)]
    indices = [kb.white_key_index(p) for p in whites]
    ok = (len(whites) == 52
          and sorted(indices) == list(range(52))
          and len(set(indices)) == 52)
    record("백건 52개 ↔ 인덱스 0~51 전단사", ok,
           f"백건 {len(whites)}개, 고유 인덱스 {len(set(indices))}개, "
           f"범위 {min(indices)}~{max(indices)}")


# ── 3. 한 옥타브 X 중심 간격 ────────────────────────────────────
def test_octave_spacing():
    worst_name, worst_err, measured = "", 0.0, None
    # C1(24) ~ C7(96) 사이 모든 인접 옥타브 쌍 검사
    for p in range(24, 97, 12):
        gap = kb.key_center_x_mm(p + 12) - kb.key_center_x_mm(p)
        err = abs(gap - OCTAVE_PITCH_MM)
        if p == 60:
            measured = gap
        if err > worst_err:
            worst_err, worst_name = err, f"pitch {p}→{p + 12}"
    ok = worst_err < 1e-6
    record(f"옥타브 X 간격 = {OCTAVE_PITCH_MM:.1f}mm", ok,
           f"C4→C5 측정 {measured:.2f}mm, 최대오차 {worst_err:.2e}mm ({worst_name})")


# ── 4. 흑건 X가 인접 두 백건 중심의 중앙인지 ────────────────────
def test_black_key_centering():
    worst_err, worst_pitch, checked = 0.0, None, 0
    for p in range(kb.MIN_PITCH, kb.MAX_PITCH + 1):
        if not kb.is_black_key(p):
            continue
        x_black = kb.key_center_x_mm(p)
        x_left = kb.key_center_x_mm(p - 1)   # 좌측 인접 백건
        x_right = kb.key_center_x_mm(p + 1)  # 우측 인접 백건
        checked += 1
        # 중앙 배치 + 두 백건 사이에 위치
        err = abs(x_black - (x_left + x_right) / 2.0)
        if not (x_left < x_black < x_right):
            err = float("inf")
        if err > worst_err:
            worst_err, worst_pitch = err, p
    ok = (checked == 36) and worst_err < 1e-6
    record("흑건 X = 인접 백건 중심의 중앙", ok,
           f"흑건 {checked}개 검사, 최대오차 {worst_err:.2e}mm (pitch {worst_pitch})")


# ── 5. 접점 Y 차이 (문서 5.2절) ─────────────────────────────────
def test_touch_y_offset():
    y_white = kb.key_touch_y_mm(60)   # C4 백건
    y_black = kb.key_touch_y_mm(61)   # C#4 흑건
    diff = y_black - y_white
    # 모든 건반에 대해 종류별 값이 일정한지도 확인
    consistent = all(
        near(kb.key_touch_y_mm(p), 85.0 if kb.is_black_key(p) else 30.0)
        for p in range(kb.MIN_PITCH, kb.MAX_PITCH + 1)
    )
    ok = near(diff, 55.0) and near(y_white, 30.0) and near(y_black, 85.0) and consistent
    record("접점 Y: 흑건 85.0 − 백건 30.0 = 55.0mm", ok,
           f"백건 {y_white:.1f} / 흑건 {y_black:.1f} / 차 {diff:.1f}mm, "
           f"전건반 일관성={consistent}")


# ── 6. 목표 Z (문서 5.1절 식) ───────────────────────────────────
def test_target_z():
    # Z_target = (is_black ? 12.5 : 0.0) - (key_depth × 10.0)
    cases = [
        (60, 0.0, 0.0),     # 백건 비타건
        (60, 1.0, -10.0),   # 백건 최대 타건
        (61, 0.0, 12.5),    # 흑건 비타건
        (61, 1.0, 2.5),     # 흑건 최대 타건
        (60, 0.5, -5.0),    # 백건 중간
        (61, 0.5, 7.5),     # 흑건 중간
    ]
    bad = []
    for pitch, depth, expected in cases:
        got = kb.key_target_z_mm(pitch, depth)
        if not near(got, expected):
            bad.append(f"pitch{pitch}@{depth}: {got:.3f}≠{expected:.3f}")
    # 전체 건반에 대해 문서 식과 대조
    for p in range(kb.MIN_PITCH, kb.MAX_PITCH + 1):
        for depth in (0.0, 0.25, 1.0):
            expected = (12.5 if kb.is_black_key(p) else 0.0) - depth * 10.0
            if not near(kb.key_target_z_mm(p, depth), expected):
                bad.append(f"pitch{p}@{depth}")
    ok = not bad
    record("목표 Z = (흑건?12.5:0) − depth×10.0", ok,
           "전건반×depth(0/0.25/1) 일치" if ok else "; ".join(bad[:3]))


# ── 7. 범위 밖 pitch는 ValueError ───────────────────────────────
def test_out_of_range():
    funcs = [
        ("white_key_index", lambda p: kb.white_key_index(p)),
        ("is_black_key", lambda p: kb.is_black_key(p)),
        ("key_center_x_mm", lambda p: kb.key_center_x_mm(p)),
        ("key_touch_y_mm", lambda p: kb.key_touch_y_mm(p)),
        ("key_target_z_mm", lambda p: kb.key_target_z_mm(p, 0.5)),
        ("key_target_position", lambda p: kb.key_target_position(p, 0.5)),
    ]
    bad = []
    for name, fn in funcs:
        for bad_pitch in (20, 0, -1, 109, 127):
            try:
                fn(bad_pitch)
            except ValueError:
                continue
            except Exception as exc:
                bad.append(f"{name}({bad_pitch})→{type(exc).__name__}")
            else:
                bad.append(f"{name}({bad_pitch})→예외없음")
    # 경계값은 정상 동작해야 함
    for good_pitch in (21, 108):
        for name, fn in funcs:
            try:
                fn(good_pitch)
            except Exception as exc:
                bad.append(f"{name}({good_pitch})→{type(exc).__name__}")
    ok = not bad
    record("범위 밖 pitch → ValueError", ok,
           f"6개 함수 × 경계 밖 5값 검증" if ok else "; ".join(bad[:3]))


TESTS = [
    test_index_bounds,
    test_white_key_bijection,
    test_octave_spacing,
    test_black_key_centering,
    test_touch_y_offset,
    test_target_z,
    test_out_of_range,
]


def main():
    print(f"{'검증 항목':44s} {'판정':>6s}  상세")
    print("-" * 110)

    for fn in TESTS:
        try:
            fn()
        except Exception as exc:
            record(fn.__name__, False, f"ERROR {type(exc).__name__}: {exc}")

    failures = []
    for name, ok, detail in results:
        print(f"{name:44s} {'PASS' if ok else 'FAIL':>6s}  {detail}")
        if not ok:
            failures.append((name, detail))

    print("-" * 110)
    print(f"PASS {len(results) - len(failures)} / FAIL {len(failures)}")
    for name, detail in failures:
        print(f"  - {name}: {detail}")

    if failures:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
