"""
V6 Pipeline — 보고서용 이미지 생성기
results/ 의 JSON 데이터를 읽어 보고서 첨부용 PNG 이미지를 생성합니다.
GUI 없이 파일로 저장합니다.

생성 이미지:
  report_imgs/fig1_pipeline.png        — 전체 파이프라인 다이어그램
  report_imgs/fig2_finger_dist.png     — 손가락 사용 분포 (드뷔시 vs 마리오)
  report_imgs/fig3_piano_roll.png      — 피아노 롤 시각화 (드뷔시 첫 60초)
  report_imgs/fig4_wrist_yaw.png       — 손목 Yaw 분포
  report_imgs/fig5_role_dist.png       — 성부 역할 분포
"""
import os, json, glob
import matplotlib
matplotlib.use("Agg")   # GUI 없이 파일 저장
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import platform

if platform.system() == "Windows":
    plt.rcParams["font.family"] = "Malgun Gothic"
else:
    plt.rcParams["font.family"] = "AppleGothic"
plt.rcParams["axes.unicode_minus"] = False

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.abspath(os.path.join(BASE_DIR, "../results"))
OUT_DIR     = os.path.join(RESULTS_DIR, "report_imgs")
os.makedirs(OUT_DIR, exist_ok=True)

BLACK_KEY_PITCH = {1, 3, 6, 8, 10}
WHITE_KEY_PITCH = {0, 2, 4, 5, 7, 9, 11}


def load(name_pattern):
    paths = glob.glob(os.path.join(RESULTS_DIR, name_pattern))
    if not paths:
        return None, None
    p = paths[0]
    with open(p, encoding="utf-8") as f:
        return json.load(f), os.path.basename(p)


# ── Fig 1: 전체 파이프라인 다이어그램 ──────────────────────────────────
def fig1_pipeline():
    fig, ax = plt.subplots(figsize=(12, 5), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    ax.axis("off")

    boxes = [
        (0.05, "MIDI\n파일",          "#2C3E50"),
        (0.22, "01 Fingering\n운지법 DP",   "#1A5276"),
        (0.42, "results/\nJSON",       "#1D6A54"),
        (0.60, "02 IK\nJacobian IK",  "#6E2C00"),
        (0.78, "03 Skinning\nUE5 렌더링", "#4A235A"),
    ]
    for x, label, color in boxes:
        ax.add_patch(mpatches.FancyBboxPatch(
            (x, 0.25), 0.14, 0.5,
            boxstyle="round,pad=0.02",
            facecolor=color, edgecolor="#AAAAAA", linewidth=1.5,
            transform=ax.transAxes, clip_on=False))
        ax.text(x + 0.07, 0.50, label,
                ha="center", va="center", color="white",
                fontsize=10, fontweight="bold", transform=ax.transAxes)

    for x in [0.19, 0.38, 0.56, 0.74]:
        ax.annotate("", xy=(x + 0.03, 0.50), xytext=(x, 0.50),
                    xycoords="axes fraction", textcoords="axes fraction",
                    arrowprops=dict(arrowstyle="->", color="#FF4B4B", lw=2.0))

    labels = ["", "Interface A\nNoteEvent JSON", "→", "Interface B\nJoint Transform", ""]
    for i, (x, lbl) in enumerate([(0.19, "Interface A\nNoteEvent JSON"),
                                   (0.56, "Interface B\nJoint Transform")]):
        ax.text(x + 0.015, 0.82, lbl,
                ha="center", va="bottom", color="#FF4B4B",
                fontsize=8, transform=ax.transAxes)

    # UE5 CSV 화살표
    ax.annotate("", xy=(0.42 + 0.07, 0.10), xytext=(0.42 + 0.07, 0.25),
                xycoords="axes fraction", textcoords="axes fraction",
                arrowprops=dict(arrowstyle="->", color="#F39C12", lw=1.5))
    ax.text(0.42 + 0.07, 0.06, "UE5 DataTable\nCSV (v6)",
            ha="center", va="top", color="#F39C12",
            fontsize=8, transform=ax.transAxes)

    ax.text(0.5, 0.97, "PianoHandSimulator — 전체 파이프라인",
            ha="center", va="top", color="white",
            fontsize=13, fontweight="bold", transform=ax.transAxes)

    path = os.path.join(OUT_DIR, "fig1_pipeline.png")
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  저장: {path}")


# ── Fig 2: 손가락 사용 분포 비교 ──────────────────────────────────────
def fig2_finger_dist():
    debussy, _  = load("deb_clai_fingering.json")
    mario,   _  = load("Super Mario 64*_fingering.json")
    if not debussy or not mario:
        print("  [skip] fig2: 데이터 없음")
        return

    names   = ["1번\n(엄지)", "2번\n(검지)", "3번\n(중지)", "4번\n(약지)", "5번\n(새끼)"]
    colors  = ["#FF3E3E", "#FF9F43", "#F1C40F", "#2ECC71", "#3498DB"]
    x       = np.arange(5)
    width   = 0.35

    def pct(data):
        total = len(data)
        return [sum(1 for n in data if n["finger"] == f) / total * 100 for f in range(1, 6)]

    d_pct = pct(debussy)
    m_pct = pct(mario)

    fig, ax = plt.subplots(figsize=(10, 5), facecolor="#111")
    ax.set_facecolor("#1a1a1a")

    bars1 = ax.bar(x - width/2, d_pct, width, label="드뷔시 Clair de Lune",
                   color=[c + "CC" for c in colors], edgecolor="white", linewidth=0.5)
    bars2 = ax.bar(x + width/2, m_pct, width, label="Super Mario 64 Medley",
                   color=colors, edgecolor="white", linewidth=0.5, alpha=0.7)

    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}%", ha="center", va="bottom",
                color="white", fontsize=8)
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.3,
                f"{bar.get_height():.1f}%", ha="center", va="bottom",
                color="#aaa", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(names, color="white", fontsize=11)
    ax.set_ylabel("사용 비율 (%)", color="white")
    ax.set_title("손가락별 사용 분포 비교", color="white", fontsize=13, fontweight="bold")
    ax.tick_params(colors="white")
    ax.spines[:].set_color("#444")
    ax.yaxis.label.set_color("white")
    ax.legend(facecolor="#333", edgecolor="#555", labelcolor="white", fontsize=10)
    ax.set_ylim(0, max(max(d_pct), max(m_pct)) * 1.2)
    ax.grid(axis="y", color="#333", linewidth=0.5)

    path = os.path.join(OUT_DIR, "fig2_finger_dist.png")
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  저장: {path}")


