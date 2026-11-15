# Flesh ↔ 스키닝 합치기 인계 (곽경민 → 이수민)

이수민 님 Claude 세션에 그대로 붙여 넣는 용도. 곽경민 쪽(04_Flesh)이 한 일, 수민 님 코드와 맞닿는 지점, 씬 구성.
기준: `main` `06cea9a` (2026-11-08). 수민 님의 새 결합 방식(접힘 안쪽만 받기)은 아직 깃에 없으므로 이 문서에 반영되지 않았음.

## 1. 한 줄 요약
Chaos Flesh가 시뮬레이션한 손 표면을 `SKM_MH_Hand_R_Dense`의 렌더 정점 74,186개 위치로 바꿔, 수민 님 `UPianoHandSkinDeformer`의 스키닝 패스 **바로 다음**에 `Position = lerp(Skinned, Flesh, Blend)`로 섞는다. Flesh 데이터가 없으면 아무 일도 안 하므로, 디포머 코드는 Flesh가 없는 레벨에서도 그대로 동작한다.

## 2. 곽경민 쪽 파일 (수민 님 파일 아님)
| 파일 | 역할 |
|---|---|
| `Source/pianohand_simulator/Flesh/PianoHandFleshInput.h/.cpp` | 게임 스레드 컴포넌트 `UPianoHandFleshInputComponent`(Flesh 읽기 → 게시), 렌더 스레드 함수 `PianoHandFlesh::AddFleshBlendPass` |
| `Shaders/Private/PianoHandFleshBlend.usf` | `BlendCS`: `PositionBufferUAV = lerp(Position, FleshPositions, BlendWeight)` |
| `pianohand_simulator.Build.cs` | 의존성 `DataflowSimulation`, `ChaosFleshEngine`, `ChaosFlesh`, `Chaos`, `ChaosCore` 추가 |
| `Scripts/attach_skin_deformer_flesh.py` | `L_FleshTest`의 `PH_MH_Hand`에 디포머를 붙이고 DETAIL 값 적용(레벨에 디포머가 저장돼 있지 않아서) |
| `Content/PianoHand/FleshAssets/HandFleshAsset(.uasset, _Dataflow)` | Flesh 에셋과 Dataflow 그래프 |
| `Content/PianoHand/Maps/L_FleshTest.umap` | 합친 결과를 보는 테스트 레벨 |

## 3. 수민 님 코드와 맞닿는 지점 (2줄, 이미 `main`에 있음)
`Source/pianohand_simulator/Skinning/PianoHandSkinDeformer.cpp`
```cpp
#include "../Flesh/PianoHandFleshInput.h"  // 04_Flesh adapter (kyungmin)        // 24행 부근
...
AddSkinPasses(...);                                                                // 스키닝
PianoHandFlesh::AddFleshBlendPass(GraphBuilder, MeshObject, PositionBuffer, Lod.GetNumVertices()); // 432행 부근, implicit skinning(Phase 8) 앞
```
- 시그니처: `bool AddFleshBlendPass(FRDGBuilder&, const FSkeletalMeshObject* Key, FRDGBufferRef PositionBuffer, uint32 NumLodVertices)`
- `Key`는 `USkeletalMeshComponent::GetMeshObject()`. 게임 스레드가 같은 키로 게시한 위치를 찾는다.
- false를 돌려주고 아무것도 안 하는 경우: 게시된 데이터 없음 / `Blend` 0 / 정점 수 불일치.
- 섞인 위치는 PositionBuffer에 덮어써지므로 그 뒤의 implicit skinning, 주름, 이음매 용접은 섞인 위치를 입력으로 받는다.
- 노멀/탄젠트는 섞지 않는다(위치만).

## 4. 데이터 흐름 (매 프레임)
1. 애니메이션 → 뼈 자세.
2. Flesh 솔버(`DeformableSolverActor`)가 사면체 5,688 정점을 시뮬레이션.
3. `UPianoHandFleshInputComponent::TickComponent`(TG_PostUpdateWork, Flesh 컴포넌트 다음):
   - `GenerateSurfaceBindings`로 만든 바인딩(Parents/Weights/Offsets)으로 렌더 정점 74,186개 위치 계산. 바인딩은 처음 한 번 복사해 두고 병렬 계산(약 0.2 ms).
   - Flesh 컴포넌트 공간 → 스키닝 컴포넌트 공간 변환(같으면 생략).
   - `PianoHandFlesh::Publish(Key, Positions, Blend)`로 렌더 스레드에 넘김.
4. 렌더 스레드: 수민 님 디포머 → 스키닝 → `AddFleshBlendPass`(섞기) → 이후 단계.

정점 순서: `GenerateSurfaceBindings`가 렌더 메시 LOD0 정점마다 바인딩을 만들어 순서가 같다. 첫 프레임 로그로 검증(휴지 편차 평균 약 0.3 cm). 별도 매핑(WeldCanon 등)은 쓰지 않는다.

## 5. 컴포넌트 속성 (`Piano Hand Flesh Input`)
| 속성 | 기본값 | 설명 |
|---|---|---|
| `Enabled` | 켬 | 끄면 스키닝만 |
| `Blend` | 1 | 0 = 스키닝, 1 = Flesh. **전체 정점에 같은 값** |
| `Target Mesh Name` | `SKM_MH_Hand_R_Dense` | 이 메시를 쓰는 스켈레탈 컴포넌트를 찾음 |
| `Skinned Actor` | 비움 | 디포머가 붙은 손 액터(`PH_MH_Hand`). 비우면 자기 액터 |
| `Fast Read` | 켬 | 끄면 엔진 함수(약 46 ms) |
| `Debug Lift Cm` | 0 | 시험용. 5로 두면 섞인 결과가 위로 떠서 섞임 여부가 바로 보임 |
| `Log Diagnostics`, `Log Tip Error` | 켬 | 첫 프레임 진단, 손끝 어긋남 `[FleshTip]`(에디터 전용) |

