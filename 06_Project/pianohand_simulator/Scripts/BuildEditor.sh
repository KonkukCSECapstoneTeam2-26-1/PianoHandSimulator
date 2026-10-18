#!/bin/bash
# Full editor-target build for pianohand_simulator on macOS (close the Unreal Editor first).
# UE 5.6 install path - override with: export PH_ENGINE_ROOT="/Users/Shared/Epic Games/UE_5.6"
set -e
ENGINE="${PH_ENGINE_ROOT:-/Users/Shared/Epic Games/UE_5.6}"
if [ ! -d "$ENGINE/Engine" ]; then
  echo "ERROR: UE 5.6 not found at '$ENGINE'. Set PH_ENGINE_ROOT." >&2
  exit 1
fi
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
UPROJECT="$SCRIPT_DIR/../pianohand_simulator.uproject"
"$ENGINE/Engine/Build/BatchFiles/Mac/Build.sh" pianohand_simulatorEditor Mac Development -Project="$UPROJECT" -WaitMutex
echo "BUILD OK"
