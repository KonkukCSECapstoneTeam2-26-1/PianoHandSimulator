"""
PianoHandSimulator — Piano + Hand Visualizer
피아노 건반을 그리고, 현재 눌린 키를 색칠하며, 손 뼈대를 실시간으로 표시합니다.

사용법:
    python piano_player.py              # 처음부터 자동 재생
    python piano_player.py 120 150      # 120~150초 구간
키 조작:
    Space : 재생/일시정지
    ← →  : ±5초 이동
    Q/Esc : 종료
"""
import json, sys, time, platform
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
import numpy as np
import pygame

if platform.system() == 'Windows':
    matplotlib.rc('font', family='Malgun Gothic')
else:
    matplotlib.rc('font', family='AppleGothic')
matplotlib.rcParams['axes.unicode_minus'] = False

# ── 색상 ──────────────────────────────────────────
FINGER_COLORS = {1:'#E74C3C', 2:'#E67E22', 3:'#F1C40F', 4:'#2ECC71', 5:'#3498DB'}
WHITE_NOTES   = {0, 2, 4, 5, 7, 9, 11}   # C D E F G A B
BLACK_NOTES   = {1, 3, 6, 8, 10}

# ── 피아노 치수 (white key = 1 unit) ──────────────
WK_H = 6.5    # 흰 건반 높이
BK_H = 4.2    # 검은 건반 높이
BK_W = 0.62   # 검은 건반 너비

# ── 손 y 좌표 (높을수록 위) ───────────────────────
PIANO_TOP = WK_H          # 건반 윗면 = 손끝이 닿는 곳
TIP_REST  = WK_H + 1.2    # 누르지 않을 때 손끝 높이
DIP_Y     = WK_H + 3.0
PIP_Y     = WK_H + 5.0
MCP_Y     = WK_H + 7.0    # 손가락 기저부
PALM_Y    = WK_H + 8.5    # 손바닥 (MCP 모임점)
WRIST_Y   = WK_H + 11.0   # 손목
VIEW_TOP  = WK_H + 12.5   # 화면 상단

# ── 손가락 x 오프셋 (palm 기준, white key 단위) ──
# 오른손: 엄지(1)=왼쪽/낮은음, 새끼(5)=오른쪽/높은음
R_DX = {1:-2.8, 2:-1.3, 3:0.0, 4:1.3, 5:2.5}
# 왼손: 엄지(1)=오른쪽/높은음, 새끼(5)=왼쪽/낮은음
L_DX = {1: 2.8, 2: 1.3, 3:0.0, 4:-1.3, 5:-2.5}

FPS = 25
VISUAL_OFFSET_MS = 150   # 오디오 버퍼 레이턴시 보정 (양수 = 시각을 앞으로)
NOTE_MIN_DISPLAY_MS = 120  # 최소 노트 표시 시간 (ms)


# ─────────────────────────────────────────────────────────────
# 건반 x 위치 계산
# ─────────────────────────────────────────────────────────────
def compute_key_positions():
    """MIDI pitch → ('white'|'black', center_x) 반환"""
    white_x, white_pos, pos = 0, {}, {}
    for p in range(21, 109):
        if (p % 12) in WHITE_NOTES:
            white_pos[p] = white_x
            pos[p] = ('white', white_x + 0.5)
            white_x += 1
    for p in range(21, 109):
        if (p % 12) in BLACK_NOTES:
            lw = next((q for q in range(p-1, 20, -1) if (q%12) in WHITE_NOTES), None)
            rw = next((q for q in range(p+1, 109)    if (q%12) in WHITE_NOTES), None)
            lx = white_pos.get(lw, 0)
            rx = white_pos.get(rw, white_x)
            pos[p] = ('black', (lx + rx) / 2)
    return pos, white_x   # white_x = 총 흰 건반 수


def get_active(data, t_ms):
    """현재 시간에 눌려있는 노트 목록"""
    return [d for d in data
            if d['start_ms'] <= t_ms < d['start_ms'] + max(d['duration_ms'], NOTE_MIN_DISPLAY_MS)]


