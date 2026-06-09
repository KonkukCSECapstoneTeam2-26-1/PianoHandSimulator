"""
V5 Polyphonic Hand Simulator — Pure MIDI Sync Version
- MIDI 파일 사용 필수 조건 준수
- 슬라이더 조작 시 화면 위치 고정 (오디오 튕김 영향 차단)
- 2중 오디오 탐색 로직 (play start + set_pos)
"""
import sys, time, os, platform, json
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
from matplotlib.widgets import Slider
import numpy as np
import pygame
import pygame.midi

# 폰트 설정
if platform.system() == 'Windows': plt.rcParams['font.family'] = 'Malgun Gothic'
else: plt.rcParams['font.family'] = 'AppleGothic'

# --- 설정 ---
ROLE_COLORS = {"MELODY": "#FF4B4B", "BASS": "#4B89FF", "INNER": "#FFD700"}
FINGER_COLORS = {
    1: "#FF3E3E", # 1번: 빨강 (Thumb)
    2: "#FF9F43", # 2번: 주황 (Index)
    3: "#F1C40F", # 3번: 노랑 (Middle)
    4: "#2ECC71", # 4번: 초록 (Ring)
    5: "#3498DB"  # 5번: 파랑 (Pinky)
}
WHITE_NOTES = {0, 2, 4, 5, 7, 9, 11}; BLACK_NOTES = {1, 3, 6, 8, 10}
WK_H, BK_H = 6.5, 4.2
WRIST_Y, MCP_Y, TIP_REST, TIP_PRESSED = -4.0, -1.0, 0.5, 2.0
VIEW_BOTTOM, VIEW_TOP = -6.5, WK_H + 2.0
R_DX = {1:-2.5, 2:-1.0, 3:0.0, 4:1.0, 5:2.2}
L_DX = {1: 2.5, 2: 1.0, 3:0.0, 4:-1.0, 5:-2.2}
FPS = 30

def load_v5_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(base_dir, "../results/mario_polyphonic_result.json"))
    if not os.path.exists(path): return None
    with open(path, encoding='utf-8') as f: return json.load(f)

def compute_key_positions():
    white_x, pos, white_pos = 0, {}, {}
    for p in range(21, 109):
        if (p % 12) in WHITE_NOTES:
            white_pos[p] = white_x; pos[p] = ('white', white_x + 0.5); white_x += 1
    for p in range(21, 109):
        if (p % 12) in BLACK_NOTES:
            lw = next((q for q in range(p-1, 20, -1) if (q%12) in WHITE_NOTES), None)
            rw = next((q for q in range(p+1, 109)    if (q%12) in WHITE_NOTES), None)
            lx = white_pos.get(lw, 0); rx = white_pos.get(rw, white_x)
            pos[p] = ('black', (lx + rx) / 2)
    return pos, white_x

class HandVisualizer:
    def __init__(self, ax, is_right, key_pos):
        self.ax, self.is_right, self.key_pos = ax, is_right, key_pos
        self.dx = R_DX if is_right else L_DX
        
        # 안쪽 마디 (Wrist -> MCP -> PIP) - 성부 색상용
        self.inner_lines = [ax.plot([], [], color='#333', lw=3.0, solid_capstyle='round', zorder=10)[0] for _ in range(5)]
        # 끝 마디 (PIP -> Tip) - 손가락 구분 색상용
        self.tip_lines = [ax.plot([], [], color='#555', lw=4.0, solid_capstyle='round', zorder=11)[0] for _ in range(5)]
        
        self.palm_line, = ax.plot([], [], color='#bbb', lw=3, zorder=9)
        self.joint_pts = ax.scatter([], [], s=25, c='white', edgecolors='black', zorder=12)

    def update(self, active_notes):
        wrist_x = sum(self.key_pos[n['pitch']][1] for n in active_notes)/len(active_notes) if active_notes else (25 if not self.is_right else 65)
        wrist_pos = np.array([wrist_x, WRIST_Y])
        all_joints, palm_joints = [wrist_pos], []
        
        for f_idx in range(1, 6):
            target = next((n for n in active_notes if n['finger'] == f_idx), None)
            mcp_pos = np.array([wrist_x + self.dx[f_idx], MCP_Y]); palm_joints.append(mcp_pos)
            
            # 건반 타점 및 관절 위치 계산
            tip_pos = np.array([self.key_pos[target['pitch']][1] if target else mcp_pos[0], TIP_PRESSED if target else TIP_REST])
            pip_pos = mcp_pos * 0.5 + tip_pos * 0.5; pip_pos[1] -= 0.5
            
            # 1. 안쪽 마디 업데이트 (Wrist -> MCP -> PIP)
            inner_data = np.array([wrist_pos, mcp_pos, pip_pos])
            self.inner_lines[f_idx-1].set_data(inner_data[:,0], inner_data[:,1])
            self.inner_lines[f_idx-1].set_color(ROLE_COLORS.get(target['role'], '#333') if target else '#222')
            self.inner_lines[f_idx-1].set_alpha(1.0 if target else 0.3)
            
            # 2. 끝 마디 업데이트 (PIP -> Tip)
            tip_data = np.array([pip_pos, tip_pos])
            self.tip_lines[f_idx-1].set_data(tip_data[:,0], tip_data[:,1])
            self.tip_lines[f_idx-1].set_color(FINGER_COLORS[f_idx] if target else '#444')
            self.tip_lines[f_idx-1].set_alpha(1.0 if target else 0.2)
            
            all_joints.extend([mcp_pos, pip_pos, tip_pos])
            
        if palm_joints: self.palm_line.set_data(np.array(palm_joints)[:,0], np.array(palm_joints)[:,1])
        self.joint_pts.set_offsets(np.array(all_joints))

