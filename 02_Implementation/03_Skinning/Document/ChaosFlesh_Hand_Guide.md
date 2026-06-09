# Chaos Flesh 손 적용 가이드
> 프로젝트: Chaos_Flesh_Muscle | 대상 메시: fbx_Clean | UE 5.6 기준 (5.5에서 작성, 5.6 호환 확인됨)

## 5.6 버전 호환성 참고

- 전체 워크플로우(Flesh Asset → Dataflow → Blueprint) 구조는 동일합니다.
- Dataflow 그래프의 **일부 노드 이름**이 5.5 대비 변경되었을 수 있습니다. 노드를 찾을 때 이름이 다르면 유사한 키워드로 검색하세요.
  - 예: `Generate Tetrahedral Mesh` → `Tet Mesh` 또는 `Build Tetrahedral Mesh` 등으로 표기될 수 있음
- 에디터 UI 레이아웃이 일부 변경되었을 수 있으나 기능은 동일합니다.
- 공식 변경 내역은 에디터 내 **Help > What's New** 또는 언리얼 공식 릴리즈 노트 참조를 권장합니다.

---

---

## 사용 에셋 목록

| 에셋 경로 | 역할 |
|-----------|------|
| `/Game/ExampleContent/NewModel/fbx_Clean` | Skeletal Mesh (전신, 손/팔 포함) |
| `/Game/ExampleContent/NewModel/fbx_Clean_Skeleton` | 스켈레톤 |
| `/Game/ExampleContent/NewModel/fbx_Clean_PhysicsAsset` | Physics Asset (Flesh 콜리전) |
| `/Game/ExampleContent/NewModel/fbx_Clean_Anim` | 피아노 애니메이션 |
| `/Game/ExampleContent/NewModel/Std_Skin_Arm_Diffuse` | 팔/손 베이스 컬러 텍스처 |
| `/Game/ExampleContent/NewModel/Std_Skin_Arm_Normal` | 팔/손 노말맵 |
| `/Game/ExampleContent/NewModel/Std_Nails_Diffuse` | 손톱 베이스 컬러 |
| `/Game/ExampleContent/NewModel/Std_Nails_Normal` | 손톱 노말맵 |

> 참고 예제: `/Game/ExampleContent/5_5_ChaosFlesh/Characters/Emil/`

---

## STEP 1 — Physics Asset 확인

Chaos Flesh는 뼈대 기반 콜리전을 사용하므로 손 본에 콜리전 바디가 있어야 합니다.

1. Content Browser에서 `fbx_Clean_PhysicsAsset` 더블클릭
2. 왼쪽 Skeleton Tree에서 다음 본들이 있는지 확인:
   - `hand_l` / `hand_r`
   - `index_01_l` ~ `index_03_l` (검지 3마디)
   - `middle_01_l` ~ `middle_03_l`
   - `ring_01_l` ~ `ring_03_l`
   - `pinky_01_l` ~ `pinky_03_l`
   - `thumb_01_l` ~ `thumb_03_l`
3. 각 손가락 본에 **Capsule Body**가 할당되어 있지 않으면:
   - 해당 본 우클릭 → **Add Body**
   - Shape Type: `Capsule`
   - 손가락 길이에 맞게 Length / Radius 조정
4. 툴바 **Compile** → **Save**

---

## STEP 2 — Flesh Asset 생성

Flesh Asset은 Skeletal Mesh의 부드러운 살 볼륨(사면체 메시)을 정의합니다.

1. Content Browser에서 `fbx_Clean` 우클릭
2. **Create > Flesh Asset** 선택
3. 저장 경로: `/Game/ExampleContent/NewModel/FleshAssets/`
4. 파일명: `FA_Hand_Flesh` 로 저장
5. 저장하면 Flesh Asset 에디터가 자동으로 열립니다

---

## STEP 3 — Flesh Asset 에디터 설정 (Dataflow Graph)

