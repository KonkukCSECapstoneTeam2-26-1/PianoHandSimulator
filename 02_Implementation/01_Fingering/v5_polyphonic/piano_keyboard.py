"""건반 3D 좌표 변환 공유 모듈 (01_Fingering ↔ 02_IK 공용).

근거 문서: `01_Design/09_Interface_Parameter_Decisions.md`
  - 3장   건반 물리 치수 기준 확정
  - 4.1절 MAX_KEY_TRAVEL 확정
  - 4.2절 pitch → X좌표 변환 기준 원점 (WHITE_BEFORE 테이블)
  - 5.1절 흑건 상면 높이 (신규)
  - 5.2절 흑건 Y 오프셋 (기존 +3.0cm → +5.5cm 수정)

이 모듈은 운지법 엔진(01_Fingering)과 IK 솔버(02_IK)가 **동일한 상수·동일한 식**을
참조하도록 하기 위한 단일 진실 공급원(single source of truth)이다.
양측이 각자 가정값으로 변환하던 기존 방식의 불일치를 제거하는 것이 목적이다.

설계 원칙
  - 외부 의존 없음: 표준 라이브러리만 사용 (mido 등 불필요)
  - 순수 함수: 전역 상태 변경 없음, 동일 입력 → 동일 출력
  - 단위: 전부 밀리미터(mm), 각도 없음

좌표계 (문서 4.2 / 5.1 / 5.2절)
  X : 건반 좌우. A0(MIDI 21) **좌측 모서리** = 0, 고음 방향으로 증가
  Y : 건반 앞뒤. 연주자측 백건 앞단 = 0, 건반 후방(안쪽) 방향으로 증가
  Z : 건반 높이. 백건 상면(비타건 상태) = 0, 위쪽이 양(+)

주의: 반환값은 모두 '건반 로컬 좌표(mm)'이다.
      UE5 월드 좌표(cm, 좌수 Z-up)로 쓰려면 소비측에서 축 매핑·단위 변환을 수행한다.
"""

# ── 공유 상수 (01/02/03 파트 공용) ──────────────────────────────
# 수치는 `02_Implementation/01_Fingering/shared_constants.py` 가 단일 출처다.
# 이 모듈은 그 값을 쓰는 '변환 식'만 책임진다. 상수를 여기서 다시 정의하지 말 것.
import os as _os
import sys as _sys
_SC_DIR = _os.path.abspath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".."))
if _SC_DIR not in _sys.path:
    _sys.path.insert(0, _SC_DIR)
import shared_constants as _sc

# 아래 이름들은 기존 소비측(테스트·시뮬레이터)과의 호환을 위해 그대로 노출한다.
OCTAVE_WIDTH_MM = _sc.OCTAVE_WIDTH_MM
WHITE_KEY_WIDTH_MM = _sc.WHITE_KEY_WIDTH_MM
BLACK_KEY_WIDTH_MM = _sc.BLACK_KEY_WIDTH_MM
WHITE_KEY_LENGTH_MM = _sc.WHITE_KEY_LENGTH_MM
BLACK_KEY_LENGTH_MM = _sc.BLACK_KEY_LENGTH_MM
BLACK_KEY_HEIGHT_MM = _sc.BLACK_KEY_HEIGHT_MM
MAX_KEY_TRAVEL_MM = _sc.MAX_KEY_TRAVEL_MM

BLACK_KEY_FRONT_Y_MM = _sc.BLACK_KEY_FRONT_Y_MM
WHITE_TOUCH_Y_MM = _sc.WHITE_TOUCH_Y_MM
BLACK_TOUCH_Y_MM = _sc.BLACK_TOUCH_Y_MM

MIN_PITCH = _sc.MIDI_MIN
MAX_PITCH = _sc.MIDI_MAX
WHITE_KEY_COUNT = _sc.WHITE_KEY_COUNT

BLACK_PITCH_CLASSES = frozenset(_sc.BLACK_KEY_PITCH_CLASSES)

# 옥타브 내 선행 백건 수 — 인덱싱 편의를 위해 튜플로 변환
WHITE_BEFORE = tuple(_sc.WHITE_BEFORE[i] for i in range(12))


def _validate_pitch(pitch):
    """88키 범위(21~108) 밖이면 ValueError. 정수형이 아니면 TypeError."""
    if isinstance(pitch, bool) or not isinstance(pitch, int):
        raise TypeError(f"pitch는 정수여야 합니다: {pitch!r}")
    if pitch < MIN_PITCH or pitch > MAX_PITCH:
        raise ValueError(
            f"pitch {pitch}는 88키 범위를 벗어났습니다 "
            f"(허용: {MIN_PITCH}~{MAX_PITCH})"
        )
    return pitch


def is_black_key(pitch):
    """해당 pitch가 흑건인지 판정."""
    _validate_pitch(pitch)
    return (pitch % 12) in BLACK_PITCH_CLASSES