# ─────────────────────────────────────────────────────────────
# 피아노 건반
# ─────────────────────────────────────────────────────────────
class Piano:
    def __init__(self, ax, key_pos, num_white):
        self.key_pos = key_pos
        self.white_rects = {}   # pitch → Rectangle
        self.black_rects = {}
        self.labels = {}        # pitch → Text

        # 흰 건반 (정적 외곽선 + 동적 색상)
        for p, (kt, cx) in key_pos.items():
            if kt != 'white': continue
            r = mpatches.Rectangle(
                (cx - 0.47, 0.05), 0.94, WK_H - 0.1,
                facecolor='#eeeeee', edgecolor='#555', lw=0.6, zorder=2
            )
            ax.add_patch(r)
            self.white_rects[p] = r
            t = ax.text(cx, 0.45, '', ha='center', va='bottom',
                        fontsize=6.5, fontweight='bold', color='#111', zorder=6)
            self.labels[p] = t

        # 검은 건반
        for p, (kt, cx) in key_pos.items():
            if kt != 'black': continue
            r = mpatches.Rectangle(
                (cx - BK_W/2, WK_H - BK_H), BK_W, BK_H - 0.05,
                facecolor='#111111', edgecolor='#000', lw=0.5, zorder=4
            )
            ax.add_patch(r)
            self.black_rects[p] = r
            t = ax.text(cx, WK_H - BK_H + 0.15, '', ha='center', va='bottom',
                        fontsize=5.5, fontweight='bold', color='white', zorder=8)
            self.labels[p] = t

    def update(self, active_notes):
        am = {n['pitch']: n for n in active_notes}
        for p, r in self.white_rects.items():
            n = am.get(p)
            r.set_facecolor(FINGER_COLORS.get(n['finger'], '#fff') if n else '#eeeeee')
            r.set_alpha(0.9 if n else 1.0)
            self.labels[p].set_text(str(n['finger']) if n else '')
        for p, r in self.black_rects.items():
            n = am.get(p)
            r.set_facecolor(FINGER_COLORS.get(n['finger'], '#fff') if n else '#111111')
            self.labels[p].set_text(str(n['finger']) if n else '')


# ─────────────────────────────────────────────────────────────
# 손 뼈대
# ─────────────────────────────────────────────────────────────
class Hand:
    """손목 → 손바닥 → MCP → PIP → DIP → 손끝  (선으로 표현)"""

    def __init__(self, ax, hand_id, default_x, key_pos):
        self.hand_id   = hand_id
        self.default_x = default_x
        self.key_pos   = key_pos
        self.finger_dx = L_DX if hand_id == 0 else R_DX

        # 손목 점
        self._wrist = ax.plot([], [], 'o', color='#ddddee', ms=10, zorder=25)[0]
        # 손목 → 손바닥 라인
        self._arm = ax.plot([], [], '-', color='#9999bb', lw=2.5, zorder=22)[0]
        # 손바닥 → 각 MCP 라인
        self._metacarpal = {f: ax.plot([], [], '-', color='#5a5a77', lw=2, zorder=23)[0]
                            for f in range(1, 6)}
        # 각 손가락: 3 세그먼트 (MCP-PIP, PIP-DIP, DIP-TIP)
        self._segs = {f: [ax.plot([], [], '-', lw=2.8, zorder=24)[0] for _ in range(3)]
                      for f in range(1, 6)}
        # 관절 점 (MCP, PIP, DIP, TIP)
        self._dots = {f: [ax.plot([], [], 'o', ms=5, zorder=26)[0] for _ in range(4)]
                      for f in range(1, 6)}

        label = '왼손' if hand_id == 0 else '오른손'
        ax.text(default_x, VIEW_TOP - 0.25, label,
                ha='center', va='top', fontsize=9, color='#888899', zorder=30)

    def _calc_joints(self, mcp_x, tip_x, pressing):
        """MCP → PIP → DIP → TIP 좌표 계산 (간단한 선형 IK)"""
        mcp = np.array([mcp_x, MCP_Y])
        if pressing:
            tip = np.array([tip_x, PIANO_TOP + 0.15])
            pip = mcp + 0.42 * (tip - mcp) + np.array([0.0,  1.0])
            dip = mcp + 0.72 * (tip - mcp) + np.array([0.0,  0.45])
        else:
            # 휴식 상태: 살짝 구부러진 자세
            tip = np.array([mcp_x, TIP_REST])
            pip = np.array([mcp_x + 0.05, (MCP_Y + TIP_REST)*0.55 + 0.5])
            dip = np.array([mcp_x + 0.03, (MCP_Y + TIP_REST)*0.28 + 0.2])
        return mcp, pip, dip, tip

    def update(self, active_notes):
        # 활성 손가락 → 건반 x 위치
        fk = {}
        for n in active_notes:
            _, cx = self.key_pos[n['pitch']]
            fk[n['finger']] = cx

        # 손바닥 중심 x (활성 키 평균 또는 기본값)
        palm_x = sum(fk.values()) / len(fk) if fk else self.default_x

        # 손목 & 전완 라인
        self._wrist.set_data([palm_x], [WRIST_Y])
        self._arm.set_data([palm_x, palm_x], [WRIST_Y, PALM_Y])

        for f in range(1, 6):
            mcp_x   = palm_x + self.finger_dx[f]
            pressing = f in fk
            tip_x   = fk.get(f, mcp_x)
            color   = FINGER_COLORS[f] if pressing else '#7a7a99'
            lw      = 3.0 if pressing else 1.8

            # 손바닥 → MCP
            self._metacarpal[f].set_data([palm_x, mcp_x], [PALM_Y, MCP_Y])
            self._metacarpal[f].set_color('#aaaacc' if pressing else '#5a5a77')

            # 손가락 관절
            joints = self._calc_joints(mcp_x, tip_x, pressing)
            for i, seg in enumerate(self._segs[f]):
                p1, p2 = joints[i], joints[i+1]
                seg.set_data([p1[0], p2[0]], [p1[1], p2[1]])
                seg.set_color(color)
                seg.set_linewidth(lw)
            for i, dot in enumerate(self._dots[f]):
                dot.set_data([joints[i][0]], [joints[i][1]])
                dot.set_color(color)
                dot.set_markersize(5 if pressing else 3.5)

    def artists(self):
        a = [self._wrist, self._arm]
        for f in range(1, 6):
            a.append(self._metacarpal[f])
            a.extend(self._segs[f])
            a.extend(self._dots[f])
        return a


