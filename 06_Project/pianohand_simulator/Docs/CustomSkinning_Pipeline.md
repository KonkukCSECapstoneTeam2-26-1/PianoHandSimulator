# 커스텀 스키닝 셰이더 파이프라인 (UE 5.6)

`06_Project/pianohand_simulator` 안에서 스켈레탈 메시의 스키닝을 엔진 기본 GPU Skin Cache 대신
**직접 작성한 컴퓨트 셰이더**로 처리하기 위한 기반 코드와 로드맵.

관련 설계 문서: `01_Design/06_Skinning_Detailed_Design.md` (텐션맵 · 핏줄맵 · 노멀맵 디테일 모듈)

---

## 1. 현재 구성 (Phase 0 — 파이프라인 골격)

| 파일 | 역할 |
|---|---|
| `pianohand_simulator.uproject` | 모듈 `LoadingPhase = PostConfigInit` (글로벌 셰이더 등록에 필수), 플러그인 ComputeFramework / DeformerGraph / ChaosFlesh 활성화 |
| `Source/pianohand_simulator/pianohand_simulator.Build.cs` | `RenderCore`, `RHI`, `Renderer`, `Projects` 의존성 추가 |
| `Source/pianohand_simulator/pianohand_simulator.{h,cpp}` | 모듈 시작 시 가상 셰이더 경로 `/PianoHand` → `<Project>/Shaders` 매핑 등록, `LogPianoHand` 로그 카테고리 |
| `Shaders/Public/SkinningCommon.ush` | HLSL 공용 타입 `FBoneTransform`(3행 아핀 행렬), 듀얼 쿼터니언 유틸 |
| `Shaders/Private/CustomSkinning.usf` | 스키닝 커널 `MainCS`. `SKIN_MODE 0` = LBS, `SKIN_MODE 1` = DQS. 정점당 본 4개 |
| `Source/.../Skinning/CustomSkinningShader.{h,cpp}` | `FCustomSkinningCS` 글로벌 컴퓨트 셰이더, `CustomSkinning::AddSkinningPass()` RDG 패스 추가 헬퍼 |
| `Source/.../Skinning/CustomSkinningSmokeTest.cpp` | 콘솔 커맨드 `PianoHand.SkinningSmokeTest` : 2본 테스트 메시로 LBS/DQS 디스패치 → GPU 리드백 → CPU 레퍼런스 비교 |

### 데이터 레이아웃 (C++ ↔ HLSL)

```
RestPositions   StructuredBuffer<float3>          FVector3f          (rest/bind 공간)
RestNormals     StructuredBuffer<float3>          FVector3f
BoneIndices     StructuredBuffer<uint4>           FIntVector4        정점당 4개
BoneWeights     StructuredBuffer<float4>          FVector4f          합 = 1
BoneTransforms  StructuredBuffer<FBoneTransform>  FSkinBoneTransform 48 bytes, RefPoseInverse * CurrentPose
OutPositions    RWStructuredBuffer<float3>
OutNormals      RWStructuredBuffer<float3>
```

`FSkinBoneTransform::FromMatrix(FMatrix44f)` 가 UE의 행벡터 행렬(`v' = v * M`)을 HLSL의 `p' = M * [p,1]` 행 형식으로 전치해 준다.

### 검증 방법

1. 에디터 실행 후 `~` 콘솔에서 `PianoHand.SkinningSmokeTest` 입력
2. Output Log 에서 `LogPianoHand` 필터:
   - `[SkinningSmokeTest] LBS: PASS (12 vertices)`
   - `[SkinningSmokeTest] DQS: PASS (12 vertices)`
   - `[SkinningSmokeTest] RESULT: PASS`
3. 헤드리스 실행 (에디터를 닫은 뒤): `Scripts\RunSkinningSmokeTest.bat`
   → 에디터 타깃 빌드 후 아래 명령을 실행하고 로그를 요약한다.
   ```
   UnrealEditor-Cmd.exe <uproject> -ExecCmds="PianoHand.SkinningSmokeTest" -SkinningTestAutoQuit -unattended -nosplash -log
   ```
   종료 코드 0 = PASS, 1 = FAIL.
4. HLSL 문법만 빠르게 확인하려면 Windows SDK `fxc.exe /T cs_5_0 /E MainCS /D SKIN_MODE=0|1` 로 컴파일해 볼 수 있다
   (`/Engine/Public/Platform.ush` include 를 제거하고 `#define UNROLL [unroll]` 추가).

