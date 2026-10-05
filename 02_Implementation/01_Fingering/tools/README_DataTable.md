# 운지법 JSON → UE5 DataTable 변환 가이드

**대상 독자**: 02_IK(한승현) / 03_Skinning(곽경민) / 04_Main(이수민) — UE5 측 담당자
**작성 파트**: 01_Fingering (정근녕)
**관련 명세**: `01_Design/03_Interface_Design_Spec.md` 2.2 / 2.6 / 2.7절,
`01_Design/09_Interface_Parameter_Decisions.md`

운지법 엔진이 출력한 NoteEvent JSON(Interface A)을 UE5 에디터가 바로 임포트할 수 있는
CSV로 바꾸는 도구와 그 사용법을 정리한다.

| 파일 | 역할 |
|------|------|
| `tools/export_datatable.py` | JSON → CSV 변환 스크립트 (Python 3, 표준 라이브러리만 사용) |
| `tools/FPianoNoteRow.h` | 임포트에 필요한 USTRUCT 정의 **(참조용 스니펫, 빌드 대상 아님)** |
| `tools/README_DataTable.md` | 이 문서 |

---

## 1. 스크립트 실행법

### 1.1 기본

```bash
cd 02_Implementation/01_Fingering
python tools/export_datatable.py results/deb_clai_polyphonic_result.json
```

→ `results/deb_clai_polyphonic_result_datatable.csv` 생성.

> **Windows 콘솔 주의**: 기본 코드페이지가 cp949라 한글 요약 출력이 깨질 수 있다.
> `PYTHONIOENCODING=utf-8` 을 붙여 실행할 것 (PowerShell: `$env:PYTHONIOENCODING="utf-8"`).

### 1.2 옵션

| 옵션 | 기본값 | 설명 |
|------|--------|------|
| `<result.json>` | (필수) | 운지법 결과 JSON (`results/*_polyphonic_result.json`) |
| `-o`, `--output` | `<입력폴더>/<원본이름>_datatable.csv` | 출력 CSV 경로 |
| `--fps` | `30` | `FrameIndex` / `ReleaseFrameIndex` 환산 기준 프레임레이트 |
| `--no-bom` | (미지정 = BOM 포함) | UTF-8 BOM 없이 저장 |

```bash
# 60 FPS 렌더링용, 경로 지정
python tools/export_datatable.py results/deb_clai_polyphonic_result.json \
    -o ../../../UE5Project/Content/Data/DT_ClairDeLune.csv --fps 60
```

### 1.3 실행 결과 확인

스크립트는 변환 후 자체 검증 요약을 출력한다. 마지막 줄이 `판정: PASS`여야 한다.

```
JSON 음표 수                 1491
CSV 데이터 행 수             1491      ← JSON 음표 수와 같아야 함
행 이름 고유 개수            1491      ← 행 수와 같아야 함 (RowName 중복 불가)
열 수 (행 이름 열 포함)         19
마지막 해제 프레임            7430
선택 좌표 열      TargetXMm, TargetYMm, TargetZMm
판정: PASS
```

`선택 좌표 열`이 `(없음)`으로 나오면 입력 JSON에 건반 3D 좌표가 아직 들어있지 않다는 뜻이며,
`Target*Mm` 열 자체가 CSV에 생성되지 않는다 (§4 참고).

---

## 2. UE5 에디터에서 DataTable로 임포트하기

### STEP 1 — USTRUCT를 프로젝트에 추가 (최초 1회)

1. `tools/FPianoNoteRow.h` 내용을 UE5 프로젝트 게임 모듈로 복사한다.
   예: `Source/PianoHandSimulator/Public/PianoNoteRow.h`
2. `#include "PianoNoteRow.generated.h"` 의 파일명이 실제 헤더 파일명과 일치하는지 확인한다.
3. **에디터를 닫고 프로젝트를 리빌드**한다 (Live Coding만으로는 새 USTRUCT가
   임포트 창 목록에 나타나지 않는 경우가 많다).

> `tools/` 안의 `.h`는 Python 도구 옆에 둔 **참조용 스니펫**이다. 어떤 모듈에도
> 컴파일되지 않으므로 반드시 복사해서 쓸 것.

### STEP 2 — CSV 임포트

1. Content Browser에서 대상 폴더(예: `Content/Data`)를 연다.
2. **Import** 버튼 → 생성된 `*_datatable.csv` 선택.
   (또는 CSV 파일을 Content Browser로 드래그 앤 드롭)
3. **DataTable Options** 창이 뜬다.
   - **Import As**: `DataTable`
   - **Choose DataTable Row Type**: `PianoNoteRow` 선택 ★
   - **Ignore Extra Fields**: 끄는 것을 권장 (열 이름 오타를 경고로 잡기 위해)
   - **Ignore Missing Fields**: 끄는 것을 권장
