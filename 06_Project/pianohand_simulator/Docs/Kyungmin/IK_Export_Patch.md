# IK 프로그램에 "관절 각도 CSV 내보내기" 추가하기 (제안 패치)

대상: `02_Implementation/02_IK/src/Vulkan_IK_Tutorial.cpp` (2026-10-25 기준 2,273줄)

IK는 이미 매 프레임 관절 각도를 `hand[i].joints[j].angle`에 계산해 두고 있고, 화면에 그리기만 한다. 파일로 쓰는 코드만 없다. 아래 네 군데를 더하면 `docs/Kyungmin/IK_Handoff_Format.md` 형식의 CSV가 나온다.

> **주의**: 이 패치는 제가 컴파일해 보지 못했다(Vulkan SDK 필요). 줄 번호와 식별자는 코드를 읽고 확인했다. 컴파일 에러가 나면 알려 주세요.

## 왜 실시간 루프에서 꺼내지 않는가

화면 루프(`drawFrame`, 약 1998줄)는 `high_resolution_clock`의 실제 경과 시간으로 `time`을 넣는다. 모니터 주사율에 따라 프레임 간격이 일정하지 않아서 30 FPS 데이터가 되지 않는다. 그래서 `time = frame / 30`으로 직접 돌리는 **별도 루프**를 쓴다. `updateJacobianKinematics`가 `static` 변수에 상태를 쌓으므로, 실시간 루프(`mainLoop`)가 시작되기 **전에** 실행한다.

## 변경 4곳

**① 멤버 변수 추가** (`wristCenterZ` 선언 근처, 418줄)

```cpp
    glm::vec3 exportRightWrist = glm::vec3(0.0f);   // 내보내기용: 오른손목 위치(IK 단위)
```

**② 손목 위치를 밖으로 빼기** (`updateJacobianKinematics` 안, 1691줄 `wristCenterZ = ...` 바로 아래)

```cpp
        exportRightWrist = currentRightWrist;       // currentRightWrist 는 함수 안 static 이라 밖에서 못 본다
```

**③ 내보내기 함수 추가** (`updateJacobianKinematics` 아래 어디든)

```cpp
    // 오른손 관절 각도와 손목 위치를 30 FPS CSV로 저장한다 (형식: IK_Handoff_Format.md)
    void exportJointAnglesCsv(const std::string& jointsPath, const std::string& wristPath, float fps = 30.0f) {
        const float cmPerUnit = 2.3f / kWhiteKeyWidth;        // 흰 건반 폭: IK 0.45 = 실제 2.3 cm
        static const char* fingerNames[5] = { "thumb", "index", "middle", "ring", "pinky" };
        static const char* jointSuffix[3] = { "01", "02", "03" };   // joints[0..2] -> _01_r, _02_r, _03_r

        std::ofstream jf(jointsPath), wf(wristPath);
        if (!jf || !wf) { std::cerr << "[Export] cannot open output files" << std::endl; return; }
        jf << "frame,time_ms,bone,flex_deg,abd_deg,twist_deg\n";
        wf << "frame,time_ms,x_cm,y_cm,z_cm,yaw_deg,pitch_deg,roll_deg\n";
        jf << std::fixed << std::setprecision(4);
        wf << std::fixed << std::setprecision(4);

        const int frames = static_cast<int>(std::ceil(songLengthMs / 1000.0f * fps));
        for (int frame = 0; frame <= frames; ++frame) {
            const float t = frame / fps;
            updateJacobianKinematics(t, getActiveNotesForCurrentTime(t));
            const float timeMs = frame * 1000.0f / fps;

            for (int f = 0; f < 5; ++f) {
                const Finger& finger = hand[5 + f];            // 5~9 = 오른손 (엄지 -> 소지)
                for (int j = 0; j < 3; ++j) {                  // joints[3] 은 손가락 끝이라 각도가 없다
                    const glm::vec3& a = finger.joints[j].angle;   // 라디안
                    jf << frame << ',' << timeMs << ',' << fingerNames[f] << '_' << jointSuffix[j] << "_r,"
                       << -glm::degrees(a.x) << ','            // IK 는 굴곡을 음수로 저장 -> 닫힘이 + 가 되게 부호 반전
                       << glm::degrees(a.y) << ','
                       << glm::degrees(a.z) << '\n';
                }
            }
            wf << frame << ',' << timeMs << ','
               << exportRightWrist.x * cmPerUnit << ','        // x: 앞뒤, y: 높이, z: 좌우 (IK 축 그대로)
               << exportRightWrist.y * cmPerUnit << ','
               << exportRightWrist.z * cmPerUnit << ",0,0,0\n";   // IK 에는 손목 회전이 없다
        }
        std::cout << "[Export] wrote " << frames + 1 << " frames to " << jointsPath << std::endl;
    }
```

**④ 호출** (`run()`, 372~373줄 사이)

```cpp
        initVulkan();
        if (std::getenv("PH_EXPORT_CSV")) {            // 환경 변수 PH_EXPORT_CSV 가 있을 때만 내보낸다
            exportJointAnglesCsv("ik_joints.csv", "ik_wrist.csv");
        }
        mainLoop();
```

**⑤ include 추가** (`#include <fstream>` 근처, 12줄)

```cpp
#include <iomanip>
```

## 실행과 확인

```
set PH_EXPORT_CSV=1
Vulkan_IK_Tutorial.exe
python Scripts/check_ik_csv.py ik_joints.csv ik_wrist.csv
```

검증기가 통과하면 UE 쪽 임포터(`import_ik_csv_to_anim.py`)에 그대로 넣을 수 있다.

## 알아 둘 점

- 내보내는 건 **오른손**이다(스키닝 쪽에 오른손 메시만 있음). 왼손은 `hand[0..4]`로 같은 방식이다.
- `joints[0..2]`가 `*_01_r ~ *_03_r`에 대응한다. `*_metacarpal_r`은 IK에 없어서 보내지 않는다.
- `songLengthMs`는 곡 길이 + 0.5초이고 `getActiveNotesForCurrentTime`은 그 길이로 반복한다. 곡 전체가 한 번 나온다.
- 프레임 사이 점프가 보이면(검증기 경고) 이전 프레임 결과를 초기값으로 쓰는 개선이 필요하다. 지금은 매 프레임 0도에서 시작한다.
