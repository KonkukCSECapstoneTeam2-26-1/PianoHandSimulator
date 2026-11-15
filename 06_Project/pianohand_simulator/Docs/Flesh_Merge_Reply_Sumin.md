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
  휴지 캡처는 모든 뼈가 레퍼런스 자세에서 3° 이내일 때 일어나므로, 애니메이션이 한 번은 편 자세를 지나야 보정이 켜집니다
  (`A_IK_DebClai` 는 시작 자세가 굽어 있어 로그에 "rest shape NOT captured" 가 나올 수 있음 → 필요하면 임계값을 올리거나 첫 프레임 캡처로 바꿀 예정).

## 3. 비교 결과 (`Docs/images/skin_v12_flesh_compare.jpg`)
- Flesh 전체 블렌드는 주먹에서 손 전체가 구겨집니다(접힘 안쪽 지글거림이 그대로 표면에 나옴).
- 접힘부 결합은 강도 1.0 에서 일부 찢기고, 0.5 / 0.4 cm / 평활 24 에서 깨끗합니다. 효과는 미묘합니다.
- Flesh 쪽에서 접힘 안쪽 안정화(자기충돌 또는 Damping)가 되면 강도를 올릴 수 있습니다.

## 4. 씬
- `L_FleshTest` 는 건드리지 않았습니다(맵 저장 안 함). `GC_HandFlesh_Dense` 는 저장소에 없고 쓰지 않습니다.
- `L_PianoHandDemo` 에는 아직 Flesh 액터가 없습니다. 옮길 때는 레벨 파일 수정 순서를 먼저 정하겠습니다.
- 제 Mac 측정: Flesh 읽기 1.3 ms, 프레임 약 49 ms(20 FPS, 에디터 PIE·다른 프로그램 켠 상태). 60 FPS 수치는 재현하지 못했습니다.
