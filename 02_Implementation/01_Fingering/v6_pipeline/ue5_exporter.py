"""
V6 Pipeline — UE5 Exporter
fingering JSON → UE5 DataTable CSV 변환기

사용법:
  python ue5_exporter.py                          # results/ 에서 최신 JSON 자동 선택
  python ue5_exporter.py --json path/to/file.json # 특정 JSON 지정
  python ue5_exporter.py --all                    # results/ 의 모든 *_fingering.json 일괄 변환

출력:
  results/ue5/{stem}_datatable.csv   — UE5 DataTable Import용 CSV
  results/ue5/{stem}_summary.txt     — 통계 요약

UE5 DataTable 구조체 (C++ USTRUCT):
  USTRUCT(BlueprintType)
  struct FFingeringNoteData : public FTableRowBase {
      UPROPERTY() int32   Pitch;
      UPROPERTY() float   StartMs;
      UPROPERTY() float   DurationMs;
      UPROPERTY() FString Hand;           // "Left" | "Right"
      UPROPERTY() FString Role;           // "MELODY" | "BASS" | "INNER"
      UPROPERTY() int32   Finger;         // 1~5
      UPROPERTY() float   Pressure;       // 0.0~1.0
      UPROPERTY() float   KeyDepth;       // 0.0~1.0
      UPROPERTY() bool    bIsBlack;
      UPROPERTY() float   WristPosNorm;   // 0.0~1.0 (88키 기준)
      UPROPERTY() float   WristYawDeg;    // -35.0~+35.0
      UPROPERTY() float   WristRollDeg;   // -20.0~+20.0
  };
"""
import json
import os
import csv
import glob
import argparse
from collections import Counter

# UE5 DataTable CSV 헤더 (첫 번째 열 --- 은 RowName)
CSV_COLUMNS = [
    "---",
    "Pitch", "StartMs", "DurationMs",
    "Hand", "Role", "Finger",
    "Pressure", "KeyDepth", "bIsBlack",
    "WristPosNorm", "WristYawDeg", "WristRollDeg"
]


def json_to_datatable_csv(json_path: str, output_path: str):
    with open(json_path, encoding="utf-8") as f:
        notes = json.load(f)

    rows = []
    for idx, n in enumerate(notes):
        row_name = f"Note_{idx:06d}"
        rows.append({
            "---":           row_name,
            "Pitch":         n["pitch"],
            "StartMs":       round(n["start_ms"], 2),
            "DurationMs":    round(n["duration_ms"], 2),
            "Hand":          n["hand"],
            "Role":          n["role"],
            "Finger":        n["finger"],
            "Pressure":      round(n["pressure"], 4),
            "KeyDepth":      round(n["key_depth"], 4),
            "bIsBlack":      "True" if n["is_black"] else "False",
            "WristPosNorm":  round(n["wrist_pos_normalized"], 4),
            "WristYawDeg":   round(n["wrist_yaw_deg"], 2),
            "WristRollDeg":  round(n["wrist_roll_deg"], 2),
        })

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return notes, rows


