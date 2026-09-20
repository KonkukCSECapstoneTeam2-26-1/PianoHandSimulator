@echo off
REM Full editor-target build for pianohand_simulator (close the Unreal Editor first).
set ENGINE=C:\Program Files\Epic Games\UE_5.6
set UPROJECT=%~dp0..\pianohand_simulator.uproject
call "%ENGINE%\Engine\Build\BatchFiles\Build.bat" pianohand_simulatorEditor Win64 Development -Project="%UPROJECT%" -WaitMutex -FromMsBuild
if %ERRORLEVEL% NEQ 0 (
  echo BUILD FAILED
  exit /b 1
)
echo BUILD OK