> 참고: standalone 게임 exe(`Binaries/Win64/pianohand_simulator.exe`)로는 이 테스트를 돌릴 수 없다.
> 쿠킹된 글로벌 셰이더 라이브러리를 요구해 `FShaderCodeLibrary::InitForRuntime` 에서 종료된다. 반드시 에디터(-Cmd)로 실행한다.

셰이더(.usf/.ush)를 수정했을 때는 에디터 콘솔에서 `RecompileShaders Changed` 로 재컴파일할 수 있다.

---

## 1-B. Phase 1 구현 (2026-09-13) — MeshDeformer 연결

| 파일 | 역할 |
|---|---|
| `Shaders/Private/CustomSkinningDeformer.usf` | 커널 `DeformCS`. 섹션 단위 디스패치. 엔진 LOD 버퍼(rest position, packed tangent, skin weight stream)를 직접 읽고 패스스루 정점 팩토리의 position/tangent 버퍼에 기록. `SKIN_MODE`, `GPUSKIN_BONE_INDEX_UINT16`, `GPUSKIN_BONE_WEIGHTS_UINT16` 퍼뮤테이션 |
| `Source/.../Skinning/PianoHandSkinDeformer.{h,cpp}` | `UPianoHandSkinDeformer`(UMeshDeformer) / `UPianoHandSkinDeformerInstance` / `UPianoHandSkinningLibrary`(BP·Python 헬퍼) |
| `Scripts/skin_deformer_demo.py` | Emil 메시 2개(커스텀 vs 엔진) 나란히 스폰해 A/B 비교하는 데모 |
| `Scripts/BuildEditor.bat` | 에디터 종료 후 풀 빌드 |

동작 흐름
1. `UPianoHandSkinningLibrary::ApplyCustomSkinning(Component, Mode)` → `NewObject<UPianoHandSkinDeformer>` + `SetMeshDeformer()`.
2. 엔진이 매 프레임 `UMeshDeformerInstance::EnqueueWork()` 호출 → 게임 스레드에서 `RefBasesInvMatrix[i] * ComponentSpaceTransforms[i]` 로 본 행렬(`FSkinBoneTransform`)을 계산.
3. 렌더 스레드: `FSkeletalMeshDeformerHelpers::AllocateVertexFactory{Position,Tangent}Buffer` 로 출력 버퍼 확보 → 섹션마다 BoneMap 순서의 본 버퍼 업로드 + `DeformCS` 디스패치 → `UpdateVertexFactoryBufferOverrides` 로 패스스루 정점 팩토리에 바인딩.
4. 실패(CPU 스키닝, unlimited bone influence 등) 시 엔진 fallback delegate 호출 → 기본 스키닝으로 복귀.

검증
- 빌드 후 에디터에서 `skin_deformer_demo.py` 실행 → Output Log `LogPianoHand: [SkinDeformer] ... LOD0 verts=... influences=... index16=... mode=LBS` 라인 확인.
- `unreal.PianoHandSkinningLibrary.get_custom_skinning_frame_count(comp)` 가 프레임마다 증가하면 디스패치 중.
- 두 액터의 포즈가 일치하면 커스텀 커널이 엔진 스키닝과 동일한 결과. DQS 모드는 관절 부위 부피 보존 차이로 미세하게 다름(의도된 차이).

### Phase 1 검증 결과 (2026-09-13 02:50~03:00, 에디터 5.6.1)

| 항목 | 결과 |
|---|---|
| 빌드 | `Scripts\BuildEditor.bat` → 에러 0, 경고 0. 유일한 수정: `PianoHandSkinDeformer.cpp` 의 `#include "pianohand_simulator.h"` → `"../pianohand_simulator.h"` (Skinning/ 하위 폴더에서는 모듈 루트가 include 경로에 없음. `CustomSkinningSmokeTest.cpp` 와 동일 방식) |
| 셰이더 | `FPianoHandSkinDeformerCS` 8개 퍼뮤테이션(SKIN_MODE×INDEX16×WEIGHT16) 전부 컴파일 성공 |
| 레이아웃 로그 | `[SkinDeformer] SKM_skin_coarse: LOD0 verts=33739 sections=1 influences=8 stride=16 index16=0 weight16=0 bones=87 mode=LBS` |
| 디스패치 | `get_custom_skinning_frame_count` 가 매 프레임 증가 (에디터 포그라운드일 때 ~1500 frames/1분) |
| 정확도 | 같은 포즈·같은 카메라 1280x720 HighResShot 픽셀 비교 — 메시 영역 엔진 vs 커스텀 LBS 평균 차이 1.4 (배경 TAA 노이즈 1.1 수준, 32 이상 차이 픽셀 0개) → **엔진 스킨캐시와 동일**. DQS 는 관절부 93픽셀만 32 이상 차이 (의도된 부피 보존 차이) |
| 로그 | 디포머/RDG/RHI 관련 경고·에러 0건 |

