@echo off
REM Builds the editor target and runs the custom skinning GPU smoke test headlessly.
REM Close the Unreal Editor first (UBT refuses to build while Live Coding is active).
setlocal
set ENGINE=C:\Program Files\Epic Games\UE_5.6\Engine
set PROJECT=%~dp0..\pianohand_simulator.uproject

echo === [1/2] Building pianohand_simulatorEditor (Win64 Development)
call "%ENGINE%\Build\BatchFiles\Build.bat" pianohand_simulatorEditor Win64 Development -project="%PROJECT%" -waitmutex
if errorlevel 1 (
	echo BUILD FAILED
	exit /b 1
)

echo === [2/2] Running PianoHand.SkinningSmokeTest
"%ENGINE%\Binaries\Win64\UnrealEditor-Cmd.exe" "%PROJECT%" -ExecCmds="PianoHand.SkinningSmokeTest" -SkinningTestAutoQuit -unattended -nosplash -nopause -log=SkinningSmokeTest.log
set RESULT=%errorlevel%
echo.
echo --- LogPianoHand lines from Saved\Logs\SkinningSmokeTest.log
findstr /C:"LogPianoHand" "%~dp0..\Saved\Logs\SkinningSmokeTest.log"
echo.
if %RESULT%==0 (echo SMOKE TEST: PASS) else (echo SMOKE TEST: FAIL ^(exit %RESULT%^))
exit /b %RESULT%
