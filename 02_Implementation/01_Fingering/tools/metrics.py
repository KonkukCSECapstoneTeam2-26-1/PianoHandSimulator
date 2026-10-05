"""운지법 엔진 정량 평가 지표 측정 도구.

엔진이 출력한 결과 JSON(`results/*_polyphonic_result.json`)만을 입력으로 받아,
정답(기준 운지) 데이터 없이 계산 가능한 객관 지표를 산출한다.

  [A] 물리 제약 위반 — 설계 명세서(01_Design/02_Fingering_Design_Spec.md)가
      하드 제약으로 규정한 항목. 정상이라면 모두 0건이어야 한다.
  [B] 분포·품질 지표 — 좋음/나쁨의 절대 기준이 없는 참고값.

주의: "실제 피아니스트 일치율"은 정답 운지 데이터셋이 필요하므로 본 도구의
범위가 아니다. 상세는 01_Design/10_Fingering_Metrics_Definition.md 참조.

실행:
    python tools/metrics.py <result.json>   # 단일 파일
    python tools/metrics.py                 # results/ 전체 순회

종료 코드: [A] 하드 제약 위반이 하나라도 있으면 1, 없으면 0.
"""
import glob
import json
import os
import sys
import unicodedata
from bisect import bisect_left
from collections import Counter, defaultdict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FINGERING_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
RESULTS_DIR = os.path.join(FINGERING_DIR, "results")
sys.path.insert(0, os.path.join(FINGERING_DIR, "v5_polyphonic"))

try:
    # 제약 상수는 복제하지 않고 엔진에서 직접 import 한다 (단일 진실 공급원).
    from piano_fingering_engine import MAX_SPAN, WRIST_ROM
except Exception as exc:  # pragma: no cover - 환경 문제
    print(f"엔진 모듈 import 실패 (v5_polyphonic/piano_fingering_engine.py): {exc}")
    sys.exit(2)

# 엔진이 parse_midi_to_hand_chords() / split_wide_chords_between_hands()에서
# 화음 그룹화 임계값으로 하드코딩한 값(30ms)과 동일하게 맞춘다.
CHORD_WINDOW_MS = 30.0

# 부동소수 비교 오차 허용치
EPS = 1e-6

# 동시 누름 충돌(A3) 판정 허용치.
# 결과 JSON은 start_ms/duration_ms를 소수 2자리로 반올림하므로
# "앞 음을 떼는 순간 뒤 음을 누르는" 레가토 경계에서 0.01ms 수준의 가짜 중첩이 생긴다.
# 이는 물리적 충돌이 아니므로 1ms 이하 중첩은 '경계 접촉'으로 분리 집계한다.
OVERLAP_TOLERANCE_MS = 1.0

# MAX_SPAN에 등재되지 않은 손가락 쌍의 기본 허용 간격 (엔진의 .get(pair, 12)와 동일)
DEFAULT_MAX_SPAN = 12

# 성부별 선호/기피 손가락 (설계 명세서 4.2 RoleAffinity)
ROLE_PREFERENCE = {
    ("MELODY", "Right"): ({4, 5}, {1}),
    ("MELODY", "Left"): ({1, 2}, {5}),
    ("BASS", "Right"): ({1}, set()),
    ("BASS", "Left"): ({5}, set()),
    ("INNER", "Right"): ({2, 3}, set()),
    ("INNER", "Left"): ({2, 3}, set()),
}


# ─────────────────────────────────────────────────────────────
# 출력 유틸 (한글 전각 폭을 고려한 정렬)
# ─────────────────────────────────────────────────────────────
def _width(text):
    """터미널 표시 폭 (전각 문자는 2칸)."""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in str(text))


def _pad(text, width):
    return str(text) + " " * max(0, width - _width(text))


COL = (48, 24, 6)
LINE = "-" * (COL[0] + COL[1] + COL[2])


def _row(name, value, verdict=""):
    print(_pad(name, COL[0]) + _pad(value, COL[1]) + str(verdict))


