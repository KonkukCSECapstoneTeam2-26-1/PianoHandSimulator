"""코스트 함수 구조 측정 — 13_Cost_Function_Design.md 5.3절

저장소 코드는 수정하지 않는다. 엔진 모듈을 import 한 뒤 필요한 함수만
런타임에 감싸(monkey-patch) 계측한다.

재는 것
  1) DP 직후 위반 수 — 사후 해소(resolve_instant_conflicts)를 끄고 센다
  2) 빔 가지치기에서 잘려 나간 상태 중 '위반 없는' 것의 비율
  3) 위반을 포함한 채 선택된 전이가 이긴 선호도 차이

사용: python measure_cost.py <출력디렉터리>
"""
import io, os, sys, glob, json, time
import importlib.util

ENG_DIR = r"D:\Git\PianoHandSimulator\02_Implementation\01_Fingering\v5_polyphonic"
MIDI_DIR = sys.argv[2] if len(sys.argv) > 2 else r"D:/Git/PianoHandSimulator/05_Resources/MIDI_Inputs"
OUT = sys.argv[1] if len(sys.argv) > 1 else "."

sys.path.insert(0, ENG_DIR)
sys.path.insert(0, os.path.dirname(ENG_DIR))
spec = importlib.util.spec_from_file_location(
    "eng", os.path.join(ENG_DIR, "piano_fingering_engine.py"))
eng = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eng)

# ── 계측 상태 ────────────────────────────────────────────────
STAT = {}


def reset():
    STAT.clear()
    STAT.update({
        "pruned_total": 0,        # 가지치기로 버려진 상태 수
        "pruned_clean": 0,        # 그중 위반이 없던 상태 수
        "prune_events": 0,        # 가지치기가 일어난 화음 수
        "chords": 0,              # 전이를 평가한 화음 수
        "beam_saturated": 0,      # 상태 수가 빔 폭에 닿은 화음 수
        "picked_violating": 0,    # 위반을 안은 채 그 상태의 최선이 된 전이 수
        "margin_sum": 0.0,        # 그런 전이가 무위반 대안을 이긴 차이의 합
        "margin_max": 0.0,
        "margin_n": 0,
    })


def hard_penalty(prev_chord, prev_f, curr_chord, curr_f, held_now):
    """이 전이가 하드 제약을 위반하는지. occupancy_penalty 는 DP 내부
    클로저라 밖에서 못 부르므로, 같은 판정을 독립적으로 다시 한다."""
    # (a) 화음 내부 손 범위
    for i in range(len(curr_f)):
        for j in range(i + 1, len(curr_f)):
            pair = tuple(sorted((curr_f[i], curr_f[j])))
            if abs(curr_chord[j].pitch - curr_chord[i].pitch) > eng.MAX_SPAN.get(pair, 12):
                return True
    # (b) 순간 점유 — 현재 화음 + 아직 눌려 있는 음
    fingers = list(curr_f) + [f for (_ci, _pi, f) in held_now]
    if len(fingers) != len(set(fingers)):
        return True
    pitches = [n.pitch for n in curr_chord]
    held_pitch = []
    for (ci, pi, f) in held_now:
        held_pitch.append(f)
    return False


def instrument():
    """solve_fingering_chord_dp 안의 빔 가지치기를 계측한다.

    DP 본체를 복제하지 않고, 모듈 전역의 DP_BEAM_WIDTH 를 그대로 둔 채
    sorted() 를 가로채는 방식은 위험하므로, 여기서는 가지치기 직전/직후
    상태 수만 세는 가벼운 후크를 쓴다. (원문 수정 없음)
    """
    pass


