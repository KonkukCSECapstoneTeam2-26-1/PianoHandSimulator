# Claude 하이브리드 작업 환경 (MCP + 컴퓨터 사용)

에디터를 스크린샷·클릭으로만 조작하지 않고, **API로 되는 것은 MCP 툴로**, **눈으로 봐야 하는 것만 컴퓨터 사용(화면 조작)** 으로 처리한다.

---

## 1. 구성 요소

| 구성 | 위치 | 역할 |
|---|---|---|
| unreal-mcp 서버 (sam-david/unreal-mcp) | `C:\Git\unreal-mcp-server` (`dist/bin.js`) | 127개 툴. 에디터 내장 Python 원격 실행 + Remote Control API 로 동작. C++ 플러그인 불필요 |
| 프로젝트 설정 | `pianohand_simulator.uproject` | `PythonScriptPlugin`, `RemoteControl` 플러그인 활성화 |
| `Config/DefaultEngine.ini` | `[/Script/PythonScriptPlugin.PythonScriptPluginSettings]` | 원격 실행 ON, 멀티캐스트 바인드 `0.0.0.0`, 그룹 `239.0.0.1:6766` |
| `Config/DefaultRemoteControl.ini` | `[/Script/RemoteControlCommon.RemoteControlSettings]` | HTTP 30010 자동 시작, 원격 Python/콘솔 명령 허용 |
| 레포 루트 `.unrealmcp.json` | `C:\Git\PianoHandSimulator\.unrealmcp.json` | MCP 서버가 어느 .uproject 를 다룰지 (상대 경로) |
| Claude Code MCP 등록 | `claude mcp get unreal-mcp` (local scope) | CLI 세션에서 `unreal-mcp` 툴 사용 |
| Claude 데스크톱 앱 MCP 등록 | `%LOCALAPPDATA%\Packages\Claude_pzs8sxrjxfjjc\LocalCache\Roaming\Claude\claude_desktop_config.json` 의 `mcpServers.unreal-mcp` | 데스크톱 앱(Microsoft Store 패키지 버전)은 `%APPDATA%\Claude` 가 아니라 이 경로를 읽는다. 데스크톱 앱의 원격 세션에서는 `mcp__remote-devices__unreal-mcp__<툴>` 형태로 노출된다. 설정 변경 후 앱을 완전히 종료(트레이 아이콘 > Quit)하고 다시 열어야 반영된다 |

참고: `C:\Git\unreal-mcp` 는 이전에 받아둔 다른 프로젝트(chongdashu/unreal-mcp, C++ 플러그인 필요, 2025-04)이다. 지금 쓰는 것은 `unreal-mcp-server` 쪽이다.

---

## 2. 포트

| 포트 | 프로토콜 | 용도 |
|---|---|---|
| 6766 | UDP 멀티캐스트 | Python 원격 실행 노드 탐색 |
| 6776 | TCP | Python 원격 실행 명령 채널 |
| 30010 | HTTP | Remote Control API |

Windows 방화벽이 막으면 MCP 서버가 "No Unreal Editor nodes found" 를 낸다. UDP 6766, TCP 6776 인바운드를 허용한다. VPN/Tailscale 어댑터가 멀티캐스트를 가로챌 수 있다.

---

## 3. 역할 분담 원칙

**MCP 툴로 처리 (기본)**
- Python 실행 (`execute_python`), 콘솔 명령 (`execute_console_command`) — 예: `PianoHand.SkinningSmokeTest`
- 에셋 조회/임포트/이동, 액터 스폰/변환, 머티리얼·머티리얼 인스턴스 생성과 파라미터 설정
- 스켈레탈 메시/애니메이션 에셋 조작, 뷰포트 카메라 이동, 뷰포트 스크린샷 (`take_screenshot`)
- 빌드/쿡/프로젝트 파일 생성, 자동화 테스트 실행

**컴퓨터 사용(화면 조작)으로 처리 (예외)**
- 렌더 결과를 눈으로 판단해야 할 때 (주름·핏줄 디테일 품질, 스키닝 아티팩트)
- MCP 툴이 없는 에디터 UI: 머티리얼 에디터 노드 그래프 시각 확인, Deformer Graph 편집, Chaos Flesh 툴 패널
- 모달 다이얼로그, 플러그인 활성화 재시작 프롬프트 등 에디터가 사용자 입력을 기다리는 경우

원칙: 먼저 MCP 툴로 시도하고, 툴이 없거나 시각 판단이 필요할 때만 화면 조작으로 전환한다. 화면 조작 후 상태 확인은 다시 MCP(`execute_python`)로 한다.

---

