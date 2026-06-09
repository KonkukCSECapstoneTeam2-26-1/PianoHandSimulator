# [최종 종합 보고서] 피아노 연주 시뮬레이션을 위한 지능형 운지법 및 고정밀 물리 기반 렌더링 시스템
## (Comprehensive Report: Intelligent Fingering and High-Fidelity Physics-based Rendering for Piano Simulation)

**과제명**: 졸업프로젝트 3201 (2팀)
**작성일**: 2026년 6월 9일
**팀원**: 정근녕(운지법), 한승현(IK), 이수민(셰이더/통합), 곽경민(피부 시뮬레이션)

---

## 1. 프로젝트 개요 (Project Overview)

### 1.1 배경 및 필요성
기존의 캐릭터 애니메이션 기술은 Linear Blend Skinning(LBS)에 의존하여 피아노 연주와 같은 정교한 동작 시 관절 뭉개짐(Candy Wrapper Artifact)과 부피 소실 문제를 해결하지 못했다. 또한, MIDI 데이터로부터 음악적 맥락과 인체 해부학적 제약을 동시에 만족하는 운지법을 자동 생성하는 통합 파이프라인의 부재로 인해 고품질 시뮬레이션 제작에 막대한 수동 작업이 소요되어 왔다.

### 1.2 목표
본 프로젝트는 MIDI 데이터를 입력받아 **지능형 운지 결정 → 정밀 모션 합성 → 물리 기반 피부 변형 → 고품질 렌더링**으로 이어지는 통합 자동화 시스템을 구축하여, 피아니스트의 연주를 공학적으로 완벽히 재현하는 것을 목표로 한다.

---

## 2. 지능형 운지법 결정 엔진 (Intelligent Fingering Engine)

### 2.1 V5 Polyphonic 분석 및 전처리
- **MIDI Parser**: Standard MIDI File (Format 0/1)을 지원하며, 틱(Tick) 단위를 템포 이벤트를 참조한 절대 시간(ms)으로 변환한다.
- **Hand Splitter**: 트랙 이름 매핑 및 피치 밀도 히스토그램을 분석하여 양손을 분리한다. 특히 화음 스팬이 17반음을 초과할 경우 지능적으로 반대 손에 이관하거나 이분(Binary Split)하는 로직을 포함한다.
- **Voice Role Tagging**: 화음 내 음표를 `MELODY`, `BASS`, `INNER`로 분류하여 성부별 음악적 특성을 부여한다.

### 2.2 Chord-based Dynamic Programming (DP)
- **상태 정의**: 화음 인덱스 $i$에서의 손가락 배정 튜플 $F = (f_1, f_2, ..., f_k)$.
- **비용 함수 ($Total Cost$):**
  - **SpanPenalty**: 손가락 쌍별 해부학적 가동 범위(`MAX_SPAN`) 초과 시 항목당 **+5,000** 패널티.
  - **RoleAffinity**: 멜로디 성부는 4, 5번 손가락 선호(보상), 1번 기피(패널티) 적용.
  - **CrossingPenalty**: 엄지(1번) 외의 손가락 교차 시 **+2,000** 패널티.
  - **MelodyContinuity**: 인접 화음 간 멜로디 라인의 수평적 연결성(Legato) 보상.

### 2.3 손목 물리 모델링
- **Wrist Yaw**: $\Sigma [ (note.pitch - avg\_pitch) - OFFSET[finger] ]$ 식을 통해 ±35° 범위의 회전각을 산출한다.
- **Wrist Roll**: 엄지나 새끼손가락의 흑건 사용 여부에 따라 ±20° 범위의 기울기를 결정하여 사실감을 극대화한다.

---

## 3. Jacobian DLS 기반 역운동학(IK) 시스템 (IK Motion Synthesis)

### 3.1 관절 계층 구조 및 생리적 ROM 제약
MetaHuman 규격을 준수하는 17개 관절에 대해 해부학적 한계를 설정하였다.
- **MCP**: 0°~90°(굴곡), 0°~20°(신전), ±20°(내외전).
- **엄지(CMC)**: 대립 운동을 포함한 3축 복합 회전 및 축회전(0°~15°) 적용.

### 3.2 Damped Least Squares (DLS) 솔버
특이점(Singularity)에서의 불안정성을 해소하기 위해 DLS 방식을 도입하였다.
- **수식**: $\Delta \theta = J^T (J J^T + \lambda^2 I)^{-1} \Delta e$ (Damping $\lambda = 0.05$)
- **궤적 제어**: 2차 베지어 곡선을 활용한 '아치형 타건 경로'를 생성하여 타건의 물리적 무게감을 모사한다.

---

## 4. 고품질 디테일 스키닝 및 렌더링 (High-Fidelity Skinning)

### 4.1 Chaos Flesh (PBD) 기반 거시 변형
- **사면체 메시 최적화**: 전신 시뮬레이션의 부하를 줄이기 위해 손 영역으로 범위를 한정, 정점 수를 **40,128개에서 6,147개**로 85% 감축하여 실시간 성능을 확보하였다.
- **Collision Setup**: 손가락 마디별 17개 Capsule 콜리전을 배치하여 피부 관통 문제를 해결하였다.

### 4.2 텐션맵(Tension Map) 기반 미시 디테일
- **구동 원리**: "거시 변형(물리) + 미시 디테일(셰이딩) 분리" 전략을 채택하였다.
- **Tension Value**: 관절 굴곡 각도 $\theta$를 기반으로 $tension = clamp( (\theta - \theta_{rest}) / \theta_{max}, 0, 1 )$을 산출한다.
- **Procedural Displacement (WPO)**:
  - **주름(Wrinkle)**: 텐션맵 신호에 따라 다중 사인 파형을 중첩하여 압축 부위에 실시간 주름 생성.
  - **핏줄(Vein)**: 핏줄 맵에 텐션 가중치를 곱하여 장력 발생 시 핏줄이 도드라지는 효과 구현.
  - **노멀 디테일**: 텐션으로 블렌드 강도를 조절하여 모공 및 잔주름 셰이딩 반영.

### 4.3 UE5 커스텀 렌더링 파이프라인
- **SVE & RDG**: Scene View Extension을 통해 톤매핑 단계 이후 커스텀 패스를 삽입하고, Render Dependency Graph를 통해 GPU 자원을 관리한다.
- **Compute Shader**: LBS와 PBD 오프셋을 합산하여 최종 버텍스 위치를 계산하는 고속 스키닝 셰이더를 구현하였다.

---

## 5. 결과 및 결론 (Results & Conclusion)

### 5.1 성과 요약
- **운지 정확도**: 실제 피아니스트의 연주와 비교 시 **85% 이상의 일치율** 달성.
- **시각적 사실성**: Chaos Flesh와 텐션맵의 결합으로 기존 LBS 대비 압절적인 해부학적 디테일 구현.
- **실시간성**: 최적화된 물리 연산과 GPU 기반 셰이더를 통해 30 FPS 이상의 성능 확보.

### 5.2 기대 효과
본 시스템은 고품질 음악 교육 콘텐츠 제작, VR 피아노 시뮬레이션, 그리고 디지털 휴먼의 정교한 상호작용 구현을 위한 핵심 기술로 활용될 수 있다.

---
**[부록: 데이터 인터페이스 명세]**
- **Interface A**: JSON 포맷 (Fingering $\rightarrow$ IK)
- **Interface B**: UE5 AnimSequence (IK $\rightarrow$ Skinning)
- **Interface C**: Material Parameters (Skinning $\rightarrow$ Shader)
