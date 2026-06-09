# [최종 종합 보고서] 피아노 연주 시뮬레이션을 위한 지능형 운지법 및 고정밀 물리 기반 렌더링 시스템
## (PROJECT FINAL REPORT: Intelligent Fingering and High-Fidelity Physics-based Rendering for Piano Simulation)

**과제명**: 졸업프로젝트 3201 (2팀)
**작성일**: 2026년 6월 9일
**팀원**: 정근녕(운지법), 한승현(IK), 이수민(셰이더/통합), 곽경민(피부 시뮬레이션)

---

## 1. 프로젝트 개요 (Project Overview)

### 1.1 배경 및 필요성
현대 캐릭터 애니메이션 기술은 비약적으로 발전하였으나, 피아노 연주와 같이 극도로 정교하고 빠른 손가락의 움직임을 재현하는 데에는 여전히 기술적 한계가 존재한다. 기존의 대다수 시뮬레이션은 단순한 Linear Blend Skinning(LBS) 방식에 의존하고 있어, 관절이 깊게 굽혀질 때 발생하는 'Candy Wrapper Artifact'(관절 뭉개짐 현상)와 피부의 부피 보존 실패 문제를 해결하지 못하고 있다. 또한, MIDI 데이터로부터 실제 피아니스트의 복잡한 운지법(Fingering)을 자동화하여 생성하고, 이를 해부학적으로 타당한 물리적 변형으로 연결하는 통합 파이프라인의 부재로 인해 고품질 시뮬레이션 제작에 막대한 수동 작업이 소요되어 왔다.

### 1.2 연구 목표 및 핵심 기능
본 프로젝트는 MIDI 입력을 시작으로 최적의 운지법을 결정하고, 이를 역운동학(IK)으로 변환하여 최종적으로 물리 기반의 피부 변형(Skinning)과 고품질 렌더링까지 이어지는 **End-to-End 자동화 파이프라인** 구축을 목표로 한다.
1.  **MIDI-to-Motion**: MIDI 데이터를 파싱하여 최적의 운지법(IK)을 계산하고 애니메이션화.
2.  **High-Fidelity Rendering**: Tension Map 기반의 동적 노멀 맵 변화를 활용한 주름 렌더링 및 Chaos Flesh PBD 시뮬레이션.

---

## 2. 시스템 요구사항 및 설계 (Requirements & Design)

### 2.1 기능적 요구사항 (Functional Requirements)
- **UC-01: MIDI 파싱**: Format 0/1 지원, 템포 기반 절대 시간(ms) 변환, 피아노 트랙 자동 선별.
- **UC-02: 손 모델 프리셋**: 성인 남/여, 아동 프리셋 지원 및 관절 가동 범위(ROM) 파라미터 로드.
- **UC-03: 시뮬레이션 및 렌더링**: Jacobian IK 연산, Chaos Flesh 변형, 텐션맵 기반 셰이딩.
- **UC-04: 영상 캡처**: Movie Render Queue를 통한 고해상도 연주 영상 출력.

### 2.2 비기능적 요구사항 (Non-Functional Requirements)
- **성능**: 실시간 30 FPS 이상의 렌더링 유지 (RTX 3080 기준 8ms 이내 프레임 타임).
- **정확도**: 실제 피아니스트 운지법과 85% 이상의 일치율 확보.
- **안정성**: Jacobian 특이점 회피를 위한 DLS 적용 및 IK Flip 현상 방지.

---

## 3. 전체 시스템 아키텍처 및 인터페이스 (Architecture & Interfaces)

### 3.1 처리 파이프라인 (Processing Pipeline)
전체 시스템은 4개 파트로 구성되며, 각 파트는 이전 파트의 출력을 입력으로 받아 처리한다.
1.  **01_Fingering**: MIDI 파서 + 운지법 DP 엔진.
2.  **02_IK**: Jacobian DLS IK 솔버 + Bone 애니메이션 생성.
3.  **03_Skinning**: Chaos Flesh PBD + Tension Map Shader.
4.  **04_Main (UE5)**: 카메라/UI + 최종 시퀀서 렌더링.

### 3.2 인터페이스 명세 (Inter-Module Data Interface)
- **Interface A (Fingering → IK)**: JSON 포맷. `pitch`, `start_ms`, `finger`, `wrist_yaw_deg` 등을 포함.
- **Interface B (IK → Skinning)**: UE5 AnimSequence. 30 FPS 기준의 Joint Transform 시퀀스.
- **Interface C (Skinning → Main)**: Material Instance & Render Target. Tension Value 및 Vertex Displacement.

---

## 4. 지능형 운지법 결정 엔진 (Intelligent Fingering Engine)

### 4.1 V5 Polyphonic 분석 로직
본 엔진은 단순 피치 분리를 넘어 음악적 성부(Voice)를 분석하여 운지법을 결정한다.
- **Hand Splitter**: 트랙 이름 매핑 및 피치 밀도 히스토그램 최저점 탐색을 통한 양손 자동 분리.
- **Voice Leading**: 화음 내 음표를 `MELODY` (최고음), `BASS` (최저음), `INNER` (내성)로 분류하여 성부별 손가락 선호도 부여.

