"""
V6 Pipeline — Batch Runner
assets/midi/ 폴더의 모든 MIDI 파일을 운지법 엔진으로 일괄 처리하고
결과를 results/ 에 저장한 뒤 요약 테이블을 출력합니다.

사용법:
  python run_batch.py              # 전체 처리
  python run_batch.py --export-ue5 # 처리 후 UE5 CSV도 자동 생성
"""
import os
import sys
import time
import glob
import argparse

# 같은 폴더의 엔진/익스포터 임포트
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fingering_engine import analyze_polyphonic
from ue5_exporter     import export_one


def find_midi_files(midi_dir: str) -> list:
    patterns = ["*.mid", "*.midi", "*.MID", "*.MIDI"]
    files = []
    for pat in patterns:
        files.extend(glob.glob(os.path.join(midi_dir, pat)))
    return sorted(set(files))


def run_batch(midi_dir: str, results_dir: str, export_ue5: bool):
    midi_files = find_midi_files(midi_dir)
    if not midi_files:
        print(f"Error: {midi_dir} 에 MIDI 파일이 없습니다.")
        raise SystemExit(1)

    os.makedirs(results_dir, exist_ok=True)

    print("=" * 64)
    print("  PianoHandSimulator — Batch Runner V6")
    print("=" * 64)
    print(f"  MIDI 폴더  : {midi_dir}")
    print(f"  결과 폴더  : {results_dir}")
    print(f"  파일 수    : {len(midi_files)}개")
    print(f"  UE5 내보내기: {'ON' if export_ue5 else 'OFF'}")
    print("-" * 64)

    results = []
    for midi_path in midi_files:
        stem        = os.path.splitext(os.path.basename(midi_path))[0]
        output_path = os.path.join(results_dir, f"{stem}_fingering.json")

        t0 = time.time()
        try:
            out = analyze_polyphonic(midi_path, output_path)
            elapsed = time.time() - t0
            results.append({"file": stem, "status": "OK", "elapsed": elapsed, "json": out})
        except Exception as e:
            elapsed = time.time() - t0
            results.append({"file": stem, "status": f"FAIL: {e}", "elapsed": elapsed, "json": None})
            print(f"  [!] 실패: {stem} — {e}")

    print("\n" + "=" * 64)
    print("  처리 결과 요약")
    print("=" * 64)
    print(f"  {'파일명':<45}  {'상태':<6}  {'시간':>5}")
    print("-" * 64)
    ok_count = 0
    for r in results:
        status_display = "✓ OK" if r["status"] == "OK" else "✗ FAIL"
        name = r["file"][:44] if len(r["file"]) > 44 else r["file"]
        print(f"  {name:<45}  {status_display:<6}  {r['elapsed']:>4.1f}s")
        if r["status"] == "OK":
            ok_count += 1
    print("-" * 64)
    print(f"  완료: {ok_count}/{len(results)}개 성공")

    if export_ue5:
        ue5_dir = os.path.join(results_dir, "ue5")
        os.makedirs(ue5_dir, exist_ok=True)
        print("\n" + "-" * 64)
        print("  UE5 DataTable CSV 내보내기")
        print("-" * 64)
        for r in results:
            if r["status"] == "OK" and r["json"]:
                export_one(r["json"], ue5_dir)

    print("\n[Batch Runner] 전체 완료")
    print(f"  결과 위치: {results_dir}")
    if export_ue5:
        print(f"  UE5 CSV  : {os.path.join(results_dir, 'ue5')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PianoHandSimulator — Batch Runner V6")
    parser.add_argument("--export-ue5", action="store_true",
                        help="운지법 처리 후 UE5 DataTable CSV도 자동 생성")
    args = parser.parse_args()

    base_dir    = os.path.dirname(os.path.abspath(__file__))
    midi_dir    = os.path.abspath(os.path.join(base_dir, "../assets/midi"))
    results_dir = os.path.abspath(os.path.join(base_dir, "../results"))

    run_batch(midi_dir, results_dir, export_ue5=args.export_ue5)
