# Flesh → 스키닝 어댑터 (04_Flesh ↔ 03_Skinning)

Flesh가 계산한 표면 위치를 스키닝 직후에 섞어 넣는다. 합의 사항(2026-10-27, 곽경민·이수민):
스키닝 직후에 섞기 / 이음매는 수민 방식(순서가 같으면 불필요) / 입력 구멍은 곽경민 별도 파일, 수민은 읽는 몇 줄 / Flesh 쓸 때는 손 크기 조절(Phase 5) 끔.

## 파일 (곽경민 쪽, 전부 새 파일)

| 파일 | 역할 |
|---|---|
| `Source/pianohand_simulator/Flesh/PianoHandFleshInput.h/.cpp` | 게임 스레드 컴포넌트 `UPianoHandFleshInputComponent` + 렌더 스레드 패스 `PianoHandFlesh::AddFleshBlendPass` |
| `Shaders/Private/PianoHandFleshBlend.usf` | `Out = lerp(Skinned, Flesh, Blend)` |
| `pianohand_simulator.Build.cs` | `DataflowSimulation` 의존성 한 줄 추가 |

## 수민 쪽에서 추가할 것 (2곳)

`Source/pianohand_simulator/Skinning/PianoHandSkinDeformer.cpp`

1. 맨 위 include:
```cpp
#include "../Flesh/PianoHandFleshInput.h"
```
2. `AddSkinPasses(TEXT("SkinDeformer"), AllBones, AllBoneNormals, PositionUAV, TangentUAV);` 바로 다음 줄(Phase 8 implicit 앞):
```cpp
PianoHandFlesh::AddFleshBlendPass(GraphBuilder, MeshObject, PositionBuffer, Lod.GetNumVertices());
```
Flesh 데이터가 없거나 정점 수가 다르면 아무것도 하지 않는다(반환값은 무시해도 된다).

## 레벨 설정

1. Flesh 액터(`HandFleshAsset`)에 **Add → Piano Hand Flesh Input** 컴포넌트를 추가한다.
2. 컴포넌트 Details에서 `Skinned Actor`에 수민 손 액터(`PH_MH_Hand`)를 지정한다. 같은 액터에 있으면 비워 둔다.
3. `Blend`로 섞는 정도(0 = 스키닝만, 1 = Flesh만)를 조절한다. `Enabled`를 끄면 스키닝만 나온다.
4. Flesh 에셋의 `GenerateSurfaceBindings`가 `SKM_MH_Hand_R_Dense`로 만들어져 있어야 한다(`Target Mesh Name`과 같은 이름).
5. 수민 손 액터를 가리지 않는다(`Hidden In Game` 끄기).
6. Play 직후 Output Log에서 `[FleshInput]`을 검색한다. 정점 수와 "deviation from rest"가 한 번 찍힌다.

## 로그 읽는 법

```
[FleshInput] first frame: 74186 Flesh positions for 'SKM_MH_Hand_R_Dense'
[FleshInput] deviation from rest over 74186 verts: as-is mean A max B | converted mean C max D (cm)
```
- 정점 수가 LOD0 정점 수와 다르면 `Flesh returned N positions but LOD0 has M` 경고가 나고 섞지 않는다.
- Play 직후 첫 프레임은 휴지 자세에 가까우므로, 순서와 좌표계가 맞으면 평균이 1 cm 안쪽이다. 수십 cm이면 순서 또는 좌표계가 틀린 것이다.
- `converted`가 작으면 현재 처리(Flesh 컴포넌트 공간 → 스키닝 컴포넌트 공간)가 맞다. `as-is`가 작으면 변환이 필요 없는 설정이다.

## 알려진 한계

- Flesh 위치는 게임 스레드에서 읽어 렌더 스레드로 넘기므로 한 프레임 늦을 수 있다.
- `GetMeshImportVertexMap`/이음매 매핑은 쓰지 않는다. `GenerateSurfaceBindings`가 렌더 메시 정점마다 바인딩을 만들기 때문에 순서가 같다고 보고, 위 로그로 검증한다. 어긋나면 수민 님 `WeldCanon` 방식으로 매핑을 추가한다.
- 에디터 빌드에서만 진단 로그(rest 편차)와 `[FleshTip]`이 나온다.
- 컴파일과 동작은 확인했다(정점 수 74,186 일치, 렌더 패스 301/301 실행, 휴지 편차 평균 약 0.3 cm).

## Fast Read (속도)