### 4.2 Chord-based Dynamic Programming (DP)
- **상태 정의**: 화음 인덱스 $i$에서의 손가락 배정 튜플 $F = (f_1, f_2, ..., f_k)$.
- **비용 함수 ($Total Cost$):**
  - **SpanPenalty**: 손가락 쌍별 가동 범위(`MAX_SPAN`) 초과 시 **+5,000** 패널티.
  - **CrossingPenalty**: 엄지(1번) 외 손가락 교차 시 **+2,000** 패널티.
  - **ArpeggioRolling**: 단음 구간 방향성(상행/하행)에 따른 손가락 순서 비용 (+35).
  - **SimultaneousConflict**: 유지 중인 음표와 손가락 중복 사용 시 **+2,500**.

### 4.3 손목 물리 모델링 (Wrist Physics)
- **Wrist Yaw**: 건반 위치와 손가락 오프셋을 고려한 좌우 회전각(±35°).
- **Wrist Roll**: 흑건 타건 시 발생하는 손목 기울기(±20°).

---

## 5. 역운동학(IK) 및 모션 합성 (Kinematic Motion Synthesis)

### 5.1 관절 계층 및 생리적 ROM 제약
MetaHuman 기반 17개 관절에 대해 해부학적 한계를 엄격히 적용한다.
- **MCP**: 굴곡 0°~90°, 신전 0°~20°, 내외전 ±20°.
- **엄지(CMC)**: 대립(Opposition) 운동 포함 3축 회전 및 축회전(0°~15°).

### 5.2 Jacobian Damped Least Squares (DLS) IK
- **수학적 모델**: $\Delta \theta = J^T (J J^T + \lambda^2 I)^{-1} \Delta e$
- **안정성**: Damping $\lambda = 0.05$를 적용하여 특이점 부근의 발산을 억제.
- **궤적 생성**: 2차 베지어 곡선을 이용한 아치형 타건 경로 생성으로 자연스러운 타건감 모사.

### 5.3 클래스 구조 (Architecture)
- **`HelloTriangleApplication`**: 메인 클래스 (IK 연산 트리거 및 렌더링).
- **`Finger` / `Joint`**: 손가락 계층 구조 및 ROM 제약 관리.

---

## 6. 고품질 디테일 스키닝 및 렌더링 (High-Fidelity Skinning)

### 6.1 Chaos Flesh (PBD) 물리 시뮬레이션
- **Tetrahedral Mesh**: 내부 볼륨 사면체 생성 및 **85% 정점 최적화** (40,128 $\rightarrow$ 6,147).
- **Collision**: 손가락 마디별 17개 Capsule 콜리전 배치를 통한 피부 관통 방지.
- **Dataflow**: Geometry 생성 및 시뮬레이션 물성(탄성, 댐핑) 설정을 위한 그래프 구성.

### 6.2 텐션맵(Tension Map) 기반 디테일
- **구동 메커니즘**: 관절 굴곡 각도 $\theta$ 기반 Tension Value (0.0~1.0) 산출.
- **Procedural Displacement**:
  - **주름(Wrinkle)**: 텐션맵 신호에 따른 다중 사인 파형 중첩 WPO 생성.
  - **핏줄(Vein)**: 텐션 가중치를 곱한 핏줄 맵 융기 표현.
- **Nanite Tessellation**: 저밀도 표면에서 엔진 기능을 활용한 기하 디테일 보완.

### 6.3 커스텀 렌더 파이프라인 (SVE & RDG)
- **Pipeline Insertion**: 톤매핑 단계 이후 SVE를 통한 커스텀 패스 삽입.
- **Compute Shader**: 본 매트릭스 SBO 연동을 통한 고속 GPU 스키닝 처리.

---

## 7. 결과 분석 및 결론 (Evaluation & Conclusion)

### 7.1 실험 결과
- **정확도**: 실제 연주(드뷔시 '달빛')와 비교 분석 결과 **85% 이상의 운지 일치율** 확인.
- **물리적 타당성**: 비정상적 화음 스팬 발생율 **0.0%** 달성.
- **성능**: RTX 3080 환경에서 30 FPS 이상의 안정적인 시뮬레이션 및 렌더링 확인.

### 7.2 한계점 및 향후 과제
- **버전 호환성**: UE 5.5 및 5.6 간의 Flesh 컴포넌트 API 변경에 따른 통합 이슈 해결 필요.
- **고도화**: 아르페지오 구간 Thumb-under 자동 감지 보상 및 딥러닝 기반 운지 예측 모델 연동.

### 7.3 결론
본 프로젝트는 피아노 연주 시뮬레이션의 난제들을 알고리즘(DP), 수학(Jacobian), 물리(PBD), 그래픽스(Custom Shader) 기술의 융합을 통해 성공적으로 해결하였다. 본 시스템은 향후 정교한 디지털 휴먼 상호작용 및 음악 교육 플랫폼의 핵심 기술로 기여할 것으로 기대된다.

---
**[부록: 상세 설계 데이터]**
- **Span Constraints**: (1,2):12, (2,3):6, (3,4):5, (4,5):6, (1,5):17 (반음 단위)
- **Wrist Offset**: Finger 1: ±4, 2: ±2, 3: 0, 4: ±2, 5: ±4
- **IK Target Mapping**: `thumb_03_r`, `index_03_r` 등 메타휴먼 본 이름 매핑 규격 준수.

**[문서 종료]**
