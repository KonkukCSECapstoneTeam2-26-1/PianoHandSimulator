"""PianoHandSimulator — 공유 상수 모듈 (Shared Constants)

모든 파트(01_Fingering, 02_IK, 03_Skinning)가 공통으로 참조하는 상수를
한 곳에 모아 관리한다. 각 파트가 자기 가정값으로 계산하던 방식의 불일치를
제거하는 것이 목적이다.

근거 문서
  - `01_Design/09_Interface_Parameter_Decisions.md` — 건반 치수·좌표 확정안
  - `01_Design/03_Interface_Design_Spec.md`         — 파트 간 인터페이스 명세
  - `01_Design/11_Temporal_Constraint_Design.md`    — 시간 구간 기반 물리 제약

단위 규약
  - **길이는 밀리미터(mm)가 기준**이다. UE5 는 cm 를 쓰므로 소비측에서 ÷10 한다.
  - 혼동을 막기 위해 cm 값은 따로 두지 않고 `MM_TO_CM` 으로 환산한다.
    (상수를 양쪽 단위로 중복 정의하면 한쪽만 고쳐져 어긋난다)

변경 이력
  2026-09-14 (W03) : 흑건 Y 오프셋·손가락 오프셋 수치 정의
  2026-09-21 (W04) : 공유 상수 분리, IK 본 이름·프레임레이트 동기화
  2026-10-06 (W06) : 물리 제약을 시간 구간 기준으로 재정의. key_hold_ms 신설
  2026-10-18 (W08) : 아래 수치 3건 정정·1건 신규 (근거: 09번 문서)
                     · 백건 폭  2.3 cm  → 164.0/7 mm  (반올림 시 88키 1.5mm 누적 오차)
                     · 흑건 Y   +3.0 cm → +55.0 mm    (건반 형상에서 도출 불가한 값이었음)
                     · 타이밍   duration_ms → key_hold_ms 기준으로 해제 시점 정정
                     · 흑건 상면 높이 12.5 mm 신규 (IK 의 손목 Z 보간이 참조할 값)
"""

# ── 0. 단위 환산 ──────────────────────────────────────────────────────
MM_TO_CM = 0.1    # 엔진 출력(mm) → UE5(cm)

# ── 1. 피아노 건반 물리 치수 ──────────────────────────────────────────
# 1차 규격값은 '옥타브 폭'이며 백건 폭은 여기서 파생된다.
# 백건 폭을 23.4 로 반올림하면 옥타브가 163.8mm 가 되어 88키 끝에서 약 1.5mm 어긋난다.
OCTAVE_WIDTH_MM = 164.0                          # 백건 7개 폭 (표준 규격)
WHITE_KEY_WIDTH_MM = OCTAVE_WIDTH_MM / 7.0       # = 23.4286 mm
BLACK_KEY_WIDTH_MM = 13.7
WHITE_KEY_LENGTH_MM = 150.0
BLACK_KEY_LENGTH_MM = 95.0

# 백건 상면 대비 흑건 상면 높이. IK 가 흑건 타건 시 손목 Z 를 보간할 때 참조한다.
BLACK_KEY_HEIGHT_MM = 12.5

# 건반 최대 누름 깊이 (key dip). key_depth(0~1) 에 곱해 Z 변위를 얻는다.
MAX_KEY_TRAVEL_MM = 10.0

# ── 2. 타건 접점 Y ────────────────────────────────────────────────────
# 백건 150.0 / 흑건 95.0 이므로 흑건 앞단은 백건 앞단에서 55.0mm 후방에 있다.
# 기존 명세의 '흑건 Y = +3.0cm' 는 이 형상에서 도출될 수 없는 값이었다.
BLACK_KEY_FRONT_Y_MM = WHITE_KEY_LENGTH_MM - BLACK_KEY_LENGTH_MM   # = 55.0
WHITE_TOUCH_Y_MM = 30.0      # 백건 타건 접점 — 흑건 앞쪽 노출 구간(0~55)의 중앙부
BLACK_TOUCH_Y_MM = 85.0      # 흑건 타건 접점 — 흑건 앞단(55.0) + 30.0

# ── 3. MIDI 범위 (88건반) ─────────────────────────────────────────────
MIDI_MIN = 21    # A0
MIDI_MAX = 108   # C8
WHITE_KEY_COUNT = 52

# ── 4. 피치 분류 ──────────────────────────────────────────────────────
BLACK_KEY_PITCH_CLASSES = {1, 3, 6, 8, 10}
WHITE_KEY_PITCH_CLASSES = {0, 2, 4, 5, 7, 9, 11}

# 옥타브 내에서 해당 pitch_class 앞에 있는 백건 수 (백건 인덱스 산출용)
WHITE_BEFORE = {0: 0, 1: 1, 2: 1, 3: 2, 4: 2, 5: 3,
                6: 4, 7: 4, 8: 5, 9: 5, 10: 6, 11: 6}

