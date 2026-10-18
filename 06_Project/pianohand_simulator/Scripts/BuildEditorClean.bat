@echo off
REM Full editor-target build for pianohand_simulator, after clearing stale Unreal helper
REM processes that keep the Live Coding mutex / the module DLL locked when the editor crashed.
REM Writes a report next to this script so the build result can be inspected without a console.
setlocal
REM UE 5.6 install path - set once per machine: setx PH_ENGINE_ROOT "D:\Unreal\Epic Games\UE_5.6"
set ENGINE=%PH_ENGINE_ROOT%
if not defined ENGINE (
  echo ERROR: PH_ENGINE_ROOT is not set.
  echo Set it once:  setx PH_ENGINE_ROOT "D:\Unreal\Epic Games\UE_5.6"
  echo Then open a new terminal and retry.
  exit /b 1
)
set UPROJECT=%~dp0..\pianohand_simulator.uproject
set REPORT=%~dp0build_report.txt

echo === Processes before cleanup > "%REPORT%"
tasklist /FI "IMAGENAME eq UnrealEditor.exe" >> "%REPORT%" 2>&1
tasklist /FI "IMAGENAME eq LiveCodingConsole.exe" >> "%REPORT%" 2>&1
tasklist /FI "IMAGENAME eq CrashReportClientEditor.exe" >> "%REPORT%" 2>&1

echo === Killing stale helpers >> "%REPORT%"
taskkill /F /IM LiveCodingConsole.exe >> "%REPORT%" 2>&1
taskkill /F /IM CrashReportClientEditor.exe >> "%REPORT%" 2>&1
taskkill /F /IM UnrealEditor.exe >> "%REPORT%" 2>&1

echo === Building >> "%REPORT%"
call "%ENGINE%\Engine\Build\BatchFiles\Build.bat" pianohand_simulatorEditor Win64 Development -Project="%UPROJECT%" -WaitMutex -FromMsBuild >> "%REPORT%" 2>&1
if %ERRORLEVEL% NEQ 0 (
  echo BUILD FAILED >> "%REPORT%"
  exit /b 1
)
echo BUILD OK >> "%REPORT%"
