"""
copy_assets.py
N:\\ 작업 폴더의 이미지/결과물을 Git 리포지토리로 복사합니다.
사용법: python copy_assets.py
"""
import os
import shutil

SRC_BASE = r"N:\개인\건국대학교\4-1\졸업프로젝트\2학기"
DST_BASE = r"D:\GitClone\PianoHandSimulator"

COPIES = [
    # (원본 경로, 대상 경로)  — 디렉터리면 tree 전체 복사
    # 보고서 이미지
    (r"이미지\fig1_pipeline.png",          r"03_Reports\images\fig1_pipeline.png"),
    (r"이미지\fig0_simulator_양손.png",     r"03_Reports\images\fig0_simulator_양손.png"),
    (r"이미지\fig0_simulator_오른손.png",   r"03_Reports\images\fig0_simulator_오른손.png"),
    (r"이미지\fig2_finger_dist.png",        r"03_Reports\images\fig2_finger_dist.png"),
    (r"이미지\fig3_piano_roll.png",         r"03_Reports\images\fig3_piano_roll.png"),
    (r"이미지\fig4_wrist_yaw.png",          r"03_Reports\images\fig4_wrist_yaw.png"),
    (r"이미지\fig5_role_dist.png",          r"03_Reports\images\fig5_role_dist.png"),
    # IK 테스트베드 스크린샷 (카카오톡 → 이미지 폴더에 복사 후 아래 이름으로)
    (r"이미지\fig_ik_melody.png",           r"03_Reports\images\fig_ik_melody.png"),
    (r"이미지\fig_ik_chord.png",            r"03_Reports\images\fig_ik_chord.png"),
    # 스키닝 파이프라인 스크린샷
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110514.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110514.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110527.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110527.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110538.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110538.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110545.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110545.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110552.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110552.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110559.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110559.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110606.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110606.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110612.png",
     r"03_Reports\images\skinning_pipeline\스크린샷_2026-09-29_110612.png"),
    # Skinning Document 이미지 (4.3/4.4 문서용)
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110514.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110514.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110527.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110527.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110538.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110538.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110545.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110545.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110552.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110552.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110559.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110559.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110606.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110606.png"),
    (r"이미지\스키닝 파이프라인\스크린샷 2026-09-29 110612.png",
     r"02_Implementation\03_Skinning\Document\images\skinning_pipeline\스크린샷_2026-09-29_110612.png"),
]

# 결과 JSON/CSV — 결과샘플/ 전체
FLESH_IMAGES = [
    # (원본 파일명, 대상 파일명)
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 010649.png",
     r"02_Implementation\03_Skinning\Document\images\fig_flesh_follow_after.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 013157.png",
     r"02_Implementation\03_Skinning\Document\images\fig_flesh_follow_after2.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 014020.png",
     r"02_Implementation\03_Skinning\Document\images\fig_flesh_graph.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-28 231149.png",
     r"02_Implementation\03_Skinning\Document\images\fig_flesh_isostuffing.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-28 234329.png",
     r"02_Implementation\03_Skinning\Document\images\fig_flesh_tetwild.png"),
    # 보고서용 사본
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 010649.png",
     r"03_Reports\images\flesh_pipeline\fig_flesh_follow_after.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 013157.png",
     r"03_Reports\images\flesh_pipeline\fig_flesh_follow_after2.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-29 014020.png",
     r"03_Reports\images\flesh_pipeline\fig_flesh_graph.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-28 231149.png",
     r"03_Reports\images\flesh_pipeline\fig_flesh_isostuffing.png"),
    (r"이미지\4.4_Chaos_Flesh_PBD_Skinning\스크린샷 2026-09-28 234329.png",
     r"03_Reports\images\flesh_pipeline\fig_flesh_tetwild.png"),
]

RESULTS_SRC = os.path.join(SRC_BASE, "결과샘플")
RESULTS_DST = os.path.join(DST_BASE, r"02_Implementation\01_Fingering\results")


def copy_file(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(src):
        shutil.copy2(src, dst)
        print(f"  OK  {os.path.basename(src)}")
    else:
        print(f"  --  없음: {src}")


def copy_tree(src_dir, dst_dir):
    if not os.path.isdir(src_dir):
        print(f"  --  폴더 없음: {src_dir}")
        return
    for root, dirs, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        for f in files:
            src = os.path.join(root, f)
            dst = os.path.join(dst_dir, rel, f)
            copy_file(src, dst)


if __name__ == "__main__":
    print("=== 개별 파일 복사 ===")
    for src_rel, dst_rel in COPIES:
        copy_file(os.path.join(SRC_BASE, src_rel), os.path.join(DST_BASE, dst_rel))

    print("\n=== Chaos Flesh 이미지 복사 ===")
    for src_rel, dst_rel in FLESH_IMAGES:
        copy_file(os.path.join(SRC_BASE, src_rel), os.path.join(DST_BASE, dst_rel))

    print("\n=== 결과샘플 복사 ===")
    copy_tree(RESULTS_SRC, RESULTS_DST)

    print("\n완료.")
