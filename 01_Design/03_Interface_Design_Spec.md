# 파트 간 데이터 인터페이스 설계 명세서
# (Inter-Module Data Interface Specification)

**프로젝트**: PianoHandSimulator
**작성일**: 2026년 6월 1일

---

## 1. 개요

본 문서는 PianoHandSimulator의 각 파트(모듈) 간에 어떤 데이터가 어떤 형태로 전달되는지를 명세한다.
전체 파이프라인은 4개 파트로 구성되며, 각 파트는 이전 파트의 출력을 입력으로 받아 처리한다.

### 전체 파이프라인 흐름

```
사용자
  │  MIDI 파일
  ▼
┌─────────────────────┐
│  01_Fingering        │  담당: 정근녕
│  MIDI 파서 +         │
│  운지법 DP 엔진      │
└──────────┬──────────┘
           │  [Interface A]  NoteEvent JSON
           ▼
┌─────────────────────┐
│  02_IK               │  담당: 한승현
│  Jacobian IK 솔버    │
│  Bone 애니메이션 생성 │
└──────────┬──────────┘
           │  [Interface B]  Joint Transform 시퀀스
           ▼
┌─────────────────────┐
│  03_Skinning         │  담당: 곽경민
│  Skinning + Shader   │
│  Texture 기반 렌더링 │
└──────────┬──────────┘
           │  [Interface C]  렌더링 파라미터
           ▼
┌─────────────────────┐
│  04_Main (UE5)       │  담당: 이수민
│  카메라 / UI         │
│  Movie Render Queue  │
└─────────────────────┘
```

---

## 2. Interface A — 01_Fingering → 02_IK

### 2.1 전달 방식

- **포맷**: JSON 파일 (`mario_polyphonic_result.json`)
- **생성 위치**: `Project/01_Fingering/results/`
- **소비 위치**: `Project/02_IK/`
- **전달 시점**: 운지법 엔진 실행 완료 후 1회 생성 (오프라인 사전 계산)

### 2.2 데이터 스키마

```json
[
  {
    "pitch":                int,    // MIDI 음고 (21~108, A0~C8)
    "start_ms":             float,  // 음표 시작 시각 (ms)
    "duration_ms":          float,  // 음표 지속 시간 (ms)
    "hand":                 string, // "Left" | "Right"
    "role":                 string, // "MELODY" | "BASS" | "INNER"
    "finger":               int,    // 배정 손가락 번호 (1~5)
    "pressure":             float,  // 타건 강도 (0.0~1.0)
    "key_depth":            float,  // 건반 누름 깊이 (0.0~1.0)
    "is_black":             bool,   // 흑건 여부
    "wrist_pos_normalized": float,  // 손목 가로 위치 (0.0~1.0, 88키 기준)
    "wrist_yaw_deg":        float,  // 손목 좌우 회전각 (±35.0°)
    "wrist_roll_deg":       float   // 손목 기울기 (±20.0°)
  },
  ...
]
```

### 2.3 실제 데이터 예시

드뷔시 Clair de Lune 첫 화음 구간 일부:

```json
[
  {
    "pitch": 60, "start_ms": 0.0, "duration_ms": 1200.0,
    "hand": "Right", "role": "MELODY", "finger": 3,
    "pressure": 0.622, "key_depth": 0.622,
    "is_black": false,
    "wrist_pos_normalized": 0.449,
    "wrist_yaw_deg": -5.0, "wrist_roll_deg": 0.0
  },
  {
    "pitch": 64, "start_ms": 0.0, "duration_ms": 1200.0,
    "hand": "Right", "role": "INNER", "finger": 4,
    "pressure": 0.559, "key_depth": 0.559,
    "is_black": false,
    "wrist_pos_normalized": 0.449,
    "wrist_yaw_deg": -5.0, "wrist_roll_deg": 0.0
  },
  {
    "pitch": 67, "start_ms": 0.0, "duration_ms": 1200.0,
    "hand": "Right", "role": "INNER", "finger": 5,
    "pressure": 0.496, "key_depth": 0.496,
    "is_black": false,
    "wrist_pos_normalized": 0.449,
    "wrist_yaw_deg": -5.0, "wrist_roll_deg": 0.0
  }
]
```