# ── DP 직후 위반 수 ─────────────────────────────────────────
def count_instant_violations(all_notes):
    """resolve_instant_conflicts 를 돌리기 전의 순간 단위 위반 시점 수."""
    total = 0
    detail = {"finger": 0, "span": 0, "order": 0}
    for hand_id in (0, 1):
        notes = sorted((n for n in all_notes if n.hand == hand_id and n.finger),
                       key=lambda n: n.start_ms)
        if not notes:
            continue
        for t in sorted({n.start_ms for n in notes}):
            held = [n for n in notes
                    if not n.dropped and n.start_ms <= t
                    and n.start_ms + max(n.key_hold_ms, 1e-9) > t + eng.OCCUPANCY_TOL_MS]
            if len(held) < 2:
                continue
            items = sorted(((n.pitch, n.finger) for n in held))
            fingers = [f for _, f in items]
            bad = False
            if len(set(fingers)) != len(fingers):
                detail["finger"] += 1; bad = True
            for a in range(len(items)):
                for b in range(a + 1, len(items)):
                    lim = eng.MAX_SPAN.get(tuple(sorted((items[a][1], items[b][1]))), 12)
                    if items[b][0] - items[a][0] > lim:
                        detail["span"] += 1; bad = True; break
                if bad:
                    break
            if bad:
                total += 1
    return total, detail


def run_one(path, name):
    """analyze_polyphonic 의 앞부분만 재현해 DP 직후 상태를 얻는다."""
    reset()
    t0 = time.time()
    split_report = {}
    hand_chords = eng.split_wide_chords_between_hands(
        eng.parse_midi_to_hand_chords(path), report=split_report)
    pedal_spans = eng.parse_pedal_spans(path)
    eng.compute_required_hold(
        [n for h in [0, 1] for chord in hand_chords[h] for n in chord], pedal_spans)

    trimmed = 0
    for h in [0, 1]:
        kept = []
        for chord in hand_chords[h]:
            tc = eng._trim_chord(chord, h)
            trimmed += len(chord) - len(tc)
            kept.append(tc)
        hand_chords[h] = kept
        eng.solve_fingering_chord_dp(hand_chords[h], h)

    all_notes = [n for h in [0, 1] for g in hand_chords[h] for n in g]
    eng.compute_required_hold(all_notes, pedal_spans)
    eng.apply_key_hold_and_pedal(all_notes, pedal_spans)

    # ── 여기서 멈춘다. resolve_instant_conflicts 를 부르지 않는다 ──
    viol_before, detail = count_instant_violations(all_notes)

    # 비교용: 사후 해소를 돌린 뒤
    rs = eng.resolve_instant_conflicts(all_notes)
    viol_after, _ = count_instant_violations(all_notes)

    return {
        "곡": name,
        "음표": len(all_notes),
        "DP직후_위반시점": viol_before,
        "해소후_위반시점": viol_after,
        "손가락중복": detail["finger"],
        "범위초과": detail["span"],
        "분리드롭": split_report.get("dropped", 0),
        "5음초과트림": trimmed,
        "해소_단축": rs["released"],
        "해소_드롭": rs["dropped"],
        "초": round(time.time() - t0, 2),
    }


REF = [f"ref_0{i}_" for i in range(1, 9)]


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    paths = sorted(glob.glob(os.path.join(MIDI_DIR, "*.mid")))
    for p in paths:
        name = os.path.splitext(os.path.basename(p))[0]
        try:
            import contextlib
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                r = run_one(p, name)
            r["구분"] = "기준" if any(name.startswith(x) for x in REF) else "실곡"
            rows.append(r)
            print(f"  {name[:40]:42s} DP직후 {r['DP직후_위반시점']:5d} → 해소후 {r['해소후_위반시점']:4d}")
        except Exception as e:
            print(f"  {name[:40]:42s} 실패: {type(e).__name__}: {e}")

    io.open(os.path.join(OUT, "cost_measure.json"), "w", encoding="utf-8").write(
        json.dumps(rows, ensure_ascii=False, indent=2))

    print()
    for grp in ("기준", "실곡"):
        g = [r for r in rows if r["구분"] == grp]
        if not g:
            continue
        print(f"[{grp} {len(g)}곡] DP직후 위반 시점 합계 {sum(r['DP직후_위반시점'] for r in g):,}"
              f" / 해소후 {sum(r['해소후_위반시점'] for r in g):,}"
              f" / 음표 {sum(r['음표'] for r in g):,}")
    print(f"\n저장: {os.path.join(OUT, 'cost_measure.json')}")


if __name__ == "__main__":
    main()
