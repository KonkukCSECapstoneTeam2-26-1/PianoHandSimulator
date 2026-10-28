# IK → Flesh/스키닝 인계 형식 (v1 초안)

02_IK가 계산한 손가락 관절 각도를 UE5 손(MetaHuman)에 넘기는 형식이다. IK 쪽은 UE 없이 **CSV 두 개**만 내보내면 되고, `AnimSequence` 변환은 `Scripts/import_ik_csv_to_anim.py`가 한다.

```
IK 프로그램 ──▶ joints.csv + wrist.csv ──▶ check_ik_csv.py (검증) ──▶ import_ik_csv_to_anim.py ──▶ AnimSequence ──▶ Flesh / 스키닝
```

## 1. 파일

| 파일 | 내용 | 행 단위 |
|---|---|---|
| `*_joints.csv` | 손가락 관절 각도 (필수) | 프레임 × 뼈 |
| `*_wrist.csv` | 손목 위치·회전 (선택) | 프레임 |

오른손만 먼저 받는다. 스키닝 쪽에는 오른손 메시(`SKM_MH_Hand_R`)만 있다.

## 2. 열

**joints.csv**: `frame,time_ms,bone,flex_deg,abd_deg,twist_deg`

| 열 | 뜻 |
|---|---|
| `frame` | 0부터 연속 정수 |
| `time_ms` | `frame × 1000 / 30` (±1 ms) |
| `bone` | 아래 19개 뼈 이름 중 하나 |
| `flex_deg` | 굴곡. **닫히는 방향이 +** |
| `abd_deg` | 벌림(외전·내전). 손가락을 옆으로 벌리는 회전 |
| `twist_deg` | 손가락 축을 도는 회전 |

각도는 **기준 자세 대비 변화량(도)** 이다. 기준 자세(손가락이 거의 펴진 MetaHuman 기본 자세)에서 0이다.

**wrist.csv**: `frame,time_ms,x_cm,y_cm,z_cm,yaw_deg,pitch_deg,roll_deg`

## 3. 뼈 이름 (IK가 채우는 15개 + 선택 4개)

IK 프로그램(`Vulkan_IK_Tutorial.cpp`, `initHand`)은 손가락마다 관절 4개(`joints[0..3]`)를 두고, **앞의 3개만 각도(`angle`)를 가진다.** `joints[3]`은 손가락 끝 위치일 뿐이다. 그래서 대응은 이렇다.

| 손가락 | IK `joints[j]` | UE 뼈 |
|---|---|---|
| 엄지 | `[0]`, `[1]`, `[2]` | `thumb_01_r`, `thumb_02_r`, `thumb_03_r` |
| 검지·중지·약지·소지 | `[0]` (MCP) | `<finger>_01_r` |
| | `[1]` (PIP) | `<finger>_02_r` |
| | `[2]` (DIP) | `<finger>_03_r` |
| | 없음 | `<finger>_metacarpal_r` (선택, 생략하면 기준 자세 유지) |

`<finger>` = `index`, `middle`, `ring`, `pinky`. IK의 `hand[5..9]`가 오른손(엄지→소지 순)이다.

IK 모델에는 중수골(metacarpal) 관절이 없어서, `metacarpal` 뼈 4개는 보내지 않아도 된다(검증기가 경고만 한다).

## 4. 검증

보내기 전에 아래를 실행한다. UE는 필요 없다.

```
python Scripts/check_ik_csv.py joints.csv [wrist.csv]
```

- **ERROR**: 헤더, 뼈 이름, 프레임 번호, `time_ms`, 프레임 수가 규칙에 안 맞음. 임포트가 막힌다.
- **WARN**: 각도 범위를 벗어났거나(부호·단위 실수 의심) 한 프레임에 크게 튐(연속성 의심). 임포트는 되지만 확인이 필요하다.

## 5. 가져오기 (UE 에디터)

```python
IK_JOINTS_CSV = r'C:/path/to/joints.csv'
IK_WRIST_CSV  = r'C:/path/to/wrist.csv'
IK_ANIM_NAME  = 'A_IK_Import'
exec(open(r'<project>/Scripts/import_ik_csv_to_anim.py').read())
```

손목 위치는 기본으로 적용되지 않는다(IK 축과 UE 축이 달라서). 시험하려면 `IK_APPLY_WRIST_TRANSLATION = True`를 먼저 지정한다. IK 프로그램에서 이 CSV를 뽑는 방법은 `IK_Export_Patch.md`에 있다.