스크린샷: `Saved/Screenshots/WindowsEditor/PH_engine_LBS.png`, `PH_custom_LBS.png`, `PH_custom_DQS.png`

검증 시 주의
- `skin_deformer_demo.py` 는 UE 5.6 API 에 맞게 `set_animation()` / `set_update_animation_in_editor()` 를 쓴다 (`anim_to_play`, `update_animation_in_editor` 프로퍼티는 Python 에서 직접 설정 불가).
- 에디터 창이 **최소화되어 있으면 렌더/틱이 멈춰** 프레임 카운트가 1에서 증가하지 않는다. 창을 복원하면 바로 증가한다.
- 두 액터를 150cm 떨어뜨려 놓고 한 카메라로 보면 원근 차이 때문에 포즈가 달라 보인다. 정확한 A/B 는 같은 위치에 두고 visibility 를 토글해 HighResShot 을 찍어 비교한다.

알려진 제약
- Unlimited bone influence 웨이트 레이아웃은 미지원(엔진 스키닝으로 fallback).
- 모프 타겟·클로스 입력은 아직 커널에 합성하지 않음.
- 디스패치를 ComputeFramework 실행 그룹이 아니라 `ENQUEUE_RENDER_COMMAND` 로 바로 실행하므로, 본 행렬은 엔진 본 버퍼가 아니라 자체 업로드 값을 쓴다(타이밍 의존 없음).

---

## 1-C. Phase 2 구현 (2026-09-20) — 정점 텐션(엣지 신장률) → Vertex Color

| 파일 | 역할 |
|---|---|
| `Shaders/Private/CustomSkinningTension.usf` | `AccumulateCS`(삼각형당 1스레드: 3개 엣지의 `|skinned|/|rest| - 1` 을 고정소수점(×65536) `InterlockedAdd` 로 양 끝 정점에 누적 + 기여 횟수) / `ResolveCS`(정점당 평균 → 컬러 버퍼) |
| `PianoHandSkinDeformer.{h,cpp}` | `bComputeTension`, `TensionScale` 프로퍼티(매 프레임 재읽기 → Details/Python 에서 즉시 반영), `AllocateVertexFactoryColorBuffer` 로 컬러 스트림 오버라이드, `GetOutputBuffers()` 에 `SkinnedMeshVertexColor` 추가, `GetCustomSkinDeformer()` 헬퍼 |
| `Scripts/create_tension_material.py` | `/Game/PianoHand/M_PianoHandTension` 생성 (BaseColor = lerp(lerp(회색, 빨강, R), 파랑, G)) |
| `Scripts/skin_deformer_demo.py` | `SHOW_TENSION`, `TENSION_SCALE` 옵션 — 커스텀 액터에 텐션 머티리얼 적용 |

Vertex Color 레이아웃 (머티리얼 VertexColor 노드로 읽음)

| 채널 | 값 |
|---|---|
| R | `saturate( strain * TensionScale)` — 신장 (0..1) |
| G | `saturate(-strain * TensionScale)` — 압축 (0..1) |
| B | `0.5 + 0.5 * clamp(strain * TensionScale, -1, 1)` — 부호 포함 (0.5 = rest) |
| A | 1 |

`strain = |p_i - p_j| / |r_i - r_j| - 1` (정점에 닿는 모든 엣지 평균). CPU 인접 정보 없이 LOD 인덱스 버퍼 SRV 만 사용하므로 임의 스켈레탈 메시에 바로 적용된다. 컬러 버퍼는 엔진 패스스루 정점 팩토리의 컬러 스트림을 그대로 오버라이드하므로 메시 자체에 정점 컬러가 없어도 된다.

검증 (SKM_skin_coarse, TensionScale=8)
- 정지 포즈(t=0): 거의 회색(신장/압축 없음). 관절 굽힘 포즈(t=12, 20): 어깨·목·겨드랑이·팔꿈치에 빨강/파랑 분포 — `Saved/Screenshots/WindowsEditor/PH_tension_scale8_t{0,12b,20}.png`
- 전 셰이더(`FPianoHandTensionAccumulateCS`, `FPianoHandTensionResolveCS`) 컴파일 성공, 디포머/RDG 경고·에러 0.
- `TensionScale` 을 Python 에서 `deformer.set_editor_property('tension_scale', 8.0)` 으로 바꾸면 다음 프레임부터 반영.