### 2.4 IK가 사용하는 필드 및 목적

| 필드 | IK에서의 역할 | 비고 |
|------|--------------|------|
| `pitch` | 건반 3D Target Position 계산 | 아래 2.5 변환 규칙 참고 |
| `start_ms` | IK 계산 시작 타임라인 트리거 | AnimSequence 키프레임 삽입 기준 |
| `duration_ms` | 건반 누름 유지 구간 | 해제 시점 = start_ms + duration_ms |
| `hand` | 왼손/오른손 Skeletal Mesh 선택 | "Left" → `hand_l`, "Right" → `hand_r` |
| `finger` | IK End Effector 타겟 본 선택 | 아래 2.6 본 이름 매핑 참고 |
| `key_depth` | Fingertip IK 목표 Z축 오프셋 | 0.0~1.0 → 0~MAX_KEY_TRAVEL cm |
| `wrist_yaw_deg` | Wrist 본 Yaw 회전 가이드값 | IK 초기 자세 설정에 활용 |
| `wrist_roll_deg` | Wrist 본 Roll 회전 가이드값 | IK 초기 자세 설정에 활용 |
| `pressure` | 타건 강도 애니메이션 | 손가락 가속도 곡선 조절 (보조 활용) |
| `role` | 향후 성부별 모션 강조 | MELODY: 더 강한 누름 모션 예정 |

### 2.5 pitch → 건반 3D 좌표 변환 규칙

피아노 건반의 물리적 치수 (기준):

| 항목 | 수치 |
|------|------|
| 흰건 너비 | 2.3 cm |
| 흑건 너비 | 1.3 cm |
| 흰건 길이 | 15.0 cm |
| 흑건 길이 | 9.5 cm |
| 최대 건반 누름 깊이 (MAX_KEY_TRAVEL) | 1.0 cm (**미확정**) |

**X축 (좌우) 위치 계산:**

MIDI pitch를 옥타브 내 음계 인덱스로 변환 후, 흰건 인덱스를 기준으로 X 좌표 결정.

```
pitch_class = pitch % 12
옥타브 내 흰건 인덱스 (pitch_class → white_index):
  C(0)→0, D(2)→1, E(4)→2, F(5)→3, G(7)→4, A(9)→5, B(11)→6

흑건 위치 (pitch_class → 인접 흰건 사이 중간):
  C#(1): C와 D 사이, D#(3): D와 E 사이
  F#(6): F와 G 사이, G#(8): G와 A 사이, A#(10): A와 B 사이

전체 흰건 인덱스 (MIDI 21 = A0 기준):
  white_key_index = 흰건 누적 인덱스 (pitch 21~108 범위에서 0~51)

X = white_key_index × 2.3 cm          (흰건)
X = 인접 두 흰건 X의 평균              (흑건)
```

**Y축 (앞뒤) 위치:**
- 흰건: Y = 0.0 cm (건반 앞면 기준)
- 흑건: Y = +3.0 cm (흰건 대비 뒤쪽으로 들어감)

**Z축 (누름 깊이):**
```
Z = -(key_depth × MAX_KEY_TRAVEL)   (누를수록 아래)
  = -(key_depth × 1.0) cm
```

### 2.6 finger → UE5 본(bone) 이름 매핑

| finger | 오른손 End Effector 본 | 왼손 End Effector 본 |
|--------|----------------------|---------------------|
| 1 (엄지) | `thumb_03_r` | `thumb_03_l` |
| 2 (검지) | `index_03_r` | `index_03_l` |
| 3 (중지) | `middle_03_r` | `middle_03_l` |
| 4 (약지) | `ring_03_r` | `ring_03_l` |
| 5 (새끼) | `pinky_03_r` | `pinky_03_l` |

> `_03`: 각 손가락의 말단 지절(Distal Phalanx) 끝, IK End Effector로 사용

### 2.7 타이밍 동기화 프로토콜

```
t = start_ms:
  · Fingertip이 Target Position에 도달 완료 (건반 눌림 시작)
  · Z = -(key_depth × MAX_KEY_TRAVEL)

t = start_ms ~ start_ms + duration_ms:
  · 해당 position 유지

t = start_ms + duration_ms:
  · Fingertip Z → 0 복귀 (건반 해제)
  · 복귀 속도: (1.0 - pressure) 에 반비례 (강타일수록 천천히 복귀)
```

