# [최종 보고서] 피아노 연주 시뮬레이션을 위한 고정밀 운지법 및 물리 기반 피부 변형 시스템
## (Intelligent Piano Fingering and Physics-based Skin Deformation System)

**과제명**: 졸업프로젝트 3201 (2팀)
**일시**: 2026년 6월 9일
**팀원**: 정근녕, 한승현, 이수민, 곽경민

---

## 1. 서론 (Introduction)

### 1.1 연구 배경 및 필요성
현대 캐릭터 애니메이션 기술은 비약적으로 발전하였으나, 피아노 연주와 같이 극도로 정교하고 빠른 손가락의 움직임을 재현하는 데에는 여전히 기술적 한계가 존재한다. 기존의 대다수 시뮬레이션은 단순한 Linear Blend Skinning(LBS) 방식에 의존하고 있어, 관절이 깊게 굽혀질 때 발생하는 'Candy Wrapper Artifact'(관절 뭉개짐 현상)와 피부의 부피 보존 실패 문제를 해결하지 못하고 있다. 또한, MIDI 데이터만으로 실제 피아니스트의 복잡한 운지법(Fingering)을 자동화하여 생성하고, 이를 해부학적으로 타당한 물리적 변형으로 연결하는 통합 파이프라인은 현재 공백 상태에 가깝다.

### 1.2 연구 목표
본 프로젝트는 MIDI 입력을 시작으로 최적의 운지법을 결정하고, 이를 역운동학(IK)으로 변환하여 최종적으로 물리 기반의 피부 변형(Skinning)과 고품질 렌더링까지 이어지는 **End-to-End 자동화 파이프라인** 구축을 목표로 한다.
1.  **지능형 운지법 생성**: 동적 계획법(DP)을 활용해 성부별 음악적 맥락을 고려한 최적의 손가락 배정.
2.  **정밀 모션 합성**: Jacobian Damped Least Squares(DLS) 기반의 IK 솔버를 통한 자연스러운 타건 및 궤적 생성.
3.  **물리 기반 피부 표현**: Chaos Flesh(PBD)를 통한 볼륨 보존 및 텐션맵 기반의 동적 주름/핏줄 렌더링.

---

## 2. 전체 시스템 아키텍처 (System Architecture)

### 2.1 전체 파이프라인 개요
전체 시스템은 4개의 핵심 모듈로 구성되며, 각 모듈은 독립적인 연산을 수행한 후 정해진 데이터 규격(Interface)을 통해 다음 단계로 정보를 전달한다.

1.  **Module 1 (01_Fingering)**: MIDI 파일을 분석하여 각 음표에 손가락 번호(1~5)와 손목 회전각(Yaw/Roll)을 배정한다.
2.  **Module 2 (02_IK)**: 배정된 정보를 바탕으로 손가락 끝(End-effector)의 목표 3D 좌표를 계산하고, IK 연산을 통해 관절별 Transform 시퀀스를 생성한다.
3.  **Module 3 (03_Skinning)**: IK 결과를 바탕으로 Chaos Flesh 물리 시뮬레이션을 수행하고, 텐션 정보를 커스텀 셰이더로 전달하여 미세 디테일을 표현한다.
4.  **Module 4 (04_Main)**: Unreal Engine 5 환경에서 카메라 제어, UI 및 최종 영상 출력을 담당한다.

### 2.2 데이터 인터페이스 명세 (Data Interfaces)

#### [Interface A] 01_Fingering → 02_IK (JSON)
IK 솔버가 사전 계산(Offline)을 수행할 수 있도록 밀리초(ms) 단위의 정밀 데이터를 전달한다.
- `pitch`: MIDI 음고 (21~108)
- `start_ms / duration_ms`: 시간 정보
- `finger`: 배정 손가락 (1~5)
- `wrist_yaw_deg / wrist_roll_deg`: 손목 회전 가이드값 (±35° / ±20°)
- `pressure`: velocity 기반 타건 강도 (0.0~1.0)