알려진 제약 / 다음
- 부드러운 결과를 원하면 정점 이웃 평활 패스(라플라시안 1~2회) 추가 가능 — 현재는 1-ring 엣지 평균만.
- 텐션은 삼각형 단위 등방 근사(엣지 길이)라 방향성(주 신장 방향)은 없다. 주름 방향이 필요하면 삼각형 변형 그래디언트의 주축을 추가 스트림(UV)으로 내보내야 한다.
- 머티리얼에서 B(부호 포함)로 `disp_w`(주름, 압축 시), `disp_v`(핏줄, 신장 시)를 구동하는 것이 Phase 3.

## 1-D. 손 메시 적용 (2026-09-20)

Emil `SKM_skin_coarse` 는 손목에서 잘린 상반신 스킨이라 손가락이 없다. 손가락이 있는 메시가 필요해
UE 5.6 VR 템플릿의 손 메시를 프로젝트로 복사했다.

| 항목 | 값 |
|---|---|
| 원본 | `C:\Program Files\Epic Games\UE_5.6\Templates\TP_VirtualRealityBP\Content\Characters\MannequinsXR` (39MB) |
| 복사 위치 | `Content/Characters/MannequinsXR` (패키지 경로가 `/Game/Characters/MannequinsXR/...` 로 그대로 맞음) |
| 메시 | `SKM_MannyXR_right` — 손 단독 메시, 47본(손가락 5개 × 3마디 + metacarpal) |
| 포즈 | `A_MannequinsXR_{Idle,IndexCurl,Point,ThumbUp,Grasp}_Right` — 1프레임짜리 포즈 시퀀스 |
| 데모 | `Scripts/hand_tension_demo.py` (`set_pose` / `set_scale` / `look_at_hand` / `compare_with_engine`) |

검증 결과
- **텐션**: Idle 포즈는 전면 회색(텐션 ≈ 0), Grasp(주먹)에서 너클 바깥쪽이 빨강(신장) · 관절 주름이 파랑(압축) — 피부 물리와 일치. `Saved/Screenshots/WindowsEditor/HAND_final_{idle,grasp}.png`
- **스키닝 정확도**: 같은 포즈를 프레임 0에 고정하고 메시 원본 머티리얼 + 텐션 OFF 로 A/B — 손 영역 픽셀 차이 평균 1.18, 32 초과 8픽셀. 같은 이미지의 배경(TAA 노이즈)이 평균 4.97 / 4144픽셀이므로 **렌더러 자체 노이즈보다 작은 차이 = 일치**. `HANDAB_{custom,engine}.png`

주의 (실수하기 쉬운 지점)
- 1~2프레임짜리 포즈 시퀀스를 `play(True)` 로 두면 루프하며 프레임이 흔들려 A/B 비교가 어긋난다. 반드시 `play(False)` + `set_position(0)` 으로 고정할 것.
- 파이썬 `unreal.Rotator(a, b, c)` 는 **(roll, pitch, yaw)** 순서다. `Rotator(pitch, 0, 0)` 은 roll 을 설정한다 — 키워드 인자를 쓸 것.

## 1-E. 크래시 수정 — LOD 스트리밍 가드 (2026-09-20)

새 손 메시를 임포트한 직후 포즈/가시성/머티리얼을 연달아 바꾸자 에디터가 죽었다.

```
Assertion failed: (Index >= 0) & (Index < ArrayNum)  Array index out of bounds: 0 into an array of size 0
  PianoHandSkinDeformer::Execute_RenderThread()   <- FSkeletalMeshDeformerHelpers::AllocateVertexFactoryPositionBuffer
```

원인: `AllocateVertexFactoryPositionBuffer` 내부의 `GetBaseSkinVertexFactory(LodIndex, Section)` 이
`LODs[LodIndex].GPUSkinVertexFactories.VertexFactories[0]` 을 인덱싱하는데, **LOD 스트리밍이 끝나지 않은
LOD 는 이 배열이 비어 있다.** 방금 39MB 를 임포트해 스트리밍이 한창일 때 그 LOD 로 디스패치해서 터졌다.
엔진 Optimus 는 ComputeFramework 실행 그룹에서 돌아 이 구간을 피하지만, 우리는 `ENQUEUE_RENDER_COMMAND`
로 직접 디스패치하므로 직접 막아야 한다.

`Execute_RenderThread` 앞에 가드 추가:
- `IsGPUSkinMesh()` (헬퍼가 `FSkeletalMeshObjectGPUSkin` 으로 static_cast 하므로 Nanite/CPU 스킨 제외)
- `HaveValidDynamicData()` (렌더 스테이트 재생성 중이면 스킵)
- `RenderData.IsInitialized()` + `LODRenderData.IsValidIndex(LodIndex)`
- **`LodIndex >= max(CurrentFirstLODIdx, GetPendingFirstLODIdx(0))`** ← 실제 원인을 막는 가드
- `Lod.GetNumVertices() > 0 && RenderSections.Num() > 0`

