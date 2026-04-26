"""
PianoHandSimulator Interactive Player
MIDI를 재생하면서 피아노롤에 실시간 커서를 표시합니다.

사용법:
    python player.py                    # 전체 (처음부터)
    python player.py 120 150            # 120~150초 구간
    python player.py 120 150 mario.mid  # MIDI 파일 지정

키 조작:
    Space   : 재생 / 일시정지
    Q / Esc : 종료
    ← →     : 5초 앞뒤 이동
"""
import json
import sys
import time
import threading
import platform
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
import matplotlib.animation as animation

# 한글 폰트
if platform.system() == 'Windows':
    matplotlib.rc('font', family='Malgun Gothic')
else:
    matplotlib.rc('font', family='AppleGothic')
matplotlib.rcParams['axes.unicode_minus'] = False

import pygame

# --- 상수 ---
FINGER_COLORS = {
    1: '#E74C3C', 2: '#E67E22', 3: '#F1C40F',
    4: '#2ECC71', 5: '#3498DB',
}
FINGER_NAMES = {1: '엄지', 2: '검지', 3: '중지', 4: '약지', 5: '새끼'}
BLACK_KEYS = {1, 3, 6, 8, 10}
FPS = 30


def load_data(path="mario_rom_result.json"):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def draw_piano_roll_static(ax, notes, t_start, t_end, title):
    """정적 피아노롤 배경 (노트 직사각형)"""
    for pitch in range(21, 109):
        if (pitch % 12) in BLACK_KEYS:
            ax.axhspan(pitch - 0.5, pitch + 0.5, color='#f0f0f0', zorder=0)

    for n in notes:
        x = n['start_ms'] / 1000
        w = max(n['duration_ms'] / 1000, 0.03)
        color = FINGER_COLORS.get(n['finger'], '#aaa')
        edge = 'black' if n['hand'] == 'Left' else 'none'
        lw = 0.5 if n['hand'] == 'Left' else 0
        rect = mpatches.FancyBboxPatch(
            (x, n['pitch'] - 0.42), w, 0.84,
            boxstyle="round,pad=0.01",
            facecolor=color, edgecolor=edge, linewidth=lw,
            alpha=0.85, zorder=2
        )
        ax.add_patch(rect)

    octave_pitches = [21, 33, 45, 57, 69, 81, 93, 105]
    note_names     = ['A0','A1','A2','A3','A4','A5','A6','A7']
    for p in octave_pitches:
        ax.axhline(y=p, color='gray', alpha=0.3, linewidth=0.5)

    ax.set_xlim(t_start, t_end)
    ax.set_ylim(20, 110)
    ax.set_yticks(octave_pitches)
    ax.set_yticklabels(note_names, fontsize=8)
    ax.set_ylabel('Pitch', fontsize=9)
    ax.set_title(title, fontsize=10, fontweight='bold')
    ax.grid(axis='x', alpha=0.3, linewidth=0.5)


def draw_wrist_static(ax_yaw, ax_roll, data, t_start, t_end):
    for hand, color in [('Left', '#3498DB'), ('Right', '#E74C3C')]:
        hd = sorted(
            [(d['start_ms']/1000, d['wrist_yaw_deg'], d['wrist_roll_deg'])
             for d in data if d['hand'] == hand],
            key=lambda x: x[0]
        )
        if not hd: continue
        ts, yaws, rolls = zip(*hd)
        label = '왼손' if hand == 'Left' else '오른손'
        ax_yaw.plot(ts, yaws,  color=color, alpha=0.6, lw=0.8, label=label)
        ax_roll.plot(ts, rolls, color=color, alpha=0.6, lw=0.8, label=label)

    for ax, lim, ylabel, title in [
        (ax_yaw, 35, 'Yaw (°)',  '손목 Yaw'),
        (ax_roll, 20, 'Roll (°)', '손목 Roll'),
    ]:
        ax.axhline(y=lim,  color='#E74C3C', ls='--', lw=0.8, alpha=0.5)
        ax.axhline(y=-lim, color='#E74C3C', ls='--', lw=0.8, alpha=0.5)
        ax.axhline(y=0,    color='gray',    lw=0.5,  alpha=0.4)
        ax.set_xlim(t_start, t_end)
        ax.set_ylim(-lim*1.3, lim*1.3)
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=10, fontweight='bold')
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(alpha=0.3)
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

    ax_roll.set_xlabel('시간 (초)', fontsize=9)


class Player:
    def __init__(self, midi_path, data, t_start, t_end):
        self.midi_path = midi_path
        self.data = data
        self.t_start = t_start
        self.t_end   = t_end
        self.duration = t_end - t_start

        self.playing   = False
        self.pos_s     = t_start        # 현재 재생 위치 (초)
        self._wall_ref = None           # 마지막 play 시작 시 wall time
        self._play_ref = None           # 마지막 play 시작 시 pos_s

        # pygame MIDI 초기화
        pygame.init()
        pygame.mixer.init()
        self._midi_loaded = False
        try:
            pygame.mixer.music.load(midi_path)
            self._midi_loaded = True
        except Exception as e:
            print(f"[WARN] MIDI 로드 실패: {e}\n       소리 없이 커서만 작동합니다.")

    def play(self):
        if self.playing: return
        self.playing = True
        self._play_ref = self.pos_s
        if self._midi_loaded:
            start_offset = max(0.0, self.pos_s - self.t_start)
            pygame.mixer.music.play(start=start_offset)
        else:
            self._wall_ref = time.time()

    def pause(self):
        if not self.playing: return
        self.pos_s = self.get_pos()
        self.playing = False
        if self._midi_loaded:
            pygame.mixer.music.pause()

    def toggle(self):
        if self.playing: self.pause()
        else: self.play()

    def seek(self, delta_s):
        was_playing = self.playing
        if was_playing: self.pause()
        self.pos_s = max(self.t_start, min(self.t_end, self.pos_s + delta_s))
        if was_playing: self.play()

    def get_pos(self):
        if not self.playing:
            return self.pos_s
        if self._midi_loaded:
            midi_ms = pygame.mixer.music.get_pos()
            if midi_ms < 0:
                self.pause()
                return self.pos_s
            pos = self._play_ref + midi_ms / 1000.0
        else:
            pos = self._play_ref + time.time() - self._wall_ref
        pos = min(pos, self.t_end)
        if pos >= self.t_end and self.playing:
            self.pause()
        return pos

    def stop(self):
        self.playing = False
        if self._midi_loaded:
            pygame.mixer.music.stop()
        pygame.quit()


