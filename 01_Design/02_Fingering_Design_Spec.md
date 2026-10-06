# 운지법 엔진 설계 명세서 (Fingering Engine Design Specification)

**프로젝트**: PianoHandSimulator — `01_Fingering` 모듈
**버전**: V5 Polyphonic
**작성일**: 2026년 5월 25일

---

## 1. 목적 및 범위

본 문서는 `piano_fingering_engine.py` (V5)의 설계를 공식적으로 명세한다.
MIDI 데이터를 입력으로 받아 각 음표에 손가락 번호·손목 회전각을 배정하고, UE5 IK 애니메이션 구동을 위한 JSON을 출력하는 전 과정을 대상으로 한다.

---

## 2. 시스템 구조

### 2.1 처리 파이프라인

```
┌─────────────┐
│  MIDI 파일   │
└──────┬──────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Module 1: MIDI Parser               │
│  parse_midi_to_hand_chords()         │
│  · 전 트랙 set_tempo → 템포맵 구성   │
│  · tick → ms 변환 (구간 누적)        │
│  · pitch별 FIFO (재타격 보존)        │
│  · 88키 범위 밖 음표 제외            │
│  · 트랙 이름 → 손 분류               │
│  · 피치 밀도 최저점 → 동적 분리      │
│  · 30ms 그룹화 → 화음 구성          │
│  · 동일 pitch 중복 병합              │
│  · MELODY / BASS / INNER 태깅        │
└──────────────────┬───────────────────┘
                   │  hand_chords: {0: [[NoteEvent...]], 1: [...]}
                   ▼
┌──────────────────────────────────────┐
│  Module 2: Hand Splitter             │
│  split_wide_chords_between_hands()   │
│  · while 루프: split → merge 반복   │
│  · is_chord_playable() 로 가능성 판정│
│  · 불가 시 반대 손 이관 or drop      │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  Module 3: DP Solver                 │
│  solve_fingering_chord_dp()          │
│  · 화음 단위 상태 공간 탐색          │
│  · 6종 비용 함수 합산               │
│  · 역추적으로 최적 경로 확정         │
└──────────────────┬───────────────────┘
                   │  NoteEvent.finger 배정 완료
                   ▼
┌──────────────────────────────────────┐
│  Module 4: Wrist Physics             │
│  calculate_wrist_rotation_rom()      │
│  · Yaw: 건반 위치 vs 손가락 오프셋  │
│  · Roll: 흑건 담당 손가락 여부       │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│  Module 5: Key Hold & Pedal          │
│  parse_pedal_spans()                 │
│  apply_key_hold_and_pedal()          │
│  · CC64 페달 구간 추출               │
│  · key_hold_ms = 손가락 점유 시간    │
│    (소리 지속 duration_ms 와 분리)   │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌─────────────┐
│  JSON 출력   │  → UE5 IK 입력
└─────────────┘
```

### 2.2 모듈 인터페이스 명세

| 함수 | 입력 | 출력 | 부수 효과 |
|------|------|------|----------|
| `parse_midi_to_hand_chords(file_path)` | MIDI 파일 경로 | `{0: chord_list, 1: chord_list}` | NoteEvent.role 태깅 |
| `split_wide_chords_between_hands(hand_chords)` | hand_chords dict | hand_chords dict (수정됨) | NoteEvent.hand 재배정 가능 |
| `solve_fingering_chord_dp(chord_sequence, hand_id)` | 화음 리스트, 손 ID | 없음 | NoteEvent.finger 배정 |
| `calculate_wrist_rotation_rom(chord_group, hand_id)` | 화음 그룹, 손 ID | `(yaw_deg, roll_deg)` | 없음 |
| `is_chord_playable(chord, hand_id)` | 화음, 손 ID | `bool` | 없음 |
| `parse_pedal_spans(file_path)` | MIDI 파일 경로 | `[(start_ms, end_ms)]` | 없음 |
| `apply_key_hold_and_pedal(all_notes, pedal_spans)` | 음표 리스트, 페달 구간 | 보정 건수 | NoteEvent.key_hold_ms / pedal_down 설정 |
| `analyze_polyphonic(file_path)` | MIDI 파일 경로 | 없음 | JSON 파일 저장 |