# ─────────────────────────────────────────────────────────────
# MIDI 재생 타이머
# ─────────────────────────────────────────────────────────────
class Player:
    def __init__(self, midi_path, total_s, t_start=0.0):
        self.total_s = total_s
        self.pos_s   = t_start
        self.playing = False
        self._wall = self._pref = None

        pygame.init()
        pygame.mixer.init()
        self._ok = False
        try:
            pygame.mixer.music.load(midi_path)
            self._ok = True
        except Exception as e:
            print(f'[WARN] MIDI 로드 실패: {e}')

    def play(self):
        if self.playing: return
        self.playing = True
        self._pref = self.pos_s
        if self._ok:
            pygame.mixer.music.play(start=self.pos_s)
        else:
            # 오디오 없을 때 fallback: wall clock
            self._wall = time.time()

    def pause(self):
        if not self.playing: return
        self.pos_s = self.get_pos()
        self.playing = False
        if self._ok: pygame.mixer.music.pause()

    def toggle(self):
        self.pause() if self.playing else self.play()

    def seek(self, delta):
        was = self.playing
        if was: self.pause()
        self.pos_s = max(0, min(self.total_s, self.pos_s + delta))
        if was: self.play()

    def get_pos(self):
        if not self.playing:
            return self.pos_s
        if self._ok:
            # pygame.mixer.music.get_pos() → play() 호출 후 경과 ms
            # start= 오프셋을 더해야 실제 곡 위치가 됨
            midi_ms = pygame.mixer.music.get_pos()
            if midi_ms < 0:   # 재생 종료
                self.pause()
                return self.pos_s
            pos = self._pref + midi_ms / 1000.0
        else:
            pos = self._pref + time.time() - self._wall
        pos = min(pos, self.total_s)
        if pos >= self.total_s and self.playing:
            self.pause()
        return pos

    def stop(self):
        self.playing = False
        if self._ok: pygame.mixer.music.stop()
        pygame.quit()