# ─────────────────────────────────────────────────────────────
# 입력 정규화
# ─────────────────────────────────────────────────────────────
class Note:
    """결과 JSON 한 원소의 안전 래퍼.

    알 수 없는 필드(다른 파트가 추가하는 target_x_mm 등)는 raw에 보존하며
    지표 계산에는 영향을 주지 않는다. 필수 필드가 없거나 타입이 달라도
    예외 없이 기본값으로 대체한다.
    """

    __slots__ = ("raw", "idx", "pitch", "start", "dur", "end", "hand",
                 "role", "finger", "is_black", "yaw", "roll", "chord_id", "hold")

    def __init__(self, raw, idx):
        self.raw = raw if isinstance(raw, dict) else {}
        self.idx = idx
        self.pitch = _as_int(self.raw.get("pitch"), 0)
        self.start = _as_float(self.raw.get("start_ms"), 0.0)
        self.dur = _as_float(self.raw.get("duration_ms"), 0.0)
        # 손가락 점유 종료 시각은 key_hold_ms 기준이다.
        # duration_ms는 '소리'의 지속(Sustain 페달로 늘어남)이므로 중첩이 정상이며,
        # 손가락 충돌(A3) 판정에 쓰면 페달로 유지된 음을 전부 위반으로 오검출한다.
        # key_hold_ms가 없는 구버전 JSON은 duration_ms로 폴백한다.
        hold = self.raw.get("key_hold_ms")
        self.hold = _as_float(hold, self.dur) if hold is not None else self.dur
        self.end = self.start + max(0.0, self.hold)
        hand = self.raw.get("hand")
        self.hand = hand if hand in ("Left", "Right") else "Unknown"
        role = self.raw.get("role")
        self.role = role if isinstance(role, str) else "UNKNOWN"
        self.finger = _as_int(self.raw.get("finger"), 0)
        black = self.raw.get("is_black")
        self.is_black = bool(black) if black is not None else (self.pitch % 12) in {1, 3, 6, 8, 10}
        self.yaw = _as_float(self.raw.get("wrist_yaw_deg"), 0.0)
        self.roll = _as_float(self.raw.get("wrist_roll_deg"), 0.0)
        self.chord_id = -1

    def label(self):
        return f"#{self.idx} {self.hand[:1]} p{self.pitch} f{self.finger} @{self.start:.0f}ms"


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value, default):
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return default if f != f else f  # NaN 방어