---

## 3. 핵심 데이터 구조

### 3.1 NoteEvent

```
NoteEvent
├── pitch          : int      # MIDI 음고 (21~108)
├── velocity       : int      # 타건 강도 (0~127)
├── start_ms       : float    # 시작 시각 (ms)
├── duration_ms    : float    # 지속 시간 (ms)
├── hand           : int      # 0=왼손, 1=오른손, -1=미분류
├── finger         : int      # 배정 손가락 (1~5), 초기값 0
├── role           : str      # "MELODY" | "BASS" | "INNER"
├── is_black       : bool     # 흑건 여부
├── pressure       : float    # velocity / 127.0
├── key_depth      : float    # 건반 누름 깊이 (애니메이션용)
├── key_hold_ms    : float    # 손가락이 건반을 누르고 있는 시간 (운지 확정 후 산출)
└── pedal_down     : bool     # 타건 시점 Sustain 페달(CC64) 상태
```

### 3.2 화음 그룹 (Chord)

- 타입: `list[NoteEvent]`
- 조건: 동일 손에서 `start_ms` 차이 < 30ms인 음표들
- 정렬: 항상 `pitch` 오름차순 유지

### 3.3 DP 상태 공간

- **상태**: 화음 인덱스 `i`에서의 손가락 배정 튜플 `f = (f₁, f₂, ..., fₖ)`
  - `fⱼ ∈ {1, 2, 3, 4, 5}`, 모든 `fⱼ` 서로 다름
  - 오른손: `f₁ < f₂ < ... < fₖ` (피치 오름차순 = 손가락 번호 오름차순)
  - 왼손: `f₁ > f₂ > ... > fₖ` (피치 오름차순 = 손가락 번호 내림차순)
- **전이**: `dp[i][f] = min over f' { dp[i-1][f'] + cost(chord[i-1], f', chord[i], f) }`
- **초기값**: `dp[0][f] = Σ FINGER_DIFFICULTY[fⱼ]`

---

## 4. 비용 함수 설계

### 4.1 전체 비용 공식

```
cost(prev_chord, prev_f, curr_chord, curr_f)
  = WristMove × 2.0
  + FingerDifficulty(curr_f)
  + BlackKeyPenalty(curr_chord, curr_f)
  + SpanPenalty(curr_chord, curr_f)
  + RoleAffinity(curr_chord, curr_f)
  + MelodyContinuity(prev_chord, prev_f, curr_chord, curr_f)
  + SimultaneousConflict(prev_chord, prev_f, curr_chord)
  + ArpeggioRolling(prev_chord, prev_f, curr_chord, curr_f)
  + CrossingPenalty(prev_chord, prev_f, curr_chord, curr_f)
```

### 4.2 항목별 수치 명세

#### SpanPenalty (해부학적 가동 범위)

화음 내 **모든 손가락 쌍** `(fᵢ, fⱼ)` (i < j) 에 대해 검사한다.
인접 쌍만 검사하면 `2-3`(6반음) · `3-5`(9반음)가 각각 통과하면서
`2-5`가 15반음(한계 12)이 되는 물리적으로 불가능한 화음이 통과한다.

손가락 쌍별 허용 최대 반음 간격:

| 손가락 쌍 | MAX_SPAN |
|----------|----------|
| (1,2) | 12 |
| (2,3) | 6 |
| (3,4) | 5 |
| (4,5) | 6 |
| (1,3) | 14 |
| (1,4) | 15 |
| (1,5) | 17 |
| (2,4) | 10 |
| (2,5) | 12 |
| (3,5) | 10 |

초과 시 항목당 **+5,000** 패널티.

#### RoleAffinity (성부별 손가락 선호)