결과는 `/Game/Characters/MetaHumanHand/<IK_ANIM_NAME>`. 임포터가 맞는지는 `Scripts/test_ik_import.py`로 확인한다. 샘플 CSV는 `A_MH_Hand_Cycle`과 같은 동작이라, 가져온 결과가 그 애니메이션과 같아야 한다.

## 6. 샘플

`Docs/Kyungmin/samples/ik_sample_joints.csv`, `ik_sample_wrist.csv` (4초 쥐었다 펴기, 121프레임). 생성: `python Scripts/make_sample_ik_csv.py`.

## 7. 미확정 사항

| # | 항목 | 현재 가정 | 확인할 곳 |
|---|---|---|---|
| 1 | `flex_deg` 부호 | 닫힘 = +. **코드로 확인됨**: IK는 굴곡을 음수로 저장한다(`flexionExtension.x = -굴곡한계`, 단위 라디안) | 내보낼 때 `flex_deg = -degrees(angle.x)` |
| 2 | `abd_deg`, `twist_deg`의 부호와 축 | `abd_deg = degrees(angle.y)`, `twist_deg = degrees(angle.z)`를 그대로 pitch, roll로 적용 | 시각 확인 후 `import_ik_csv_to_anim.py`의 `SIGN`에서 한 번에 수정 |
| 3 | 손목 위치의 단위·축 | IK는 cm가 아니라 자체 단위(흰 건반 폭 0.45 = 실제 2.3 cm, 약 5.1배)이고 x=앞뒤, y=높이, z=좌우. UE는 Z-up 왼손 좌표계 | 단위는 내보낼 때 환산. 축 변환은 아직 없어서 **임포터는 손목 위치를 기본으로 적용하지 않는다** |
| 4 | 손목 회전 | **IK에는 손목 회전이 없다**(손목은 위치만 보간). `yaw/pitch/roll`은 0으로 채운다 | 운지법의 `wrist_yaw_deg`, `wrist_roll_deg` 반영은 IK 쪽 향후 과제 |
| 5 | 손목 위치 처리 | 미정 | `hand_r` 트랙으로 넣을지 컴포넌트 이동으로 처리할지 팀에서 결정 |
| 6 | 프레임 연속성 | **점프 위험이 코드로 확인됨**: 매 타임스텝마다 관절 각도를 0으로 초기화하고 최대 40회 반복해서 푼다. 웜스타트는 국소해에 고착되어 의도적으로 뺐다(코드 주석) | 검증기가 경고함. 초기값은 건드리지 말고 기록한 각도를 시간 방향으로 평활화하는 것을 검토 |
| 7 | 손가락 비율 | IK의 마디 비율은 모든 손가락 공통 1 : 0.5 : 0.25, 손바닥 없음 | 각도만 넘기면 MetaHuman 손의 마디 길이가 달라 손끝이 건반 위치에 정확히 안 닿을 수 있음. 실측(`Scripts/dump_hand_proportions.py`, cm): 근위/중간 = 검지 4.01/1.96, 중지 4.33/2.56, 약지 3.74/2.84, 소지 2.55/1.56. 엄지는 MetaHuman에 손허리뼈 전용 뼈가 없어 `thumb_01`이 손허리뼈라서 손허리뼈/첫마디 = 4.08/2.39(같은 열이지만 한 칸 밀린 값). IK 엄지 뿌리는 MCP 줄에서 4.5 cm 뒤(해부학 추정, `thumb_01` 위치 실측 후 교체)에 두고, 엄지는 건반 앞쪽을 누른다(흰 건반 0.2, 검은 건반 0.3 IK 단위 앞). 손바닥(손목→MCP) 7.2~8.1, 손가락 뿌리 간격 1.9~2.1. 원위 마디는 뼈가 없어 정점으로 잰 값(검지 약 2.1)을 쓴다. 손가락마다 길이가 달라 공통 비율로는 완전히 맞지 않음 |
| 8 | 왼손 | 미지원 | 왼손 메시가 아직 없음 |
| 9 | 손가락 움직임의 프레임 속도 의존 | 손가락 타겟 보간이 호출 1회당 고정 비율(0.25)이라 갱신 속도에 따라 움직임이 달라짐 | 내보내기는 60 Hz로 계산해 30 FPS로 기록(패치에 반영). 근본 해결은 `dt` 기반 보간 |
| 10 | IK의 "손목" 위치 | 손가락 뿌리(MCP)가 손목 위치에 놓여 있고 손바닥 길이가 없음 | MetaHuman `hand_r`(진짜 손목)과 손바닥 길이만큼 어긋남. 손목 위치를 쓰려면 보정 필요 |