## 4. 세션 시작 절차

1. 언리얼 에디터로 `pianohand_simulator.uproject` 를 연다 (MCP 서버는 에디터가 떠 있어야 연결된다).
2. Claude Code 를 `C:\Git\PianoHandSimulator` 에서 시작한다 (`.unrealmcp.json` 이 cwd 기준으로 읽힌다).
3. `/mcp` 로 `unreal-mcp` 가 연결됐는지 확인하고, `get_connection_status` 툴로 Python/Remote Control 두 트랜스포트가 살아 있는지 본다.
4. 화면 조작이 필요하면 Claude 데스크톱 앱에서 컴퓨터 사용을 켠다 (설정 > General, 앱별 첫 사용 시 승인).

---

## 5. 검증 결과 (2026-09-13) 와 알려진 제약

`get_connection_status` 결과: `remoteControl: true`, `pythonExec: false`, `editorRunning: true`.

- **Remote Control(HTTP 30010) 경로로 모든 Python 실행이 동작한다.** `execute_python`, `execute_console_command`(`PianoHand.SkinningSmokeTest` → PASS 확인) 모두 정상.
- **Python 원격 실행(UDP 멀티캐스트) 트랜스포트는 미연결.** 에디터는 UDP 6766 에 바인드돼 있지만 node 클라이언트가 노드를 발견하지 못한다. 원인은 node.exe 인바운드 UDP 응답이 Windows 방화벽에 막히는 것으로 추정. 서버가 자동으로 Remote Control 로 폴백하므로 기능 손실은 없다. 직접 연결을 원하면 관리자 PowerShell 에서:
  ```
  New-NetFirewallRule -DisplayName "unreal-mcp node UDP" -Direction Inbound -Program "C:\Program Files\nodejs\node.exe" -Protocol UDP -Action Allow
  New-NetFirewallRule -DisplayName "unreal-mcp node TCP" -Direction Inbound -Program "C:\Program Files\nodejs\node.exe" -Protocol TCP -Action Allow
  ```
- **`take_screenshot` 는 파일을 만들지 못했다.** 에디터가 백그라운드일 때 레벨 뷰포트가 그려지지 않아 스크린샷 요청이 소비되지 않는 것으로 보인다. 시각 확인은 컴퓨터 사용(화면 조작) 쪽에서 직접 화면을 보는 것으로 대체한다.

## 5-B. 데스크톱 앱(Cowork) 원격 세션에서 확인된 사항 (2026-09-13)

- `unreal-mcp` 의 `build_target` 툴은 이 환경에서 실제로 UBT 를 돌리지 않고 즉시 "succeeded" 를 반환했다 (DLL 시간이 바뀌지 않음). 빌드는 `Scripts\BuildEditor.bat` 을 직접 실행해야 한다. 원격 세션에는 device_bash 가 없어 파일 탐색기에서 .bat 을 더블클릭해 실행했고, 결과는 `%LOCALAPPDATA%\UnrealBuildTool\Log.txt` 로 확인했다 (콘솔 창은 종료 시 닫힘).
- 컴퓨터 사용 권한: `UnrealEditor.exe` 는 설치 앱 목록에 없어서 앱 이름으로는 해석되지 않는다. 에디터가 떠 있는 상태에서 스크린샷을 찍으면 "unrealeditor.exe 가 숨겨짐" 안내가 나오고, 그 basename(`unrealeditor.exe`)으로 `computer_resolve_access` 를 호출하면 full 티어로 승인 요청이 가능하다.
- 탐색기에서 .uproject 를 더블클릭해 연 에디터는 **최소화 상태로 시작**될 수 있다. 이때 Remote Control 은 연결되지만 뷰포트 렌더/애니메이션 틱이 멈춘다. `execute_python` 에서 ctypes 로 `ShowWindow(hwnd, SW_RESTORE)` + `SetForegroundWindow` 를 호출하면 복원된다 (창 제목 `pianohand_simulator - Unreal Editor`).
- `HighResShot 1280x720 filename=<name>` 콘솔 명령은 백그라운드 문제 없이 `Saved/Screenshots/WindowsEditor/<name>.png` 를 만든다. `take_screenshot` MCP 툴 대신 이 방법을 쓰고, 파일을 스테이징해 비교한다 (에디터 Python 에는 numpy/PIL 이 없다).

## 6. 검증 스크립트

`scratchpad/mcp_probe.mjs` 와 같은 방식으로 MCP 서버에 직접 JSON-RPC 를 보내 `initialize` → `tools/list` → `get_connection_status` → `execute_python` → `execute_console_command` 순으로 확인할 수 있다.