| 성부 | 손 | 보상(-) / 패널티(+) |
|------|-----|-------------------|
| MELODY | 오른손 f=4 | −12 |
| MELODY | 오른손 f=5 | −6 |
| MELODY | 오른손 f=1 | +20 |
| MELODY | 왼손 f=1 | −12 |
| MELODY | 왼손 f=2 | −6 |
| MELODY | 왼손 f=5 | +15 |
| BASS | 오른손 f=1 | −10 |
| BASS | 왼손 f=5 | −12 |
| INNER | f∈{2,3} | −5 |

#### MelodyContinuity (레가토 연속성)

멜로디 성부 인접 음표의 피치 거리 `d = |pitch_curr − pitch_prev|`:

| 조건 | 비용 |
|------|------|
| `0 < d ≤ 2` AND 같은 손가락 | **−20** (보상) |
| `d ≥ 3` AND 같은 손가락 | **+30** (패널티) |

#### SimultaneousConflict (동시 누름 방지)

이전 화음 음표 `n`에 대해 `n.start_ms + n.duration_ms > curr_start_ms`이면 `n`에 배정된 손가락은 `busy`. 현재 화음에서 busy 손가락 재사용 시 항목당 **+2,500**.

#### ArpeggioRolling (단음 연속 방향성)

단음→단음 전환(`|prev_chord|=1`, `|curr_chord|=1`)에서:

| 조건 | 비용 |
|------|------|
| 동일 손가락 반복 | **+60** |
| 오른손: pitch 상행 AND 손가락 번호 감소 | **+35** |
| 오른손: pitch 하행 AND 손가락 번호 증가 | **+35** |
| 왼손: pitch 상행 AND 손가락 번호 증가 | **+35** |
| 왼손: pitch 하행 AND 손가락 번호 감소 | **+35** |

#### CrossingPenalty (손가락 교차 차단)

엄지(1번) 넘기기 외의 손가락 교차 시 **+2,000**.

#### FingerDifficulty & BlackKeyPenalty

| 항목 | 조건 | 비용 |
|------|------|------|
| FingerDifficulty | f=4 | +6 |
| FingerDifficulty | f=5 | +3 |
| BlackKeyPenalty | f=1 AND 흑건 | +25 |
| BlackKeyPenalty | f=5 AND 흑건 | +10 |

---

## 5. 손 분리 알고리즘 설계

### 5.1 우선순위

```
1순위: 트랙 이름 키워드 매칭 (_detect_hand_from_track_name)
   · Left 키워드: left, lh, l, bass, lower → 왼손(0)
   · Right 키워드: right, rh, r, treble, upper, melody, lead → 오른손(1)

2순위: 피치 밀도 최저점 탐색 (_find_split_pitch)
   · 피아노 연주 범위 40~80 MIDI pitch 내
   · 윈도우 크기 5 (±2반음)의 밀도 히스토그램에서 최솟값 위치
   · 해당 pitch 미만 → 왼손, 이상 → 오른손
```

### 5.2 화음 스팬 초과 처리 (split_wide_chords_between_hands)

- **기준**: 다음 둘 중 하나라도 어기면 분리 대상
  1. 한 손 화음의 최고음−최저음 > `max_span` (기본값 17반음)
  2. `is_chord_playable()` 실패 — MAX_SPAN을 모두 만족하는 손가락 조합이 **존재하지 않음**
     (예: `[43, 50, 53, 57, 60]` 은 폭 17로 1번은 통과하나,
      어떤 조합에서도 내부 쌍이 한계를 넘어 연주 불가)
- **분리 방법**: 화음 내 최대 간격 위치에서 이분(Binary Split)
- **이관 조건**:
  - 반대 손에 동일 시간대(30ms 이내) 화음 없음 → 이관
  - 있을 경우 합산 스팬 재검사 → 허용 시 이관, 초과 시 drop
- **수렴 조건**: split·merge 반복 후 모든 화음 스팬 ≤ max_span

---

## 6. 물리 제약 상수 체계

### 6.1 손목 가동 범위 (WRIST_ROM)

