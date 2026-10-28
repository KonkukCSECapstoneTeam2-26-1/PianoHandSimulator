"""발표 슬라이드 7 · 26 에 들어갈 도식 2종.
기존 report_imgs 와 같은 다크 스타일로 그린다."""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = sys.argv[1]
BG = "#111111"
GOLD, RED, GREEN, BLUE = "#D9A441", "#D1544F", "#4FA87A", "#4E9AC7"
MUTED, LINE = "#9C9CA6", "#5E5E68"


def bar(ax, x0, x1, y, color, h=0.56, alpha=1.0, ec=None):
    ax.add_patch(mp.FancyBboxPatch(
        (x0, y - h / 2), x1 - x0, h,
        boxstyle="round,pad=0,rounding_size=0.08",
        facecolor=color, edgecolor=ec or color, linewidth=1.2, alpha=alpha, zorder=3))


# ─────────── 도식 1: 제약을 거는 단위 ───────────
# (시작, 끝, 행, 라벨, 속한 화음)
NOTES = [
    (0.30, 4.70, 5, "C4  지속음", 1),
    (0.30, 1.50, 4, "E4", 1),
    (0.30, 1.50, 3, "G4", 1),
    (1.80, 4.30, 4, "F4  지속음", 2),
    (1.80, 3.00, 2, "A4", 2),
    (3.30, 4.70, 3, "D4", 3),
    (3.30, 4.70, 1, "B3", 3),
]
CHORDS = [(0.30, "화음 1"), (1.80, "화음 2"), (3.30, "화음 3")]
T = 3.98


def _panel(ax, hit, title, title_color, caption, marker):
    ax.set_facecolor(BG)
    for cx, name in CHORDS:
        ax.vlines(cx, -0.70, 6.05, color=LINE, lw=1.0, ls=(0, (3, 3)), zorder=1)
        ax.text(cx + 0.06, 6.25, name, color=LINE, fontsize=10, va="center")
    for (st, en, r, lb, ch) in NOTES:
        on = hit(st, en, ch)
        col = GOLD if on else "#3A3A42"
        bar(ax, st, en, r, col, ec=GOLD if on else "#4A4A52")
        ax.text(st + 0.12, r, lb, fontsize=9.5, va="center", ha="left", zorder=4,
                fontweight="bold", color="#111111" if on else MUTED)
    if marker is not None:
        ax.vlines(marker, -0.70, 6.05, color=GOLD, lw=2.4, zorder=5)
    n = sum(1 for (st, en, r, lb, ch) in NOTES if hit(st, en, ch))
    ax.text(5.05, 6.25, f"검사 대상 {n}개", color=GOLD, fontsize=14,
            fontweight="bold", va="center", ha="right")
    ax.set_title(title, color=title_color, fontsize=14, fontweight="bold",
                 loc="left", pad=12)
    ax.text(0.30, -1.15, caption, color=MUTED, fontsize=10.5, va="top",
            ha="left", linespacing=1.65)
    ax.set_xlim(0, 5.25)
    ax.set_ylim(-2.75, 6.7)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.annotate("", xy=(5.20, -0.70), xytext=(0.20, -0.70),
                arrowprops=dict(arrowstyle="->", color=LINE, lw=1.2))
    ax.text(5.20, -0.56, "시간", color=LINE, fontsize=10, ha="right")


def fig_constraint_unit(path):
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), facecolor=BG,
                             gridspec_kw={"wspace": 0.09})
    _panel(axes[0], lambda st, en, ch: ch == 3,
           "1학기 — 화음 단위로 검사  (화음 3을 검사하는 중)", RED,
           "묶음에 속한 음만 본다. 앞 화음에서 넘어온 C4·F4 지속음은 이 검사에 들어오지 않는다.",
           None)
    _panel(axes[1], lambda st, en, ch: st <= T <= en,
           "2학기 — 시간 구간 겹침으로 검사  (순간 T)", GREEN,
           "음표마다 점유 시작·끝을 두고 그 순간에 눌려 있는 건반을 모은다. 지속음이 함께 잡힌다.\n"
           "같은 데이터에서 화음 단위 위반 3건 → 순간 단위 위반 2,552건. 지금은 0건.",
           T)
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("saved", path)


