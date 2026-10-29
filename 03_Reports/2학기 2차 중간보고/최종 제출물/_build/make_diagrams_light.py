"""발표 도식 2종 — 견본 덱의 밝은 세이지 팔레트에 맞춰 다시 그린다."""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp

import glob
import matplotlib.font_manager as fm
for _p in (glob.glob(os.path.expandvars(r"C:\Windows\Fonts\Pretendard*.otf"))
           + glob.glob(os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Windows\Fonts\Pretendard*.otf"))):
    try:
        fm.fontManager.addfont(_p)
    except Exception:
        pass
# Pretendard OTF 는 matplotlib 에서 한글 글리프가 깨져 Malgun Gothic 을 쓴다.
# 슬라이드 본문과 글꼴이 조금 다르지만 둘 다 같은 계열의 고딕이라 이질감은 작다.
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = sys.argv[1]
BG      = "#F7F3EF"
SAGE    = "#6A7E74"
SAGE_D  = "#466456"
SAGE_L  = "#BACCC3"
BEIGE   = "#E4DFD8"
BEIGE_D = "#CDC5B9"
INK     = "#222222"
INK2    = "#444444"


def bar(ax, x0, x1, y, face, edge, h=0.56):
    ax.add_patch(mp.FancyBboxPatch(
        (x0, y - h / 2), x1 - x0, h,
        boxstyle="round,pad=0,rounding_size=0.08",
        facecolor=face, edgecolor=edge, linewidth=1.1, zorder=3))


# ───────── 도식 1: 제약을 거는 단위 ─────────
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
        ax.vlines(cx, -0.70, 6.05, color=BEIGE_D, lw=1.0, ls=(0, (3, 3)), zorder=1)
        ax.text(cx + 0.07, 6.28, name, color=BEIGE_D, fontsize=10.5, va="center")
    for (st, en, r, lb, ch) in NOTES:
        on = hit(st, en, ch)
        bar(ax, st, en, r,
            SAGE if on else BEIGE,
            SAGE_D if on else BEIGE_D)
        ax.text(st + 0.13, r, lb, fontsize=10, va="center", ha="left", zorder=4,
                fontweight="bold", color="#FFFFFF" if on else INK2)
    if marker is not None:
        ax.vlines(marker, -0.70, 6.05, color=SAGE_D, lw=2.4, zorder=5)
    n = sum(1 for (st, en, r, lb, ch) in NOTES if hit(st, en, ch))
    ax.text(5.05, 6.28, f"검사 대상 {n}개", color=SAGE_D, fontsize=14.5,
            fontweight="bold", va="center", ha="right")
    ax.set_title(title, color=title_color, fontsize=15, fontweight="bold",
                 loc="left", pad=14)
    ax.text(0.30, -1.15, caption, color=INK2, fontsize=11, va="top",
            ha="left", linespacing=1.7)
    ax.set_xlim(0, 5.25)
    ax.set_ylim(-2.75, 6.7)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.annotate("", xy=(5.20, -0.70), xytext=(0.20, -0.70),
                arrowprops=dict(arrowstyle="->", color=BEIGE_D, lw=1.2))
    ax.text(5.20, -0.55, "시간", color=BEIGE_D, fontsize=10, ha="right")


def fig_constraint_unit(path):
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.6), facecolor=BG,
                             gridspec_kw={"wspace": 0.09})
    _panel(axes[0], lambda st, en, ch: ch == 3,
           "1학기 — 화음 단위로 검사  (화음 3을 검사하는 중)", "#A8584F",
           "묶음에 속한 음만 본다. 넘어온 C4·F4 지속음은 검사에 들어오지 않는다.",
           None)
    _panel(axes[1], lambda st, en, ch: st <= T <= en,
           "2학기 — 시간 구간 겹침으로 검사  (순간 T)", SAGE_D,
           "음표마다 점유 시작·끝을 두고 그 순간에 눌려 있는 건반을 모은다. 지속음이 함께 잡힌다.\n"
           "같은 데이터에서 화음 단위 위반 3건 → 순간 단위 위반 2,552건. 지금은 0건.",
           T)
    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("saved", path)


