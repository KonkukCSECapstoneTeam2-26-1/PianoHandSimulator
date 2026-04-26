"""
V5 Polyphonic Hand Simulator — Piano + Skeletal Hand + Role Visualizer
성부(Role)와 손가락 뼈대를 실시간으로 시각화합니다. (연주자 시점)
"""
import json, sys, time, os, platform
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.animation as animation
import numpy as np
import pygame

# 폰트 설정
if platform.system() == 'Windows':
    matplotlib.rc('font', family='Malgun Gothic')
else:
    matplotlib.rc('font', family='AppleGothic')
matplotlib.rcParams['axes.unicode_minus'] = False

# ── 색상 및 상수 ──────────────────────────────────────────
ROLE_COLORS = {
    "MELODY": "#FF4B4B", # Red
    "BASS": "#4B89FF",   # Blue
    "INNER": "#FFD700"   # Gold
}
FINGER_COLORS = {1:'#E74C3C', 2:'#E67E22', 3:'#F1C40F', 4:'#2ECC71', 5:'#3498DB'}
WHITE_NOTES   = {0, 2, 4, 5, 7, 9, 11}
BLACK_NOTES   = {1, 3, 6, 8, 10}

# 피아노 치수 및 손 높이 (연주자 시점: 아래->위)
WK_H = 6.5
BK_H = 4.2
WRIST_Y   = -4.0   # 손목 (화면 아래쪽)
MCP_Y     = -1.0   # 손바닥 기저부
TIP_REST  = 0.5    # 안 누를 때 손끝 (건반 앞쪽 상단)
TIP_PRESSED = 2.0  # 누를 때 손끝 (건반 안쪽)
VIEW_BOTTOM = -6.0
VIEW_TOP  = WK_H + 2.0

# 손가락별 상대 X 오프셋 (손목 중심 기준)
R_DX = {1:-2.5, 2:-1.0, 3:0.0, 4:1.0, 5:2.2}
L_DX = {1: 2.5, 2: 1.0, 3:0.0, 4:-1.0, 5:-2.2}

FPS = 30
VISUAL_OFFSET_MS = 100

def load_v5_data():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.abspath(os.path.join(base_dir, "../../results/mario_polyphonic_result.json"))
    if not os.path.exists(path): return None
    with open(path, encoding='utf-8') as f: return json.load(f)

def compute_key_positions():
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
    return pos, white_x

# ── 손가락 및 손 클래스 ──────────────────────────
class HandVisualizer:
    def __init__(self, ax, is_right, key_pos):
        self.ax = ax
        self.is_right = is_right
        self.key_pos = key_pos
        self.dx = R_DX if is_right else L_DX
        
        # 시각화 요소 (Line, Scatter)
        self.finger_lines = []
        for i in range(5):
            line, = ax.plot([], [], color='#ddd', lw=2.5, solid_capstyle='round', zorder=10)
            self.finger_lines.append(line)
        self.palm_line, = ax.plot([], [], color='#bbb', lw=3, zorder=9)
        self.joint_pts = ax.scatter([], [], s=25, c='white', edgecolors='black', zorder=11)

    def update(self, active_notes):
        if active_notes:
            avg_x = sum(self.key_pos[n['pitch']][1] for n in active_notes) / len(active_notes)
            wrist_x = avg_x 
        else:
            wrist_x = 25 if not self.is_right else 65
            
        wrist_pos = np.array([wrist_x, WRIST_Y])
        all_joints = [wrist_pos]
        
        palm_joints = []
        for f_idx in range(1, 6):
            target_note = next((n for n in active_notes if n['finger'] == f_idx), None)
            
            # MCP (손가락 뿌리)
            mcp_x = wrist_x + self.dx[f_idx]
            mcp_pos = np.array([mcp_x, MCP_Y])
            palm_joints.append(mcp_pos)
            
            # TIP (손가락 끝)
            if target_note:
                tip_x = self.key_pos[target_note['pitch']][1]
                tip_y = TIP_PRESSED
                role_color = ROLE_COLORS.get(target_note['role'], '#FFD700')
            else:
                tip_x = mcp_x
                tip_y = TIP_REST
                role_color = '#444'
                
            tip_pos = np.array([tip_x, tip_y])
            
            # 중간 마디 (아치형 굽힘)
            pip_pos = mcp_pos * 0.5 + tip_pos * 0.5
            pip_pos[1] -= 0.5 
            
            # 그리기
            line_data = np.array([wrist_pos, mcp_pos, pip_pos, tip_pos])
            self.finger_lines[f_idx-1].set_data(line_data[:,0], line_data[:,1])
            self.finger_lines[f_idx-1].set_color(role_color if target_note else '#333')
            
            all_joints.extend([mcp_pos, pip_pos, tip_pos])
            
        palm_data = np.array(palm_joints)
        self.palm_line.set_data(palm_data[:,0], palm_data[:,1])
        self.joint_pts.set_offsets(np.array(all_joints))
        
        return self.finger_lines + [self.palm_line, self.joint_pts]

