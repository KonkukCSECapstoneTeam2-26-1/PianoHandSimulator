[요구사항 분석서] 
피아노 연주 시뮬레이션 및 고정밀 렌더링 시스템
1. 개요
1.1 프로젝트 기획 배경
기술적 니즈: 기존 게임이나 시뮬레이션에서의 손가락 움직임은 단순한 스키닝(Linear Blend Skinning)에 의존하여, 피아노 연주와 같은 정교한 동작 시 살 뭉침이나 주름 및 피하 조직 표현이 부자연스러움.
사용자 니즈: MIDI 데이터를 입력하는 것만으로 실제 피아니스트의 운지법을 재현하고, 영화적 퀄리티의 연주 영상을 생성할 수 있는 도구의 부재.
1.2 기술 동향
XPBD/FEM: 실시간성이 보장되면서도 물리적으로 정확한 변형(Deformation) 시뮬레이션 기술 확산.
LBS: Unreal Engine에서 가장 기본적으로 사용되는 선형 혼합 스키닝. 연산 속도가 매우 빠르나 Candy wrapper artifact skinning 문제가 발생.
DBS: LBS의 부피감소문제를 수학적으로 보간하여 해결하기 위해 함께 사용. 다만 바깥쪽으로 불룩하게 튀어나오는 부작용 발생. 
Chaos Flesh: 최신 상용엔진인 Unreal 5 Engine에서는 FEM기반의 Softbody 시뮬레이션을 통해 자동차 바퀴, 손 등의 범용적인 Skinning 구현.
Motion Generation: 전신 모션(Locomotion)에 대한 연구는 생성형 AI 및 물리 기반 강화학습 모델이 도입되어 적극적으로 연구되고 있으며, 피아노 연주와 같은 미세 동작에 대한 연구는 비교적 데이터가 적음.
Inverse Kinematics: Jacobian matrix를 linear approximation를 통해 근사하는 것이 고전적인 애니메이션 생성 기법
1.3 프로젝트 주요 기능 및 특징
MIDI-to-Motion: MIDI 데이터를 파싱하여 최적의 운지법(IK)을 계산하고 애니메이션화.
High-Fidelity Rendering: Tension Map 기반의 동적 노멀 맵 변화를 활용한 주름 렌더링.
1.4 조원 구성 및 역할 분담
정근녕: MIDI 파서 구현 및 운지법 결정 알고리즘 개발.
한승현: Inverse Kinematics 기반 모션 생성.
이수민: Unreal Engine 머티리얼 셰이더(Tension Map) 및 카메라/UI 시스템 구현. PBD 시뮬레이션 검토
곽경민: 핏줄 등 피하 조직 표현하는 Skinning, shader 단계에서 Texture map 기반 mapping 진행. PBD 시뮬레이션 검토
1.5 일정
3월 4일: 대면 수업 (Orientation 및 초기 기획)
3월 18일: 대면 수업 2 (기술 스택 및 세부 추진 방향 검토)
4월 15일: 제안서 및 요구사항 분석서 발표 
5월 6일: 중간 발표 1 (진행 상황 점검 및 피드백)
6월 10일: 1학기 최종 발표 (데모 시연 및 학기 마무리)

2. 기능적 요구사항
2.1 Top Level Use Case Diagram
Actor: 사용자 (User)
Use Cases:
UC-01: MIDI 파일 업로드 및 에디팅.  
사전조건
애플리케이션이 실행 중이며 사용자가 유효한 MIDI 파일을 보유하고 있음.
주 흐름
사용자가 UI에서 MIDI 파일을 선택한다.
시스템이 파일의 포맷(format 0 또는 format 1) 여부를 확인한다.
멀티트랙 MIDI(format 1)의 경우 피아노 트랙을 자동 선별한다.
음표(Note On/Off), 벨로시티, 타이밍 정보를 파싱한다.
파싱 결과를 UI의 피아노 롤(Piano Roll) 뷰에 표시한다.
대안 흐름
피아노 트랙 자동 선별에 실패한 경우: 사용자에게 트랙 목록을 제시하고 수동 선택을 요청한다
예외 처리
지원되지 않는 파일 포맷: 오류 메시지를 표시하고 파일 선택 화면으로 복귀한다.
파일 손상(읽기 실패): 크래시 없이 오류 메시지를 출력하고 진행을 중단한다.
사후 조건
유효한 NoteEvent 시퀀스가 메모리에 적재되고 피아노 롤에 시각화된다.

UC-02: 손 모델 프리셋 선택.
사전조건
애플리케이션이 실행 중임
주 흐름
사용자가 UI 드롭다운에서 프리셋을 선택한다 (성인 남성 / 성인 여성 / 아동).
시스템이 해당 프리셋의 손 크기, 관절 길이, 관절 가동범위(ROM) 파라미터를 로드한다.
3D 뷰포트의 손 모델이 즉시 업데이트된다.
대안 흐름
사용자가 커스텀 파라미터를 직접 입력하는 경우: 각 손가락 마디 길이 및 ROM 수치를 개별 입력할 수 있으며, 입력값이 생리적 제약범위를 벗어나면 경고를 표시한다.
사후 조건
IK 솔버 및 운지법 알고리즘이 선택된 프리셋의 파라미터를 기반으로 동작한다.


