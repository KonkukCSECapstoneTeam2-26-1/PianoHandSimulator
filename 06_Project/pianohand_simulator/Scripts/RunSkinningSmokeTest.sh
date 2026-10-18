#!/bin/bash
# Builds the editor target and runs the custom skinning GPU smoke test headlessly (macOS).
# Close the Unreal Editor first (UBT refuses to build while Live Coding is active).
ENGINE="${PH_ENGINE_ROOT:-/Users/Shared/Epic Games/UE_5.6}"
if [ ! -d "$ENGINE/Engine" ]; then
  echo "ERROR: UE 5.6 not found at '$ENGINE'. Set PH_ENGINE_ROOT." >&2
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT="$SCRIPT_DIR/../pianohand_simulator.uproject"

echo "=== [1/2] Building pianohand_simulatorEditor (Mac Development)"
"$ENGINE/Engine/Build/BatchFiles/Mac/Build.sh" pianohand_simulatorEditor Mac Development -Project="$PROJECT" -WaitMutex || { echo "BUILD FAILED"; exit 1; }

echo "=== [2/2] Running PianoHand.SkinningSmokeTest"
"$ENGINE/Engine/Binaries/Mac/UnrealEditor-Cmd" "$PROJECT" -ExecCmds="PianoHand.SkinningSmokeTest" -SkinningTestAutoQuit -unattended -nosplash -nopause -log=SkinningSmokeTest.log
RESULT=$?
echo
echo "--- LogPianoHand lines from Saved/Logs/SkinningSmokeTest.log"
grep "LogPianoHand" "$SCRIPT_DIR/../Saved/Logs/SkinningSmokeTest.log"
echo
if [ $RESULT -eq 0 ]; then echo "SMOKE TEST: PASS"; else echo "SMOKE TEST: FAIL (exit $RESULT)"; fi
exit $RESULT