4. **Apply** → `DT_<파일명>` 애셋 생성. 더블클릭해 행 수가 요약 출력의
   「CSV 데이터 행 수」와 같은지 확인한다.
5. **Output Log**에서 경고가 없는지 확인한다. 경고가 있으면 §6을 볼 것.

### STEP 3 — 재임포트

엔진 출력이 갱신되면 스크립트를 다시 실행한 뒤, 기존 DataTable 애셋 우클릭 →
**Reimport** 로 갱신한다. 이때 RowName(`Note_00001`)이 유지되므로
RowName을 참조하는 블루프린트가 깨지지 않는다.

### STEP 4 — 사용 예 (C++)

```cpp
TArray<FPianoNoteRow*> Rows;
NoteTable->GetAllRows<FPianoNoteRow>(TEXT("PianoNotes"), Rows);

for (const FPianoNoteRow* Row : Rows)
{
    const FVector TargetCm = Row->GetTargetLocationCm();   // mm → cm 변환 포함
    SetIKGoal(Row->BoneName, TargetCm);                    // 예: thumb_03_r
    // Row->FrameIndex ~ Row->ReleaseFrameIndex 구간 동안 유지
}
```

---

## 3. 열별 의미와 단위

### 3.1 행 이름 열

| 열 | 형식 | 설명 |
|----|------|------|
| `Name` | `Note_00001` | UE5가 **RowName**으로 소비하는 첫 열. 구조체 멤버가 아니다.<br>JSON 배열 순서(= 시간 순서) 1-based 인덱스이므로 CSV N번째 행 = JSON N번째 음표. |

### 3.2 엔진 원본 필드 (Interface A 2.2절)

| 열 | 타입 | 단위/범위 | 설명 |
|----|------|-----------|------|
| `Pitch` | int32 | 21~108 | MIDI 음고 (A0~C8) |
| `StartMs` | float | **ms** | 음표 시작 시각 (곡 시작 기준 절대 시각) |
| `DurationMs` | float | **ms** | **소리**가 울리는 시간. 페달로 늘어난 청각적 지속이며 건반 해제 타이밍이 아니다 |
| `KeyHoldMs` | float | **ms** | **손가락이 건반을 누르고 있는 시간.** 해제 시각 = `StartMs + KeyHoldMs`. ★ IK는 이 값을 쓴다 |
| `PedalDown` | bool | — | 타건 시점의 Sustain 페달 상태. `True`면 손가락을 떼도 소리가 유지됨 |
| `Hand` | FString | `Left` / `Right` | 손 선택 → `hand_l` / `hand_r` |
| `Role` | FString | `MELODY` / `BASS` / `INNER` | 성부. 화음 충돌 시 우선순위 `MELODY > BASS > INNER` |
| `Finger` | int32 | 1~5 | 1=엄지, 2=검지, 3=중지, 4=약지, 5=새끼 |
| `Pressure` | float | 0.0~1.0 | 타건 강도. 손가락 가속도 곡선 / 복귀 속도에 사용 |
| `KeyDepth` | float | 0.0~1.0 | 건반 누름 깊이 비율. ×`MAX_KEY_TRAVEL`(10 mm)이 실제 하강량 |
| `IsBlack` | bool | `True` / `False` | 흑건 여부 |
| `WristPosNormalized` | float | 0.0~1.0 | 손목 가로 위치 (88키 전체 폭 기준 정규화) |
| `WristYawDeg` | float | **도**, ±35 | 손목 좌우 회전 가이드값 |
| `WristRollDeg` | float | **도**, ±20 | 손목 기울기 가이드값 |

### 3.3 건반 3D 목표 좌표 — **선택 열**

| 열 | 타입 | 단위 | 설명 |
|----|------|------|------|
| `TargetXMm` | float | **mm** | 좌우. 원점 = 88키 최좌단 A0(MIDI 21) 좌측 모서리 |
| `TargetYMm` | float | **mm** | 앞뒤 타건 접점. 백건 30.0 / 흑건 85.0 |
| `TargetZMm` | float | **mm** | 높이. `(IsBlack ? 12.5 : 0.0) - KeyDepth × 10.0` |

입력 JSON에 해당 필드가 없으면 **이 세 열은 생성되지 않는다.** 그 경우
`Pitch` + `KeyDepth`로 UE5 측에서 직접 계산해야 하며,
변환 규칙은 `01_Design/09_Interface_Parameter_Decisions.md` 3~5장에 있다.

### 3.4 변환 도구가 추가한 파생 열