# ── 메인 시뮬레이터 ──────────────────────────
class PianoSimulator:
    def __init__(self, data):
        self.data = data
        self.key_pos, self.num_white = compute_key_positions()
        
        self.fig = plt.figure(figsize=(16, 8))
        self.ax = plt.gca()
        self.ax.set_facecolor('#050505')
        
        self.rects = {}
        for p, (kt, cx) in self.key_pos.items():
            if kt == 'white':
                r = mpatches.Rectangle((cx-0.47, 0), 0.94, WK_H, facecolor='white', edgecolor='#222', zorder=1)
            else:
                r = mpatches.Rectangle((cx-0.3, WK_H-BK_H), 0.6, BK_H, facecolor='#111', edgecolor='black', zorder=3)
            self.ax.add_patch(r)
            self.rects[p] = r
            
        self.left_hand = HandVisualizer(self.ax, False, self.key_pos)
        self.right_hand = HandVisualizer(self.ax, True, self.key_pos)
            
        self.ax.set_xlim(0, self.num_white)
        self.ax.set_ylim(VIEW_BOTTOM, VIEW_TOP)
        self.ax.set_aspect('equal')
        plt.axis('off')
        plt.title("V5 Polyphonic Hand Simulator (Player Perspective)", color='white', fontsize=16)

        self.start_time = time.time()

    def update(self, frame):
        t_ms = (time.time() - self.start_time) * 1000 - VISUAL_OFFSET_MS
        active = [n for n in self.data if n['start_ms'] <= t_ms < n['start_ms'] + n['duration_ms']]
        
        l_active = [n for n in active if n['hand'] == 'Left']
        r_active = [n for n in active if n['hand'] == 'Right']
        active_pitches = {n['pitch']: n for n in active}

        for p, r in self.rects.items():
            if p in active_pitches:
                r.set_facecolor(ROLE_COLORS.get(active_pitches[p]['role'], '#FFD700'))
            else:
                r.set_facecolor('white' if (p%12) in WHITE_NOTES else '#111')
        
        h1 = self.left_hand.update(l_active)
        h2 = self.right_hand.update(r_active)
        
        return list(self.rects.values()) + h1 + h2

def main():
    data = load_v5_data()
    if not data: return
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    midi_path = os.path.abspath(os.path.join(base_dir, "../../assets/midi/Super Mario 64 - Medley.mid"))
    
    try:
        pygame.mixer.init()
        if os.path.exists(midi_path):
            pygame.mixer.music.load(midi_path)
            pygame.mixer.music.play()
            print(f"Playing Audio: {os.path.basename(midi_path)}")
    except Exception as e:
        print(f"Audio Error: {e}")

    sim = PianoSimulator(data)
    ani = animation.FuncAnimation(sim.fig, sim.update, interval=1000/FPS, blit=True, cache_frame_data=False)
    
    plt.tight_layout()
    print("V5 Simulator Running (Corrected Perspective)...")
    print("Red: Melody | Blue: Bass | Gold: Inner")
    plt.show()
    
    pygame.mixer.music.stop()

if __name__ == "__main__":
    main()