# ── Fig 3: 피아노 롤 (드뷔시 첫 60초) ────────────────────────────────
def fig3_piano_roll():
    data, _ = load("deb_clai_fingering.json")
    if not data:
        print("  [skip] fig3: 데이터 없음")
        return

    ROLE_COLORS = {"MELODY": "#FF4B4B", "BASS": "#4B89FF", "INNER": "#FFD700"}
    FINGER_COLORS = {1:"#FF3E3E", 2:"#FF9F43", 3:"#F1C40F", 4:"#2ECC71", 5:"#3498DB"}

    clip = [n for n in data if n["start_ms"] < 60000]

    fig, axes = plt.subplots(2, 1, figsize=(14, 7), facecolor="#0d0d0d",
                              gridspec_kw={"height_ratios": [1, 1], "hspace": 0.35})

    for ax, color_key, title in zip(
            axes,
            ["role", "finger"],
            ["성부(Role) 기반 피아노 롤 — 드뷔시 Clair de Lune (첫 60초)",
             "손가락(Finger) 기반 피아노 롤 — 드뷔시 Clair de Lune (첫 60초)"]):
        ax.set_facecolor("#111")
        for n in clip:
            if color_key == "role":
                c = ROLE_COLORS.get(n["role"], "#fff")
            else:
                c = FINGER_COLORS.get(n["finger"], "#fff")
            alpha = 0.85 if n["is_black"] else 0.6
            ax.add_patch(mpatches.Rectangle(
                (n["start_ms"] / 1000, n["pitch"] - 0.45),
                max(n["duration_ms"] / 1000, 0.05), 0.9,
                facecolor=c, edgecolor="none", alpha=alpha))
        ax.set_xlim(0, 60)
        ax.set_ylim(38, 90)
        ax.set_xlabel("시간 (초)", color="white", fontsize=9)
        ax.set_ylabel("MIDI Pitch", color="white", fontsize=9)
        ax.set_title(title, color="white", fontsize=10, fontweight="bold")
        ax.tick_params(colors="white", labelsize=8)
        ax.spines[:].set_color("#444")

        if color_key == "role":
            legend_handles = [mpatches.Patch(color=v, label=k) for k, v in ROLE_COLORS.items()]
        else:
            legend_handles = [mpatches.Patch(color=v, label=f"{k}번 손가락")
                              for k, v in FINGER_COLORS.items()]
        ax.legend(handles=legend_handles, facecolor="#222", edgecolor="#555",
                  labelcolor="white", fontsize=8, loc="upper right", ncol=3)

    path = os.path.join(OUT_DIR, "fig3_piano_roll.png")
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  저장: {path}")


