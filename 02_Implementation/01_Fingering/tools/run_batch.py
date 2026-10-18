"""PianoHandSimulator — 배치 실행기 (Batch Runner)

MIDI 폴더의 모든 파일을 운지법 엔진으로 일괄 처리하고, 요약 표를 출력한다.
선택적으로 UE5 DataTable CSV 생성과 물리 제약 지표 측정까지 한 번에 수행한다.

구조는 `제출_정근녕_중간/코드_v6/run_batch.py` 에서 가져왔고, 호출 대상만
현행 v5_polyphonic 파이프라인(엔진 · metrics · export_datatable)으로 바꿨다.

사용법
  python tools/run_batch.py                      # 실곡만 처리
  python tools/run_batch.py --reference          # 기준 코퍼스까지 포함
  python tools/run_batch.py --all --metrics      # 전체 + 물리 제약 검사
  python tools/run_batch.py --all --export-ue5   # 전체 + UE5 CSV 생성

Windows 콘솔(cp949)에서는 `PYTHONIOENCODING=utf-8` 을 지정하고 실행할 것.
"""
import argparse
import contextlib
import glob
import io
import json
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FINGERING_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, os.path.join(FINGERING_DIR, "v5_polyphonic"))
sys.path.insert(0, BASE_DIR)

import piano_fingering_engine as engine   # noqa: E402
import export_datatable                   # noqa: E402
import metrics                            # noqa: E402

MIDI_DIR = os.path.join(FINGERING_DIR, "assets", "midi")
REFERENCE_DIR = os.path.join(MIDI_DIR, "reference")
RESULTS_DIR = os.path.join(FINGERING_DIR, "results")

MIDI_PATTERNS = ("*.mid", "*.midi", "*.MID", "*.MIDI")

# 엔진이 stdout 으로 남기는 경고에서 수치를 뽑는다.
# 형식이 바뀌면 '-' 로 표시될 뿐 배치 자체는 계속 동작한다.
RE_SPLIT_DROP = re.compile(r"배정할 수 없어 제외한 음표 (\d+)개")
RE_TRIM_DROP = re.compile(r"5음 초과 화음에서 음표 (\d+)개 제외")
RE_RANGE_DROP = re.compile(r"88키 범위 밖 음표 (\d+)개 제외")
RE_RESOLVE = re.compile(
    r"점유 단축 (\d+)건 \(소리 희생 (\d+)건, ([\d.]+)s\) / 음표 제외 (\d+)개 / 미해결 (\d+)시점")


def find_midi_files(directory):
    found = []
    for pattern in MIDI_PATTERNS:
        found.extend(glob.glob(os.path.join(directory, pattern)))
    return sorted(set(found))


def collect_targets(include_real, include_reference):
    targets = []
    if include_real:
        targets += find_midi_files(MIDI_DIR)
    if include_reference and os.path.isdir(REFERENCE_DIR):
        targets += find_midi_files(REFERENCE_DIR)
    return targets


def parse_engine_log(text):
    """엔진 로그에서 요약 수치를 추출. 인식 못 하면 None 으로 둔다."""
    stats = {"dropped": 0, "released": 0, "sound_cut_s": 0.0, "unresolved": None}

    for pattern in (RE_SPLIT_DROP, RE_TRIM_DROP, RE_RANGE_DROP):
        for m in pattern.finditer(text):
            stats["dropped"] += int(m.group(1))

    m = RE_RESOLVE.search(text)
    if m:
        stats["released"] = int(m.group(1))
        stats["sound_cut_s"] = float(m.group(3))
        stats["dropped"] += int(m.group(4))
        stats["unresolved"] = int(m.group(5))
    return stats


def hard_violations(result_path):
    """metrics.evaluate 의 하드 제약 위반 합계만 조용히 얻는다."""
    with contextlib.redirect_stdout(io.StringIO()):
        return metrics.evaluate(result_path)


def run_one(midi_path, do_metrics):
    """한 곡 처리. (레코드, 엔진 로그) 반환."""
    stem = os.path.splitext(os.path.basename(midi_path))[0]
    record = {"name": stem, "status": "OK", "elapsed": 0.0, "notes": 0,
              "json": None, "violations": None}

    started = time.time()
    buffer = io.StringIO()
    try:
        with contextlib.redirect_stdout(buffer):
            record["json"] = engine.analyze_polyphonic(midi_path)
    except Exception as exc:                      # 한 곡이 실패해도 배치는 계속한다
        record["status"] = f"FAIL: {type(exc).__name__}: {exc}"
        record["elapsed"] = time.time() - started
        return record, buffer.getvalue()

    record["elapsed"] = time.time() - started
    log = buffer.getvalue()
    record.update(parse_engine_log(log))

    if record["json"] and os.path.exists(record["json"]):
        with io.open(record["json"], encoding="utf-8") as handle:
            record["notes"] = len(json.load(handle))

    if do_metrics and record["json"]:
        try:
            record["violations"] = hard_violations(record["json"])
        except Exception as exc:
            record["status"] = f"METRICS FAIL: {type(exc).__name__}: {exc}"

    return record, log