UC-03: 시뮬레이션 실행 및 렌더링 결과 확인.
사전조건
손가락 모델에 대한 skeletal mesh가 로드되어 있음.
애니메이션 데이터가 생성되어 있음.
PBD 기반 조직 변형 데이터가 준비되어 있음.
texture map (skin, vein, normal)이 준비되어 있음
주 흐름
애니메이션 시스템을 통해 손가락 관절 변형 데이터를 생성한다.
Rendering System이 deformation 정보를 수신한다.
skinning을 통해 mesh deformation을 계산한 뒤, shader가 해당 vertex 정보를 읽는다.
texture mapping이 적용된다.
normal map 및 shading 계산이 수행된다.
대안 흐름
고품질 렌더링 모드 선택 시 : detail map을 추가 적용한 후 shading 품질을 향상시킨다. 
예외 처리
texture 파일 로드 실패 : 오류 로그를 기록한 뒤 렌더링 계속 수행한다.
deformation 계산 실패 : simulation 기능 비활성화 이후 렌더링 계속 수행한다.
성능 저하 발생 : texture 해상도를 낮춘 후 기본 렌더링으로 전환한다.
사후 조건
손가락 변형이 화면에 정상적으로 렌더링된다. 
피부 및 피하 조직이 자연스럽게 표현된다. 




UC-04: 카메라 워킹 설정 및 연주 영상 캡처.
사전조건
시뮬레이션이 완료되어 애니메이션 데이터가 존재함.
주 흐름
사용자가 카메라 앵글(위치, 회전, FOV)을 설정한다.
키프레임 기반 카메라 워킹 경로를 설정한다.
캡처 해상도 및 프레임레이트를 선택한다.
렌더링을 시작하면 Movie Render Queue를 통해 이미지 시퀀스 또는 동영상으로 출력한다
사후 조건
설정한 해상도와 프레임레이트로 렌더링된 결과물 파일이 생성된다.



2.2 각 기능별 동작 시나리오
입력 단계: 사용자가 MIDI 파일을 로드하면 시스템은 음표 데이터와 시간 정보를 추출한다.
계산 단계: IK 솔버가 피아노 건반 위치와 손가락 가동 범위를 계산하여 최적의 운지법을 도출하고 Bone 애니메이션을 생성한다.
렌더링 단계: 계산된 Bone 각도에 따라 구축된 파이프 라인에서 살 뭉침을 계산하고, 메테리얼 셰이더가 관절 굴곡에 따른 인체 구성을 실시간으로 그려낸다.

2.3 MIDI 파서 요구사항
지원 포맷: Standard MIDI File format 0, format 1
필수 파싱 항목:
음표 이벤트: Note On / Note Off, 음높이(pitch), 벨로시티(velocity), 채널 번호
템포 이벤트: BPM 값 → 절대 시간(ms) 변환
박자표(Time Signature) 메타 이벤트
피아노 트랙 자동 선별 기준 (우선순위 순):
GM 프로그램 번호 0~7 (Piano 계열 악기)에 해당하는 트랙
음역대가 A0(MIDI 21) ~ C8(MIDI 108) 범위에 집중된 트랙
노트 이벤트 수가 가장 많은 트랙
출력 자료구조:
  NoteEvent {
    time_ms      // 절대 시간 (밀리초)
    pitch        // MIDI 음높이 (0~127)
    velocity     // 벨로시티 (0~127)
    duration_ms  // 음표 지속 시간 (밀리초)
    hand        // 왼손이면 0, 오른손이면 1
    finger       // 운지법 알고리즘이 배정한 손가락 번호 (1~5, 미배정 시 0)
  }



2.4 운지법 결정 알고리즘 요구사항
알고리즘 방식: 동적 프로그래밍(Dynamic Programming) 기반 최적 시퀀스 탐색
비용 함수(Cost Function) 구성 요소:
스트레치 비용: 연속된 음표 간 손가락 간격이 해당 프리셋의 최대 스트레치에 가까울수록 비용 증가
이동 비용: 이전 음표에서 현재 음표까지 손 전체의 이동 거리
약지·소지 패널티: 4번(약지), 5번(소지) 손가락 단독 사용 시 추가 비용 부여
엄지 통과: 음계형 패시지에서 엄지가 다른 손가락 아래를 통과하는 동작 허용
연속 사용 패널티: 동일 손가락이 빠른 연속 음표에 반복 배정될 경우 비용 증가
제약 조건:
동시 발음(화음) 처리: 동일 시간에 발음되는 음표들은 서로 다른 손가락에 배정
트릴/트레몰로: 2개 손가락 교번 패턴 우선 적용
생리적 ROM 내에서만 배정 유효 처리
2.5 IK 시스템 상세 요구사항
방식: Jacobian 기반 IK (Damped Least Squares, DLS 변형 적용)
  선택 이유: 본 시스템의 IK 계산은 실시간이 아닌 오프라인 사전 계산 단계에서 수행되므로
  수렴 속도보다 정확도와 제약 처리 유연성을 우선한다.
  DLS(Damped Least Squares)를 적용하여 Jacobian 특이점(Singularity) 문제를 회피한다.