# ───────── 도식 2: 손목 롤 값이 어디서 사라지는가 ─────────
ROLL_DIST = [("-12°", 2849), ("0°", 16497), ("+12°", 2566)]
TOTAL_NOTES = 21912


def _axstyle(ax):
    ax.set_facecolor(BG)
    ax.set_ylim(0, 24800)
    ax.tick_params(colors=INK2, labelsize=11.5, length=0)
    ax.grid(axis="y", color=BEIGE, lw=1.0, zorder=0)
    ax.set_axisbelow(True)
    for k, sp in ax.spines.items():
        sp.set_visible(k == "bottom")
        if k == "bottom":
            sp.set_color(BEIGE_D)


def fig_wrist_roll(path):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.3), facecolor=BG,
                             gridspec_kw={"wspace": 0.34, "width_ratios": [1.3, 1]})

    ax = axes[0]
    labels = [l for l, _ in ROLL_DIST]
    vals = [v for _, v in ROLL_DIST]
    b = ax.bar(labels, vals, color=[SAGE, BEIGE, SAGE],
               edgecolor=[SAGE_D, BEIGE_D, SAGE_D], linewidth=1.2, width=0.6, zorder=3)
    for rect, v in zip(b, vals):
        ax.text(rect.get_x() + rect.get_width() / 2, v + 460, f"{v:,}",
                ha="center", va="bottom", color=INK, fontsize=12.5, fontweight="bold")
    ax.set_title("운지법 엔진이 내보낸  wrist_roll_deg", color=SAGE_D, fontsize=14,
                 fontweight="bold", loc="left", pad=14)
    ax.text(0, -0.235,
            f"21곡 {TOTAL_NOTES:,}음 중 0이 아닌 값 {ROLL_DIST[0][1]+ROLL_DIST[2][1]:,}음 (24.7%)\n"
            "엄지 또는 소지가 흑건을 누르면 손 전체에 ±12°가 붙는다",
            transform=ax.transAxes, color=INK2, fontsize=11,
            va="top", ha="left", linespacing=1.7)
    _axstyle(ax)

    ax2 = axes[1]
    ax2.bar(["0°"], [TOTAL_NOTES], color=BEIGE, edgecolor="#A8584F",
            linewidth=1.5, width=0.36, zorder=3)
    ax2.text(0, TOTAL_NOTES + 460, "전량", ha="center", va="bottom",
             color="#A8584F", fontsize=12.5, fontweight="bold")
    ax2.set_title("IK 가 기록한  wrist.csv 의 roll_deg", color="#A8584F", fontsize=14,
                  fontweight="bold", loc="left", pad=14)
    ax2.text(0, -0.235,
             "IK 는 손목을 위치만 보간하고 회전은 다루지 않는다.\n"
             "인계 규격서에 \"yaw/pitch/roll 은 0으로 채운다\" 로 적혀 있다.",
             transform=ax2.transAxes, color=INK2, fontsize=11,
             va="top", ha="left", linespacing=1.7)
    ax2.set_xlim(-0.75, 0.75)
    _axstyle(ax2)

    fig.text(0.532, 0.58, "→", color=SAGE_D, fontsize=30, ha="center", va="center")
    fig.text(0.532, 0.47, "값이 버려진다", color=SAGE_D, fontsize=11.5,
             ha="center", va="center", fontweight="bold")

    plt.savefig(path, dpi=150, bbox_inches="tight", facecolor=BG)
    plt.close(fig)
    print("saved", path)


os.makedirs(OUT, exist_ok=True)
fig_constraint_unit(os.path.join(OUT, "lt_constraint_unit.png"))
fig_wrist_roll(os.path.join(OUT, "lt_wrist_roll.png"))