def print_summary(records, do_metrics):
    header = f"  {'곡':<34} {'음표':>6} {'제외':>5} {'단축':>5} {'미해결':>6} {'시간':>6}"
    if do_metrics:
        header += f" {'위반':>5}"
    print()
    print("=" * len(header))
    print("  처리 결과 요약")
    print("=" * len(header))
    print(header)
    print("-" * len(header))

    totals = {"notes": 0, "dropped": 0, "released": 0, "violations": 0, "elapsed": 0.0}
    failures = []
    for r in records:
        if not r["status"].startswith("OK"):
            print(f"  {r['name'][:33]:<34} {'—':>6} {'—':>5} {'—':>5} {'—':>6} "
                  f"{r['elapsed']:>5.1f}s" + (f" {'—':>5}" if do_metrics else ""))
            failures.append(f"{r['name']}: {r['status']}")
            continue

        unresolved = "—" if r["unresolved"] is None else str(r["unresolved"])
        line = (f"  {r['name'][:33]:<34} {r['notes']:>6} {r['dropped']:>5} "
                f"{r['released']:>5} {unresolved:>6} {r['elapsed']:>5.1f}s")
        if do_metrics:
            line += f" {('—' if r['violations'] is None else r['violations']):>5}"
        print(line)

        totals["notes"] += r["notes"]
        totals["dropped"] += r["dropped"]
        totals["released"] += r["released"]
        totals["elapsed"] += r["elapsed"]
        if r["violations"]:
            totals["violations"] += r["violations"]
        if r["unresolved"]:
            failures.append(f"{r['name']}: 미해결 {r['unresolved']}시점")

    print("-" * len(header))
    line = (f"  {'합계':<32} {totals['notes']:>6} {totals['dropped']:>5} "
            f"{totals['released']:>5} {'':>6} {totals['elapsed']:>5.1f}s")
    if do_metrics:
        line += f" {totals['violations']:>5}"
    print(line)

    ok = sum(1 for r in records if r["status"].startswith("OK"))
    print(f"\n  성공 {ok}/{len(records)}곡", end="")
    if do_metrics:
        verdict = "ALL PASS" if totals["violations"] == 0 else "FAIL"
        print(f" · 하드 제약 위반 {totals['violations']}건 — {verdict}")
    else:
        print()

    if failures:
        print("\n  확인 필요")
        for f in failures:
            print(f"    - {f}")
    return failures


def export_ue5(records, fps):
    out_dir = os.path.join(RESULTS_DIR, "ue5")
    os.makedirs(out_dir, exist_ok=True)
    print("\n" + "-" * 60)
    print(f"  UE5 DataTable CSV 생성 → {out_dir}")
    print("-" * 60)
    count = 0
    for r in records:
        if not r["status"].startswith("OK") or not r["json"]:
            continue
        stem = os.path.splitext(os.path.basename(r["json"]))[0]
        target = os.path.join(out_dir, f"{stem}_datatable.csv")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                export_datatable.export(r["json"], target, fps)
            count += 1
        except Exception as exc:
            print(f"    [실패] {r['name']}: {type(exc).__name__}: {exc}")
    print(f"  {count}개 생성 완료")


def main(argv=None):
    parser = argparse.ArgumentParser(description="PianoHandSimulator 운지법 배치 실행기")
    parser.add_argument("--reference", action="store_true",
                        help="기준 코퍼스(assets/midi/reference)만 처리")
    parser.add_argument("--all", action="store_true",
                        help="실곡 + 기준 코퍼스 모두 처리")
    parser.add_argument("--metrics", action="store_true",
                        help="처리 후 물리 제약 위반 수를 함께 측정")
    parser.add_argument("--export-ue5", action="store_true",
                        help="처리 후 UE5 DataTable CSV 생성")
    parser.add_argument("--fps", type=int, default=30,
                        help="UE5 CSV 프레임레이트 (기본 30)")
    parser.add_argument("--verbose", action="store_true",
                        help="엔진 경고 로그를 그대로 출력")
    args = parser.parse_args(argv)

    include_real = args.all or not args.reference
    include_reference = args.all or args.reference
    targets = collect_targets(include_real, include_reference)

    if not targets:
        print(f"처리할 MIDI 가 없습니다: {MIDI_DIR}")
        return 1

    print("=" * 60)
    print("  PianoHandSimulator — 운지법 배치 실행기")
    print("=" * 60)
    print(f"  대상       : {len(targets)}곡"
          f" ({'실곡+기준' if include_real and include_reference else ('기준 코퍼스' if include_reference else '실곡')})")
    print(f"  결과 폴더  : {RESULTS_DIR}")
    print(f"  지표 측정  : {'ON' if args.metrics else 'OFF'}"
          f" · UE5 내보내기: {'ON' if args.export_ue5 else 'OFF'}")
    print("-" * 60)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    records = []
    for index, midi_path in enumerate(targets, 1):
        name = os.path.basename(midi_path)
        print(f"  [{index:2d}/{len(targets)}] {name[:46]}", flush=True)
        record, log = run_one(midi_path, args.metrics)
        records.append(record)
        if args.verbose and log.strip():
            for line in log.splitlines():
                if line.strip().startswith(("[경고]", "[제외]", "순간 충돌", "페달 구간")):
                    print(f"        {line.strip()}")

    failures = print_summary(records, args.metrics)

    if args.export_ue5:
        export_ue5(records, args.fps)

    print(f"\n[배치 완료] 결과 위치: {RESULTS_DIR}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
