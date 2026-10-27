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
- 에디터 빌드에서만 진단 로그(rest 편차)가 나온다.
- 컴파일과 동작은 아직 확인하지 못했다.