# ── 5. 손가락 해부학적 제약 ───────────────────────────────────────────
# 손가락 쌍 간 최대 허용 반음 간격 (하드 제약)
# 주의: 인접 쌍만이 아니라 화음 내 **모든 쌍**을 검사해야 한다.
#       인접만 보면 2-3(6) · 3-5(9) 가 각각 통과하면서 2-5 가 15반음이 되는
#       물리적으로 불가능한 화음이 빠져나간다.
MAX_SPAN = {
    (1, 2): 12, (2, 3): 6, (3, 4): 5, (4, 5): 6,
    (1, 3): 14, (1, 4): 15, (1, 5): 17,
    (2, 4): 10, (2, 5): 12, (3, 5): 10,
}
DEFAULT_MAX_SPAN = 12    # 표에 없는 쌍(같은 손가락 등)의 기본 한계

# 피아노 교육학 기반 손가락 난이도 (DP 비용 항목)
FINGER_DIFFICULTY = {1: 0, 2: 0, 3: 0, 4: 6, 5: 3}

# 포지션(5지 묶음) 전환 임계값 (반음) — 초과 시 손목 이동 비용 가산
POSITION_SHIFT_THRESHOLD = 5

# 타건 동작 자체에 필요한 최소 건반 점유 시간.
# 이보다 짧게 누르고 떼는 것은 물리적으로 불가능하다.
MIN_STRIKE_HOLD_MS = 30.0

# ── 6. 손목 가동 범위 (ROM) ───────────────────────────────────────────
WRIST_YAW_MAX_DEG = 35.0     # 좌우 회전
WRIST_ROLL_MAX_DEG = 20.0    # 기울기

# 손가락별 손목 중심 기준 오프셋 (반음 단위, 3번 중지 = 0)
FINGER_WRIST_OFFSET_R = {1: -4, 2: -2, 3: 0, 4:  2, 5:  4}
FINGER_WRIST_OFFSET_L = {1:  4, 2:  2, 3: 0, 4: -2, 5: -4}

# ── 7. IK 인터페이스 — UE5 본(bone) 이름 매핑 ─────────────────────────
BONE_NAME_R = {1: "thumb_03_r", 2: "index_03_r", 3: "middle_03_r",
               4: "ring_03_r",  5: "pinky_03_r"}
BONE_NAME_L = {1: "thumb_03_l", 2: "index_03_l", 3: "middle_03_l",
               4: "ring_03_l",  5: "pinky_03_l"}

# UE5 AnimSequence 출력 프레임레이트
IK_FRAME_RATE = 30   # fps

# ── 8. IK 타이밍 프로토콜 ─────────────────────────────────────────────
# ★ 해제 시점은 duration_ms 가 아니라 key_hold_ms 기준이다.
#   duration_ms 는 Sustain 페달로 늘어난 '소리'의 지속이며, 손가락은 그보다 먼저
#   건반에서 떨어진다. duration_ms 로 건반을 떼면 한 손가락이 서로 다른 건반을
#   동시에 누르는 자세가 만들어진다. (드뷔시 '달빛'에서 111건 발생)
#
#   t = start_ms
#       Fingertip → Target Position 도달 완료
#       Z = (흑건 ? BLACK_KEY_HEIGHT_MM : 0.0) − key_depth × MAX_KEY_TRAVEL_MM
#
#   t = start_ms ~ (start_ms + key_hold_ms)
#       해당 위치 유지
#
#   t = start_ms + key_hold_ms
#       Fingertip Z → 건반 상면 복귀 (백건 0 / 흑건 BLACK_KEY_HEIGHT_MM)
#       복귀 속도 = (1.0 − pressure) 에 반비례 (강타일수록 천천히 복귀)
#
#   t = start_ms + duration_ms
#       소리 종료. pedal_down=true 면 손가락이 떨어진 뒤에도 이 시점까지 울린다.
#       → 오디오 측에서만 처리하며 손 자세와 무관하다.
#
#   항상 key_hold_ms ≤ duration_ms 가 성립한다.

# ── 9. pitch → 건반 3D 좌표 변환 ──────────────────────────────────────
# 변환 식은 본 모듈이 아니라 `v5_polyphonic/piano_keyboard.py` 가 **유일하게** 구현한다.
# 상수를 복제하지 말고 그 모듈의 함수를 호출할 것.
#
#   X : A0(MIDI 21) 좌측 모서리 = 0, 고음 방향으로 증가
#       백건 = white_key_index × WHITE_KEY_WIDTH_MM + WHITE_KEY_WIDTH_MM / 2
#       흑건 = (좌측 인접 백건 인덱스 + 1) × WHITE_KEY_WIDTH_MM   (두 백건의 경계)
#   Y : 백건 앞단 = 0, 건반 안쪽으로 증가 (WHITE/BLACK_TOUCH_Y_MM)
#   Z : 백건 상면 = 0, 위쪽이 양(+)
