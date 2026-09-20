@echo off
REM Full editor-target build for pianohand_simulator, after clearing stale Unreal helper
REM processes that keep the Live Coding mutex / the module DLL locked when the editor crashed.
REM Writes a report next to this script so the build result can be inspected without a console.
setlocal
set ENGINE=C:\Program Files\Epic Games\UE_5.6
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