가드에 걸리면 `false` 를 반환해 엔진 fallback(기본 스키닝)으로 1프레임 넘어간다. 수정 후 포즈·가시성·
머티리얼을 반복 토글하는 동일 시퀀스에서 크래시 재현되지 않음.

빌드 참고: 에디터가 크래시로 죽으면 `UnrealEditor.exe` / `LiveCodingConsole.exe` 좀비가 남아
DLL 잠금(LNK1104)과 "Unable to build while Live Coding is active" 를 일으킨다. 이 좀비는 **포트 30010 도
잡고 있어 새로 띄운 에디터의 Remote Control 이 MCP 에서 안 보인다.** `Scripts/BuildEditorClean.bat` 이
빌드 전에 이 프로세스들을 정리하고 결과를 `Scripts/build_report.txt` 로 남긴다.

## 1-F. Phase 3 구현 (2026-09-20) — 부피 보존 + 관절 주름 (셰이더 전용)

목표: **손가락을 쫙 편 상태에서도 마디마다 보이는 주름**을, 텐션맵·주름맵 같은 저작 리소스 없이
셰이더만으로 만든다. 설계서의 `disp_w`(주름) 항을, 절차적 사인파 대신 **부피 보존 + 관절 밴드**로 구성.

| 파일 | 역할 |
|---|---|
| `Shaders/Private/CustomSkinningDetail.usf` | `DisplaceCS`(정점당, 노멀 방향 변위) / `NormalAccumulateCS`(삼각형당 face normal atomic 누적) / `NormalResolveCS`(정점당 정규화 + 탄젠트 재직교화) |
| `PianoHandSkinDeformer.{h,cpp}` | `bDetailDisplacement`, `bRecomputeNormals`, `VolumeBulge`, `CreaseDepth`, `CreaseSharpness`, `CreaseCompressionGain`, `WrinkleAmplitude`, `WrinkleFrequency` — 전부 매 프레임 재읽기 |
| `Scripts/create_clay_material.py` | `/Game/PianoHand/M_PianoHandClay` — 무광 점토 머티리얼(기하 형상만 보려고) |

패스 순서: `DeformCS`(스키닝) → `TensionAccumulate` → `TensionResolve`(컬러 + **raw strain 버퍼**)
→ `DisplaceCS` → `NormalAccumulate` → `NormalResolve` → `UpdateVertexFactoryBufferOverrides`

### 변위 세 항

**① 부피 보존 (`d_volume`)**
`lambda = 1 + strain` 이 국소 면내 신축률. 비압축성 물질은 면내로 눌리면 법선 방향으로 부풀어야 하고,
등방 신축 lambda 에 대해 두께 배율은 `1/lambda^2`. 그래서
`d_volume = VolumeBulge * clamp(1/lambda^2 - 1, -2, 2)` — 압축(lambda<1)이면 바깥으로, 신장이면 안으로.
LBS 가 관절에서 부피를 잃고 납작해지는 것을 되밀어준다.

**② 관절 주름 (`d_crease`) ← "편 상태에서도 보이는 마디 주름"**
핵심 아이디어: **관절 위의 정점은 정의상 두 본 사이를 블렌딩하는 정점이다.** 가장 큰 두 영향 가중치를
`w0 >= w1` 이라 하면 `4*w0*w1` 은 강체 부위에서 0, 관절을 따라 달리는 50/50 블렌드 선에서 정확히 1 이 된다.
즉 **스킨 웨이트만으로 관절 밴드가 공짜로 나온다** — 저작한 마스크도, UV 도, 텍스처도 필요 없고
어떤 스켈레탈 메시에도 그대로 적용된다.

```
JointBand = pow(saturate(4*w0*w1), CreaseSharpness)
d_crease  = -CreaseDepth * JointBand * (1 + CreaseCompressionGain * compression * 10)
```

`compression = max(-strain, 0)` 이므로 **strain 이 0 인 rest 포즈에서도 `-CreaseDepth * JointBand` 만큼
홈이 남는다** — 이게 편 손에서도 마디마다 보이는 주름이다. 굽히면 압축이 더해져 깊어진다.

**③ 굽힘 전용 잔주름 (`d_wrinkle`)**
관절 밴드 안에서, 본 로컬 축을 따라 사인 리플. `compression` 을 곱하므로 편 손에서는 사라진다.
본 로컬 좌표를 얻으려고 `RefBasesInvMatrix` 를 섹션 BoneMap 순서로 별도 업로드한다
(기존 본 버퍼는 `RefPoseInverse * ComponentSpace` 라 rest 좌표를 못 준다).

