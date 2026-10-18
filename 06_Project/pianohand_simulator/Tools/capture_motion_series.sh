#!/bin/bash
S=/private/tmp/claude-501/-Users-nunsori-Git-PianoHandSimulator/9a6accd9-1ec0-4f5a-a0d5-cb821657229a/scratchpad
P=/Users/nunsori/Git/PianoHandSimulator/06_Project/pianohand_simulator
run_py() { printf "exec(open('%s/tools/ph.py').read())\n%s\n" "$S" "$1" > $S/tools/_mo2_body.py; printf "exec(open('%s/tools/_mo2_body.py').read())\n" "$S" > $S/tools/_mo2.py; python3 $S/tools/ue_exec.py $S/tools/_mo2.py 2>&1 | grep -E "rror|FAILED" | grep -v Deprecation; }
frame() { local F="$P/Saved/Screenshots/MacEditor/$1.png"; rm -f "$F"
  pgrep -f "MacOS/UnrealEditor " >/dev/null || { echo "ABORT editor down at $1"; exit 3; }
  run_py "set_t($2)"; sleep 2.0; run_py "shot('$1', $3, $4)"
  for i in $(seq 1 60); do [ -f "$F" ] && break; sleep 0.5; done; [ -f "$F" ] && echo "FRAME $1" || echo "MISSING $1"; }
run_py "cmd('r.SetNearClipPlane 1.5'); hide_backdrop(); exposure(1.0); use_material('skin'); light_from('dorsal', 6.0, 40.0); set_t(0.25); ref_view2(11.0, ahead=6.5)"
sleep 1
N=48; for i in $(seq 0 $((N-1))); do t=$(python3 -c "print($i*4.0/$N)"); frame mo2_ref_$(printf %02d $i) $t 1280 720; done
echo SERIES_MOTION2_DONE
