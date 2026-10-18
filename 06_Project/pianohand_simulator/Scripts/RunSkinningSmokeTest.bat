@echo off
REM Builds the editor target and runs the custom skinning GPU smoke test headlessly.
REM Close the Unreal Editor first (UBT refuses to build while Live Coding is active).
setlocal
REM UE 5.6 install path - set once per machine: setx PH_ENGINE_ROOT "D:\Unreal\Epic Games\UE_5.6"
set ENGINE=%PH_ENGINE_ROOT%
if not defined ENGINE (
  echo ERROR: PH_ENGINE_ROOT is not set.
  echo Set it once:  setx PH_ENGINE_ROOT "D:\Unreal\Epic Games\UE_5.6"
  echo Then open a new terminal and retry.
  exit /b 1
)
set PROJECT=%~dp0..\pianohand_simulator.uproject

echo === [1/2] Building pianohand_simulatorEditor (Win64 Development)
call "%ENGINE%\Engine\Build\BatchFiles\Build.bat" pianohand_simulatorEditor Win64 Development -project="%PROJECT%" -waitmutex
if errorlevel 1 (
	echo BUILD FAILED
	exit /b 1
)

echo === [2/2] Running PianoHand.SkinningSmokeTest
"%ENGINE%\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" "%PROJECT%" -ExecCmds="PianoHand.SkinningSmokeTest" -SkinningTestAutoQuit -unattended -nosplash -nopause -log=SkinningSmokeTest.log
set RESULT=%errorlevel%
echo.
echo --- LogPianoHand lines from Saved\Logs\SkinningSmokeTest.log
findstr /C:"LogPianoHand" "%~dp0..\Saved\Logs\SkinningSmokeTest.log"
echo.
if %RESULT%==0 (echo SMOKE TEST: PASS) else (echo SMOKE TEST: FAIL ^(exit %RESULT%^))
exit /b %RESULT%