def load_notes(path):
    """결과 JSON을 Note 리스트로 로드. 배열이 아니면 ValueError."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):  # {"notes": [...]} 형태도 허용
        for key in ("notes", "data", "result"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        raise ValueError("최상위가 음표 배열이 아님")
    return [Note(raw, i) for i, raw in enumerate(data)]


def group_chords(notes):
    """손별 화음 그룹 재구성.

    엔진과 동일한 규칙: 같은 손에서 start_ms 차이가 그룹 첫 음표 기준
    30ms 미만인 음표들을 하나의 화음으로 묶고 pitch 오름차순 정렬.
    반환: {hand: [chord(list[Note]), ...]}
    """
    chords = {}
    cid = 0
    for hand in ("Left", "Right", "Unknown"):
        h_notes = sorted([n for n in notes if n.hand == hand], key=lambda n: (n.start, n.pitch))
        if not h_notes:
            continue
        groups, cur = [], [h_notes[0]]
        for n in h_notes[1:]:
            if n.start - cur[0].start < CHORD_WINDOW_MS:
                cur.append(n)
            else:
                groups.append(sorted(cur, key=lambda x: x.pitch))
                cur = [n]
        groups.append(sorted(cur, key=lambda x: x.pitch))
        for g in groups:
            for n in g:
                n.chord_id = cid
            cid += 1
        chords[hand] = groups
    return chords


# ─────────────────────────────────────────────────────────────
# [A] 하드 제약 위반
# ─────────────────────────────────────────────────────────────
def check_max_span(chords, adjacent_only=True):
    """A1/A1b. 같은 손·같은 화음 내 손가락 쌍의 MAX_SPAN 초과.

    adjacent_only=True  → A1: pitch 기준 인접 쌍만 (엔진 DP 비용 함수와 동일 범위)
    adjacent_only=False → A1b: 비인접(건너뛴) 쌍만. 엔진이 검사하지 않는 사각지대로,
                          인접 쌍이 모두 통과해도 손 전체가 벌어지지 않는 경우가 있다.
    """
    total, bad, examples = 0, 0, []
    for groups in chords.values():
        for g in groups:
            for i in range(len(g)):
                # 인접 모드는 j = i+1 하나만, 비인접 모드는 j = i+2 .. 끝
                j_range = range(i + 1, min(i + 2, len(g))) if adjacent_only \
                    else range(i + 2, len(g))
                for j in j_range:
                    a, b = g[i], g[j]
                    if a.finger == 0 or b.finger == 0 or a.finger == b.finger:
                        continue  # 미배정(A5)·중복(A4)은 별도 지표에서 집계
                    total += 1
                    limit = MAX_SPAN.get(tuple(sorted((a.finger, b.finger))), DEFAULT_MAX_SPAN)
                    gap = b.pitch - a.pitch
                    if gap > limit:
                        bad += 1
                        if len(examples) < 3:
                            examples.append(
                                f"{a.hand} @{a.start:.0f}ms 화음{[n.pitch for n in g]} "
                                f"f{a.finger}(p{a.pitch})-f{b.finger}(p{b.pitch}) "
                                f"gap {gap} > {limit}")
    return bad, total, examples


def check_monotonicity(chords):
    """A2. 오른손 pitch↑=finger↑, 왼손 pitch↑=finger↓ 위반 (인접 쌍 기준)."""
    total, bad, examples = 0, 0, []
    for hand, groups in chords.items():
        if hand not in ("Left", "Right"):
            continue
        for g in groups:
            for a, b in zip(g, g[1:]):
                if a.finger == 0 or b.finger == 0:
                    continue
                total += 1
                ok = b.finger > a.finger if hand == "Right" else b.finger < a.finger
                if not ok:
                    bad += 1
                    if len(examples) < 3:
                        examples.append(
                            f"{hand} @{a.start:.0f}ms p{a.pitch}:f{a.finger} -> "
                            f"p{b.pitch}:f{b.finger}")
    return bad, total, examples


def check_simultaneous_conflict(notes):
    """A3. 같은 손·같은 손가락이 시간적으로 겹치는 음표 쌍 (다른 화음 간).

    조건: 앞 음표의 start+duration > 뒤 음표의 start (엔진 SimultaneousConflict와 동일).
    같은 화음 내 중복은 A4에서 집계하므로 제외한다.

    반환: (충돌 쌍 수, 경계 접촉 쌍 수(≤1ms), 최대 중첩 ms, 예시)
    """
    buckets = defaultdict(list)
    for n in notes:
        if n.finger != 0 and n.hand in ("Left", "Right"):
            buckets[(n.hand, n.finger)].append(n)

    bad, boundary, max_overlap, examples = 0, 0, 0.0, []
    for bucket in buckets.values():
        bucket.sort(key=lambda n: (n.start, n.end))
        prefix_max_end = []
        running = float("-inf")
        for n in bucket:
            running = max(running, n.end)
            prefix_max_end.append(running)
        for j in range(1, len(bucket)):
            cur = bucket[j]
            for i in range(j - 1, -1, -1):
                if prefix_max_end[i] <= cur.start + EPS:
                    break  # 이보다 앞선 음표는 모두 이미 끝났음
                prev = bucket[i]
                if prev.chord_id == cur.chord_id:
                    continue
                overlap = prev.end - cur.start
                if overlap <= EPS:
                    continue
                if overlap <= OVERLAP_TOLERANCE_MS:
                    boundary += 1
                    continue
                bad += 1
                max_overlap = max(max_overlap, overlap)
                if len(examples) < 3:
                    examples.append(
                        f"{cur.hand} f{cur.finger}: p{prev.pitch} "
                        f"[{prev.start:.0f}~{prev.end:.0f}ms] vs p{cur.pitch} "
                        f"[{cur.start:.0f}ms] 중첩 {overlap:.0f}ms")
    return bad, boundary, max_overlap, examples


def check_duplicate_in_chord(chords):
    """A4. 한 화음에서 같은 손가락이 2회 이상 배정된 건수(초과 배정 음표 수)."""
    bad, chord_hits, examples = 0, 0, []
    for groups in chords.values():
        for g in groups:
            counts = Counter(n.finger for n in g if n.finger != 0)
            extra = sum(c - 1 for c in counts.values() if c > 1)
            if extra:
                bad += extra
                chord_hits += 1
                if len(examples) < 3:
                    dup = [f for f, c in counts.items() if c > 1]
                    examples.append(
                        f"{g[0].hand} @{g[0].start:.0f}ms 손가락 {dup} 중복 "
                        f"(화음 {[n.pitch for n in g]})")
    return bad, chord_hits, examples


def check_unassigned(notes):
    """A5. finger == 0 (미배정) 음표 수."""
    hits = [n for n in notes if n.finger == 0]
    return len(hits), [n.label() for n in hits[:3]]


def check_rom(notes):
    """A6. |yaw| > yaw_max, |roll| > roll_max 초과 음표 수."""
    yaw_max, roll_max = WRIST_ROM["yaw_max"], WRIST_ROM["roll_max"]
    yaw_bad = [n for n in notes if abs(n.yaw) > yaw_max + EPS]
    roll_bad = [n for n in notes if abs(n.roll) > roll_max + EPS]
    examples = [f"{n.label()} yaw={n.yaw}" for n in yaw_bad[:2]]
    examples += [f"{n.label()} roll={n.roll}" for n in roll_bad[:2]]
    return len(yaw_bad), len(roll_bad), yaw_max, roll_max, examples


# ─────────────────────────────────────────────────────────────
# [B] 분포·품질 지표
# ─────────────────────────────────────────────────────────────
def finger_distribution(notes):
    """B7. 손가락 1~5 사용 분포(%)와 균등분포 대비 편차."""
    assigned = [n.finger for n in notes if 1 <= n.finger <= 5]
    total = len(assigned)
    counts = Counter(assigned)
    pct = {f: (counts.get(f, 0) / total * 100 if total else 0.0) for f in range(1, 6)}
    max_dev = max(abs(p - 20.0) for p in pct.values()) if total else 0.0
    # 총변동거리: 0=완전균등, 0.8=한 손가락에 전부 몰림
    tvd = sum(abs(p / 100 - 0.2) for p in pct.values()) / 2 if total else 0.0
    return counts, pct, max_dev, tvd, total


def chord_statistics(chords):
    """B8. 화음 수, 평균/최대 span, 최대 동시 발음 수, 단음 비율."""
    spans, sizes, max_span_chord = [], [], None
    for groups in chords.values():
        for g in groups:
            span = g[-1].pitch - g[0].pitch
            spans.append(span)
            sizes.append(len(g))
            if max_span_chord is None or span > max_span_chord[0]:
                max_span_chord = (span, g)
    n = len(spans)
    multi = [s for s, sz in zip(spans, sizes) if sz > 1]
    return {
        "chords": n,
        "avg_span_all": sum(spans) / n if n else 0.0,
        "avg_span_multi": sum(multi) / len(multi) if multi else 0.0,
        "max_span": max(spans) if spans else 0,
        "max_span_chord": max_span_chord,
        "max_poly": max(sizes) if sizes else 0,
        "single_ratio": sum(1 for sz in sizes if sz == 1) / n * 100 if n else 0.0,
        "over17": sum(1 for s in spans if s > 17),
    }


def single_note_runs(chords):
    """B9. 단음 연속 구간에서 같은 손가락 반복 횟수 (동음 제외).

    엔진 ArpeggioRolling의 '동일 손가락 반복 +60' 조건과 동일 판정.
    """
    repeats, transitions = 0, 0
    for hand, groups in chords.items():
        if hand not in ("Left", "Right"):
            continue
        for prev, cur in zip(groups, groups[1:]):
            if len(prev) != 1 or len(cur) != 1:
                continue
            if prev[0].finger == 0 or cur[0].finger == 0:
                continue
            if prev[0].pitch == cur[0].pitch:
                continue  # 동음 반복은 같은 손가락이 정상
            transitions += 1
            if prev[0].finger == cur[0].finger:
                repeats += 1
    return repeats, transitions


def arpeggio_mismatch(chords):
    """B10. 단음→단음 전환에서 피치 방향과 손가락 방향 불일치 (엔진과 동일 규칙).

    오른손: 상행=손가락 번호 증가, 하행=감소.
    왼손:   상행=손가락 번호 감소, 하행=증가.
    """
    bad, transitions, examples = 0, 0, []
    for hand, groups in chords.items():
        if hand not in ("Left", "Right"):
            continue
        for prev, cur in zip(groups, groups[1:]):
            if len(prev) != 1 or len(cur) != 1:
                continue
            p, c = prev[0], cur[0]
            if p.finger == 0 or c.finger == 0 or p.finger == c.finger:
                continue
            direction = c.pitch - p.pitch
            if direction == 0:
                continue
            transitions += 1
            if hand == "Right":
                mismatch = (direction > 0 and c.finger < p.finger) or \
                           (direction < 0 and c.finger > p.finger)
            else:
                mismatch = (direction > 0 and c.finger > p.finger) or \
                           (direction < 0 and c.finger < p.finger)
            if mismatch:
                bad += 1
                if len(examples) < 3:
                    examples.append(
                        f"{hand} @{c.start:.0f}ms p{p.pitch}:f{p.finger} -> "
                        f"p{c.pitch}:f{c.finger}")
    return bad, transitions, examples


def hand_separation(chords):
    """B11. 좌우 음역 중첩 폭과 손 교차(왼손 최고음 > 오른손 최저음) 발생 건수.

    교차 판정은 동시 온셋(시작 시각 차 < 30ms) 화음 쌍 단위로 센다.
    """
    left, right = chords.get("Left", []), chords.get("Right", [])
    out = {"left_range": None, "right_range": None, "overlap": 0,
           "cross": 0, "pairs": 0, "examples": []}
    if left:
        out["left_range"] = (min(n.pitch for g in left for n in g),
                             max(n.pitch for g in left for n in g))
    if right:
        out["right_range"] = (min(n.pitch for g in right for n in g),
                              max(n.pitch for g in right for n in g))
    if out["left_range"] and out["right_range"]:
        out["overlap"] = max(0, out["left_range"][1] - out["right_range"][0])

    if not left or not right:
        return out
    r_starts = [g[0].start for g in right]
    for lg in left:
        lo = bisect_left(r_starts, lg[0].start - CHORD_WINDOW_MS)
        for i in range(lo, len(right)):
            rg = right[i]
            if rg[0].start - lg[0].start >= CHORD_WINDOW_MS:
                break
            if abs(rg[0].start - lg[0].start) >= CHORD_WINDOW_MS:
                continue
            out["pairs"] += 1
            if lg[-1].pitch > rg[0].pitch:
                out["cross"] += 1
                if len(out["examples"]) < 3:
                    out["examples"].append(
                        f"@{lg[0].start:.0f}ms L최고 p{lg[-1].pitch} > R최저 p{rg[0].pitch}")
    return out


def black_key_thumb_pinky(notes):
    """B12. 흑건에 1번/5번 손가락이 배정된 비율."""
    black = [n for n in notes if n.is_black and n.finger != 0]
    total = len(black)
    f1 = sum(1 for n in black if n.finger == 1)
    f5 = sum(1 for n in black if n.finger == 5)
    assigned = sum(1 for n in notes if n.finger != 0)
    return {
        "black": total,
        "black_ratio": total / assigned * 100 if assigned else 0.0,
        "f1": f1, "f5": f5,
        "f1_pct": f1 / total * 100 if total else 0.0,
        "f5_pct": f5 / total * 100 if total else 0.0,
        "both_pct": (f1 + f5) / total * 100 if total else 0.0,
    }


def role_preference(notes):
    """B13. 성부별(MELODY/BASS/INNER) 손가락 선호 실현도.

    설계 명세서 RoleAffinity의 보상 대상 손가락 비율(실현율)과
    패널티 대상 손가락 비율(기피 위반율)을 손별로 집계한다.
    """
    stats = {}
    for (role, hand), (pref, avoid) in ROLE_PREFERENCE.items():
        subset = [n for n in notes if n.role == role and n.hand == hand and n.finger != 0]
        if not subset:
            continue
        stats[(role, hand)] = {
            "n": len(subset),
            "pref": pref,
            "avoid": avoid,
            "pref_pct": sum(1 for n in subset if n.finger in pref) / len(subset) * 100,
            "avoid_pct": (sum(1 for n in subset if n.finger in avoid) / len(subset) * 100
                          if avoid else None),
            "dist": Counter(n.finger for n in subset),
        }
    return stats


# ─────────────────────────────────────────────────────────────
# 리포트
# ─────────────────────────────────────────────────────────────
def evaluate(path):
    """단일 결과 파일을 평가하고 표를 출력. 하드 위반 총합을 반환."""
    notes = load_notes(path)
    chords = group_chords(notes)

    name = os.path.basename(path)
    print("=" * (COL[0] + COL[1] + COL[2]))
    print(f" 운지법 엔진 정량 평가 — {name}")
    print("=" * (COL[0] + COL[1] + COL[2]))

    if not notes:
        print(" 음표 0개 — 평가할 데이터가 없음")
        print()
        return 0

    n_left = sum(1 for n in notes if n.hand == "Left")
    n_right = sum(1 for n in notes if n.hand == "Right")
    n_other = len(notes) - n_left - n_right
    n_chords = sum(len(g) for g in chords.values())
    dur = max(n.end for n in notes) / 1000.0
    print(f" 음표 {len(notes)}개 (왼손 {n_left} / 오른손 {n_right}"
          + (f" / 미분류 {n_other}" if n_other else "")
          + f") · 화음 {n_chords}개 · 길이 {dur:.1f}초")
    print()

    # ---- [A] 하드 제약 --------------------------------------
    span_bad, span_total, span_ex = check_max_span(chords, adjacent_only=True)
    span2_bad, span2_total, span2_ex = check_max_span(chords, adjacent_only=False)
    mono_bad, mono_total, mono_ex = check_monotonicity(chords)
    conf_bad, conf_edge, conf_max, conf_ex = check_simultaneous_conflict(notes)
    dup_bad, dup_chords, dup_ex = check_duplicate_in_chord(chords)
    un_bad, un_ex = check_unassigned(notes)
    yaw_bad, roll_bad, yaw_max, roll_max, rom_ex = check_rom(notes)

    hard_total = (span_bad + span2_bad + mono_bad + conf_bad + dup_bad
                  + un_bad + yaw_bad + roll_bad)

    print("[A] 물리 제약 위반 — 하드 제약 (0이어야 정상)")
    _row("지표", "값", "판정")
    print(LINE)
    _row("A1. MAX_SPAN 초과 (화음 내 인접 손가락쌍)",
         f"{span_bad} / {span_total}쌍 ({_pc(span_bad, span_total)})",
         _verdict(span_bad))
    _row("A1b. MAX_SPAN 초과 (비인접 손가락쌍)",
         f"{span2_bad} / {span2_total}쌍 ({_pc(span2_bad, span2_total)})",
         _verdict(span2_bad))
    _row("A2. Monotonicity 위반 (pitch↔finger 순서)",
         f"{mono_bad} / {mono_total}쌍 ({_pc(mono_bad, mono_total)})",
         _verdict(mono_bad))
    _row("A3. 동시 누름 충돌 (같은 손·같은 손가락 중첩)",
         f"{conf_bad}쌍 (최대 {conf_max:.0f}ms)", _verdict(conf_bad))
    _row(f"A3b. 경계 접촉 (중첩 ≤{OVERLAP_TOLERANCE_MS:g}ms, 반올림 오차)",
         f"{conf_edge}쌍", "참고")
    _row("A4. 화음 내 손가락 중복",
         f"{dup_bad}건 (화음 {dup_chords}개)", _verdict(dup_bad))
    _row("A5. 미배정 (finger == 0)",
         f"{un_bad} / {len(notes)} ({_pc(un_bad, len(notes))})", _verdict(un_bad))
    _row(f"A6. ROM 초과 |yaw|>{yaw_max:g}°",
         f"{yaw_bad} / {len(notes)} ({_pc(yaw_bad, len(notes))})", _verdict(yaw_bad))
    _row(f"A6. ROM 초과 |roll|>{roll_max:g}°",
         f"{roll_bad} / {len(notes)} ({_pc(roll_bad, len(notes))})", _verdict(roll_bad))
    print(LINE)
    _row("[A] 하드 제약 위반 합계", f"{hard_total}건", _verdict(hard_total))
    print()

    for title, ex in (("A1", span_ex), ("A1b", span2_ex), ("A2", mono_ex),
                      ("A3", conf_ex), ("A4", dup_ex), ("A5", un_ex), ("A6", rom_ex)):
        if ex:
            print(f"  [{title}] 위반 예시 (최대 3건)")
            for e in ex:
                print(f"    · {e}")
    if any((span_ex, span2_ex, mono_ex, conf_ex, dup_ex, un_ex, rom_ex)):
        print()

    # ---- [B] 분포·품질 --------------------------------------
    counts, pct, max_dev, tvd, assigned = finger_distribution(notes)
    cs = chord_statistics(chords)
    repeats, run_trans = single_note_runs(chords)
    arp_bad, arp_trans, arp_ex = arpeggio_mismatch(chords)
    hs = hand_separation(chords)
    bk = black_key_thumb_pinky(notes)
    roles = role_preference(notes)

    print("[B] 분포·품질 지표 — 참고값 (절대 합격 기준 없음)")
    _row("지표", "값", "비고")
    print(LINE)
    for f in range(1, 6):
        _row(f"B7. 손가락 {f}번 사용률",
             f"{pct[f]:.1f}% ({counts.get(f, 0)}개)",
             f"{pct[f] - 20.0:+5.1f}pp")
    _row("B7. 균등분포 대비 최대 편차", f"{max_dev:.1f}pp", "낮을수록 균형")
    _row("B7. 총변동거리(TVD, 0~0.8)", f"{tvd:.3f}", "0=완전균등")
    _row("B8. 화음 수", f"{cs['chords']}개", "")
    _row("B8. 평균 span (전체 화음)", f"{cs['avg_span_all']:.2f}반음", "")
    _row("B8. 평균 span (2음 이상 화음)", f"{cs['avg_span_multi']:.2f}반음", "")
    _row("B8. 최대 span", f"{cs['max_span']}반음",
         "참고" if cs["max_span"] <= 17 else "17반음 초과")
    _row("B8. span > 17반음 화음 수", f"{cs['over17']}개", _verdict(cs["over17"]))
    _row("B8. 최대 동시 발음 수", f"{cs['max_poly']}음",
         "참고" if cs["max_poly"] <= 5 else "5음 초과")
    _row("B8. 단음 화음 비율", f"{cs['single_ratio']:.1f}%", "")
    _row("B9. 단음 연속 같은 손가락 반복",
         f"{repeats} / {run_trans}회 ({_pc(repeats, run_trans)})", "낮을수록 양호")
    _row("B10. 아르페지오 방향성 불일치",
         f"{arp_bad} / {arp_trans}회 ({_pc(arp_bad, arp_trans)})", "낮을수록 양호")
    _row("B11. 왼손 음역", f"{_rng(hs['left_range'])}", "")
    _row("B11. 오른손 음역", f"{_rng(hs['right_range'])}", "")
    _row("B11. 좌우 음역 중첩 폭", f"{hs['overlap']}반음", "0=완전 분리")
    _row("B11. 손 교차 발생 (동시 화음쌍)",
         f"{hs['cross']} / {hs['pairs']}쌍 ({_pc(hs['cross'], hs['pairs'])})", "참고")
    _row("B12. 흑건 음표 비율", f"{bk['black_ratio']:.1f}% ({bk['black']}개)", "")
    _row("B12. 흑건에 1번 손가락", f"{bk['f1_pct']:.1f}% ({bk['f1']}개)", "낮을수록 양호")
    _row("B12. 흑건에 5번 손가락", f"{bk['f5_pct']:.1f}% ({bk['f5']}개)", "낮을수록 양호")
    _row("B12. 흑건에 1·5번 합계", f"{bk['both_pct']:.1f}%", "참고")
    for (role, hand), st in sorted(roles.items()):
        pref = "".join(str(f) for f in sorted(st["pref"]))
        _row(f"B13. {role}/{hand} 선호({pref}번) 실현율",
             f"{st['pref_pct']:.1f}% (n={st['n']})",
             (f"기피 {st['avoid_pct']:.1f}%" if st["avoid_pct"] is not None else ""))
    print(LINE)
    print()

    if arp_ex:
        print("  [B10] 불일치 예시 (최대 3건)")
        for e in arp_ex:
            print(f"    · {e}")
    if hs["examples"]:
        print("  [B11] 교차 예시 (최대 3건)")
        for e in hs["examples"]:
            print(f"    · {e}")
    if arp_ex or hs["examples"]:
        print()

    print("  ※ 실제 피아니스트와의 운지 일치율은 기준(정답) 운지 데이터셋이 없어")
    print("    본 도구로 측정할 수 없음. 01_Design/10_Fingering_Metrics_Definition.md 참조.")
    print()
    return hard_total


def _pc(part, whole):
    return f"{part / whole * 100:.2f}%" if whole else "n/a"


def _verdict(count):
    return "PASS" if count == 0 else "FAIL"


def _rng(rng):
    return f"p{rng[0]}~p{rng[1]} ({rng[1] - rng[0]}반음)" if rng else "없음"


USAGE = """사용법: python tools/metrics.py [result.json ...]

  인자 없음 : results/*_polyphonic_result.json 전체 순회
  종료 코드 : 0=하드 제약 위반 없음, 1=위반 있음, 2=측정 실패

  Windows cp949 콘솔에서는 PYTHONIOENCODING=utf-8 을 지정할 것.
  지표 정의: 01_Design/10_Fingering_Metrics_Definition.md"""


def main(argv):
    if any(a in ("-h", "--help") for a in argv):
        print(USAGE)
        return 0
    args = [a for a in argv if not a.startswith("-")]
    if args:
        targets = args
    else:
        targets = sorted(glob.glob(os.path.join(RESULTS_DIR, "*_polyphonic_result.json")))
        if not targets:
            print(f"평가 대상 JSON이 없음: {RESULTS_DIR}/*_polyphonic_result.json")
            return 2

    results = []
    for path in targets:
        if not os.path.isfile(path):
            print(f"파일을 찾을 수 없음: {path}")
            results.append((os.path.basename(path), None))
            continue
        try:
            results.append((os.path.basename(path), evaluate(path)))
        except Exception as exc:
            print(f"{os.path.basename(path)}: 평가 실패 {type(exc).__name__}: {exc}")
            print()
            results.append((os.path.basename(path), None))

    if len(results) > 1:
        print("=" * (COL[0] + COL[1] + COL[2]))
        print(" 전체 요약 (하드 제약)")
        print("=" * (COL[0] + COL[1] + COL[2]))
        _row("파일", "하드 위반", "판정")
        print(LINE)
        for name, hard in results:
            if hard is None:
                _row(name, "-", "ERROR")
            else:
                _row(name, f"{hard}건", _verdict(hard))
        print(LINE)
        print()

    if any(h is None for _, h in results):
        return 2
    return 1 if any(h for _, h in results) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