| 축 | 범위 | 의미 |
|----|------|------|
| Yaw | ±35.0° | 손목 좌우 회전 |
| Roll | ±20.0° | 손목 기울기 |

### 6.2 손가락-손목 오프셋 (반음 단위)

손목 중심(3번 손가락 기준)으로부터의 오프셋:

| 손가락 | 오른손 | 왼손 |
|--------|--------|------|
| 1 (엄지) | −4 | +4 |
| 2 (검지) | −2 | +2 |
| 3 (중지) | 0 | 0 |
| 4 (약지) | +2 | −2 |
| 5 (새끼) | +4 | −4 |

### 6.3 Wrist Yaw 계산

```
yaw_score = Σ [ (note.pitch − avg_pitch) − OFFSET[note.finger] ]
yaw_deg   = clamp(yaw_score × 2.5 × sign, −35.0, +35.0)
  where sign = +1 (오른손), −1 (왼손)
```

### 6.4 Wrist Roll 계산

```
roll_score = 0
if 엄지(1번)가 흑건: roll_score += 12
if 새끼(5번)가 흑건: roll_score -= 12
roll_deg = clamp(roll_score × sign, −20.0, +20.0)
  where sign = +1 (오른손), −1 (왼손)
```

---

## 7. 출력 JSON 스키마

```json
{
  "pitch":                 int,    // MIDI 음고 (21~108)
  "start_ms":              float,  // 시작 시각 (ms)
  "duration_ms":           float,  // 소리가 울리는 시간 (ms) — 페달로 늘어남
  "key_hold_ms":           float,  // 손가락이 건반을 누르고 있는 시간 (ms) ★IK 사용
  "pedal_down":            bool,   // 타건 시점 Sustain 페달 상태
  "hand":                  string, // "Left" | "Right"
  "role":                  string, // "MELODY" | "BASS" | "INNER"
  "finger":                int,    // 1~5
  "pressure":              float,  // 0.0~1.0 (velocity 기반)
  "key_depth":             float,  // 건반 누름 깊이
  "is_black":              bool,   // 흑건 여부
  "wrist_pos_normalized":  float,  // 0.0~1.0 (88키 기준 손목 위치)
  "wrist_yaw_deg":         float,  // ±35.0°
  "wrist_roll_deg":        float,  // ±20.0°
  "target_x_mm":           float,  // 건반 목표 X (mm) — piano_keyboard 모듈 산출
  "target_y_mm":           float,  // 건반 타건 접점 Y (mm)
  "target_z_mm":           float   // 건반 목표 Z (mm)
}
```

---

## 8. 알려진 설계 이슈 및 개선 계획

| # | 이슈 | 영향 | 개선 방향 |
|---|------|------|----------|
| 1 | MelodyContinuity(항목 3)와 ArpeggioRolling(항목 6)이 단음 연속 구간에서 동시 적용 | 이중 비용 발생 가능 | 단음 구간 감지 플래그로 항목 3 비활성화 |
| 2 | 성부 태깅이 화음 단위 최고/최저음 기반으로만 동작 | 멜로디 선율이 내성부로 오분류될 수 있음 | 인접 화음 간 피치 연속성 추적으로 고도화 |
| 3 | Thumb-under(엄지 넘기기) 패턴을 명시적으로 장려하는 로직 없음 | 스케일·아르페지오 구간 운지 부자연스러움 | 아르페지오 구간 자동 감지 후 Thumb-under 보상 추가 |
| 4 | 단일 트랙 MIDI에서 손 분리 정확도가 피치 밀도에 의존 | 교차하는 손 패시지에서 오분류 가능 | 음역 이력(history) 기반 손 추적 보완 |
| 5 | ~~span 제약이 화음 단위로만 적용~~ → **해결 (2026-10-06)**. 제약을 구간 겹침 기준으로 재정의하고 0~4단계를 구현했다. 전 결과 파일 하드 제약 위반 0건. 상세: `01_Design/11_Temporal_Constraint_Design.md` |
| 6 | 화음 스팬/연주 가능성 위반 시 음표를 **drop** 한다. 2026-10-06 에 집계·경고를 추가해 드러냈으나 처리 방식은 여전히 '잘라내기' | 실측 2,525개(파싱 대비 10.0%). 피아노 악보 기반 입력(`deb_clai`)은 손실 0, 밴드 편곡(`Bohemian Rhapsody`)은 32.8% | 성부 중요도 기반 선택, 또는 아르페지오 분산(롤링)으로 온셋을 미세 분할 |
| 7 | **피아노 트랙 자동 선별(요구사항 2.3) 미구현** | 밴드 편곡 MIDI에서 베이스·드럼 트랙까지 운지 대상이 됨. 88키 범위 밖 음표는 제외하지만 범위 내 비피아노 음표는 그대로 처리 | GM 프로그램 0~7 → 음역 집중도 → 노트 수 우선순위로 트랙 선별 구현 |

