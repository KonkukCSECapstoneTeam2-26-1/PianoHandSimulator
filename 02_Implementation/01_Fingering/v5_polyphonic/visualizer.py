import json
import os
import sys
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# 엔진 출력 파일명은 입력 MIDI 이름을 따른다 (예: "<곡명>_polyphonic_result.json")
DEFAULT_RESULT = "Super Mario 64 - Medley_polyphonic_result.json"

def load_data(path=None):
    # 인자가 없으면 스크립트 위치 기준 기본 결과 파일을 사용
    if path is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.abspath(os.path.join(base_dir, "../results", DEFAULT_RESULT))

    if not os.path.exists(path):
        print(f"Error: Result file not found at {path}")
        return None

    with open(path, encoding='utf-8') as f:
        return json.load(f)

def visualize_fingering_with_roles(data, start_ms, end_ms, output_name="viz_polyphonic.png"):
    if not data: return
    
    # 시간 범위 필터링
    subset = [n for n in data if start_ms <= n['start_ms'] <= end_ms]
    if not subset:
        print("No data in the given time range.")
        return

    plt.figure(figsize=(15, 8))
    ax = plt.gca()

    # 성부별 색상 설정
    ROLE_COLORS = {
        "MELODY": "#FF4B4B", # Red
        "BASS": "#4B89FF",   # Blue
        "INNER": "#888888"   # Gray
    }

    for n in subset:
        color = ROLE_COLORS.get(n.get('role', 'INNER'), '#888888')
        
        # 건반 위치 (Pitch)
        # 88건반 범위 (21~108)
        rect = patches.Rectangle(
            (n['start_ms'], n['pitch']), 
            n['duration_ms'] * 0.8, 0.8, 
            linewidth=1, edgecolor='black', facecolor=color, alpha=0.7
        )
        ax.add_patch(rect)
        
        # 손가락 번호 텍스트
        plt.text(
            n['start_ms'], n['pitch'] + 0.5, 
            str(n['finger']), 
            fontsize=9, fontweight='bold', color='white' if n['role'] != 'INNER' else 'black'
        )

    plt.xlim(start_ms, end_ms)
    plt.ylim(21, 108)
    plt.title(f"Piano Fingering Visualization (V5 Polyphonic)\nRange: {start_ms}ms - {end_ms}ms\nRed: Melody | Blue: Bass | Gray: Inner", fontsize=14)
    plt.xlabel("Time (ms)")
    plt.ylabel("MIDI Pitch")
    plt.grid(True, which='both', linestyle='--', alpha=0.5)

    # 저장 경로 설정
    base_dir = os.path.dirname(os.path.abspath(__file__))
    img_dir = os.path.abspath(os.path.join(base_dir, "../../assets/images"))
    if not os.path.exists(img_dir): os.makedirs(img_dir)
    
    save_path = os.path.join(img_dir, output_name)
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"Visualization saved to: {save_path}")

def main():
    # 사용법: python visualizer.py [결과JSON경로]
    data = load_data(sys.argv[1] if len(sys.argv) > 1 else None)
    if data:
        # 곡의 앞부분(0~10초) 시각화
        visualize_fingering_with_roles(data, 0, 10000, "mario_v5_0_10s.png")
        # 특정 하이라이트 구간 시각화
        visualize_fingering_with_roles(data, 30000, 40000, "mario_v5_30_40s.png")

if __name__ == "__main__":
    main()