| 열 | 타입 | 설명 |
|----|------|------|
| `BoneName` | FName | IK End Effector 본 이름. 명세서 2.6절 매핑을 그대로 적용<br>(`thumb_03_r`, `index_03_l`, `middle_03_*`, `ring_03_*`, `pinky_03_*`) |
| `FrameIndex` | int32 | 타건 프레임 = `round(StartMs × fps / 1000)` |
| `ReleaseFrameIndex` | int32 | **건반 해제** 프레임 = `round((StartMs+KeyHoldMs) × fps / 1000)`.<br>계산 결과가 `FrameIndex`와 같아지면 `FrameIndex + 1`로 보정(최소 1프레임 유지).<br>소리 종료가 아니라 **손가락이 떨어지는** 프레임이다 |

---

## 4. ★ 좌표 단위 주의 — mm vs cm

> **운지법 엔진 출력은 밀리미터(mm), UE5 월드 기본 단위는 센티미터(cm)다.**
> `TargetXMm / TargetYMm / TargetZMm` 를 그대로 `FVector`에 넣으면
> **손이 피아노보다 10배 크게 움직인다.**

변환 도구는 **단위를 임의로 바꾸지 않는다.** 엔진이 산출한 mm 값을 그대로
기록하고, 열 이름에 `Mm` 접미사를 붙여 단위를 명시하는 방식을 택했다.
(CSV 안에서 cm로 몰래 바꾸면, 설계 명세서의 mm 수치와 DataTable 값이 달라져
추적이 어려워지기 때문이다.)

따라서 **환산은 UE5 측에서 1회 수행**한다. `FPianoNoteRow.h`에 헬퍼를 포함해 두었다.

```cpp
// 권장: 헬퍼 사용
const FVector TargetCm = Row->GetTargetLocationCm();      // (X,Y,Z) * 0.1

// 직접 쓸 경우
const FVector TargetCm = FVector(Row->TargetXMm, Row->TargetYMm, Row->TargetZMm) * 0.1f;
```

참고로 **`KeyDepth`는 0~1 정규화값이므로 단위 문제가 없다.** 명세서 2.4절대로
`Z = -(KeyDepth × MAX_KEY_TRAVEL)`로 쓰되, `MAX_KEY_TRAVEL`을 cm(=1.0)로 두면
결과가 바로 cm가 된다.

| 값 | 엔진 표기 | UE5에서 쓸 값 |
|----|-----------|---------------|
| `MAX_KEY_TRAVEL` | 10.0 mm | 1.0 cm |
| 백건 폭 | 23.4 mm | 2.34 cm |
| 흑건 상면 높이 | 12.5 mm | 1.25 cm |
| 흑건 Y 오프셋 | 55.0 mm | 5.5 cm |

> 각도(`WristYawDeg` / `WristRollDeg`)는 도(degree)이며 UE5 `FRotator`와 단위가 같다.
> 다만 축 대응(Yaw/Roll)은 리그 좌표계에 따라 부호가 뒤집힐 수 있어 시각 확인이 필요하다.

---

## 5. 타이밍 사용법 — `StartMs` vs `FrameIndex`

두 값은 **같은 시각을 다른 해상도로 표현**한 것이다. 용도에 따라 골라 쓴다.

| 상황 | 사용할 값 | 이유 |
|------|-----------|------|
| AnimSequence / Sequencer **키프레임 삽입** | `FrameIndex`, `ReleaseFrameIndex` | 키프레임은 정수 프레임 단위라 반올림 결과를 그대로 써야 양쪽이 일치한다 |
| Movie Render Queue 오프라인 렌더 | `FrameIndex`, `ReleaseFrameIndex` | 고정 프레임레이트 렌더링과 1:1 대응 |
| 런타임 재생 (가변 프레임레이트, Tick 기반) | `StartMs`, `KeyHoldMs` | 프레임이 흔들려도 실제 시각이 정확히 유지된다 |
| 오디오 동기 / 지연 보정 | `StartMs`, `DurationMs` | 소리의 지속이 필요한 유일한 경우 (프레임은 최대 ±0.5프레임 오차) |
| IK 보간 구간(approach / release) 계산 | `StartMs`, `KeyHoldMs` | 프레임 사이 중간 시각을 다룰 수 있다 |

**중요 — 반드시 변환 때와 같은 FPS로 재생할 것.**
`FrameIndex`는 `--fps` 값(기본 30)에 묶여 있다. 60 FPS로 렌더하려면
`--fps 60`으로 CSV를 다시 생성해야 하며, 그러지 않으면 전체 타이밍이 2배로 늘어진다.
Interface B(02_IK → 03_Skinning)가 30 FPS 기준이므로 기본값 30을 유지하는 것을 권장한다.

