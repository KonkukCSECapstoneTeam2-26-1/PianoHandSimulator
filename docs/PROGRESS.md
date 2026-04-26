# 피아노 연주 시뮬레이션 개발 진행 리포트

## 1. 프로젝트 개요
- **목표**: MIDI 데이터를 입력받아 고정밀 손가락 애니메이션(IK) 및 렌더링 데이터를 생성하는 시스템 구축.
- **주요 모듈**:
    1. MIDI Parser (Tick to MS 변환, 화음 그룹화)
    2. Hand Splitter (양손 분리 알고리즘)
    3. Fingering Solver (DP 기반 최적 운지법 결정)
    4. Unreal Engine IK/Rendering (애니메이션 구현)

## 2. 현재 진행 상황 (2026-04-07)
### [단계 1] 요구사항 분석 완료
- `input.md`를 통해 프로젝트 범위 및 기술 스택(UE5, PBD, IK, DP) 확인.
- MIDI Parser 및 운지법 알고리즘의 핵심 제약 조건 도출.

### [단계 2] 핵심 엔진 프로토타입 구현 (Python) - 완료
- **파일**: `piano_fingering_engine.py` (V2)
- **주요 업데이트**:
    - **Chord-based DP**: 개별 음표가 아닌 화음 그룹 단위로 상태를 정의하여 연산 효율성 및 논리적 일관성 확보.
    - **Monotonicity 제약**: 화음 내에서 피치 순서와 손가락 번호 순서가 일치하도록 강제.
    - **Wrist Hint 생성**: 88키 범위를 기준으로 한 손목의 정규화된 위치(0.0~1.0) 계산 로직 추가.
    - **결과 포맷 확장**: `fingering_v2.json`을 통해 IK 구동을 위한 풀 데이터셋 구축.

### [단계 6] 해부학적 절대 한계(ROM) 및 하드 제약 적용 - 완료
- **파일**: `piano_fingering_engine.py` (V4)
- **주요 업데이트**:
    - **Finger Span Hard Penalty**: 각 손가락 쌍(Pair)별 최대 확장폭(`MAX_SPAN`)을 설정하여 물리적으로 불가능한 운지 배제.
    - **Illegal Crossing Block**: 엄지 이외의 손가락이 교차하는 동작에 강력한 패널티 부여.
    - **Wrist ROM Clamping**: 손목 회전 각도를 인간의 가동 범위(Yaw ±35°, Roll ±20°) 내로 강제 제한.
    - **안정성 확보**: 유효 경로가 없는 극한 상황에서도 '최선의 대안'을 찾도록 DP 알고리즘 예외 처리 강화.

### [단계 8] 프로젝트 구조 체계화 및 성부 분리 로직(V5) 구현 - 완료 (2026-04-26)
- **프로젝트 구조 개편**:
    - `01_Fingering`, `02_IK`, `03_Skinning`으로 대분류하여 확장성 확보.
    - `assets`, `docs`, `results` 폴더를 통한 리소스 및 출력물 관리 체계 구축.
- **V5 Polyphonic Voice Leading 엔진**:
    - **성부 분리 (Voice Separation)**: 한 손 내에서 멜로디, 화음, 베이스 성부를 구분하여 인식.
    - **음악적 비용 함수 (Musical Cost Function)**:
        - 멜로디(4, 5번) 및 베이스(5번) 손가락 선호도 반영.
        - 멜로디 라인의 수평적 연결성(Legato)을 위한 가중치 시스템 도입.
    - **결과 데이터 포맷 확장**: JSON 출력에 `role` 필드를 추가하여 UE5 애니메이션 제어용 메타데이터 확보.

## 3. 기술적 결정 사항 (Architecture Decisions)
1. **시간 단위**: 절대 시간(ms) 기반.
2. **알고리즘**: `Chord-based DP` + `Anatomical Penalty System` + `Voice Leading Weights`.
3. **ROM 제약**: MCP/Wrist 관절 가동 범위를 상수로 관리하여 클램핑 적용.
4. **폴더 구조**: 기능 중심의 번호 체계(`01_`, `02_` 등)를 사용하여 개발 순서 및 도메인 분리.

## 4. 향후 계획 (Next Steps)
- [ ] **Unreal Engine 5 성부 기반 애니메이션**: `role` 데이터를 활용하여 멜로디 노트 연주 시 더 강조된 모션을 적용하는 IK 로직 개발.
- [ ] **V5 결과 검증**: 시각화 툴(`visualizer.py`)을 업데이트하여 성부별로 색상을 다르게 표시하는 기능 추가.
