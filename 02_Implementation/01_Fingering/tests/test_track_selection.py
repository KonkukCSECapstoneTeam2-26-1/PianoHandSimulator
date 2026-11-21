"""피아노 트랙 자동 선별 검증 테스트 (요구사항 2.3).

입력 MIDI 가 피아노 독주 악보라는 보장이 없다. 게임·밴드 편곡 MIDI 에는
드럼·베이스·효과음이 함께 들어 있다. 특히 GM 타악 채널(10번, 0-base 9)의
note 번호는 음높이가 아니라 **악기 번호**(35=Bass Drum 등)인데, 그 값이
35~81 로 88키 음역(21~108) 안에 들어오기 때문에 음역 필터로는 걸러지지
않는다. 그대로 두면 드럼 한 대가 건반 한 개로 운지된다.

이 테스트가 지키는 것은 세 가지다.

  1. 1단계(무조건 제외)가 타악 채널과 효과음 음색만 정확히 걸러내는지
  2. 2단계(피아노 편곡 판정)가 임계값 경계에서 의도대로 동작하는지
  3. 기준 코퍼스(ref_*)는 선별을 켜도 **결과가 바뀌지 않는지** — 회귀 방지

3번이 핵심이다. 기준 코퍼스는 전부 피아노 음색 단일 트랙이므로 선별이
무엇을 해도 결과가 달라져서는 안 된다. 달라지면 선별이 정상 음표를
건드리고 있다는 뜻이다.

설계 근거: 01_Design/15_Piano_Track_Selection.md
실행: python tests/test_track_selection.py
"""
import contextlib
import glob
import io
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FINGERING_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, os.path.join(FINGERING_DIR, "v5_polyphonic"))
sys.path.insert(0, FINGERING_DIR)

import piano_fingering_engine as engine  # noqa: E402
import shared_constants  # noqa: E402

REFERENCE_DIR = os.path.join(FINGERING_DIR, "assets", "midi", "reference")

DRUM_CH = shared_constants.GM_PERCUSSION_CHANNEL
SFX_PROG = shared_constants.GM_UNPLAYABLE_PROGRAM_MIN


def note(pitch, channel=0, program=0):
    """선별 판정에 필요한 필드만 채운 음표."""
    return engine.NoteEvent(pitch, 80, 0.0, 100.0, -1,
                            channel=channel, program=program)


# (이름, 입력 음표, 기대 남는 수, 기대 piano_only)
STAGE_CASES = [
    ("타악 채널 음표는 음역 안이어도 전부 제외",
     [note(60, channel=DRUM_CH), note(38, channel=DRUM_CH), note(60)],
     1, True),
    ("효과음 음색(program 112~127)은 제외",
     [note(60, program=SFX_PROG), note(60, program=127), note(60)],
     1, True),
    ("program 111 은 효과음 구간 바로 앞이므로 남는다",
     [note(60, program=111), note(60, program=0)],
     2, False),
    ("피아노 계열 경계 program 7 은 피아노로 센다",
     [note(60, program=7), note(62, program=7)],
     2, True),
    ("program 8 은 피아노가 아니다 (Celesta)",
     [note(60, program=8), note(62, program=8)],
     2, False),
    ("program_change 가 없으면 GM 기본값 0 → 피아노",
     [note(60), note(62), note(64)],
     3, True),
    ("피아노 점유율이 임계 미달이면 연주 가능 트랙 전체를 쓴다",
     [note(60, program=0)] + [note(62, program=48)] * 9,
     10, False),
    ("피아노 트랙이 아예 없으면 판정하지 않고 전체를 쓴다",
     [note(60, program=48), note(62, program=33)],
     2, False),
    ("타악만 있는 입력은 남는 음표가 없다",
     [note(38, channel=DRUM_CH), note(42, channel=DRUM_CH)],
     0, False),
]


def check_stages():
    print("1. 선별 단계 판정")
    print("-" * 78)
    failures = []
    for name, notes, want_kept, want_piano_only in STAGE_CASES:
        report = {}
        kept = engine.select_piano_sources(notes, report=report)
        ok = (len(kept) == want_kept
              and report["piano_only"] == want_piano_only)
        # 원본 리스트를 변형하지 않아야 한다
        ok = ok and len(notes) == report["total"]
        mark = "OK  " if ok else "FAIL"
        print(f"  {mark} {name[:56]:<58} "
              f"남김 {len(kept)}/{want_kept} · 피아노전용 {report['piano_only']}")
        if not ok:
            failures.append(name)
    return failures


def check_threshold_boundary():
    """임계값 경계에서 판정이 뒤집히는지 확인."""
    print()
    print("2. 임계값 경계")
    print("-" * 78)
    failures = []
    th = engine.PIANO_ARRANGEMENT_SHARE
    total = 100
    for piano_count, want in ((int(th * total), True),
                              (int(th * total) - 1, False)):
        notes = ([note(60, program=0)] * piano_count
                 + [note(62, program=48)] * (total - piano_count))
        report = {}
        engine.select_piano_sources(notes, report=report)
        ok = report["piano_only"] == want
        print(f"  {'OK  ' if ok else 'FAIL'} 점유율 {piano_count}/{total} "
              f"(임계 {th:.2f}) → 피아노전용 {report['piano_only']} (기대 {want})")
        if not ok:
            failures.append(f"임계 경계 {piano_count}/{total}")
    return failures


def _run_engine(path):
    """엔진을 한 번 돌려 결과 JSON 을 읽어 온다 (로그는 버린다)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out_path = engine.analyze_polyphonic(path)
    with open(out_path, encoding="utf-8") as f:
        return json.load(f)


def _bypass(notes, **kwargs):
    """선별을 끈 대체 구현. 보고 형식은 유지한다."""
    report = kwargs.get("report")
    if report is not None:
        report.update(dict(total=len(notes), percussion_dropped=0,
                           effects_dropped=0, playable=len(notes),
                           piano_notes=0, piano_share=0.0,
                           piano_only=False, kept=len(notes)))
    return list(notes)


def check_reference_corpus_unchanged():
    """기준 코퍼스는 선별을 켜도 결과가 완전히 같아야 한다."""
    print()
    print("3. 기준 코퍼스 불변 (선별 ON/OFF 결과 일치)")
    print("-" * 78)
    failures = []
    files = sorted(glob.glob(os.path.join(REFERENCE_DIR, "*.mid")))
    if not files:
        print("  [건너뜀] 기준 코퍼스가 없다 "
              "(tools/make_reference_corpus.py 로 생성)")
        return failures

    original = engine.select_piano_sources
    for path in files:
        name = os.path.basename(path)[:-4]
        try:
            engine.select_piano_sources = _bypass
            off = _run_engine(path)
            engine.select_piano_sources = original
            on = _run_engine(path)
        finally:
            engine.select_piano_sources = original
        ok = off == on
        print(f"  {'OK  ' if ok else 'FAIL'} {name[:40]:<42} "
              f"음표 {len(off)} → {len(on)}")
        if not ok:
            failures.append(f"{name}: 선별이 기준 코퍼스 결과를 바꿨음")
    return failures


def main():
    print("=" * 78)
    print(" 피아노 트랙 자동 선별 검증 (요구사항 2.3)")
    print("=" * 78)
    failures = []
    failures += check_stages()
    failures += check_threshold_boundary()
    failures += check_reference_corpus_unchanged()

    print()
    print("=" * 78)
    print(f"FAIL {len(failures)}건")
    for f in failures:
        print(f"  - {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