### 노멀 재계산이 필수
정점을 밀어도 노멀을 그대로 두면 주름이 **셰이딩에 전혀 안 나타난다**. 그래서 변위 후
인덱스 버퍼로 face normal 을 고정소수점 atomic 누적(`NORMAL_FIXED_SCALE 4096`)하고, 정점당 정규화한 뒤
기존 탄젠트를 새 노멀에 대해 Gram-Schmidt 재직교화해서 탄젠트 버퍼에 다시 쓴다. `bRecomputeNormals` 로 끌 수 있다.

### 검증 (SKM_MannyXR_right, 3239 verts, 무광 clay 머티리얼)
- **편 손(Idle)**: OFF 는 매끈, `CreaseDepth 0.06` 에서 마디 윤곽이 생기고, `0.14 / Sharpness 4` 에서 각
  손가락 마디마다 뚜렷한 주름. `Saved/Screenshots/WindowsEditor/P3_dorsal_{off,on,deep}.png`
- **굽힌 손(Grasp)**: 주름이 깊어지고, `VolumeBulge 0.35` 를 더하면 눌린 쪽이 다시 밀려나온다
  (크리즈만 vs 부피항 추가 사이 10,426 픽셀 변화). `P3_grasp_{off,crease,volume}.png`
- 포즈·가시성·`bDetailDisplacement`·`bRecomputeNormals` 를 반복 토글해도 크래시 없음, 디포머 경고/에러 0.

### 권장 기본값과 한계
`VolumeBulge 0.18` · `CreaseDepth 0.08` · `CreaseSharpness 3.5` · `CreaseCompressionGain 2.0` ·
`WrinkleAmplitude 0.04` · `WrinkleFrequency 6.0` (cm 단위, 손 크기 ~19cm 기준)

- **정점 밀도가 한계다.** 3239 정점 손에서는 마디당 굵은 주름 1~2줄이 한계고, 깊게 주면 실루엣에 계단이
  보인다. 설계서 UC5 의 Nanite 테셀레이션이 이 항 아래에 깔려야 진짜 피부 잔주름이 된다.
- 관절 밴드는 정점별 웨이트에서 바로 나오므로 저폴리 메시에서 다소 울퉁불퉁하다. 라플라시안 평활 패스를
  한 번 넣으면 부드러워진다(미구현).
- 변위는 등방 근사라 주름의 **방향성**이 없다. 방향이 필요하면 삼각형 변형 그래디언트의 주축을 추가 스트림으로.

## 1-G. Phase 3b 구현 (2026-09-20) — 테셀레이션 + 텐션 구동 핏줄/디테일 노멀

1-F 의 결론이 "정점 밀도가 한계다" 였으므로, 밀도를 먼저 올리고 그 위에 머티리얼 디테일을 얹었다.

### 왜 Nanite 테셀레이션이 아닌가

설계서 UC5 는 Nanite 테셀레이션을 전제했지만 **이 파이프라인과 호환되지 않는다.** 커스텀 스키닝은
`FSkeletalMeshDeformerHelpers` 가 잡아 주는 GPU skin **passthrough 정점 팩토리** 버퍼에 결과를 쓰는데,
Nanite 메시는 그 정점 팩토리를 거쳐 그려지지 않는다. Nanite 를 켜는 순간 커스텀 스키닝 전체가 우회된다
(5.6 기준 `r.Nanite.AllowTessellation` 도 기본 0). 따라서 밀도는 **에셋 단계에서** 올려야 한다.

### 1) 에셋 테셀레이션 — `Scripts/subdivide_hand.py`

GeometryScripting 플러그인(`.uproject` 에 추가)으로 PN 테셀레이션을 건다. PN 은 실루엣을 부드럽게
유지하면서 정점 속성(스킨 웨이트 포함)을 보간하므로 스켈레탈 메시에 그대로 쓸 수 있다.

```
copy_mesh_from_skeletal_mesh(LOD0) -> DynamicMesh
apply_pn_tessellation(level=3)     -> 삼각형 (N+1)^2 배
create_new_skeletal_mesh_asset_from_mesh(dyn, Skeleton, path, opts)
```

| | 삼각형 | 정점(렌더) |
|---|---|---|
| `SKM_MannyXR_right` | 11,462 | 3,239 |
| `SKM_MannyXR_right_Dense` | 183,392 | 93,725 |

스킨 웨이트는 그대로 따라오고(`mesh_has_bone_weights` = true), 스켈레톤과 머티리얼 슬롯도 원본을 재사용한다.