엔진의 `ChaosFlesh::BoundSurfacePositions`는 호출마다 바인딩과 평가기를 다시 만들고 한 스레드로 계산해 약 46 ms가 든다. 어댑터는 이를 한 번만 만들어 캐시하고 모든 코어로 병렬 계산한다(약 7 ms). 남은 7 ms의 원인은 엔진의 `FleshDeformerImpl::GetEmbeddedPosition`이 정점마다 디버그용 `FString::Printf`를 만들어 전역 변수에 쓰는 것이었다(병렬 호출 시 스레드 경합도 생긴다). 그래서 바인딩 데이터(Parents, Weights, Offsets)를 한 번 복사해 두고 같은 수식(가중합, 표면 바인딩이면 오프셋을 뺌)을 직접 계산한다 → **약 0.2 ms**. 첫 프레임에 엔진 평가기와 64개 정점을 비교해 `[FleshInput] fast read self-check ... max difference`를 남기며 결과는 0.000000 cm였다. 실패하거나 인덱스가 범위를 벗어나면 엔진 함수로 자동 복귀한다. `Fast Read`를 끄면 엔진 함수를 쓴다. 로그: `[FleshInput] fast read ready (cached bindings, parallel)` 또는 `unavailable, using Flesh's own call`. `Build.cs`에는 `DataflowSimulation`, `ChaosFleshEngine`, `ChaosFlesh`, `Chaos`, `ChaosCore`가 추가돼 있다.

## 컴포넌트 속성

| 속성 | 기본값 | 설명 |
|---|---|---|
| `Enabled` | 켬 | 끄면 스키닝만 |
| `Blend` | 1 | 0 = 스키닝, 1 = Flesh |
| `Target Mesh Name` | `SKM_MH_Hand_R_Dense` | 바인딩 대상 메시 이름 |
| `Skinned Actor` | 비움(자기 액터) | 디포머가 붙은 손 액터 |
| `Fast Read` | 켬 | 캐시·병렬 읽기 |
| `Debug Lift Cm` | 0 | 시험용, Flesh를 +Z로 이동(5로 두면 섞임을 한눈에 확인) |
| `Log Diagnostics` | 켬 | 첫 프레임 정점 수·편차 |
| `Log Tip Error`, `Tip Log Interval` | 켬, 60 | 손끝 5개 Flesh–스킨 거리를 `[FleshTip]`으로 기록(에디터 전용) |

## 측정 로그

- `[FleshInput] game thread, avg over 300 ticks: read Flesh X ms | whole tick Y ms | frame Z ms (FPS)`: 300틱 평균.
- `[FleshInput] render pass: N calls | ran | no data | blend 0 | count mismatch`: 300회마다.
- `[FleshTip] avg over 60 ticks ...`: 손끝 거리(cm). `moving`은 손끝 속도 10 cm/s 이상 틱, `along` 음수는 Flesh가 뒤처짐.
- Flesh 솔버 비용은 재생 중 콘솔에서 `stat Chaos`(`Chaos.Deformable.UDeformableSolverComponent.Simulate` 등).

## 성능 요약 (에디터 PIE, 게임 스레드)

| 상태 | 프레임 | FPS |
|---|---|---|
| 어댑터 끔(솔버 2/5) | 44.5 ms | 약 22 |
| 어댑터 켬, Fast Read 전 | 91 ms | 약 11 |
| 어댑터 켬, Fast Read | 약 51 ms | 약 20 |
| Fast Read + 솔버 서브스텝 1·반복 3 | 약 23.7 ms | 약 42 |
| 읽기 `Printf` 제거(읽기 0.2 ms) + 솔버 1·반복 3 | 약 22~24 ms | 약 41~46 |
| 위와 같고 솔버 서브스텝 1·**반복 2**(D, **현재 기본값**) | **약 16.0~16.6 ms** | **약 60~62** |

Flesh 솔버가 기준 프레임의 대부분(41.8 ms)이었다. D 설정에서 솔버는 12.0 ms, 어댑터 한 틱은 약 0.35 ms, `stat unit`은 Game 16.7 / Draw 3.0 / GPU 4.5 ms였다(게임을 끈 상태). 목표 16.7 ms에 여유가 0.1~0.7 ms뿐이라 PIE에서 흔들리면 60 아래로 내려갈 수 있다. 측정 중 다른 게임이 켜져 있으면 프레임이 두 배가 되므로 다른 프로그램을 끄고 잰다.
