# PianoHandSimulator - Fingering & Physics Engine

피아노 연주 시뮬레이션을 위한 MIDI 파싱 및 고정밀 운지법/물리 데이터 추출 엔진입니다.

## 1. 주요 기능
- **Smart MIDI Parsing**: SMF Format 0/1 지원 및 화음(Chord) 자동 그룹화.
- **Chord-based DP Solver**: 화음 내 손가락 꼬임을 방지하고 최적의 운지 시퀀스를 탐색하는 동적 프로그래밍 알고리즘.
- **Anatomical Physics Engine**:
    - **Wrist Yaw/Roll**: 손가락 위치에 따른 손목의 3D 회전 각도 추정.
    - **Pressure & Depth**: 벨로시티 기반의 건반 압력 및 눌림 깊이 계산.
- **Hard ROM Constraints**: 인체 가동 범위(Range of Motion)를 넘지 않도록 데이터 클램핑 및 패널티 부여.

## 2. 프로젝트 구조
- `piano_fingering_engine.py`: 핵심 알고리즘 엔진 (V4 - 해부학적 제약 적용 버전).
- `PROGRESS.md`: 상세 개발 진행 리포트 및 인사이트 기록.
- `input.md`: 초기 요구사항 분석서.
- `mario_rom_result.json`: `Super Mario 64 - Medley` 분석 결과 데이터 (최종 출력물).

## 3. 실행 방법
1. Python 환경에서 `mido` 라이브러리 설치:
   ```bash
   pip install mido
   ```
2. 엔진 실행 (MIDI 파일 경로 수정 후):
   ```bash
   python piano_fingering_engine.py
   ```

## 4. 데이터 포맷 (JSON Output)
출력되는 JSON 파일은 Unreal Engine의 IK 및 셰이더 구동을 위한 다음 필드를 포함합니다:
- `pitch`: MIDI 음높이
- `start_ms`: 시작 시간 (절대 시간)
- `hand`: 왼손/오른손 구분
- `finger`: 배정된 손가락 번호 (1:엄지 ~ 5:새끼)
- `wrist_yaw_deg / wrist_roll_deg`: 손목 회전 각도 가이드
- `pressure`: 연주 강도 (0.0~1.0)

## 5. 향후 계획
- Unreal Engine 5 데이터 테이블 임포터 개발.
- PBD(Position Based Dynamics) 기반 조직 변형 셰이더 연동.

- sample