Python API 주의: 클래스는 `GeometryScript_AssetUtils` / `GeometryScript_NewAssetUtils` 이고
(`GeometryScript_SkeletalMeshes` · `GeometryScript_CreateNewAsset` 는 없다), 삼각형 수는
`GeometryScript_MeshQueries.get_num_triangle_i_ds` 다 (`get_triangle_count` 없음).
`create_new_skeletal_mesh_asset_from_mesh` 는 스켈레톤을 **옵션이 아니라 인자로** 받고
경로는 패키지+이름이 아니라 전체 경로 문자열 하나다.

### 2) 머티리얼 디테일 — `Scripts/create_skin_material.py` → `M_PianoHandSkin` / `MI_PianoHandSkin`

92k 정점에서도 주름 한 줄은 정점 몇 개 폭이다. 실제 피부 요철은 그보다 한 자릿수 미세하므로
셰이딩 노멀로 간다(설계서 UC4). 텍스처는 하나도 쓰지 않고 전부 절차적이며, 지오메트리와 **같은
스트레인 필드**(1-C 의 Vertex Color)로 구동되므로 둘이 어긋나지 않는다.

Custom HLSL 노드 하나가 높이장을 만들고 유한차분으로 탄젠트 공간 노멀을 뽑는다. 높이장은 세 층이다.

- **macro** — 저주파 굵은 굴곡 주름. 압축(G)으로 진폭이 커진다.
- **micro** — ±60° 로 교차하는 고주파 선 두 벌의 **합집합**(`max`)→ 피부 다이아몬드 미세 요철. 항상 켜짐.
- **veins** — 성긴 넓은 융기. **신장(R)** 으로 드러난다. 주름과 정반대 조건이라 서로 겹치지 않는다.

세 층 모두 `-pow(1-abs(sin(...)), k)` 형태다. 부호가 음수여야 선이 **골**이 되고(양수면 두둑),
`pow` 가 골을 가늘게 만든다.

시행착오에서 나온 세 가지 함정:

1. **순수 사인은 직물처럼 보인다.** fbm 도메인 워프를 반드시 섞어야 선이 사행·분기한다.
2. **워프는 2D 여야 한다.** fbm 을 한 번만 뽑아 `float2` 로 브로드캐스트하면 대각선으로만 밀리고
   격자가 그대로 남는다. 서로 다른 오프셋으로 **두 번** 뽑아 `float2` 를 만든다.
3. **텐션 게이팅은 한 번만.** 높이에 `Blend` 를 곱한 뒤 최종 노멀을 다시 `lerp(float3(0,0,1), N, Blend)`
   하면 이중으로 눌려서(0.3 × 0.3 ≈ 0.09) 디테일이 사라진다. 게이팅은 **높이장에서만** 한다 —
   작은 기울기에서는 진폭 블렌딩과 노멀 블렌딩이 같고, 미세 요철을 게이팅에서 빼 둘 수 있다.

`Blend = saturate(WrinkleBase + Compress * CompressGain)`. `WrinkleBase` 가 안정 상태에서 남는
주름 양이라 **손가락을 쫙 폈을 때도 마디 주름이 보인다**(Phase 3 요구사항). 압축이 들어오면 깊어진다.

### 권장 기본값 (dense 메시 기준)

머티리얼 (`MI_PianoHandSkin`, 인스턴스라 재컴파일 없이 `set_skin()` 로 즉시 조정):

`WrinkleDepth 0.009` · `MicroDepth 0.0012` · `WrinkleTiling 60` · `MicroRatio 6` ·
`WrinkleWarp 2.2` · `WrinkleBase 0.30` · `CompressGain 2.2` · `NormalStrength 0.55` ·
`VeinDepth 0.020` · `VeinTiling 26` · `Eps 0.0015`

디포머 (`hand_tension_demo.py` 의 `DETAIL`):

`CreaseDepth 0.05` · `CreaseSharpness 3.0` · `CreaseCompressionGain 0.6` ·
`WrinkleAmplitude 0.035` · `WrinkleFrequency 6.0` · `VolumeBulge 0.15`

C++ 기본값은 3.2k 정점 메시 기준이라 92k 에서는 크리즈가 과하게 먹어 손가락이 깊게 접히는 곳에서
표면이 찢어진다. 압축 게인을 2.0 → 0.6 으로 내리는 것이 핵심이다.

### 검증