def white_count(pitch):
    """MIDI 0을 기준으로 한 누적 백건 수 (문서 4.2절 white_count).

    white_count(n) = 7 × (n // 12) + WHITE_BEFORE[n % 12]
    """
    _validate_pitch(pitch)
    return 7 * (pitch // 12) + WHITE_BEFORE[pitch % 12]


def white_key_index(pitch):
    """A0(MIDI 21)을 0으로 하는 백건 인덱스 (문서 4.2절 white_key_index).

    white_key_index(n) = white_count(n) - white_count(21)

    백건 pitch에 대해서는 0~51의 고유 인덱스를 반환한다.
    흑건 pitch에 대해서는 WHITE_BEFORE 정의상 **바로 우측 백건의 인덱스**가
    반환되므로(예: C#4 → D4의 인덱스), 흑건 X 산출에는 직접 쓰지 않고
    `key_center_x_mm()`이 좌측 인접 백건 기준으로 계산한다.
    """
    return white_count(pitch) - white_count(MIN_PITCH)


def key_center_x_mm(pitch):
    """건반 중심의 X 좌표(mm). A0 좌측 모서리 = 0 (문서 4.2절).

    백건: X_center = white_key_index × WHITE_KEY_WIDTH + WHITE_KEY_WIDTH / 2
    흑건: X_center = (좌측 인접 백건의 우측 모서리)
                   = (white_key_index(좌측 백건) + 1) × WHITE_KEY_WIDTH
          → 인접 두 백건 중심의 중앙에 위치 (v1 단순화)
    """
    _validate_pitch(pitch)
    if is_black_key(pitch):
        # 흑건의 좌측 인접 건은 항상 백건이다 (pitch-1은 흑건이 될 수 없음)
        left_white_index = white_key_index(pitch - 1)
        return (left_white_index + 1) * WHITE_KEY_WIDTH_MM
    return white_key_index(pitch) * WHITE_KEY_WIDTH_MM + WHITE_KEY_WIDTH_MM / 2.0


def key_touch_y_mm(pitch):
    """타건 접점(IK 목표)의 Y 좌표(mm). 백건 30.0 / 흑건 85.0 (문서 5.2절)."""
    return BLACK_TOUCH_Y_MM if is_black_key(pitch) else WHITE_TOUCH_Y_MM


def key_target_z_mm(pitch, key_depth):
    """타건 깊이를 반영한 목표 Z 좌표(mm) (문서 5.1절).

    Z_target = (is_black ? 12.5 : 0.0) - (key_depth × 10.0)

    Args:
        pitch: MIDI 노트 번호 (21~108)
        key_depth: 0.0~1.0 정규화 누름 깊이 (velocity 기반). 범위 밖은 클램핑.
    """
    surface_z = BLACK_KEY_HEIGHT_MM if is_black_key(pitch) else 0.0
    depth = min(max(float(key_depth), 0.0), 1.0)
    return surface_z - depth * MAX_KEY_TRAVEL_MM


def key_target_position(pitch, key_depth):
    """IK 타겟 3D 좌표 (x, y, z) in mm.

    운지법 엔진 JSON의 target_x_mm / target_y_mm / target_z_mm 원천.
    """
    return (
        key_center_x_mm(pitch),
        key_touch_y_mm(pitch),
        key_target_z_mm(pitch, key_depth),
    )


# ── 보조 함수 (소비측 편의용) ────────────────────────────────────
def key_width_mm(pitch):
    """해당 건반의 폭(mm)."""
    return BLACK_KEY_WIDTH_MM if is_black_key(pitch) else WHITE_KEY_WIDTH_MM


def key_length_mm(pitch):
    """해당 건반의 길이(mm)."""
    return BLACK_KEY_LENGTH_MM if is_black_key(pitch) else WHITE_KEY_LENGTH_MM


def keyboard_width_mm():
    """88키 전체 폭(mm) = 백건 52개 × 백건 폭."""
    return WHITE_KEY_COUNT * WHITE_KEY_WIDTH_MM


if __name__ == "__main__":
    # 간단한 수치 확인용 덤프 (정식 검증은 tests/test_keyboard_geometry.py)
    print(f"88키 전체 폭: {keyboard_width_mm():.1f} mm")
    print(f"{'pitch':>6s} {'이름':>5s} {'흑건':>5s} {'X(mm)':>9s} {'Y(mm)':>7s} "
          f"{'Z@0':>7s} {'Z@1':>7s}")
    NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    for p in (21, 60, 61, 62, 72, 108):
        name = f"{NAMES[p % 12]}{p // 12 - 1}"
        x, y, _ = key_target_position(p, 0.0)
        print(f"{p:6d} {name:>5s} {str(is_black_key(p)):>5s} {x:9.2f} {y:7.2f} "
              f"{key_target_z_mm(p, 0.0):7.2f} {key_target_z_mm(p, 1.0):7.2f}")