---

## 3. Interface B — 02_IK → 03_Skinning

### 3.1 전달 방식

- **포맷**: UE5 AnimSequence (Skeletal Mesh Animation Asset)
- **전달 단위**: 프레임 단위 Joint Transform 시퀀스 (30 FPS 기준)
- **좌표계**: UE5 로컬 본 좌표 (cm 단위, Z-up, 우손 좌표계)

### 3.2 관절 계층 구조 (UE5 MetaHuman 기준)

```
hand_r / hand_l  (Wrist)
├── thumb_01_r/l         (엄지 CMC)
│   ├── thumb_02_r/l     (엄지 MCP)
│   └── thumb_03_r/l     (엄지 IP) ← End Effector
├── index_metacarpal_r/l
│   └── index_01_r/l     (검지 MCP)
│       ├── index_02_r/l (검지 PIP)
│       └── index_03_r/l (검지 DIP) ← End Effector
├── middle_metacarpal_r/l
│   └── middle_01_r/l    (중지 MCP)
│       ├── middle_02_r/l
│       └── middle_03_r/l ← End Effector
├── ring_metacarpal_r/l
│   └── ring_01_r/l      (약지 MCP)
│       ├── ring_02_r/l
│       └── ring_03_r/l  ← End Effector
└── pinky_metacarpal_r/l
    └── pinky_01_r/l     (새끼 MCP)
        ├── pinky_02_r/l
        └── pinky_03_r/l ← End Effector
```

### 3.3 프레임 데이터 구조

IK 솔버가 프레임마다 출력하는 데이터:

```
JointTransformFrame {
  frame_index  : int             // 프레임 번호 (0부터 시작)
  timestamp_ms : float           // 해당 프레임의 절대 시각 (ms)

  right_hand : {
    "hand_r"              : Transform,
    "thumb_01_r"          : Transform,
    "thumb_02_r"          : Transform,
    "thumb_03_r"          : Transform,
    "index_metacarpal_r"  : Transform,
    "index_01_r"          : Transform,
    "index_02_r"          : Transform,
    "index_03_r"          : Transform,
    // ... (middle, ring, pinky 동일 구조)
  }

  left_hand : {
    // 오른손과 동일 구조, suffix = _l
  }
}

Transform {
  location : (x, y, z)               // 로컬 위치 (cm)
  rotation : (pitch, yaw, roll)      // 로컬 회전 (도, Euler)
  scale    : (x, y, z)               // 기본값 (1.0, 1.0, 1.0)
}
```

### 3.4 관절별 ROM 제약 (IK 솔버 내부 적용)

| 관절 | 굴곡 | 신전 | 내외전 | 비고 |
|------|------|------|--------|------|
| MCP (검지~새끼) | 0°~90° | 0°~20° | ±20° | |
| PIP (검지~새끼) | 0°~100° | 0°~10° | 없음 | |
| DIP (검지~새끼) | 0°~80° | 0°~5° | 없음 | |
| 엄지 CMC | 0°~50° | 0°~50° | ±40° | 대립 운동 포함 |
| 엄지 MCP | 0°~60° | 0° | 없음 | |
| 엄지 IP | 0°~80° | 0°~5° | 없음 | |
| Wrist (hand_r/l) | — | — | — | Yaw/Roll은 Interface A 가이드값 사용 |

ROM 위반 시 Jacobian 비용 함수에 **Soft Constraint 패널티** 항 추가 적용 (경계 근접 시 비용 급증).

### 3.5 다중 손가락 동시 처리

동일 `start_ms`에 여러 손가락이 동시에 눌리는 경우(화음):

```
같은 hand, 같은 timestamp → 한 프레임에 복수의 End Effector Target을 동시 설정
→ Jacobian IK를 각 End Effector별로 독립 계산 후
→ 손가락 간 충돌(겹침) 검사 → 충돌 발생 시 우선순위 적용
   우선순위: MELODY > BASS > INNER
```

---

## 4. Interface C — 03_Skinning → 04_Main

### 4.1 전달 방식

