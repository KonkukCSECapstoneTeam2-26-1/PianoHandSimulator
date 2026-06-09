"""
PianoHandSimulator Visualizer
mario_rom_result.json 데이터를 4패널로 시각화합니다.

사용법:
    python visualizer.py              # 전체 구간
    python visualizer.py 0 30        # 0~30초 구간
    python visualizer.py 140 160     # 140~160초 구간
"""
import json
import sys
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import numpy as np
from collections import Counter

# Windows 한글 폰트 설정
import platform
if platform.system() == 'Windows':
    matplotlib.rc('font', family='Malgun Gothic')
else:
    matplotlib.rc('font', family='AppleGothic')
matplotlib.rcParams['axes.unicode_minus'] = False

# --- 손가락별 색상 ---
FINGER_COLORS = {
    1: '#E74C3C',  # 엄지   - 빨강
    2: '#E67E22',  # 검지   - 주황
    3: '#F1C40F',  # 중지   - 노랑
    4: '#2ECC71',  # 약지   - 초록
    5: '#3498DB',  # 새끼   - 파랑
}
FINGER_NAMES = {1: '엄지', 2: '검지', 3: '중지', 4: '약지', 5: '새끼'}

BLACK_KEYS = {1, 3, 6, 8, 10}


def load_data(path="mario_rom_result.json"):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def filter_time(data, t_start_s, t_end_s):
    return [d for d in data if t_start_s * 1000 <= d['start_ms'] < t_end_s * 1000]


def draw_piano_roll(ax, notes, t_start_s, t_end_s, title):
    """피아노롤: 시간(x) × pitch(y), 색=손가락번호"""
    # 건반 배경 (흑건 줄)
    for pitch in range(21, 109):
        if (pitch % 12) in BLACK_KEYS:
            ax.axhspan(pitch - 0.5, pitch + 0.5, color='#f0f0f0', zorder=0)

    min_dur_s = 0.03  # 최소 표시 길이
    for n in notes:
        x = n['start_ms'] / 1000
        w = max(n['duration_ms'] / 1000, min_dur_s)
        y = n['pitch']
        color = FINGER_COLORS.get(n['finger'], '#aaaaaa')
        edge = 'black' if n['hand'] == 'Left' else 'none'
        lw = 0.5 if n['hand'] == 'Left' else 0
        rect = mpatches.FancyBboxPatch(
            (x, y - 0.42), w, 0.84,
            boxstyle="round,pad=0.01",
            facecolor=color,
            edgecolor=edge,
            linewidth=lw,
            alpha=0.85,
            zorder=2
        )
        ax.add_patch(rect)

    ax.set_xlim(t_start_s, t_end_s)
    ax.set_ylim(20, 110)
    ax.set_ylabel('MIDI Pitch', fontsize=9)
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linewidth=0.5)

    # y축: 옥타브 기준선 + 음이름
    octave_pitches = [21, 33, 45, 57, 69, 81, 93, 105]  # A0, A1, ...
    for p in octave_pitches:
        ax.axhline(y=p, color='gray', alpha=0.4, linewidth=0.5)
    note_names = ['A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7']
    ax.set_yticks(octave_pitches)
    ax.set_yticklabels(note_names, fontsize=7)


def draw_finger_stats(ax_l, ax_r, data):
    """손가락 사용 빈도 막대 그래프"""
    for ax, hand, color_base in [(ax_l, 'Left', 0.6), (ax_r, 'Right', 0.9)]:
        counts = Counter(d['finger'] for d in data if d['hand'] == hand)
        fingers = list(range(1, 6))
        vals = [counts.get(f, 0) for f in fingers]
        colors = [FINGER_COLORS[f] for f in fingers]
        bars = ax.bar(fingers, vals, color=colors, edgecolor='white', linewidth=0.8)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    str(val), ha='center', va='bottom', fontsize=8)
        ax.set_xticks(fingers)
        ax.set_xticklabels([FINGER_NAMES[f] for f in fingers], fontsize=8)
        ax.set_title(f'{"왼손" if hand=="Left" else "오른손"} 손가락 사용 횟수', fontsize=10, fontweight='bold')
        ax.set_ylabel('노트 수', fontsize=9)
        ax.grid(axis='y', alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)