---

## 8-1. 해결된 이슈 (2026-10-05)

| 이슈 | 증상 | 조치 |
|------|------|------|
| 템포맵 미적용 | Format 1에서 `set_tempo`가 음표 트랙에 반영되지 않아 타이밍 58.7% 오차 (드뷔시 '달빛' 244초 → 387초) | 전 트랙 `set_tempo`를 절대 tick으로 수집해 템포맵 구성, 구간 누적시간 선계산 후 이분 탐색 변환. MIDI 13곡 오차 **0.00000 ms** |
| 재타격 음표 유실 | `active_notes[pitch]` dict 덮어쓰기로 음표 유실 (달빛 25개) | pitch별 FIFO 큐로 전환 |
| 미종료 음표 유실 | `note_off` 없이 트랙이 끝나는 음표가 버려짐 | 트랙 종료 시점으로 닫아 복구 |
| 손가락 점유 ≠ 소리 지속 | `duration_ms`를 건반 누름 시간으로 취급. 페달(CC64 327개)을 전부 무시해 한 손가락이 서로 다른 건반을 동시에 누르는 운지 111건 (최대 3000ms) | `key_hold_ms` · `pedal_down` 신설. 같은 손가락 재사용 시점에 점유 종료. **충돌 0건** |
| SpanPenalty 인접 쌍만 검사 | `2-5` 15반음(한계 12) 등 비인접 쌍 위반이 통과 | 모든 손가락 쌍 검사로 교체 |
| 화음 내 pitch 중복 | 중복 보이싱으로 같은 건반에 손가락 2개 배정 → Monotonicity·span 연쇄 붕괴 (`wii` 1427화음 중 558개) | `_dedupe_chord()` 로 병합 (velocity 큰 음표 유지, 지속은 최대값) |
| `_trim_chord` 누출 | 5음 초과분이 `finger=0` 으로 JSON에 출력 | 자른 결과를 보관하고 제외 건수를 경고 출력 |
| 분리 기준이 span 수치 | 폭 17 이내라도 어떤 조합으로도 불가능한 화음이 통과 | `is_chord_playable()` 기반 판정으로 교체 |
| 88키 범위 밖 음표 크래시 | pitch 12에서 `ValueError`로 분석 전체 중단 | 경고 출력 후 제외 |

검증: `02_Implementation/01_Fingering/tools/metrics.py` 기준 **MIDI 13곡 중 12곡 하드 제약 위반 0건**
(남은 1곡 Bohemian Rhapsody 3건은 위 이슈 5번)

---

## 9. UE5 연동 인터페이스 계획 (향후)

```
JSON 출력
    │
    ▼
Python 변환 스크립트
· JSON → UE5 DataTable 포맷 (CSV / 구조체)
· pitch → 건반 액터 매핑 테이블 참조
    │
    ▼
UE5 DataTable
    │
    ▼
AnimBP (Animation Blueprint)
· start_ms / duration_ms → 타임라인 트리거
· finger → Control Rig 본 타겟
· wrist_yaw_deg / wrist_roll_deg → IK Solver 입력
    │
    ▼
MetaHuman Hand Control Rig
```

---

*문서 종료*
