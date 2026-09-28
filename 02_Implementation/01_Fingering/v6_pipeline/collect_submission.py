"""
V6 Pipeline — 팀원 제출 폴더 생성기
보고서, 이미지, 코드, 결과 샘플을 하나의 폴더로 수집합니다.

실행 전 필수:
  1. python generate_images.py  (보고서용 이미지 생성)
  2. 시뮬레이터 실행 후 스크린샷을 캡처하여
     results/report_imgs/fig0_simulator.png 로 저장

출력 폴더:
  제출_정근녕_중간/
  ├── 진행보고서.md
  ├── 이미지/
  ├── 코드_v6/
  └── 결과샘플/
"""
import os, shutil, glob

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
FINGER_DIR  = os.path.abspath(os.path.join(BASE_DIR, ".."))          # 01_Fingering/
RESULTS_DIR = os.path.join(FINGER_DIR, "results")
REPORT_SRC  = os.path.join(FINGER_DIR, "진행보고서_2학기중간.md")
OUT_DIR     = os.path.join(FINGER_DIR, "제출_정근녕_중간")

IMG_OUT  = os.path.join(OUT_DIR, "이미지")
CODE_OUT = os.path.join(OUT_DIR, "코드_v6")
DATA_OUT = os.path.join(OUT_DIR, "결과샘플")
UE5_OUT  = os.path.join(DATA_OUT, "ue5")


def copy(src, dst_dir, rename=None):
    if not os.path.exists(src):
        print(f"  [없음] {os.path.basename(src)}")
        return False
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, rename if rename else os.path.basename(src))
    shutil.copy2(src, dst)
    print(f"  ✓ {os.path.relpath(dst, OUT_DIR)}")
    return True


def collect():
    if os.path.exists(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    os.makedirs(OUT_DIR)

    print("=" * 56)
    print("  제출 폴더 생성: 정근녕 — 2학기 중간보고서")
    print("=" * 56)

    # ── 1. 보고서 ─────────────────────────────────────────────
    print("\n[1] 보고서")
    copy(REPORT_SRC, OUT_DIR, rename="진행보고서.md")

    # ── 2. 이미지 ─────────────────────────────────────────────
    print("\n[2] 이미지")
    report_imgs = os.path.join(RESULTS_DIR, "report_imgs")

    for fig in ["fig1_pipeline.png", "fig2_finger_dist.png",
                "fig3_piano_roll.png", "fig4_wrist_yaw.png", "fig5_role_dist.png"]:
        copy(os.path.join(report_imgs, fig), IMG_OUT)

    # 시뮬레이터 스크린샷
    # FINGER_DIR 에서 2단계 위 = D:\GitClone\PianoHandSimulator
    repo_root = os.path.abspath(os.path.join(FINGER_DIR, "../.."))
    sim_candidates = [
        (os.path.join(report_imgs,  "fig0_simulator_양손.png"),   "fig0_simulator_양손.png"),
        (os.path.join(report_imgs,  "fig0_simulator_오른손.png"),  "fig0_simulator_오른손.png"),
        (os.path.join(report_imgs,  "fig0_simulator.png"),        "fig0_simulator_양손.png"),
        (os.path.join(repo_root,    "스크린샷 2026-09-29 013808.png"), "fig0_simulator_양손.png"),
        (os.path.join(repo_root,    "스크린샷 2026-09-29 013753.png"), "fig0_simulator_오른손.png"),
    ]
    seen = set()
    for src, dst_name in sim_candidates:
        if dst_name not in seen and os.path.exists(src):
            copy(src, IMG_OUT, rename=dst_name)
            seen.add(dst_name)

    # 1학기 Fingering 이미지 — 졸업프로젝트 폴더(N:) 또는 레포 내 탐색
    mid_candidates = [
        r"N:\개인\건국대학교\4-1\졸업프로젝트\1학기\중간보고서",
        os.path.abspath(os.path.join(repo_root, "../../1학기/중간보고서")),
    ]
    mid_dir = next((d for d in mid_candidates if os.path.isdir(d)), None)
    if mid_dir:
        copy(os.path.join(mid_dir, "Fingering_ (1).png"), IMG_OUT, rename="Fingering_1.png")
        copy(os.path.join(mid_dir, "Fingering_ (2).png"), IMG_OUT, rename="Fingering_2.png")
    else:
        print("  [없음] Fingering_1.png  (1학기 중간보고서 폴더를 찾을 수 없음)")

    # ── 3. 코드 ───────────────────────────────────────────────
    print("\n[3] 코드 (v6_pipeline)")
    for f in ["shared_constants.py", "fingering_engine.py",
              "simulator.py", "ue5_exporter.py", "run_batch.py"]:
        copy(os.path.join(BASE_DIR, f), CODE_OUT)

    # ── 4. 결과 샘플 ──────────────────────────────────────────
    print("\n[4] 결과 샘플")
    # JSON 샘플: 드뷔시, 마리오
    for stem in ["deb_clai_fingering.json", "Super Mario 64 - Medley_fingering.json"]:
        copy(os.path.join(RESULTS_DIR, stem), DATA_OUT)

    # UE5 CSV 샘플
    ue5_src = os.path.join(RESULTS_DIR, "ue5")
    for stem in ["deb_clai_fingering_datatable.csv",
                 "deb_clai_fingering_summary.txt",
                 "Super Mario 64 - Medley_fingering_datatable.csv"]:
        copy(os.path.join(ue5_src, stem), UE5_OUT)

    # ── 5. 최종 목록 출력 ─────────────────────────────────────
    print("\n" + "=" * 56)
    print(f"  완료: {OUT_DIR}")
    print("=" * 56)
    print("\n  폴더 구조:")
    for root, dirs, files in os.walk(OUT_DIR):
        dirs.sort()
        level = root.replace(OUT_DIR, "").count(os.sep)
        indent = "  " + "    " * level
        print(f"{indent}{os.path.basename(root)}/")
        sub = "  " + "    " * (level + 1)
        for f in sorted(files):
            size = os.path.getsize(os.path.join(root, f))
            size_str = f"{size//1024}KB" if size > 1024 else f"{size}B"
            print(f"{sub}{f}  ({size_str})")

    print()
    missing_sim = (not os.path.exists(os.path.join(IMG_OUT, "fig0_simulator_양손.png")) and
                   not os.path.exists(os.path.join(IMG_OUT, "fig0_simulator.png")))
    if missing_sim:
        print("  ⚠  시뮬레이터 스크린샷 누락!")
        print(f"     → 스크린샷 파일을 아래 경로 중 하나로 저장 후 재실행하세요.")
        print(f"       {os.path.join(repo_root, '스크린샷 2026-09-29 013808.png')}")
        print(f"       {os.path.join(report_imgs, 'fig0_simulator_양손.png')}\n")


if __name__ == "__main__":
    collect()