# ── Fig 4: 손목 Yaw 분포 ──────────────────────────────────────────────
def fig4_wrist_yaw():
    debussy, _ = load("deb_clai_fingering.json")
    mario,   _ = load("Super Mario 64*_fingering.json")
    if not debussy or not mario:
        print("  [skip] fig4: 데이터 없음")
        return

    fig, axes = plt.subplots(1, 2, figsize=(12, 4), facecolor="#111")
    datasets = [(debussy, "드뷔시 Clair de Lune"), (mario, "Super Mario 64 Medley")]
    colors   = ["#4B89FF", "#FF4B4B"]

    for ax, (data, title), color in zip(axes, datasets, colors):
        ax.set_facecolor("#1a1a1a")
        yaws_r = [n["wrist_yaw_deg"] for n in data if n["hand"] == "Right"]
        yaws_l = [n["wrist_yaw_deg"] for n in data if n["hand"] == "Left"]
        bins = np.linspace(-36, 36, 25)
        ax.hist(yaws_r, bins=bins, color="#FF4B4B", alpha=0.7, label="오른손", edgecolor="none")
        ax.hist(yaws_l, bins=bins, color="#4B89FF", alpha=0.7, label="왼손",  edgecolor="none")
        ax.axvline(0, color="white", lw=1, linestyle="--", alpha=0.5)
        ax.set_title(title, color="white", fontsize=11, fontweight="bold")
        ax.set_xlabel("손목 Yaw 각도 (°)", color="white", fontsize=9)
        ax.set_ylabel("빈도", color="white", fontsize=9)
        ax.tick_params(colors="white", labelsize=8)
        ax.spines[:].set_color("#444")
        ax.legend(facecolor="#333", edgecolor="#555", labelcolor="white", fontsize=9)
        ax.grid(color="#333", linewidth=0.5, alpha=0.5)

    fig.suptitle("손목 Yaw 각도 분포 (±35° ROM 내)", color="white",
                 fontsize=12, fontweight="bold")
    path = os.path.join(OUT_DIR, "fig4_wrist_yaw.png")
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  저장: {path}")


# ── Fig 5: 성부 역할 분포 파이차트 ────────────────────────────────────
def fig5_role_dist():
    debussy, _ = load("deb_clai_fingering.json")
    mario,   _ = load("Super Mario 64*_fingering.json")
    if not debussy or not mario:
        print("  [skip] fig5: 데이터 없음")
        return

    ROLE_COLORS = {"MELODY": "#FF4B4B", "BASS": "#4B89FF", "INNER": "#FFD700"}

    fig, axes = plt.subplots(1, 2, figsize=(10, 4), facecolor="#111")
    for ax, data, title in zip(axes,
                                [debussy, mario],
                                ["드뷔시 Clair de Lune", "Super Mario 64 Medley"]):
        ax.set_facecolor("#111")
        from collections import Counter
        cnt = Counter(n["role"] for n in data)
        roles  = list(ROLE_COLORS.keys())
        counts = [cnt.get(r, 0) for r in roles]
        colors = list(ROLE_COLORS.values())
        wedges, texts, autotexts = ax.pie(
            counts, labels=roles, colors=colors,
            autopct="%1.1f%%", startangle=90,
            textprops={"color": "white", "fontsize": 10},
            wedgeprops={"edgecolor": "#111", "linewidth": 2})
        for at in autotexts:
            at.set_fontsize(9)
        ax.set_title(title, color="white", fontsize=11, fontweight="bold", pad=12)

    fig.suptitle("성부(Role) 분포 비교", color="white", fontsize=13, fontweight="bold")
    path = os.path.join(OUT_DIR, "fig5_role_dist.png")
    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()
    print(f"  저장: {path}")


if __name__ == "__main__":
    print(f"\n[이미지 생성] 출력 위치: {OUT_DIR}\n")
    fig1_pipeline()
    fig2_finger_dist()
    fig3_piano_roll()
    fig4_wrist_yaw()
    fig5_role_dist()
    print(f"\n완료 — {OUT_DIR}")
