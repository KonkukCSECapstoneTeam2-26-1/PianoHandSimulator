"""운지법 결과 JSON → Unreal Engine 5 DataTable용 CSV 변환 도구.

운지법 엔진(`v5_polyphonic/piano_fingering_engine.py`)이 출력한 NoteEvent JSON
(= 설계 명세서 Interface A)을 UE5 에디터가 그대로 임포트할 수 있는 CSV로 변환한다.

UE5 DataTable CSV 임포트 규격
  1. 첫 열은 행 이름(RowName) 열이며 값이 전부 고유해야 한다  → `Note_00001` 형식으로 생성
  2. 2번째 열부터의 헤더는 USTRUCT 멤버명과 정확히 일치해야 한다 → `FPianoNoteRow.h` 참조
  3. bool은 `True` / `False`, enum 성격 필드는 문자열로 기록

파생 열 (JSON에 없으며 본 도구가 계산해 추가)
  · BoneName          : finger + hand → IK End Effector 본 이름 (명세서 2.6절)
  · FrameIndex        : start_ms 를 --fps 로 환산한 타건 프레임 번호
  · ReleaseFrameIndex : start_ms + key_hold_ms 를 환산한 건반 해제 프레임 번호
                        (손가락이 떨어지는 시점. 소리 종료가 아님)

선택 열 (JSON에 있을 때만 출력)
  · KeyHoldMs : 손가락이 건반을 누르고 있는 시간(ms). **DurationMs와 다르다.**
    DurationMs는 Sustain 페달로 늘어난 '소리'의 지속이고, 손가락은 그보다 먼저
    건반에서 떨어진다. IK의 누름/해제는 반드시 KeyHoldMs를 기준으로 할 것.
  · PedalDown : 타건 시점의 Sustain 페달 상태. True면 손가락을 떼도 소리가 유지됨.
  · TargetXMm / TargetYMm / TargetZMm : 건반 3D 목표 좌표(mm).
    **단위 주의**: 엔진 출력은 mm, UE5 기본 단위는 cm → UE5 측에서 ÷10 필요.

실행
  python tools/export_datatable.py results/deb_clai_polyphonic_result.json
  python tools/export_datatable.py <result.json> [-o out.csv] [--fps 30]

Windows 콘솔(cp949)에서는 `PYTHONIOENCODING=utf-8` 지정 후 실행할 것.
"""
import argparse
import csv
import json
import os
import sys

# 공유 상수 (본 이름 등) — 수치의 단일 출처
_SC_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if _SC_DIR not in sys.path:
    sys.path.insert(0, _SC_DIR)
import shared_constants

# --- 상수 -------------------------------------------------------------------

#: 기본 프레임레이트 — Interface B(IK → Skinning)가 30 FPS 기준이므로 동일하게 맞춘다.
DEFAULT_FPS = 30.0

#: finger(1~5) → UE5 본 이름 접두사. 설계 명세서 2.6절 표를 그대로 사용.
FINGER_BONE_PREFIX = {
    1: "thumb",   # 엄지
    2: "index",   # 검지
    3: "middle",  # 중지
    4: "ring",    # 약지
    5: "pinky",   # 새끼
}

#: hand → 본 이름 접미사. "Left" → _l, "Right" → _r
HAND_BONE_SUFFIX = {
    "Left": "l",
    "Right": "r",
}

#: `_03` = 말단 지절(Distal Phalanx) 끝 = IK End Effector (명세서 2.6절 비고)
BONE_SEGMENT = "03"

#: 행 이름 접두사 / 자리수 (Note_00001 ~)
ROW_NAME_PREFIX = "Note_"
ROW_NAME_DIGITS = 5