### 타이밍 동기화 프로토콜 (명세서 2.7절)

```
t = StartMs  (= FrameIndex 프레임)
  · Fingertip이 Target Position에 "도달 완료"된 상태여야 한다 (건반 눌림 시작)
  · Z = -(KeyDepth × MAX_KEY_TRAVEL)
  → 따라서 접근(approach) 모션은 StartMs 이전 구간에서 미리 수행해야 한다

t = StartMs ~ StartMs + KeyHoldMs  (= FrameIndex ~ ReleaseFrameIndex)
  · 해당 position 유지

t = StartMs + KeyHoldMs  (= ReleaseFrameIndex 프레임)
  → PedalDown=True 인 음표는 손가락이 떨어진 뒤에도
     StartMs + DurationMs 까지 소리가 계속 울린다 (오디오 측에서 처리)
  · Fingertip Z → 0 복귀
  · 복귀 속도는 (1.0 - Pressure)에 반비례 (강타일수록 천천히 복귀)
```

### 화음(동시 타건) 처리

같은 `StartMs` 값을 가진 행이 여러 개 있는 것이 정상이다(화음). 예시 CSV의
`Note_00001` / `Note_00002`는 둘 다 `StartMs = 300`이다.
같은 `Hand` + 같은 `StartMs` 행들을 **한 프레임에 모아** 복수 End Effector 타겟을
동시에 설정하고, 충돌 시 `Role` 우선순위(`MELODY > BASS > INNER`)를 적용한다
(명세서 3.5절).

---

## 6. UE5 임포트 시 주의사항 / 문제 해결

| 증상 | 원인 | 대처 |
|------|------|------|
| 임포트 창에 `PianoNoteRow`가 없다 | USTRUCT 미추가 또는 리빌드 안 함 | §2 STEP 1 재확인 후 에디터 재시작 + 리빌드 |
| 행이 하나도 안 들어온다 | Row Type을 엉뚱한 구조체로 선택 | Row Type을 `PianoNoteRow`로 재선택 후 재임포트 |
| `Unknown property 'XXX'` 경고 | CSV 헤더와 UPROPERTY 이름 불일치 | 헤더는 §3 표 기준. 구조체를 직접 수정했다면 이름을 다시 맞출 것 |
| `Row 'Note_xxxxx' is duplicated` | RowName 중복 | 스크립트가 고유성을 보장하므로, CSV를 수동 편집했는지 확인 |
| 숫자가 전부 0으로 들어온다 | 열이 비어 있거나 Target 열이 없음 | 요약 출력의 「선택 좌표 열」 확인 (§1.3) |
| 한글/특수문자가 깨진다 | 인코딩 | CSV는 **UTF-8 (BOM 포함)** 으로 생성된다. Excel 등으로 열어 저장하면 cp949로 바뀔 수 있으니 **CSV를 직접 편집하지 말 것** |

### 인코딩에 대한 메모

출력 CSV는 기본적으로 **UTF-8 BOM 포함(`utf-8-sig`)** 으로 저장한다.
UE5의 `FFileHelper::LoadFileToString`은 BOM이 없는 바이트열을 ANSI로 해석할 수 있어,
BOM을 붙이면 UTF-8로 확실히 인식된다. UE는 임포트 시 BOM을 제거하므로
첫 열 헤더가 `Name`으로 정상 인식된다 (검증 완료).
BOM을 싫어하는 외부 파이프라인(git diff 도구, 일부 CSV 라이브러리)에 넣을 때는
`--no-bom` 을 쓴다.

### 그 밖의 주의점

- **DataTable은 사전 계산된 정적 데이터다.** 행 순서는 시간 순이지만, UE5에서
  `GetAllRows`의 반환 순서를 신뢰하지 말고 필요하면 `StartMs`로 명시적으로 정렬할 것.
- **데이터 규모**: Clair de Lune = 1,491행, Mario Medley = 5,435행.
  매 Tick마다 전체 순회하면 비용이 크므로, 임포트 후 `FrameIndex` 기준
  버킷(`TMap<int32, TArray<...>>`)으로 한 번 인덱싱해 두는 것을 권장한다.
- **값 범위 검증은 엔진 쪽에서 이미 수행**했다(MAX_SPAN, 손목 ROM 클램핑).
  UE5에서 범위를 다시 클램핑하면 의도된 자세가 뭉개질 수 있으니, 이상값이 보이면
  클램핑하지 말고 01_Fingering에 알릴 것.
- **`BoneName`은 MetaHuman 표준 본 이름을 전제**한다. 다른 리그를 쓰면
  `BoneName`을 리맵하는 테이블이 UE5 측에 추가로 필요하다 (명세서 3.2절 계층 구조 참고).

---

*문서 종료*
