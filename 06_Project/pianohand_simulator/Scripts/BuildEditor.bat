@echo off
REM Full editor-target build for pianohand_simulator (close the Unreal Editor first).
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
call "%ENGINE%\Engine\Build\BatchFiles\Build.bat" pianohand_simulatorEditor Win64 Development -Project="%UPROJECT%" -WaitMutex -FromMsBuild
if %ERRORLEVEL% NEQ 0 (
  echo BUILD FAILED
  exit /b 1
)
echo BUILD OK