## 6. 수민 님 새 결합 방식(접힘 안쪽만)과 합칠 때
- 지금 API는 **전역 Blend 하나**뿐이다. 접힘 안쪽만 받으려면 정점별 가중치가 필요하다.
- 가능한 방법(제안, 미구현):
  1. `AddFleshBlendPass`에 정점별 가중치 버퍼(수민 님의 접힘/텐션 마스크)를 받는 인자를 추가하고, `PianoHandFleshBlend.usf`에서 `lerp(P, Flesh, BlendWeight * Mask[i])`로 바꾼다.
  2. 또는 Flesh 위치 버퍼를 꺼내는 함수(예: `GetFleshPositionsSRV`)를 추가해 수민 님 패스 안에서 직접 쓴다.
- 섞는 위치(스키닝 직후, implicit 앞)를 옮길 경우, 뒤 단계가 Flesh 위치를 입력으로 받는다는 점을 고려.
- `Flesh/` 파일은 곽경민 담당이지만 합치기 위해 수정해도 됨. 수정 내용은 알려 주면 문서에 반영.

## 7. 씬 구성 (`L_FleshTest`)
| 액터 | 구성 | 설정 |
|---|---|---|
| `PH_MH_Hand` (수민 님 손) | 스켈레탈 메시 `SKM_MH_Hand_R_Dense` + `UPianoHandSkinDeformer` | 디포머는 레벨에 저장 안 됨 → 재생 전 `attach_skin_deformer_flesh.py` 실행(LINEAR_BLEND, tension 켬, DETAIL 값). `Hidden In Game` 끔 |
| `HandFleshAsset` (Flesh) | Deformable Tetrahedral 컴포넌트(에셋 `HandFleshAsset`) + 스켈레탈 메시 `SKM_MH_Hand_R` + `Piano Hand Flesh Input` | Flesh는 **같은 액터의** 스켈레탈 메시에서만 뼈를 읽고, 메시 이름이 에셋을 만든 `SKM_MH_Hand_R`(Dense 아님)이어야 함. `Skinned Actor = PH_MH_Hand`. Flesh 표면과 이 스켈레탈 메시는 최종 장면에서 숨김 |
| `DeformableSolverActor` | Flesh 솔버 | Flesh 컴포넌트의 솔버로 지정. **Solver Timing: Num Sub Steps 1, Num Solver Iterations 2**(기본 2/5에서 변경) |
| 애니메이션 | `A_IK_DebClai`(IK CSV → AnimSequence) | 두 손 액터에 **같은 애니메이션**, 같은 시작 시간 |

`L_PianoHandDemo`(수민 님 데모)에는 Flesh 액터·솔버·`Flesh Input`이 없다. 그래서 그 레벨에서는 Flesh가 섞이지 않고 스키닝만 나온다. 데모에서 합치려면 위 세 액터를 옮겨 와야 한다. 레벨 파일은 바이너리라 두 사람이 동시에 고치면 합칠 수 없으니 순서를 정할 것.

## 8. 재생 후 확인 (Output Log에서 `[FleshInput]` 검색)
```
[FleshInput] fast read ready (cached bindings, parallel)
[FleshInput] fast read self-check vs engine evaluator: max difference 0.000000 cm ...
[FleshInput] first frame: 74186 Flesh positions for 'SKM_MH_Hand_R_Dense'
[FleshInput] deviation from rest over 74186 verts: ... mean ~0.3~1 (cm)
[FleshInput] render pass: N calls | ran N | no data 0 | blend 0 0 | count mismatch 0
[FleshInput] game thread, avg over 300 ticks: read Flesh 0.2 ms | ... | frame ~16.5 ms (~60 FPS)
```
- `render pass`가 안 나오면 디포머가 안 붙은 것.
- `ran`이 0이고 `no data`만 늘면 `Flesh Input`이 게시를 못 하는 것(`Skinned Actor`, 메시 이름 확인).
- `count mismatch`면 Flesh 바인딩이 다른 메시로 만들어진 것 → `GenerateSurfaceBindings` 재생성.
- `stat Chaos`로 솔버 시간(`UDeformableSolverComponent.Simulate` 약 12 ms), `stat unit`으로 프레임.

## 9. 알려진 상태와 한계
- 성능(에디터 PIE, 다른 프로그램 끈 상태): 프레임 약 16.0~16.6 ms(60~62 FPS). 여유 0.1~0.7 ms. 다른 게임을 켜 두면 프레임이 두 배가 됨.
- 손끝 어긋남(Flesh vs 스켈레탈 LBS): 정지 0.35~0.50 cm(Flesh가 부피를 유지해 약간 두꺼움), 움직일 때 대부분 0.3~0.9 cm 뒤처짐, 빠른 순간(100 cm/s 이상, IK 급점프) 최대 약 3 cm.
- 프레임이 몇 초 멈춘 직후(스크린샷 등) 손끝 어긋남이 최대 10~15 cm로 튄 로그가 2건 있었음. 정상 재생에서 "터짐"은 곽경민 쪽 측정에서는 보지 못함. 수민 님이 본 "터짐"이 어떤 레벨·설정인지 알려 주면 비교 가능.
- 주먹 쥘 때 안쪽 살이 지글거림(자기충돌 없음), Damping/Inflation 튜닝 미실시.
- 섞는 것은 위치만, 한 프레임 지연 가능(게임 → 렌더 스레드 전달).
- 자세한 측정: `Docs/Kyungmin/Flesh_Adapter.md`, `Docs/Kyungmin/4.4_Chaos_Flesh_PBD_Skinning.md` 4.4.7.