def draw_wrist(ax_yaw, ax_roll, data, t_start_s, t_end_s):
    """손목 Yaw/Roll 시계열"""
    for hand, color in [('Left', '#3498DB'), ('Right', '#E74C3C')]:
        hand_data = sorted(
            [(d['start_ms'] / 1000, d['wrist_yaw_deg'], d['wrist_roll_deg'])
             for d in data if d['hand'] == hand],
            key=lambda x: x[0]
        )
        if not hand_data:
            continue
        ts, yaws, rolls = zip(*hand_data)
        label = '왼손' if hand == 'Left' else '오른손'
        ax_yaw.plot(ts, yaws, color=color, alpha=0.7, linewidth=0.8, label=label)
        ax_roll.plot(ts, rolls, color=color, alpha=0.7, linewidth=0.8, label=label)

    for ax, limit, ylabel, title in [
        (ax_yaw, 35, 'Yaw (°)', '손목 Yaw 회전 (좌우)'),
        (ax_roll, 20, 'Roll (°)', '손목 Roll 회전 (기울기)'),
    ]:
        ax.axhline(y=limit, color='#E74C3C', linestyle='--', linewidth=0.8, alpha=0.6, label=f'ROM ±{limit}°')
        ax.axhline(y=-limit, color='#E74C3C', linestyle='--', linewidth=0.8, alpha=0.6)
        ax.axhline(y=0, color='gray', linewidth=0.5, alpha=0.4)
        ax.set_xlim(t_start_s, t_end_s)
        ax.set_ylim(-limit * 1.3, limit * 1.3)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    ax_roll.set_xlabel('시간 (초)', fontsize=9)


def main():
    # 시간 범위 파싱
    data_full = load_data()
    total_s = data_full[-1]['start_ms'] / 1000

    if len(sys.argv) == 3:
        t_start = float(sys.argv[1])
        t_end = float(sys.argv[2])
    else:
        t_start = 0.0
        t_end = total_s

    data = filter_time(data_full, t_start, t_end)
    if not data:
        print(f"해당 구간({t_start}~{t_end}s)에 노트가 없습니다.")
        return

    print(f"구간: {t_start:.1f}s ~ {t_end:.1f}s  |  노트 {len(data)}개")

    # --- 레이아웃 ---
    fig = plt.figure(figsize=(22, 16))
    fig.patch.set_facecolor('#fafafa')
    gs = gridspec.GridSpec(
        4, 2,
        height_ratios=[2.5, 2.5, 1.5, 1.5],
        hspace=0.55, wspace=0.35,
        left=0.06, right=0.97, top=0.93, bottom=0.06
    )

    ax_roll_r = fig.add_subplot(gs[0, :])   # 오른손 피아노롤 (전체 너비)
    ax_roll_l = fig.add_subplot(gs[1, :])   # 왼손 피아노롤
    ax_stat_l = fig.add_subplot(gs[2, 0])   # 왼손 통계
    ax_stat_r = fig.add_subplot(gs[2, 1])   # 오른손 통계
    ax_wrist_y = fig.add_subplot(gs[3, 0])  # 손목 Yaw
    ax_wrist_r = fig.add_subplot(gs[3, 1])  # 손목 Roll

    # 피아노롤
    right_notes = [d for d in data if d['hand'] == 'Right']
    left_notes  = [d for d in data if d['hand'] == 'Left']
    draw_piano_roll(ax_roll_r, right_notes, t_start, t_end,
                    f'오른손 피아노롤  ({len(right_notes)}개 노트)')
    draw_piano_roll(ax_roll_l, left_notes, t_start, t_end,
                    f'왼손 피아노롤  ({len(left_notes)}개 노트)')
    ax_roll_r.set_xticklabels([])
    ax_roll_l.set_xlabel('시간 (초)', fontsize=9)

    # 손가락 통계
    draw_finger_stats(ax_stat_l, ax_stat_r, data)

    # 손목
    draw_wrist(ax_wrist_y, ax_wrist_r, data_full, t_start, t_end)

    # 공통 범례 (손가락 색)
    finger_patches = [
        mpatches.Patch(color=FINGER_COLORS[i], label=f'{i}번 {FINGER_NAMES[i]}')
        for i in range(1, 6)
    ]
    hand_patches = [
        mpatches.Patch(facecolor='white', edgecolor='black', linewidth=1, label='왼손 (검은 테두리)'),
        mpatches.Patch(facecolor='white', edgecolor='none', label='오른손 (테두리 없음)'),
    ]
    fig.legend(
        handles=finger_patches + hand_patches,
        loc='upper center', ncol=7,
        fontsize=9, framealpha=0.9,
        bbox_to_anchor=(0.5, 0.985)
    )

    title_range = f'{t_start:.0f}s ~ {t_end:.0f}s' if t_end < total_s else '전체'
    fig.suptitle(
        f'PianoHandSimulator — Super Mario 64 Medley  [{title_range}]',
        fontsize=14, fontweight='bold', y=0.975
    )

    out_name = f'viz_{int(t_start)}_{int(t_end)}.png'
    plt.savefig(out_name, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()
    print(f"저장 완료: {out_name}")
    # 저장된 PNG를 기본 뷰어로 열기
    import os, subprocess
    abs_path = os.path.abspath(out_name)
    if platform.system() == 'Windows':
        os.startfile(abs_path)
    elif platform.system() == 'Darwin':
        subprocess.run(['open', abs_path])
    else:
        subprocess.run(['xdg-open', abs_path])


if __name__ == "__main__":
    main()