def build_figure(data, t_start, t_end):
    right_notes = [d for d in data if d['hand'] == 'Right']
    left_notes  = [d for d in data if d['hand'] == 'Left']

    fig = plt.figure(figsize=(20, 14))
    fig.patch.set_facecolor('#fafafa')
    gs = gridspec.GridSpec(
        4, 1, height_ratios=[2.5, 2.5, 1.2, 1.2],
        hspace=0.5, left=0.07, right=0.97, top=0.92, bottom=0.06
    )
    ax_r   = fig.add_subplot(gs[0])
    ax_l   = fig.add_subplot(gs[1])
    ax_yaw = fig.add_subplot(gs[2])
    ax_rol = fig.add_subplot(gs[3])

    draw_piano_roll_static(ax_r, right_notes, t_start, t_end,
                           f'오른손 피아노롤  ({len(right_notes)}개)')
    draw_piano_roll_static(ax_l, left_notes,  t_start, t_end,
                           f'왼손 피아노롤  ({len(left_notes)}개)')
    ax_r.set_xticklabels([])
    ax_l.set_xlabel('')

    draw_wrist_static(ax_yaw, ax_rol, data, t_start, t_end)

    # 손가락 범례
    patches = [mpatches.Patch(color=FINGER_COLORS[i], label=f'{i}번 {FINGER_NAMES[i]}')
               for i in range(1, 6)]
    fig.legend(handles=patches, loc='upper center', ncol=5, fontsize=9,
               framealpha=0.9, bbox_to_anchor=(0.5, 0.985))

    title_range = f'{t_start:.0f}s ~ {t_end:.0f}s'
    fig.suptitle(
        f'PianoHandSimulator — Super Mario 64 Medley  [{title_range}]\n'
        f'Space: 재생/정지   ←→: ±5초   Q: 종료',
        fontsize=12, fontweight='bold', y=0.975
    )

    return fig, (ax_r, ax_l, ax_yaw, ax_rol)


def main():
    # 인자 파싱
    data_full = load_data()
    total_s   = data_full[-1]['start_ms'] / 1000
    midi_path = "Super Mario 64 - Medley.mid"

    if len(sys.argv) >= 3:
        t_start = float(sys.argv[1])
        t_end   = float(sys.argv[2])
    else:
        t_start = 0.0
        t_end   = total_s
    if len(sys.argv) >= 4:
        midi_path = sys.argv[3]

    data = [d for d in data_full if t_start * 1000 <= d['start_ms'] < t_end * 1000]
    if not data:
        print(f"해당 구간에 노트가 없습니다.")
        return

    print(f"구간: {t_start:.1f}s ~ {t_end:.1f}s  |  노트 {len(data)}개")
    print("Space: 재생/정지  |  ←→: ±5초  |  Q/Esc: 종료")

    player = Player(midi_path, data, t_start, t_end)
    fig, (ax_r, ax_l, ax_yaw, ax_rol) = build_figure(data, t_start, t_end)

    # 커서 라인 (4개 축 공용)
    cursor_lines = [
        ax.axvline(x=t_start, color='white', lw=1.5, alpha=0.85, zorder=10)
        for ax in (ax_r, ax_l, ax_yaw, ax_rol)
    ]
    # 상태 텍스트
    status_text = fig.text(
        0.5, 0.005, '■ 정지  |  0:00.0 / 0:00.0',
        ha='center', va='bottom', fontsize=10,
        bbox=dict(boxstyle='round', facecolor='#333', alpha=0.7),
        color='white'
    )

    def fmt_time(s):
        s = max(0, s)
        return f'{int(s)//60}:{s%60:04.1f}'

    def update(_frame):
        pos = player.get_pos()
        for line in cursor_lines:
            line.set_xdata([pos, pos])
        state = '▶ 재생' if player.playing else '■ 정지'
        status_text.set_text(
            f'{state}  |  {fmt_time(pos - t_start)} / {fmt_time(t_end - t_start)}'
            f'  (절대 {fmt_time(pos)})'
        )
        return cursor_lines + [status_text]

    def on_key(event):
        if event.key in (' ', 'space'):
            player.toggle()
        elif event.key == 'right':
            player.seek(+5)
        elif event.key == 'left':
            player.seek(-5)
        elif event.key in ('q', 'escape'):
            player.stop()
            plt.close('all')

    fig.canvas.mpl_connect('key_press_event', on_key)

    ani = animation.FuncAnimation(
        fig, update,
        interval=1000 // FPS,
        blit=True,
        cache_frame_data=False
    )

    plt.show()
    player.stop()


if __name__ == '__main__':
    main()
