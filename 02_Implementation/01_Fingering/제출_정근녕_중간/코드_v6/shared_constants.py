"""
PianoHandSimulator — 공유 상수 모듈 (Shared Constants)

모든 파트(01_Fingering, 02_IK, 03_Skinning)가 공통으로 참조하는 상수를
한 곳에 모아 관리합니다.

변경 이력:
  2026-09-14 (W03) : 흑건 상면 Y 오프셋 신규 정의 (BLACK_KEY_Y_OFFSET_CM)
                     손가락-손목 오프셋 수치 확정 (FINGER_WRIST_OFFSET_R/L)
  2026-09-21 (W04) : 공유 상수 분리 (fingering_engine, simulator 에서 이관)
                     IK 솔버 입력 인터페이스 동기화 (BONE_NAME_R/L, IK_FRAME_RATE)
"""

# ── 1. 피아노 건반 물리 치수 (W03 확정) ──────────────────────────────────
WHITE_KEY_WIDTH_CM  = 2.3    # 흰건 너비 (cm)
BLACK_KEY_WIDTH_CM  = 1.3    # 흑건 너비 (cm)
WHITE_KEY_LENGTH_CM = 15.0   # 흰건 길이 (cm)
BLACK_KEY_LENGTH_CM = 9.5    # 흑건 길이 (cm)

# 흑건 상면 Y 오프셋: 흰건 앞면(Y=0) 기준 흑건이 뒤쪽으로 들어간 거리
# W03 신규 정의 — 이전까지 미확정이었던 값을 3.0 cm 으로 결정
BLACK_KEY_Y_OFFSET_CM = 3.0

# 건반 최대 누름 깊이 — key_depth(0~1) 값에 곱해 실제 Z 변위(cm)로 변환
MAX_KEY_TRAVEL_CM = 1.0

# ── 2. MIDI 범위 ──────────────────────────────────────────────────────
MIDI_MIN = 21    # A0 (88건반 최저음)
MIDI_MAX = 108   # C8 (88건반 최고음)

# ── 3. 피치 분류 ──────────────────────────────────────────────────────
BLACK_KEY_PITCH_CLASSES = {1, 3, 6, 8, 10}
WHITE_KEY_PITCH_CLASSES = {0, 2, 4, 5, 7, 9, 11}

# ── 4. 손가락 해부학적 제약 ───────────────────────────────────────────
# 손가락 쌍 간 최대 허용 반음 간격 (Hard Limit — 초과 시 5000 패널티)
MAX_SPAN = {
    (1, 2): 12, (2, 3): 6, (3, 4): 5, (4, 5): 6,
    (1, 3): 14, (1, 4): 15, (1, 5): 17,
    (2, 4): 10, (2, 5): 12, (3, 5): 10,
}

# 피아노 교육학 기반 손가락 난이도 (DP 비용 함수 항목)
FINGER_DIFFICULTY = {1: 0, 2: 0, 3: 0, 4: 6, 5: 3}

# 포지션(5지 묶음) 전환 임계값 (반음) — 초과 시 손목 이동 비용 가산
POSITION_SHIFT_THRESHOLD = 5

# ── 5. 손목 가동 범위 (ROM) ────────────────────────────────────────────
WRIST_YAW_MAX_DEG  = 35.0   # 좌우(Yaw) 최대 회전각 (°)
WRIST_ROLL_MAX_DEG = 20.0   # 기울기(Roll) 최대 회전각 (°)

# 손가락별 손목 중심 기준 오프셋 (반음 단위, 3번 중지 = 0 기준)
# W03 수치 확정 — 손목 Yaw 계산에 사용
FINGER_WRIST_OFFSET_R = {1: -4, 2: -2, 3: 0, 4:  2, 5:  4}  # 오른손
FINGER_WRIST_OFFSET_L = {1:  4, 2:  2, 3: 0, 4: -2, 5: -4}  # 왼손

# ── 6. IK 인터페이스 — UE5 본(bone) 이름 매핑 (W04 동기화) ───────────────
# finger 번호 → UE5 Skeletal Mesh End Effector 본 이름
BONE_NAME_R = {
    1: "thumb_03_r",
    2: "index_03_r",
    3: "middle_03_r",
    4: "ring_03_r",
    5: "pinky_03_r",
}
BONE_NAME_L = {
    1: "thumb_03_l",
    2: "index_03_l",
    3: "middle_03_l",
    4: "ring_03_l",
    5: "pinky_03_l",
}

# UE5 AnimSequence 출력 프레임레이트
IK_FRAME_RATE = 30  # fps

# ── 7. IK 타이밍 프로토콜 (W04 동기화) ────────────────────────────────
# t = start_ms
#   Fingertip → Target Position 도달 완료
#   Z = -(key_depth × MAX_KEY_TRAVEL_CM)
#
# t = start_ms ~ (start_ms + duration_ms)
#   해당 위치 유지
#
# t = start_ms + duration_ms
#   Fingertip Z → 0 복귀
#   복귀 속도 = (1.0 - pressure) 에 반비례 (강타일수록 천천히 복귀)

# ── 8. pitch → 건반 3D 좌표 변환 규칙 (W04 동기화) ──────────────────────
# X (좌우):
#   흰건 : white_key_index × WHITE_KEY_WIDTH_CM
#   흑건 : 인접 두 흰건 X의 평균
#
# Y (앞뒤):
#   흰건 : 0.0 cm
#   흑건 : BLACK_KEY_Y_OFFSET_CM (= 3.0 cm, W03 확정)
#
# Z (누름 깊이):
#   Z = -(key_depth × MAX_KEY_TRAVEL_CM)
