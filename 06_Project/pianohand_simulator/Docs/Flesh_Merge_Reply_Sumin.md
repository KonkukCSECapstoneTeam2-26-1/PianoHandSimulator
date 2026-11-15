# Flesh ↔ 스키닝 합치기 회신 (이수민 → 곽경민, 2026-11-15)

`Docs/Kyungmin/Flesh_Handoff_to_Sumin.md`(main `188af39`) 기준으로 합친 결과.

## 1. 경민 님 파일에서 바꾼 것 (2곳, 버그 수정)
- `Source/pianohand_simulator/Flesh/PianoHandFleshInput.cpp`: Flesh 위치 버퍼를 `StructuredBuffer<float3>`(12 바이트 업로드)에서
  **정점당 float 3개 `StructuredBuffer<float>`** 로 변경.
- `Shaders/Private/PianoHandFleshBlend.usf`: `FleshPositions[i*3+0..2]` 로 읽음.
- 이유: Metal(macOS)은 float3 원소를 16 바이트 간격으로 읽어 위치가 모두 어긋나고 뒤쪽 1/4 은 0 이 됨 → 손이 줄기로 터짐.
  Windows 에서는 정상이라 그쪽에서는 안 보였던 문제. 바뀐 방식은 두 플랫폼에서 동일하게 동작(결과 값은 같음).
- 지난주에 제가 "표면 바인딩 결함"이라고 한 것은 오진이었습니다. 바인딩은 정상입니다(자체 검증 차이 0 확인).

## 2. 제 쪽 결합 방식 (어댑터 API 는 그대로 사용)
- 인계 문서 6절의 두 제안(마스크 인자 추가 / SRV 꺼내기) 대신, `AddFleshBlendPass` 를 **위치 버퍼 사본**에 돌려 Flesh 표면을
  별도 버퍼로 얻습니다. 그래서 어댑터 시그니처는 바꾸지 않았습니다. `Blend` 는 1 로 두면 됩니다(세기는 디포머의 `FleshStrength`).
- implicit 이 켜져 있고 `bFleshCorrection` 이면: 휴지 자세에서 Flesh 표면을 캡처해 두고, 휴지 두께를 뺀 변위만
  접힘 안쪽 마스크(관절별 FoldSide × 굽힘)로 걸러 평활한 뒤 implicit **뒤**에 더합니다.
- 그 외(implicit 끔 = `attach_skin_deformer_flesh.py` 설정): 예전과 똑같이 전체 블렌드. `L_FleshTest` 의 기존 동작은 그대로입니다.
- 기본값: `FleshStrength` 0.5, `FleshMaxCm` 0.4, `FleshSmoothIterations` 24, `FleshRestCaptureDeg` 3.
  휴지 캡처는 모든 뼈가 레퍼런스 자세에서 3° 이내일 때 일어납니다. `A_IK_DebClai` 는 시작부터 굽어 있어 캡처가 안 되므로,
  Play 시작 시 디포머가 같은 스켈레톤의 단일 노드 스켈레탈 메시(제 손과 Flesh 구동용 손)를 `FleshCalibrationSeconds`(1.5 s) 동안
  레퍼런스 자세로 두었다가 애니메이션을 0 초부터 다시 시작합니다. **Play 직후 1.5 초 동안 손이 펴져 있는 것은 이 때문입니다.**
  기준 모양이 없을 때는 전체 블렌드로 떨어지지 않고 Flesh 를 건너뜁니다.

## 3. 비교 결과 (`Docs/images/skin_v12_flesh_compare.jpg`)
- Flesh 전체 블렌드는 주먹에서 손 전체가 구겨집니다(접힘 안쪽 지글거림이 그대로 표면에 나옴).
- 접힘부 결합은 강도 1.0 에서 일부 찢기고, 0.5 / 0.4 cm / 평활 24 에서 깨끗합니다. 효과는 미묘합니다.
- Flesh 쪽에서 접힘 안쪽 안정화(자기충돌 또는 Damping)가 되면 강도를 올릴 수 있습니다.

## 4. 씬
- `L_FleshTest` 는 건드리지 않았습니다(맵 저장 안 함). `GC_HandFlesh_Dense` 는 저장소에 없고 쓰지 않습니다.
- `L_PianoHandDemo` 에는 아직 Flesh 액터가 없습니다. 옮길 때는 레벨 파일 수정 순서를 먼저 정하겠습니다.
- 제 Mac 측정: Flesh 읽기 1.3 ms, 프레임 약 49 ms(20 FPS, 에디터 PIE·다른 프로그램 켠 상태). 60 FPS 수치는 재현하지 못했습니다.

## 5. 마디 기준 정확도와 최종 레벨 (11-15 오후 추가)
- 로그 `[FleshJoint]`: 마디 접힘 안쪽 정점에서, 휴지 두께를 뺀 Flesh 표면까지의 거리(가중 평균 / 최대, cm)를 단계별로 냅니다.
  `A_IK_DebClai` 약 2 분 평균: 스키닝만 0.458, 제 파이프라인(Flesh 없이) 0.480, 최종 0.366 (약 24% 감소).
  최대 2~9 cm 는 IK 급점프 구간의 Flesh 지연입니다. 끄려면 디포머 `bLogFleshJointAccuracy`.
- `Scripts/create_final_level.py` 가 `L_FleshTest` 의 사본 `L_PianoHandFinal` 을 만듭니다. Flesh 표면·구동용 손·`GC_HandFlesh_Dense` 는
  게임에서 숨기고 최종 손만 보입니다. 디포머 설정이 레벨에 저장돼 있어 `attach_skin_deformer_flesh.py` 가 필요 없습니다.
  `L_FleshTest` 는 건드리지 않았으니 그쪽 변경은 자유롭게 하시고, 바뀌면 스크립트를 다시 돌리면 됩니다.

## 6. 텐션맵 유도와 레벨 저장 버그 (11-15 저녁 추가)
- 보정이 굴곡측 전체에 고르게 들어가 손끝 패드가 번지던 것을, 제 텐션맵의 압축량(0~4%)으로 가중하게 바꿨습니다
  (`FleshTensionGuide` 1.0, 세기 0.75). 손끝 번짐이 없어지고 마디 정확도는 −17% (고르게 넣던 때 −19%).
  비교 `Docs/images/skin_v13_tension_guide_*.jpg`, 설명은 `CustomSkinning_Pipeline.md` 1-Z.
- **정정:** 5절의 "디포머 설정이 레벨에 저장돼 있다"는 이전 커밋에서는 사실이 아니었습니다(디포머가 Transient 라 에디터를
  다시 켜면 빠졌습니다). 이번 커밋에서 고치고 `L_PianoHandFinal` 을 다시 저장했습니다. 그 전에 받아 보셨다면 손이 기본
  스키닝으로 보였을 겁니다.
- 제안(경민 님 쪽 작업): 접히는 곳만 무르게 하려면 사면체 강성을 부위별로 주는 방법이 있습니다. 필요하시면 제 접힘 마스크
  (`T_PH_WrinkleMask`)를 정점 값으로 뽑아 드리겠습니다.