#: JSON 필드 → CSV 헤더(USTRUCT 멤버명) 매핑과 값 종류.
#: kind: "int" | "float" | "str" | "bool"
CORE_COLUMNS = [
    # (JSON 키,               CSV 헤더,               kind)
    ("pitch",                "Pitch",                "int"),
    ("start_ms",             "StartMs",              "float"),
    ("duration_ms",          "DurationMs",           "float"),
    ("hand",                 "Hand",                 "str"),
    ("role",                 "Role",                 "str"),
    ("finger",               "Finger",               "int"),
    ("pressure",             "Pressure",             "float"),
    ("key_depth",            "KeyDepth",             "float"),
    ("is_black",             "IsBlack",              "bool"),
    ("wrist_pos_normalized", "WristPosNormalized",   "float"),
    ("wrist_yaw_deg",        "WristYawDeg",          "float"),
    ("wrist_roll_deg",       "WristRollDeg",         "float"),
]

#: 선택 필드. 입력 JSON에 존재할 때만 열을 추가한다.
OPTIONAL_COLUMNS = [
    # 손가락이 실제로 건반을 누르고 있는 시간. DurationMs(소리 지속)와 다르다.
    # IK는 건반 누름/해제에 반드시 이 값을 써야 한다.
    ("key_hold_ms", "KeyHoldMs", "float"),
    # 타건 시점에 Sustain 페달이 눌려 있었는지. 손가락을 떼도 소리가 유지됨을 뜻한다.
    ("pedal_down",  "PedalDown", "bool"),
    ("target_x_mm", "TargetXMm", "float"),
    ("target_y_mm", "TargetYMm", "float"),
    ("target_z_mm", "TargetZMm", "float"),
]

#: 파생 열 헤더 (계산 결과를 그대로 문자열/정수로 기록)
DERIVED_COLUMNS = [
    ("BoneName", "str"),
    ("FrameIndex", "int"),
    ("ReleaseFrameIndex", "int"),
]

#: 행 이름 열 헤더. UE5는 CSV 첫 열을 RowName으로 해석하며 헤더명 자체는 자유다.
ROW_NAME_HEADER = "Name"

#: 소수점 자리수 — ms·각도·정규화값 모두 3자리면 충분(엔진 출력 정밀도와 동일).
FLOAT_DECIMALS = 3


# --- 값 포맷터 ---------------------------------------------------------------

def format_float(value):
    """부동소수 → CSV 문자열. 3자리로 반올림하고 불필요한 0을 제거한다.

    `247676.49000000002` 같은 이진 부동소수 잡음을 제거하는 목적.
    """
    text = f"{float(value):.{FLOAT_DECIMALS}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def format_bool(value):
    """bool → UE5가 받는 표기. UE의 ImportText는 True/False를 그대로 해석한다."""
    return "True" if value else "False"


def format_value(value, kind):
    """kind에 따라 CSV 셀 문자열을 만든다."""
    if value is None:
        return ""
    if kind == "bool":
        return format_bool(value)
    if kind == "int":
        return str(int(value))
    if kind == "float":
        return format_float(value)
    return str(value)


# --- 파생 값 계산 ------------------------------------------------------------

# 본 이름의 단일 출처는 shared_constants (01/02/03 파트 공용).
# 위의 FINGER_BONE_PREFIX·BONE_SEGMENT·HAND_BONE_SUFFIX 는 명명 규칙을 설명하는
# 참조용으로 남기고, 실제 산출은 공유 표를 쓴다.
_BONE_TABLE = {"Right": shared_constants.BONE_NAME_R,
               "Left": shared_constants.BONE_NAME_L}


def resolve_bone_name(hand, finger):
    """hand + finger → UE5 IK End Effector 본 이름 (예: 'thumb_03_r').

    매핑에 없는 조합은 ValueError로 즉시 실패시킨다(조용한 오류 방지).
    """
    table = _BONE_TABLE.get(hand)
    if table is None:
        raise ValueError(f"알 수 없는 hand 값: {hand!r} ('Left' | 'Right'만 허용)")

    name = table.get(finger)
    if name is None:
        raise ValueError(f"알 수 없는 finger 값: {finger!r} (1~5만 허용)")

    return name


def ms_to_frame(ms, fps):
    """시각(ms) → 프레임 번호. 가장 가까운 프레임으로 반올림한다.

    내림(floor)을 쓰면 타건이 항상 실제 시각보다 늦게 표시되므로,
    오차를 ±0.5프레임으로 줄이는 반올림을 채택한다.
    """
    return int(round(float(ms) * fps / 1000.0))