# ─────────── 도식 2: 손목 롤 값이 어디서 사라지는가 ───────────
# 수치는 results/*_polyphonic_result.json 21곡을 집계한 값이다.
ROLL_DIST = [("-12 deg", 2849), ("0 deg", 16497), ("+12 deg", 2566)]
TOTAL_NOTES = 21912


def fig_wrist_roll(path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.3), facecolor=BG,
                             gridspec_kw={"wspace": 0.34, "width_ratios": [1.3, 1]})

    # 왼쪽 — 운지법 엔진이 내보낸 값
    ax = axes[0]
    ax.set_facecolor(BG)
    labels = [l for l, _ in ROLL_DIST]
    vals = [v for _, v in ROLL_DIST]
    cols = [GOLD, "#3A3A42", GOLD]
    b = ax.bar(labels, vals, color=cols, edgecolor=[GOLD, "#4A4A52", GOLD],
               linewidth=1.2, width=0.62, zorder=3)
    for rect, v in zip(b, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, v + 420, f"{v:,}",
                ha="center", va="bottom", color="#FFFFFF", fontsize=12,
                fontweight="bold")
    ax.set_title("운지법 엔진이 내보낸  wrist_roll_deg", color=GOLD, fontsize=13.5,
                 fontweight="bold", loc="left", pad=14)
    ax.text(0, -0.235, f"21곡 {TOTAL_NOTES:,}음 중 0이 아닌 값 "
            f"{ROLL_DIST[0][1] + ROLL_DIST[2][1]:,}음 (24.7%)\n"
            "엄지 또는 소지가 흑건을 누르면 손 전체에 ±12°가 붙는다",
            transform=ax.transAxes, color=MUTED, fontsize=11,
            va="top", ha="left", linespacing=1.6)
    ax.set_ylim(0, 24800)
    ax.tick_params(colors=MUTED, labelsize=11)
    ax.grid(axis="y", color="#2A2A30", lw=0.8, zorder=0)
    ax.set_axisbelow(True)
    for k, sp in ax.spines.items():
        sp.set_visible(k == "bottom")
        if k == "bottom":
            sp.set_color(LINE)

    # 오른쪽 — IK가 기록한 값
    ax2 = axes[1]
    ax2.set_facecolor(BG)
    ax2.bar(["0 deg"], [TOTAL_NOTES], color="#3A3A42", edgecolor=RED,
            linewidth=1.4, width=0.38, zorder=3)
    ax2.text(0, TOTAL_NOTES + 420, "전량", ha="center", va="bottom",
             color=RED, fontsize=12, fontweight="bold")
    ax2.set_title("IK 가 기록한  wrist.csv 의 roll_deg", color=RED, fontsize=13.5,
                  fontweight="bold", loc="left", pad=14)
    ax2.text(0, -0.235,
             "IK 는 손목을 위치만 보간하고 회전은 다루지 않는다.\n"
             "인계 규격서에 \"yaw/pitch/roll 은 0으로 채운다\" 로 적혀 있다.",
             transform=ax2.transAxes, color=MUTED, fontsize=11,
             va="top", ha="left", linespacing=1.6)
    ax2.set_ylim(0, 24800)
    ax2.set_xlim(-0.75, 0.75)
    ax2.tick_params(colors=MUTED, labelsize=11)
    ax2.grid(axis="y", color="#2A2A30", lw=0.8, zorder=0)
    ax2.set_axisbelow(True)
    for k, sp in ax2.spines.items():
        sp.set_visible(k == "bottom")
        if k == "bottom":
            sp.set_color(LINE)

    # 가운데 화살표
    fig.text(0.532, 0.58, "→", color=GOLD, fontsize=30, ha="center", va="center")
    fig.text(0.532, 0.47, "값이 버려진다", color=GOLD, fontsize=11,
             ha="center", va="center", fontweight="bold")

    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("saved", path)


os.makedirs(OUT, exist_ok=True)
fig_constraint_unit(os.path.join(OUT, "diag_constraint_unit.png"))
fig_wrist_roll(os.path.join(OUT, "diag_wrist_roll.png"))