#### [Interface B] 02_IK → 03_Skinning (AnimSequence)
관절별 9개의 자유도(DoF)를 포함한 30 FPS 기준의 Transform 데이터셋을 전달한다. UE5 MetaHuman Skeletal Mesh 규격을 준수한다.

---

## 3. 지능형 운지법 결정 엔진 (Intelligent Fingering Engine)

### 3.1 V5 Polyphonic Voice Leading 알고리즘
본 엔진은 단순한 피치 기반 분리를 넘어 음악적 성부(Voice)를 분석하는 V5 엔진을 채택하였다.

#### 3.1.1 MIDI 파싱 및 성부 태깅
- **Hand Splitter**: 트랙 이름 키워드(Left/Right) 및 피치 밀도 히스토그램을 분석하여 양손을 자동 분리한다. 특히 교차(Crossing) 구간에서의 논리적 일관성을 위해 윈도우 기반 밀도 탐색을 수행한다.
- **Role Tagging**: 화음 내에서의 상대적 위치를 분석하여 `MELODY` (최고음), `BASS` (최저음), `INNER` (내성) 역할을 부여한다.

#### 3.1.2 Chord-based Dynamic Programming
개별 음표가 아닌 **30ms 이내의 화음 그룹(Chord Group)**을 하나의 상태(State)로 처리한다.
- **상태 정의**: 화음 내 $k$개 음표에 대한 손가락 배정 조합 $F = (f_1, f_2, ..., f_k)$.
- **Monotonicity 제약**: 오른손의 경우 피치 상승 시 손가락 번호도 반드시 상승해야 하며($f_i < f_{i+1}$), 왼손은 그 반대($f_i > f_{i+1}$)를 강제하여 물리적 꼬임을 원천 차단한다.

### 3.2 비용 함수 (Cost Function) 상세 설계
최적의 경로는 다음 6가지 비용의 가중합($\sum W$)이 최소가 되는 지점으로 결정된다.

1.  **WristMove Cost ($W_{move}$)**: 이전 화음의 손목 위치 대비 현재 위치의 변화량. 불필요한 좌우 이동을 억제한다.
2.  **Span Penalty ($P_{span}$)**: 해부학적 한계(`MAX_SPAN`)를 초과하는 손가락 쌍에 대해 막대한 패널티를 부여한다. (예: 2-3번 손가락 사이 6반음 초과 시 +5,000점)
3.  **Role Affinity ($W_{role}$)**: 멜로디 성부는 4, 5번 손가락을 선호하고, 1번(엄지)을 기피하도록 보너스/패널티를 부여한다.
4.  **Black Key Penalty ($P_{black}$)**: 엄지(1번)가 짧은 특성상 흑건을 누를 때 발생하는 손목의 깊은 진입을 억제하기 위한 가중치.
5.  **Simultaneous Conflict**: 유지(Sustain) 중인 음표가 사용하는 손가락을 재사용하려 할 때 발생하는 패널티.
6.  **Crossing Penalty**: 엄지 밑으로 넘기기(Thumb-under) 외의 비정상적 손가락 교차 차단.

### 3.3 손목 물리 모델 및 시뮬레이션 결과
- **Wrist Yaw/Roll**: 타건하는 손가락들의 상대적 오프셋을 계산하여 Yaw(±35°)를 산출하고, 흑건 사용 여부에 따라 Roll(±20°)을 결정한다.
- **실연 비교 결과**: 드뷔시 '달빛' 분석 시 실제 연주자의 손목 회전 양상 및 손가락 번호 배정과 **85% 이상의 높은 일치율**을 보였다. 특히 아르페지오 구간에서의 손목 가이드 데이터는 IK 모션의 자연스러움에 핵심적인 기여를 하였다.

---
*(이어서 4장 IK 및 5장 Skinning 섹션이 작성될 예정입니다)*