def compute_frames(start_ms, hold_ms, fps):
    """(FrameIndex, ReleaseFrameIndex) 반환.

    ReleaseFrameIndex는 '손가락이 건반에서 떨어지는' 프레임이므로
    key_hold_ms 를 기준으로 계산한다. duration_ms(소리 지속)를 쓰면
    Sustain 페달로 늘어난 소리만큼 손가락이 건반에 붙어 있게 되어,
    한 손가락이 서로 다른 건반을 동시에 누르는 모순이 발생한다.
    hold가 1프레임보다 짧아 두 값이 같아지면 타건이 보이지 않으므로
    해제 프레임을 최소 1프레임 뒤로 보정한다.
    """
    press = ms_to_frame(start_ms, fps)
    release = ms_to_frame(float(start_ms) + float(hold_ms), fps)
    if release <= press:
        release = press + 1
    return press, release


# --- 변환 본체 ---------------------------------------------------------------

def load_notes(path):
    """결과 JSON을 읽어 음표 리스트를 반환.

    최상위가 배열인 표준 포맷 외에, {"notes": [...]} 형태도 허용한다.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        for key in ("notes", "note_events", "events"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError(f"음표 배열을 찾을 수 없음: {path}")

    if not isinstance(data, list):
        raise ValueError(f"최상위가 배열이 아님: {path}")
    return data


def detect_optional_columns(notes):
    """음표 중 하나라도 보유한 선택 필드만 골라 반환.

    02_IK 파트가 추가 중인 target_*_mm 필드에 대응하기 위한 유연 처리.
    """
    present = set()
    for note in notes:
        present.update(note.keys())
    return [col for col in OPTIONAL_COLUMNS if col[0] in present]


def build_header(optional_columns):
    """CSV 헤더 행 생성. 첫 열은 반드시 행 이름 열."""
    header = [ROW_NAME_HEADER]
    header += [csv_name for _, csv_name, _ in CORE_COLUMNS]
    header += [csv_name for _, csv_name, _ in optional_columns]
    header += [csv_name for csv_name, _ in DERIVED_COLUMNS]
    return header


def build_row(index, note, optional_columns, fps):
    """음표 1개 → CSV 한 행(문자열 리스트)."""
    row_name = f"{ROW_NAME_PREFIX}{index + 1:0{ROW_NAME_DIGITS}d}"
    row = [row_name]

    for json_key, _, kind in CORE_COLUMNS:
        if json_key not in note:
            raise ValueError(f"{row_name}: 필수 필드 누락 '{json_key}'")
        row.append(format_value(note[json_key], kind))

    # 선택 필드 — 열은 존재하지만 특정 음표에만 없을 수도 있으므로 get 사용
    for json_key, _, kind in optional_columns:
        row.append(format_value(note.get(json_key), kind))

    bone_name = resolve_bone_name(note["hand"], note["finger"])
    hold_ms = note.get("key_hold_ms", note["duration_ms"])
    press_frame, release_frame = compute_frames(note["start_ms"], hold_ms, fps)
    row += [bone_name, str(press_frame), str(release_frame)]

    return row


def default_output_path(input_path):
    """출력 경로 기본값: 입력 폴더 아래 `ue5/<원본이름>_datatable.csv`.

    UE5 임포트 대상 CSV 는 한 폴더에 모아 둔다. 배치 실행기(run_batch.py)와
    단독 실행이 서로 다른 위치에 쓰면 어느 쪽이 최신인지 알 수 없게 된다.
    """
    directory = os.path.join(os.path.dirname(os.path.abspath(input_path)), "ue5")
    stem = os.path.splitext(os.path.basename(input_path))[0]
    return os.path.join(directory, f"{stem}_datatable.csv")


def export(input_path, output_path, fps, use_bom=True):
    """JSON → CSV 변환을 수행하고 요약 통계 dict를 반환."""
    notes = load_notes(input_path)
    optional_columns = detect_optional_columns(notes)
    header = build_header(optional_columns)

    rows = [build_row(i, note, optional_columns, fps) for i, note in enumerate(notes)]

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # UTF-8 BOM: UE5의 FFileHelper는 BOM이 없는 파일을 ANSI로 간주할 수 있어
    # 안전을 위해 기본적으로 BOM을 기록한다(UE가 임포트 시 BOM을 제거함).
    encoding = "utf-8-sig" if use_bom else "utf-8"
    with open(output_path, "w", encoding=encoding, newline="") as f:
        # QUOTE_MINIMAL: 쉼표·따옴표·개행이 포함된 값만 자동 인용 처리
        writer = csv.writer(f, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
        writer.writerow(header)
        writer.writerows(rows)

    bone_names = sorted({row[header.index("BoneName")] for row in rows})
    row_names = [row[0] for row in rows]

    return {
        "note_count": len(notes),
        "row_count": len(rows),
        "unique_row_names": len(set(row_names)),
        "header": header,
        "column_count": len(header),
        "optional_columns": [csv_name for _, csv_name, _ in optional_columns],
        "bone_names": bone_names,
        "last_frame": max((int(row[-1]) for row in rows), default=0),
        "encoding": encoding,
    }


# --- CLI --------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="운지법 결과 JSON을 UE5 DataTable 임포트용 CSV로 변환한다.",
    )
    parser.add_argument("input", help="운지법 결과 JSON 경로 (*_polyphonic_result.json)")
    parser.add_argument(
        "-o", "--output",
        help="출력 CSV 경로 (기본: <입력과 같은 폴더>/<원본이름>_datatable.csv)",
    )
    parser.add_argument(
        "--fps", type=float, default=DEFAULT_FPS,
        help=f"FrameIndex 환산 기준 프레임레이트 (기본: {DEFAULT_FPS:g})",
    )
    parser.add_argument(
        "--no-bom", action="store_true",
        help="UTF-8 BOM 없이 저장 (기본은 BOM 포함 — UE5 임포트 호환)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"입력 파일을 찾을 수 없음: {args.input}")
        return 1
    if args.fps <= 0:
        print(f"--fps 는 0보다 커야 함: {args.fps}")
        return 1

    output_path = args.output or default_output_path(args.input)

    try:
        stats = export(args.input, output_path, args.fps, use_bom=not args.no_bom)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"변환 실패: {exc}")
        return 1

    # 요약 리포트 (tests/test_midi_timing.py 출력 스타일에 맞춘 표 형식)
    print(f"입력   : {os.path.abspath(args.input)}")
    print(f"출력   : {os.path.abspath(output_path)}")
    print(f"인코딩 : {stats['encoding']}  /  FPS: {args.fps:g}")
    print("-" * 66)
    print(f"{'항목':28s} {'값':>36s}")
    print("-" * 66)
    print(f"{'JSON 음표 수':28s} {stats['note_count']:>36d}")
    print(f"{'CSV 데이터 행 수':28s} {stats['row_count']:>36d}")
    print(f"{'행 이름 고유 개수':28s} {stats['unique_row_names']:>36d}")
    print(f"{'열 수 (행 이름 열 포함)':28s} {stats['column_count']:>36d}")
    print(f"{'마지막 해제 프레임':28s} {stats['last_frame']:>36d}")
    opt = ", ".join(stats["optional_columns"]) or "(없음)"
    print(f"{'선택 좌표 열':28s} {opt:>36s}")
    print(f"{'본 이름 종류':28s} {len(stats['bone_names']):>36d}")
    print("-" * 66)
    print("헤더: " + ",".join(stats["header"]))
    print("본  : " + ", ".join(stats["bone_names"]))

    # 자체 무결성 검사 — 행 수·고유성이 깨지면 실패로 종료
    problems = []
    if stats["row_count"] != stats["note_count"]:
        problems.append(
            f"행 수 불일치: JSON {stats['note_count']} vs CSV {stats['row_count']}"
        )
    if stats["unique_row_names"] != stats["row_count"]:
        problems.append(
            f"행 이름 중복: 고유 {stats['unique_row_names']} / 전체 {stats['row_count']}"
        )

    print("-" * 66)
    print(f"판정: {'PASS' if not problems else 'FAIL'}")
    for message in problems:
        print(f"  - {message}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