| 스크린샷 | 내용 |
|---|---|
| `phase3b_base_clay.png` | 3.2k 정점 + clay — 마디 주름이 뭉개지고 면이 드러난다 |
| `phase3b_dense_clay.png` | 93.7k 정점 + clay — 마디마다 실제 기하 주름이 잡힌다 |
| `phase3b_dense_skin_idle.png` | 편 손 — 마디 주름 유지, 핏줄은 신장부에만 |
| `phase3b_dense_skin_grasp.png` | 쥔 손 — 압축부 주름이 확연히 깊고 조밀해진다 |
| `phase3b_tuned_grasp.png` | 압축 게인 0.6 — 접히는 부위 표면 찢김 해소 |

`GetCustomSkinningFrameCount` 가 계속 증가하고 디포머 경고/에러 0. 뷰포트가 백그라운드면 렌더가
스로틀링되어 프레임 카운트가 멈추므로, 확인 전에 에디터 창에 포커스를 줘야 한다.

### 남은 한계

- 주름에 **방향성이 없다**(등방 근사). 실제 주름은 압축 주축에 수직으로 생긴다. 삼각형 변형
  그래디언트의 주축을 정점 스트림으로 내보내면 macro 층의 선 방향을 거기에 맞출 수 있다.
- 테셀레이션은 오프라인 1회성이다. 카메라 거리에 따른 적응적 밀도는 없다.
- 머티리얼 주름은 UV 공간이라 UV 가 늘어난 영역에서 밀도가 달라진다. 트라이플래너나
  UV 면적 보정이 필요하면 추가 항으로.

## 2. 로드맵

### Phase 1 — 실제 스켈레탈 메시 연결 (MeshDeformer) — ✅ 완료 (1-B 참조)
- `UMeshDeformer` / `UMeshDeformerInstance` 서브클래스를 만들어 `USkeletalMeshComponent::SetMeshDeformer()` 로 붙인다.
- `FSkeletalMeshLODRenderData` 에서 rest 정점 버퍼 · 스킨 웨이트 버퍼를 읽고, 컴포넌트의 `GetComponentSpaceTransforms()` × `RefBasesInvMatrix` 로 `BoneTransforms` 를 매 프레임 업로드.
- 출력은 `FSkeletalMeshDeformerHelpers` 가 제공하는 position/tangent 버퍼(`FRWBuffer`)에 써서 엔진 정점 팩토리가 그대로 소비하게 한다. 이 경로가 DeformerGraph(Optimus)가 쓰는 공식 경로다.
- 검증: 에디터에서 기본 Skin Cache 결과와 픽셀 차이 비교.

### Phase 2 — 텐션 계산을 커널에 통합 — ✅ 완료 (1-C 참조)
- 설계서의 텐션맵 구동을 CPU/텍스처가 아니라 **정점 단위 GPU 계산**으로 옮긴다.
  - 스키닝 후 엣지 길이 vs rest 엣지 길이 → 정점별 압축/신장 스칼라 (`Tension`)
  - 인접 정점 리스트(offset/adjacency 버퍼)를 프리컴퓨트해 두 번째 커널에서 계산
- `Tension` 을 추가 정점 스트림(예: UV 채널 또는 컬러)으로 내보내 머티리얼에서 읽는다.

### Phase 3 — 디테일 변위 (설계서 UC2~UC4) — ✅ 완료 (1-F, 1-G 참조)
- 주름(`disp_w`) · 부피보존은 컴퓨트 패스에서, 핏줄(`disp_v`) · 디테일 노멀 블렌드는 머티리얼에서, 모두 같은 텐션 필드로 구동. (1-F, 1-G)
- 밀도는 Nanite 가 아니라 **에셋 PN 테셀레이션**으로 올렸다 — Nanite 메시는 passthrough 정점 팩토리를 쓰지 않아 커스텀 스키닝을 통째로 우회한다 (1-G 참조).
- 남은 것: 주름 방향성(변형 그래디언트 주축), 적응적 밀도.

### Phase 4 — Chaos Flesh 표면 입력
- Chaos Flesh 시뮬레이션 결과(변형 표면 · 스트레인)를 rest 대신 입력으로 받는 어댑터.

---

## 3. 주의사항
- 글로벌 셰이더를 게임 모듈에 두므로 모듈 로딩 단계는 반드시 `PostConfigInit` 이어야 한다. `Default` 로 두면 셰이더 맵 컴파일 시 `/PianoHand` 경로를 찾지 못한다.
- `.uproject` 나 `Build.cs` 를 바꾼 뒤에는 Live Coding 이 아니라 **에디터를 닫고 전체 빌드**해야 반영된다.
- 노멀 변환은 현재 회전/균등 스케일만 가정한다(3x3 부분 그대로 사용). 비균등 스케일 본이 있으면 inverse-transpose 가 필요하다.
