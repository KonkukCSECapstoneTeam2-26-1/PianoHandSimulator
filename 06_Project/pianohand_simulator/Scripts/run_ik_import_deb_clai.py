"""One-liner runner: IK export of deb_clai (248 s) -> AnimSequence A_IK_DebClai.

In the editor Output Log (Cmd: Python):
    exec(open(r'<project>/Scripts/run_ik_import_deb_clai.py').read())
"""
import os

import unreal

PROJECT_DIR = unreal.Paths.project_dir()
IK_JOINTS_CSV = os.path.join(PROJECT_DIR, 'Saved', 'IKExport', 'deb_clai_joints.csv')
IK_WRIST_CSV = os.path.join(PROJECT_DIR, 'Saved', 'IKExport', 'deb_clai_wrist.csv')
IK_ANIM_NAME = 'A_IK_DebClai'
exec(open(os.path.join(PROJECT_DIR, 'Scripts', 'import_ik_csv_to_anim.py')).read())