관절 계층: 손목(Wrist) → 손바닥(Metacarpal) → MCP → PIP → DIP → 손가락 끝(Fingertip)
관절별 ROM(Range of Motion) 제약:
  MCP: 굴곡 0°~90°, 신전 0°~20°, 내외전 ±20°
  PIP: 굴곡 0°~100°, 신전 0°~10°, 내외전 없음
  DIP: 굴곡 0°~80°, 신전 0°~5°, 내외전 없음
  엄지 CMC: 굴곡 0°~50°, 신전 0°~50°, 내외전 ±40°, 축 회전(Axial Twist): 0°~15° (대립(Opposition) 전 범위)
  엄지 MCP: 굴곡: 0°~60°, 신전 0°, 내외전 없음
  엄지 IP: 굴곡: 0°~80°, 신전: 0°~5°, 내외전 없음
ROM 제약 처리 방식:
관절 각도가 ROM 한계에 근접할수록 비용이 급격히 증가하는 패널티 항을 Jacobian 비용 함수에 포함
경계를 부드럽게 처리(Soft Constraint)하여 수렴 안정성 확보
동작 요구사항:
음표의 타깃 위치(건반 중심점)를 IK 목표로 설정하여 손가락 끝이 정확히 도달
다중 손가락 동시 IK 계산 시 상호 충돌(손가락끼리 겹침) 방지 로직 포함

2.6 Skinning 및 Shader 기반 피하 조직 표현 요구사항
방식: Texture map 기반 deformation-aware skinning 및 shading 
선택 이유 : 기본적으로 제공하는 Linear Blend Skinning만 사용할 경우 관절 굴곡 시 피부가 납작해지거나 질감이 부자연스럽게 왜곡되는 문제가 발생함. 또한 외부 물리 시뮬레이션을 통해 계산된 조직 변형 결과를 시각적으로 반영하기 위해 deformaion-aware shading이 필요함. 
Texture 및 shader 기반 보정은 geometry 복잡도를 크게 증가시키지 않으면서 시각적 사실성을 향상시킬 수 있음
입력 데이터 :
Skeletal animation 결과 (joint transform)
PBD 기반 조직 변형 데이터 (vertex displacement)
Texture map (skin, vein, normal 등)
동작 요구사항 :
PBD 기반 조직 변형 결과를 skinning 단계에서 반영할 수 있어야 함.
관절 굴곡 및 압축 시 mesh surface deformation이 자연스럽게 표현되어야 함.
deformation된 mesh에 texture mapping이 일관되게 적요되어야 함.
deformation 결과에 따라 surface normal 및 shading 계산이 갱신되어야 함.
제약 조건 :
deformation은 관절 ROM 범위를 초과하지 않아야 함.
texture distortion이 시각적으로 허용 가능한 수준을 유지해야 함.
rendering pipeline은 animation 및 simulation 결과와 동기화되어야 함.

3. 비기능적 요구사항 (Non-functional Requirements)
3.1 사용편리성 (Usability)
Parameter Control: 전문 지식이 없는 사용자도 직관적으로 이해할 수 있도록 Widget 기반 UI 제공. (예: 손 모델 프리셋 선택 드롭다운)
Preset System: 성인 남성/성인 여성/아동 3개의 표준화된 손 크기 프리셋 제공.
3.3 성능 (Performance)
IK: 자연스러운 운지법이 선택되어 자연스러운 모션이 연출되며, IK Flip 현상이 나타나지 않아야 함.
Skinning :  피부와 뼈, 핏줄 등 피하 조직 표현이 자연스러운 Skinning이 진행되어야 하며, 관절의 뭉개짐이나 접힘 현상이 최소화되어야 한다. 
3.6 구현상 제약사항 (Constraints)
Engine: Unreal Engine 5.1 이상 버전 - 손가락 전용 커스텀 파이프라인 지원
Physiological Constraints: 인체 해부학적 구조를 바탕으로 관절의 가동 범위(Range of Motion)를 설정하여 기괴한 변형이 일어나지 않도록 강제함.
3.7 인터페이스 (Interface)
Standard MIDI Support: 포맷 0 및 1의 표준 MIDI 파일을 지원하며, 다중 트랙 중 피아노 트랙을 자동 선별하는 로직 포함.
Custom Skinning Component: 손 모델 mesh에 맞는 커스텀 skinning 컴포넌트를 엔진내에서 지원하는것을 목표로 한다.
3.8 법적 제약사항 (Legal)
Copyright: 시뮬레이션에 사용되는 MIDI 음원 및 렌더링 결과물의 저작권 주체는 원곡 저작권 및 사용자에게 있음을 명시.