def build_summary(notes: list, json_path: str, csv_path: str) -> str:
    total      = len(notes)
    left_notes = [n for n in notes if n["hand"] == "Left"]
    right_notes= [n for n in notes if n["hand"] == "Right"]
    duration_s = max(n["start_ms"] + n["duration_ms"] for n in notes) / 1000

    finger_counter = Counter(n["finger"] for n in notes)
    role_counter   = Counter(n["role"]   for n in notes)
    black_count    = sum(1 for n in notes if n["is_black"])

    # 손가락별 분포 (%)
    finger_lines = []
    for f in range(1, 6):
        name = {1:"엄지", 2:"검지", 3:"중지", 4:"약지", 5:"새끼"}[f]
        cnt  = finger_counter.get(f, 0)
        pct  = cnt / total * 100 if total else 0
        bar  = "█" * int(pct / 2)
        finger_lines.append(f"  {f}번({name}) : {cnt:5d}  {pct:5.1f}%  {bar}")

    lines = [
        "=" * 56,
        f"  PianoHandSimulator — Fingering 결과 요약",
        "=" * 56,
        f"  원본 JSON : {os.path.basename(json_path)}",
        f"  CSV 출력  : {os.path.basename(csv_path)}",
        "-" * 56,
        f"  총 음표 수   : {total}",
        f"  곡 길이      : {duration_s:.1f}초  ({duration_s/60:.1f}분)",
        f"  왼손 / 오른손 : {len(left_notes)} / {len(right_notes)}",
        f"  흑건 비율    : {black_count}/{total}  ({black_count/total*100:.1f}%)",
        "",
        "  역할 분포:",
        f"    MELODY : {role_counter.get('MELODY', 0)}",
        f"    BASS   : {role_counter.get('BASS',   0)}",
        f"    INNER  : {role_counter.get('INNER',  0)}",
        "",
        "  손가락 사용 분포:",
    ] + finger_lines + [
        "-" * 56,
        "  [UE5 DataTable Import 방법]",
        "  1. UE5 Content Browser → Import → CSV 선택",
        "  2. DataTable Row Type: FFingeringNoteData 선택",
        "  3. Import 완료 후 DataTable 에셋 확인",
        "=" * 56,
    ]
    return "\n".join(lines)


def export_one(json_path: str, output_dir: str):
    stem        = os.path.splitext(os.path.basename(json_path))[0]
    csv_path    = os.path.join(output_dir, f"{stem}_datatable.csv")
    summary_path= os.path.join(output_dir, f"{stem}_summary.txt")

    print(f"  Exporting: {os.path.basename(json_path)}")
    notes, _ = json_to_datatable_csv(json_path, csv_path)

    summary = build_summary(notes, json_path, csv_path)
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(summary)

    print(summary)
    print(f"  -> CSV    : {csv_path}")
    print(f"  -> Summary: {summary_path}\n")


def resolve_json_candidates(json_arg, export_all, base_dir):
    results_dir = os.path.abspath(os.path.join(base_dir, "../results"))
    if json_arg:
        if not os.path.exists(json_arg):
            print(f"Error: {json_arg} 파일을 찾을 수 없습니다.")
            raise SystemExit(1)
        return [json_arg]
    if export_all:
        candidates = sorted(glob.glob(os.path.join(results_dir, "*_fingering.json")))
        if not candidates:
            print("Error: results/ 에 *_fingering.json 파일이 없습니다.")
            print("  먼저 run_batch.py 또는 fingering_engine.py 를 실행하세요.")
            raise SystemExit(1)
        return candidates
    # 기본: 최신 1개
    candidates = sorted(glob.glob(os.path.join(results_dir, "*_fingering.json")),
                        key=os.path.getmtime, reverse=True)
    if not candidates:
        fallback = os.path.join(results_dir, "mario_polyphonic_result.json")
        if os.path.exists(fallback):
            return [fallback]
        print("Error: 변환할 JSON이 없습니다. fingering_engine.py 를 먼저 실행하세요.")
        raise SystemExit(1)
    return [candidates[0]]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PianoHandSimulator — UE5 Exporter V6")
    parser.add_argument("--json", default=None,       help="변환할 fingering JSON 경로")
    parser.add_argument("--all",  action="store_true", help="results/ 의 모든 JSON 일괄 변환")
    args = parser.parse_args()

    base_dir   = os.path.dirname(os.path.abspath(__file__))
    output_dir = os.path.abspath(os.path.join(base_dir, "../results/ue5"))
    os.makedirs(output_dir, exist_ok=True)

    targets = resolve_json_candidates(args.json, args.all, base_dir)
    print(f"\n[UE5 Exporter] {len(targets)}개 파일 변환 시작\n")
    for t in targets:
        export_one(t, output_dir)
    print("[UE5 Exporter] 완료")
