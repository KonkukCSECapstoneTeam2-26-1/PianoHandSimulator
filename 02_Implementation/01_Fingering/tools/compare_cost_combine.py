"""코스트 결합 방식 비교 — 13_Cost_Function_Design.md 6.3절

지도교수 피드백(가산 / max / 곱 비교)에 대한 측정 도구. 같은 입력을 결합 방식만 바꿔
엔진에 통과시키고, 하드 제약 위반 · 선호도 지표 · 운지 차이 · 실행 시간을 나란히 비교한다.

  DP직후    사후 해소 전 순간 위반 시점 수 (결합 방식이 직접 영향을 주는 값)
  최종      metrics.py [A] 하드 제약 위반 합계 (출력 품질 기준, 0 이어야 정상)
  손실      사후 해소의 음표 제외 + 미해결 시점
  반복      단음 연속 같은 손가락 반복 비율 (B9)
  롤링      아르페지오 방향성 불일치 비율 (B10)
  흑건1     흑건에 엄지 비율 (B12)
  차이      add 대비 손가락이 달라진 음표 비율

결과 JSON 은 임시 폴더에 쓰고, 저장소의 results/ 는 건드리지 않는다.

사용:
    python tools/compare_cost_combine.py              # 기준 코퍼스 + 실곡 전체
    python tools/compare_cost_combine.py --reference  # 기준 코퍼스만
    python tools/compare_cost_combine.py --json out.json

Windows 콘솔(cp949)에서는 `PYTHONIOENCODING=utf-8` 을 지정하고 실행할 것.
"""
import argparse
import contextlib
import glob
import io
import json
import os
import sys
import tempfile
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FINGERING_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, os.path.join(FINGERING_DIR, "v5_polyphonic"))
sys.path.insert(0, os.path.join(FINGERING_DIR, "tests"))
sys.path.insert(0, BASE_DIR)

import piano_fingering_engine as engine   # noqa: E402
import metrics                            # noqa: E402
from test_reference_corpus import engine_violations   # noqa: E402

MIDI_DIR = os.path.join(FINGERING_DIR, "assets", "midi")
REFERENCE_DIR = os.path.join(MIDI_DIR, "reference")


def _pct(a, b):
    return a / b * 100 if b else 0.0


def run_one(path, mode, out_dir):
    engine.COST_COMBINE = mode
    t0 = time.time()
    with contextlib.redirect_stdout(io.StringIO()):
        result_path = engine.analyze_polyphonic(path, output_dir=out_dir)
    elapsed = time.time() - t0

    # DP 직후(사후 해소 전) 순간 위반 — 결합 방식이 직접 바꾸는 값
    _inst, span_bad, dup_bad, mono_bad, _ = engine_violations(path, resolve=False)
    # 최종 출력 — 사후 해소의 손실도 함께
    _inst, _s, _d, _m, rs = engine_violations(path, resolve=True)

    notes = metrics.load_notes(result_path)
    chords = metrics.group_chords(notes)
    with contextlib.redirect_stdout(io.StringIO()):
        hard_final = metrics.evaluate(result_path)
    repeats, run_trans = metrics.single_note_runs(chords)
    arp_bad, arp_trans, _ = metrics.arpeggio_mismatch(chords)
    bk = metrics.black_key_thumb_pinky(notes)

    with open(result_path, encoding="utf-8") as f:
        fingers = [(n["pitch"], n["start_ms"], n["hand"], n["finger"]) for n in json.load(f)]
    return {
        "dp_viol": span_bad + dup_bad + mono_bad,
        "final_hard": hard_final,
        "loss": rs["dropped"] + rs["unresolved"],
        "repeat_pct": _pct(repeats, run_trans),
        "arp_pct": _pct(arp_bad, arp_trans),
        "black_thumb_pct": bk["f1_pct"],
        "sec": elapsed,
        "fingers": fingers,
    }


def finger_diff_pct(a, b):
    """두 결과에서 같은 음표(피치·시작·손)에 다른 손가락이 배정된 비율."""
    fa = {(p, s, h): f for p, s, h, f in a}
    fb = {(p, s, h): f for p, s, h, f in b}
    common = fa.keys() & fb.keys()
    return _pct(sum(1 for k in common if fa[k] != fb[k]), len(common))


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", action="store_true", help="기준 코퍼스만")
    ap.add_argument("--json", help="결과를 JSON 으로 저장")
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(REFERENCE_DIR, "*.mid")))
    if not args.reference:
        files += sorted(glob.glob(os.path.join(MIDI_DIR, "*.mid")))

    modes = engine.COST_COMBINE_MODES
    original_mode = engine.COST_COMBINE
    table = {}
    try:
        with tempfile.TemporaryDirectory() as out_dir:
            for path in files:
                name = os.path.basename(path)
                table[name] = {m: run_one(path, m, os.path.join(out_dir, m)) for m in modes}
                for m in modes:
                    table[name][m]["diff_pct"] = finger_diff_pct(
                        table[name]["add"]["fingers"], table[name][m]["fingers"])
                print(f"  {name}", file=sys.stderr)
    finally:
        engine.COST_COMBINE = original_mode

    cols = [("DP직후", "dp_viol", "d"), ("최종", "final_hard", "d"), ("손실", "loss", "d"),
            ("반복%", "repeat_pct", ".1f"), ("롤링%", "arp_pct", ".1f"),
            ("흑건1%", "black_thumb_pct", ".1f"), ("차이%", "diff_pct", ".1f"), ("초", "sec", ".1f")]
    print("| 곡 | 방식 | " + " | ".join(c[0] for c in cols) + " |")
    print("|---|---|" + "---:|" * len(cols))
    for name, by_mode in table.items():
        for m in modes:
            r = by_mode[m]
            cells = " | ".join(format(r[k], fmt) for _, k, fmt in cols)
            print(f"| {name if m == modes[0] else ''} | {m} | {cells} |")

    # 묶음별 합계 (비율은 곡 평균)
    groups = {"기준 코퍼스": [n for n in table if n.startswith("ref_")],
              "실곡": [n for n in table if not n.startswith("ref_")]}
    print()
    print("| 묶음 | 방식 | DP직후 합 | 최종 합 | 손실 합 | 반복% 평균 | 롤링% 평균 | 흑건1% 평균 | 차이% 평균 | 초 합 |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for g, names in groups.items():
        if not names:
            continue
        for m in modes:
            rs = [table[n][m] for n in names]
            avg = lambda k: sum(r[k] for r in rs) / len(rs)
            label = f"{g} ({len(names)}곡)" if m == modes[0] else ""
            print(f"| {label} | {m} | "
                  f"{sum(r['dp_viol'] for r in rs)} | {sum(r['final_hard'] for r in rs)} | "
                  f"{sum(r['loss'] for r in rs)} | {avg('repeat_pct'):.1f} | {avg('arp_pct'):.1f} | "
                  f"{avg('black_thumb_pct'):.1f} | {avg('diff_pct'):.1f} | {sum(r['sec'] for r in rs):.1f} |")

    if args.json:
        for by_mode in table.values():
            for r in by_mode.values():
                r.pop("fingers", None)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(table, f, ensure_ascii=False, indent=2)
        print(f"\n저장: {args.json}")


if __name__ == "__main__":
    main(sys.argv[1:])