에디터 좌측은 Dataflow 그래프, 우측은 프리뷰 뷰포트입니다.

### 3-1. 입력 메시 지정

1. 그래프에서 `Import Skeletal Mesh` 노드 확인
2. **Skeletal Mesh** 슬롯에 `fbx_Clean` 연결

### 3-2. 사면체 메시 생성 (Tetrahedral Mesh)

1. 빈 공간 우클릭 → `Generate Tetrahedral Mesh` 노드 추가
2. Import 노드의 출력을 연결
3. 파라미터 설정:
   - **Minimum Tet Volume**: `0.5` (너무 작으면 불안정)
   - **Max Element Count**: `5000` (전신 메시라 높게 설정)
   - **Mesh Selection** (중요): Bone Filter에서 손/팔 본만 선택
     - `hand_l`, `lowerarm_l`, `upperarm_l` 체크
     - 불필요한 부위(머리, 몸통, 다리)는 제외 → 성능 절약
4. **Generate** 버튼 클릭 → 뷰포트에 초록색 Tet Mesh가 표시되면 성공

> 전신 메시 전체에 Tet Mesh를 생성하면 퍼포먼스가 크게 저하됩니다.
> 반드시 손/팔 영역만 선택하세요.

### 3-3. Kinematic Binding (뼈대 연결)

1. `Set Kinematic Particles` 노드 추가
2. Tet Mesh 노드 출력 연결
3. **Kinematic Threshold**: `0.1` (값이 낮을수록 더 많은 버텍스가 뼈에 고정됨)
4. 손가락 끝마디 본들을 Kinematic으로 설정 → 애니메이션에 정확히 추종

### 3-4. PBD 시뮬레이션 파라미터

1. `Set Simulation Params` 노드 추가
2. 아래 값으로 설정 시작 (이후 뷰포트에서 튜닝):

| 파라미터 | 권장 초기값 | 설명 |
|----------|------------|------|
| Edge Stiffness | `0.8` | 살 탄성 (높을수록 딱딱함) |
| Volume Stiffness | `0.6` | 부피 보존 강도 |
| Damping | `0.05` | 진동 감쇠 |
| Gravity Scale | `0.0` | 손은 중력 영향 최소화 |
| Density | `1000.0` | 피부/근육 밀도 (kg/m³) |

3. 툴바 **Play Simulation** 으로 미리 확인
4. 뷰포트에서 살이 자연스럽게 흔들리면 **Save**

---

## STEP 4 — 머티리얼 설정 (팔/손)

### 4-1. 머티리얼 인스턴스 생성

1. Content Browser에서 빈 공간 우클릭 → **Material** 생성
2. 이름: `M_Hand_Flesh`
3. 저장 경로: `/Game/ExampleContent/NewModel/Materials/`

### 4-2. 머티리얼 노드 연결

Material Editor에서:

```
[Std_Skin_Arm_Diffuse] → Base Color
[Std_Skin_Arm_Normal]  → Normal
                0.8    → Roughness
                0.0    → Metallic
[Std_Skin_Arm_Diffuse] → Subsurface Color  (Shading Model: Subsurface 설정 시)
```

4. 상단 Details > **Shading Model**: `Subsurface` 또는 `Skin` 으로 변경 (피부 SSS 효과)
5. **Apply → Save**

### 4-3. 손톱 머티리얼 (별도)

1. 머티리얼 `M_Nails` 생성
2. `Std_Nails_Diffuse` → Base Color
3. `Std_Nails_Normal` → Normal
4. Roughness: `0.3`, Metallic: `0.0`

---

## STEP 5 — 캐릭터 블루프린트 생성

1. Content Browser 우클릭 → **Blueprint Class** → `Character` 선택
2. 이름: `BP_PianoHand`
3. 저장 경로: `/Game/ExampleContent/NewModel/Blueprints/`

---

## STEP 6 — 블루프린트 컴포넌트 구성

