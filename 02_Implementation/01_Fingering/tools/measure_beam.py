"""빔 가지치기 계측 — 13_Cost_Function_Design.md 3.2절 검증

저장소 코드는 수정하지 않는다. 엔진 소스를 문자열로 읽어 가지치기 지점에만
카운터를 끼워 넣은 사본을 메모리에서 실행한다.

재는 것
  - 화음당 상태 수와 빔 포화 여부 (DP_BEAM_WIDTH = 120)
  - 가지치기로 버려진 상태 수
  - 버려진 상태 중, 그 시점에 '하드 제약 위반이 없던' 것의 수
    → 3.2(좋은 쪽이 후보에서 사라진다)가 실제로 일어나는지
"""
import io, os, sys, glob, json, types, contextlib

ENG = r"D:\Git\PianoHandSimulator\02_Implementation\01_Fingering\v5_polyphonic\piano_fingering_engine.py"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."
MIDI_DIR = sys.argv[2] if len(sys.argv) > 2 else r"D:/Git/PianoHandSimulator/05_Resources/MIDI_Inputs"

SRC = io.open(ENG, encoding="utf-8").read()

ANCHOR = """        if len(curr_states) > DP_BEAM_WIDTH:
            kept = sorted(curr_states.items(), key=lambda kv: kv[1][0])[:DP_BEAM_WIDTH]
            curr_states = dict(kept)"""

PATCH = """        _BEAM['chords'] += 1
        _BEAM['states_sum'] += len(curr_states)
        _BEAM['states_max'] = max(_BEAM['states_max'], len(curr_states))
        if len(curr_states) > DP_BEAM_WIDTH:
            _BEAM['prune_events'] += 1
            _ordered = sorted(curr_states.items(), key=lambda kv: kv[1][0])
            kept = _ordered[:DP_BEAM_WIDTH]
            _dropped = _ordered[DP_BEAM_WIDTH:]
            _BEAM['pruned'] += len(_dropped)
            for _st, _ in _dropped:
                if _beam_state_clean(_st, curr_chord, hand_id):
                    _BEAM['pruned_clean'] += 1
            for _st, _ in kept:
                if not _beam_state_clean(_st, curr_chord, hand_id):
                    _BEAM['kept_dirty'] += 1
            curr_states = dict(kept)"""

assert SRC.count(ANCHOR) == 1, f"앵커 {SRC.count(ANCHOR)}회"
SRC = SRC.replace(ANCHOR, PATCH)

HELPER = '''

_BEAM = {"chords": 0, "states_sum": 0, "states_max": 0,
         "prune_events": 0, "pruned": 0, "pruned_clean": 0, "kept_dirty": 0}


def _beam_reset():
    for k in _BEAM:
        _BEAM[k] = 0


def _beam_state_clean(state, curr_chord, hand_id):
    """이 상태(현재 손가락 조합 + 점유 집합)가 하드 제약을 어기지 않는가."""
    curr_f, held = state
    fingers = list(curr_f) + [f for (_ci, _pi, f) in held]
    if len(fingers) != len(set(fingers)):
        return False
    for i in range(len(curr_f)):
        for j in range(i + 1, len(curr_f)):
            pair = tuple(sorted((curr_f[i], curr_f[j])))
            if abs(curr_chord[j].pitch - curr_chord[i].pitch) > MAX_SPAN.get(pair, 12):
                return False
    return True
'''

# 헬퍼를 상수 정의 뒤(= MAX_SPAN 이 정의된 뒤)에 끼운다
MARK = "def _occupies_at(note, t_ms):"
assert SRC.count(MARK) == 1
SRC = SRC.replace(MARK, HELPER.strip() + "\n\n\n" + MARK)

mod = types.ModuleType("eng_instr")
mod.__file__ = ENG
sys.path.insert(0, os.path.dirname(ENG))
sys.path.insert(0, os.path.dirname(os.path.dirname(ENG)))
exec(compile(SRC, ENG, "exec"), mod.__dict__)


def run(path, name):
    mod._beam_reset()
    rep = {}
    hc = mod.split_wide_chords_between_hands(mod.parse_midi_to_hand_chords(path), report=rep)
    ped = mod.parse_pedal_spans(path)
    mod.compute_required_hold([n for h in (0, 1) for c in hc[h] for n in c], ped)
    for h in (0, 1):
        hc[h] = [mod._trim_chord(c, h) for c in hc[h]]
        mod.solve_fingering_chord_dp(hc[h], h)
    b = dict(mod._BEAM)
    b["곡"] = name
    b["평균상태수"] = round(b["states_sum"] / b["chords"], 1) if b["chords"] else 0
    b["포화율%"] = round(b["prune_events"] / b["chords"] * 100, 1) if b["chords"] else 0
    b["버려진것중_무위반%"] = (round(b["pruned_clean"] / b["pruned"] * 100, 1)
                               if b["pruned"] else None)
    return b


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for p in sorted(glob.glob(os.path.join(MIDI_DIR, "*.mid"))):
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                r = run(p, name)
            rows.append(r)
            print(f"  {name[:36]:38s} 화음 {r['chords']:5d} | 평균상태 {r['평균상태수']:6.1f} "
                  f"| 포화 {r['포화율%']:5.1f}% | 버림 {r['pruned']:6d} "
                  f"| 그중 무위반 {str(r['버려진것중_무위반%']):>6s}% | 남긴것중 위반 {r['kept_dirty']:5d}")
        except Exception as e:
            print(f"  {name[:36]:38s} 실패: {type(e).__name__}: {e}")
    io.open(os.path.join(OUT, "beam_measure.json"), "w", encoding="utf-8").write(
        json.dumps(rows, ensure_ascii=False, indent=2))
    tot_p = sum(r["pruned"] for r in rows)
    tot_c = sum(r["pruned_clean"] for r in rows)
    print(f"\n합계: 버린 상태 {tot_p:,} / 그중 무위반 {tot_c:,}"
          f" ({(tot_c/tot_p*100 if tot_p else 0):.1f}%)"
          f" / 포화가 일어난 화음 {sum(r['prune_events'] for r in rows):,}"
          f" (전체 {sum(r['chords'] for r in rows):,})")


if __name__ == "__main__":
    main()
