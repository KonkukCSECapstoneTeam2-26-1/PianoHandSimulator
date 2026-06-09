**텐션맵 파이프라인 구축 가이드 (진행 중)**

본 문서는 Chaos Flesh PBD 시뮬레이션의 정점 변위량을 텐션맵으로 출력하는 파이프라인 구축 과정을 단계별로 기록한 가이드입니다. UE 5.6 환경 기준이며, Deformer Graph + Material + Render Target 세 단계로 구성됩니다.

---

## 완료된 단계

### STEP 1 — M_FleshTension 머티리얼 (완료)

경로: `/Game/ExampleContent/NewModel/M_FleshTension`

노드 구성:
```
Vertex Color (R채널) → LinearInterpolate (Alpha)
Constant3Vector (0,0,1) 파랑 → LinearInterpolate (A)
Constant3Vector (1,0,0) 빨강 → LinearInterpolate (B)
LinearInterpolate 출력 → Emissive Color
```

- 낮은 변위(0) = 파랑, 높은 변위(1) = 빨강으로 시각화
- Emissive에 연결하여 라이팅 영향 없이 텐션값만 표시

---

## 남은 단계

### STEP 2 — Deformer Graph 생성 (핵심)

Chaos Flesh 시뮬레이션의 실시간 정점 변위량을 읽어 Vertex Color로 출력하는 그래프.

**생성 방법:**
1. Content Browser → `/Game/ExampleContent/NewModel/` 우클릭
2. **Animation → Deformer Graph** 선택
3. 이름: `DG_FleshVisualizer`

**노드 구성:**
```
Flesh Mesh Data Interface
  └── Get Vertex Attribute (Position)     → 현재 시뮬레이션 위치
  └── Get Vertex Attribute (RestPosition) → 초기 Rest 위치

Subtract (Position - RestPosition) → 변위 벡터
Vector Length → 변위 크기(float)
Map Range Clamped (InRangeHigh: 20.0, OutRangeHigh: 1.0) → 0~1 정규화
Write Variable (Vertex.Color R채널) → 머티리얼로 전달
```

> Epic Developer Assistant 권장 방식. UE 5.6에서 `GetFleshTension` 노드 대신 Deformer Graph 내 Flesh Mesh Data Interface를 통해 시뮬레이션 데이터에 접근.

**Skeletal Mesh에 연결:**
1. `fbx_Clean` 더블클릭 → Asset Details 패널
2. **Mesh Deformer** 슬롯 → `DG_FleshVisualizer` 할당
3. Save

---

### STEP 3 — 시각화 머티리얼 적용 확인

1. `BP_PianoHand` 열기 → `Mesh` 컴포넌트 선택
2. Details → Materials → `M_FleshTension` 할당
3. 레벨에 배치 후 Play → 손가락 움직임 시 파랑/빨강 변화 확인

---

### STEP 4 — Render Target 베이크 (4번 팀원 전달용)

#### 4-1. Render Target 생성
1. Content Browser 우클릭 → **Render Target**
2. 이름: `RT_TensionMap`
3. Size: `1024 x 1024`, Format: `RTF RGBA8`

#### 4-2. M_FleshBake 머티리얼 생성
UV 공간으로 메시를 펼쳐서 텐션값을 텍스처로 굽는 전용 머티리얼.

```
TextureCoordinate (UV.xy)
  └── 계산: (UV.x * 2 - 1, (1 - UV.y) * 2 - 1)
  └── World Position Offset에 연결 (메시를 UV 평면으로 펼침)

Tension 시각화 로직 (M_FleshTension과 동일)
  └── Emissive Color에 연결
```

#### 4-3. Blueprint 로직 (BP_PianoHand)
Event Graph에서:

```
BeginPlay
  └── Create Dynamic Material Instance (M_FleshBake)
  └── Set Material (Mesh 컴포넌트에 적용)

Event Tick (또는 타이머)
  └── Draw Material to Render Target
        ├── Texture Target: RT_TensionMap
        └── Material: 위에서 만든 Dynamic Material Instance
```

> 매 프레임 베이크가 필요 없으면 Tick 대신 타이머(0.1초 간격 등)로 성능 최적화 가능.

---

## 전체 파이프라인 요약

```
Chaos Flesh 시뮬레이션 (FA_Hand_Flesh)
        ↓
Deformer Graph (DG_FleshVisualizer)
  - 현재 위치 vs Rest 위치 비교
  - 변위량 0~1 정규화
  - Vertex Color R채널로 출력
        ↓
M_FleshTension 머티리얼
  - Vertex Color → LinearInterpolate
  - 파랑(0) → 빨강(1) 시각화
        ↓
Render Target (RT_TensionMap)
  - M_FleshBake + Draw Material to Render Target
  - UV 공간 텍스처로 베이크
        ↓
4번 팀원 전달 (테셀레이션 기반 시각화)
```

---

## 주의사항

- Deformer Graph의 Flesh Mesh Data Interface는 FleshComponent가 활성화된 상태에서만 데이터를 읽음
- Map Range의 InRangeHigh(최대 변위값)는 실제 시뮬레이션 후 튜닝 필요 (초기값 20.0)
- 2번 팀원의 피아노 애니메이션 수령 후 실제 동작에서 텐션 분포 재검증 필요

---

작성일: 2026-06-01 | 엔진 버전: UE 5.6 | 상태: STEP 1 완료, STEP 2~4 진행 예정