`BP_PianoHand` 더블클릭 → Components 탭에서:

### 6-1. Skeletal Mesh Component 설정

1. 기존 `Mesh (SkeletalMesh)` 선택
2. Details 패널:
   - **Skeletal Mesh**: `fbx_Clean`
   - **Animation Mode**: `Use Animation Asset`
   - **Anim to Play**: `fbx_Clean_Anim`
   - **Looping**: 체크

### 6-2. Flesh Component 추가

1. Components 탭 상단 **+ Add** 클릭
2. `Chaos Flesh Component` 검색 후 추가
3. 이름: `FleshComponent`
4. Details 패널:
   - **Flesh Asset**: `FA_Hand_Flesh` (STEP 2에서 생성한 것)
   - **Skeletal Mesh Component**: `Mesh` (위에서 설정한 Skeletal Mesh)
   - **Enable Simulation**: 체크

### 6-3. Flesh Component 위치 설정

- FleshComponent를 Mesh의 **자식(Child)** 으로 드래그
- Transform은 (0, 0, 0) 유지

---

## STEP 7 — Animation Blueprint 연결 (선택)

기본 애니메이션(`fbx_Clean_Anim`) 재생만 원하면 STEP 6의 설정으로 충분합니다.
더 정밀한 제어(블렌딩, 스테이트 머신 등)가 필요하면:

1. Content Browser 우클릭 → **Animation Blueprint** 생성
2. **Skeleton**: `fbx_Clean_Skeleton` 선택
3. AnimGraph에서:
   - `Sequence Player` 노드 → `fbx_Clean_Anim` 연결
   - `Output Pose`에 연결
4. BP_PianoHand의 Mesh → Animation Mode: `Use Animation Blueprint`로 변경

---

## STEP 8 — 레벨에 배치 및 시뮬레이션 확인

1. BP_PianoHand를 레벨에 드래그 앤 드롭
2. 에디터 툴바 **Play (Alt+P)**
3. 피아노 치는 손가락 움직임에 맞춰 손등/손바닥 살이 자연스럽게 밀리는지 확인

### 확인 체크리스트

- [ ] 손가락이 애니메이션대로 움직이는가
- [ ] Flesh가 손 움직임에 따라 부드럽게 변형되는가
- [ ] Tet Mesh가 스켈레탈 메시 표면을 벗어나지 않는가
- [ ] 시뮬레이션이 불안정하게 폭발(explode)하지 않는가

---

## 트러블슈팅

| 증상 | 원인 | 해결 |
|------|------|------|
| Flesh가 전혀 움직이지 않음 | FleshComponent의 Skeletal Mesh 참조 누락 | STEP 6-2 재확인 |
| 살이 폭발적으로 튀어나옴 | Edge Stiffness가 너무 낮음 | `0.9` 이상으로 올림 |
| 손가락 끝이 이상하게 늘어남 | Kinematic Threshold 너무 높음 | `0.05` 이하로 낮춤 |
| 퍼포먼스가 너무 낮음 | 전신 Tet Mesh | STEP 3-2에서 Bone Filter 재설정 |
| 메시가 안 보임 | 머티리얼 미할당 | FleshComponent Details > Materials 확인 |

---

## 다음 단계 (핏줄/주름 추가 시)

현재는 기본 Flesh 시뮬레이션만 적용된 상태입니다.
향후 텐션맵 기반 핏줄/주름 추가 시:

1. 핏줄 Normal Map 제작 (Substance Painter 또는 Photoshop)
2. 머티리얼에 `GetFleshTension` 머티리얼 함수 추가
3. 텐션값으로 기본 Normal ↔ 핏줄 Normal 블렌딩
4. `Std_Skin_Arm_ResourceMap_WSNormal.png` 임포트 후 추가 활용

---

작성일: 2026-05-09 | 작성 기준: UE 5.5 | 적용 버전: UE 5.6