# ─────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────
def main():
    with open('mario_rom_result.json', encoding='utf-8') as f:
        data = json.load(f)
    total_s = data[-1]['start_ms'] / 1000

    t_start = float(sys.argv[1]) if len(sys.argv) >= 2 else 0.0
    t_end   = float(sys.argv[2]) if len(sys.argv) >= 3 else total_s

    key_pos, num_white = compute_key_positions()
    player = Player('Super Mario 64 - Medley.mid', total_s, t_start)

    # ── Figure 구성 ──────────────────────────────────
    fig, ax = plt.subplots(figsize=(22, 8))
    fig.patch.set_facecolor('#0d0d1a')
    ax.set_facecolor('#0d0d1a')
    ax.set_xlim(-0.8, num_white + 0.8)
    ax.set_ylim(-0.3, VIEW_TOP)
    ax.axis('off')

    # 구분선 (건반 위)
    ax.axhline(PIANO_TOP, color='#2a2a3a', lw=1.0, zorder=1)

    # 피아노 + 손
    piano = Piano(ax, key_pos, num_white)
    lhand = Hand(ax, 0, num_white * 0.20, key_pos)
    rhand = Hand(ax, 1, num_white * 0.62, key_pos)

    # 손가락 색 범례
    for f, name in {1:'엄지', 2:'검지', 3:'중지', 4:'약지', 5:'새끼'}.items():
        ax.plot([], [], 's', color=FINGER_COLORS[f], ms=9, label=f'{f}번 {name}')
    ax.legend(loc='upper left', fontsize=8, framealpha=0.3,
              facecolor='#1a1a2e', labelcolor='white',
              bbox_to_anchor=(0.01, 0.99), borderpad=0.6)

    # 상태 표시
    def fmt(s):
        s = max(0, s); return f'{int(s)//60}:{s%60:04.1f}'

    status = ax.text(
        num_white / 2, VIEW_TOP - 0.15,
        '▶  0:00.0',
        ha='center', va='top', fontsize=11, color='white', zorder=50,
        bbox=dict(boxstyle='round,pad=0.4', fc='#1a1a2e', alpha=0.9, ec='#334')
    )
    # 디버그: 활성 노트 목록
    debug_text = ax.text(
        0.5, VIEW_TOP - 0.15, '',
        ha='left', va='top', fontsize=7.5, color='#aaffaa', zorder=50,
        family='monospace'
    )
    ax.text(num_white / 2, -0.25,
            'Space: 재생/정지   ←→: ±5초   Q: 종료',
            ha='center', va='bottom', fontsize=8, color='#555566', zorder=50)

    # ── 애니메이션 ───────────────────────────────────
    def update(_):
        pos   = player.get_pos()
        t_ms  = pos * 1000 + VISUAL_OFFSET_MS   # 오디오 레이턴시 보정
        active = get_active(data, t_ms)

        piano.update(active)
        lhand.update([n for n in active if n['hand'] == 'Left'])
        rhand.update([n for n in active if n['hand'] == 'Right'])

        st = '▶' if player.playing else '■'
        status.set_text(f'{st}  {fmt(pos)} / {fmt(total_s)}')

        # 디버그 오버레이: 현재 활성 노트 표시
        lines = [f't={t_ms:.0f}ms  active={len(active)}']
        for n in sorted(active, key=lambda x: x['hand']+str(x['finger'])):
            lines.append(f"  {n['hand'][0]}  f{n['finger']}  p{n['pitch']}")
        debug_text.set_text('\n'.join(lines))
        return []

    def on_key(e):
        if e.key in (' ', 'space'):    player.toggle()
        elif e.key == 'right':         player.seek(+5)
        elif e.key == 'left':          player.seek(-5)
        elif e.key in ('q', 'escape'): player.stop(); plt.close('all')

    fig.canvas.mpl_connect('key_press_event', on_key)
    fig.suptitle('PianoHandSimulator — Super Mario 64 Medley',
                 color='white', fontsize=13, fontweight='bold', y=0.99)

    player.play()  # 자동 재생

    ani = animation.FuncAnimation(
        fig, update,
        interval=1000 // FPS,
        blit=False,
        cache_frame_data=False
    )

    plt.tight_layout(pad=0.3)
    plt.show()
    player.stop()


if __name__ == '__main__':
    main()