- **포맷**: UE5 Material Instance + Render Target / Vertex Buffer
- **처리 단위**: 프레임 단위
- **좌표계**: UE5 월드 좌표 (cm 단위)

### 4.2 전달 데이터 구성

| 데이터 | 형식 | 설명 |
|--------|------|------|
| Skeletal Animation | AnimSequence (Joint Transform) | IK 결과를 그대로 전달 |
| Vertex Displacement | Per-vertex `(Δx, Δy, Δz)` | PBD 기반 조직 변형 오프셋 (cm) |
| Skin Texture | Texture2D (4K) | 피부 기본 색상 및 질감 (Albedo) |
| Normal Map | Texture2D (4K) | 관절 굴곡에 따른 주름 표현 |
| Vein Map | Texture2D (2K) | 핏줄 등 피하 조직 가시화 |
| Tension Value | float (per-vertex, 0.0~1.0) | 관절 압축·신장 강도 → Shader 입력 |

### 4.3 Tension Value 계산

Tension Value는 각 관절의 굴곡 각도를 기반으로 산출하며, Shader에서 Normal Map 강도 및 주름 표현에 사용된다.

```
굴곡 각도 → Tension Value 매핑:
  tension = clamp( (θ - θ_rest) / θ_max, 0.0, 1.0 )
    θ       : 현재 관절 굴곡 각도 (도)
    θ_rest  : 휴식 자세 각도 (기본 0°)
    θ_max   : 해당 관절 최대 굴곡 ROM (예: PIP = 100°)

tension → Shader 적용:
  · tension ≥ 0.6 : Normal Map 강도 증가 (주름 강조)
  · tension ≤ 0.2 : 피부 신장 표현 (Vein Map 가시성 증가)
```

> **미확정**: θ_rest 및 매핑 함수의 구체적 수치는 03_Skinning 파트와 협의 필요.

### 4.4 Vertex Displacement 포맷

```
VertexDisplacement {
  vertex_id : int          // Skeletal Mesh 버텍스 인덱스
  delta     : (Δx, Δy, Δz) // 변형 오프셋 (로컬 좌표, cm)
  timestamp : float        // 해당 프레임 시각 (ms)
}
```

> **미확정**: Buffer 방식(CPU → GPU 매 프레임 업로드) vs Texture 방식(Displacement Map) 중 전달 방식 결정 필요.

### 4.5 Shader 처리 흐름

```
[입력]
  Joint Transform (IK 결과)
  Vertex Displacement (PBD 변형)
        │
        ▼
  Skinning 계산
  (LBS + PBD Offset 합산 → 최종 Vertex Position)
        │
        ▼
  Texture Mapping
  (Skin Albedo / Vein Map UV 적용)
        │
        ▼
  Normal Map + Tension 보정
  (tension 값에 따라 주름 Normal 강도 동적 조절)
        │
        ▼
  PBR Shading
  (Roughness / Specular 계산)
        │
        ▼
[출력] 최종 렌더링 픽셀 → 04_Main 뷰포트
```

---

## 5. 파트 간 인터페이스 요약

| 인터페이스 | 송신 | 수신 | 포맷 | 핵심 전달 데이터 |
|-----------|------|------|------|----------------|
| A | 01_Fingering | 02_IK | JSON | 손가락 번호·건반 위치·손목 각도·타이밍 |
| B | 02_IK | 03_Skinning | UE5 AnimSequence | 관절별 위치·회전 시퀀스 (30fps) |
| C | 03_Skinning | 04_Main | Material / Buffer | Vertex Displacement·Texture·Tension |

---

## 6. 미확정 사항 (팀 내 협의 필요)

| # | 항목 | 관련 파트 | 현재 상태 |
|---|------|----------|----------|
| 1 | `MAX_KEY_TRAVEL` 수치 (건반 최대 누름 깊이) | A / 01, 02 | 1.0 cm 가정, 미합의 |
| 2 | pitch → X좌표 변환 기준 원점 위치 | A / 01, 02 | 88키 왼쪽 끝(A0) 기준 가정 |
| 3 | Vertex Displacement 전달 방식 | B→C / 02, 03 | Buffer vs Texture 미결정 |
| 4 | Tension Value 매핑 함수 수치 | C / 03 | θ_rest, 매핑 계수 미정의 |

---

*문서 종료*