class PianoSimulator:
    def __init__(self, data, midi_out):
        self.data = data
        self.midi_out = midi_out
        self.key_pos, self.num_white = compute_key_positions()
        self.total_ms = max(n['start_ms'] + n['duration_ms'] for n in data)
        
        self.fig = plt.figure(figsize=(16, 9), facecolor='#050505')
        gs = self.fig.add_gridspec(3, 1, height_ratios=[0.12, 0.78, 0.1], hspace=0.1)
        self.ax_ov, self.ax_main, self.ax_sld = self.fig.add_subplot(gs[0]), self.fig.add_subplot(gs[1]), self.fig.add_subplot(gs[2])
        
        self.setup_overview(); self.setup_main(); self.setup_slider()
        
        self.curr_ms = 0
        self.last_update_time = time.time()
        self.is_manual_seeking = False
        self.is_paused = False

        self.fig.canvas.mpl_connect('key_press_event', self.on_key)
        self.midi_out.set_instrument(0) # Grand Piano

    def setup_overview(self):
        self.ax_ov.set_facecolor('#111')
        for n in self.data[::15]:
            color = ROLE_COLORS.get(n['role'], '#FFD700')
            self.ax_ov.add_patch(mpatches.Rectangle((n['start_ms'], n['pitch']), n['duration_ms'], 1.2, facecolor=color, alpha=0.3))
        self.ax_ov.set_xlim(0, self.total_ms); self.ax_ov.set_ylim(21, 108); self.ax_ov.axis('off')
        self.ov_line = self.ax_ov.axvline(0, color='white', lw=2)

    def setup_main(self):
        self.ax_main.set_facecolor('#050505')
        self.rects = {}
        for p, (kt, cx) in self.key_pos.items():
            clr, z = ('white', 1) if kt == 'white' else ('#111', 3)
            w, h, y = (0.94, WK_H, 0) if kt == 'white' else (0.6, BK_H, WK_H-BK_H)
            r = mpatches.Rectangle((cx-w/2, y), w, h, facecolor=clr, edgecolor='#222', zorder=z)
            self.ax_main.add_patch(r); self.rects[p] = r
        self.left_hand = HandVisualizer(self.ax_main, False, self.key_pos)
        self.right_hand = HandVisualizer(self.ax_main, True, self.key_pos)
        self.ax_main.set_xlim(0, self.num_white); self.ax_main.set_ylim(VIEW_BOTTOM, VIEW_TOP); self.ax_main.axis('off')

    def setup_slider(self):
        self.slider = Slider(self.ax_sld, '', 0, self.total_ms, valinit=0, color='#FF4B4B')
        self.slider.on_changed(self.on_slider_change)
        self.ax_sld.set_facecolor('#050505')

    def on_key(self, event):
        if event.key == ' ':
            self.is_paused = not self.is_paused
            if self.is_paused: self.panic()
        elif event.key == 'right':
            self.seek(self.curr_ms + 5000)
        elif event.key == 'left':
            self.seek(self.curr_ms - 5000)

    def panic(self):
        """실행 중인 모든 MIDI 노트를 강제 종료"""
        for p in range(21, 109):
            self.midi_out.note_off(p, 0)

    def seek(self, target_ms):
        self.panic()
        self.curr_ms = max(0, min(self.total_ms, target_ms))
        self.last_update_time = time.time()

    def on_slider_change(self, val):
        if not self.is_manual_seeking:
            self.seek(val)

    def update(self, frame):
        if not self.is_paused:
            now = time.time()
            dt = (now - self.last_update_time) * 1000
            self.last_update_time = now
            
            prev_ms = self.curr_ms
            self.curr_ms += dt
            
            # [MIDI Dispatcher] 현재 프레임에서 연주되어야 할 노트들 전송
            for n in self.data:
                start = n['start_ms']
                end = start + n['duration_ms']
                
                # Note On: 이전 프레임과 현재 프레임 사이에 시작 시간이 걸쳐있는 경우
                if prev_ms < start <= self.curr_ms:
                    self.midi_out.note_on(n['pitch'], int(n['pressure'] * 127))
                
                # Note Off: 이전 프레임과 현재 프레임 사이에 종료 시간이 걸쳐있는 경우
                if prev_ms < end <= self.curr_ms:
                    self.midi_out.note_off(n['pitch'], 0)

        if self.curr_ms > self.total_ms: 
            self.seek(0)
        
        self.is_manual_seeking = True
        self.slider.set_val(self.curr_ms)
        self.is_manual_seeking = False
        
        self.ov_line.set_xdata([self.curr_ms, self.curr_ms])
        active = [n for n in self.data if n['start_ms'] <= self.curr_ms < n['start_ms'] + n['duration_ms']]
        active_pitches = {n['pitch']: n for n in active}
        
        for p, r in self.rects.items():
            if p in active_pitches: r.set_facecolor(ROLE_COLORS.get(active_pitches[p]['role'], '#FFD700'))
            else: r.set_facecolor('white' if (p%12) in WHITE_NOTES else '#111')
        
        self.left_hand.update([n for n in active if n['hand'] == 'Left'])
        self.right_hand.update([n for n in active if n['hand'] == 'Right'])
        return []

def main():
    try:
        data = load_v5_data()
        if not data: return
        
        pygame.init()
        pygame.midi.init()
        
        # 기본 출력 장치 설정
        out_id = pygame.midi.get_default_output_id()
        if out_id == -1:
            print("Error: No MIDI output device found.")
            return
            
        midi_out = pygame.midi.Output(out_id)
        
        sim = PianoSimulator(data, midi_out)
        ani = animation.FuncAnimation(sim.fig, sim.update, interval=1000/FPS, blit=False, cache_frame_data=False)
        plt.show()
        
        del midi_out
        pygame.midi.quit()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
