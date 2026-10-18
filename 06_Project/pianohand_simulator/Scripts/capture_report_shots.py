"""Capture the Phase 3 report image set from the editor viewport.

Run inside the editor AFTER hand_tension_demo.py has spawned the hands:
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/capture_report_shots.py').read())

Every shot uses the same camera so the comparisons line up, and the landscape is hidden so the
hand reads against plain sky instead of a tiled grid.

HighResShot is queued and only runs when the editor TICKS - and the editor does not tick while a
blocking Python call is running. So a loop that fires a shot and then waits for its file inside the
same call can never succeed, and each new request replaces the pending one: you end up with exactly
one image, the last. Hence `stage(i)` / `verify(i)`: one shot per call, the caller returning control
to the editor in between. The editor window also has to be focused, or the queued shot is dropped.
"""
import unreal, os, time

D = r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Saved/Screenshots/WindowsEditor'
ELL = unreal.EditorLevelLibrary
SLB = unreal.SystemLibrary

# (socket, camera offset from that socket, pitch, yaw)
WIDE  = ('middle_02_r', unreal.Vector(-22, 3.0, 7.0), -14.0,  0.0)
CLOSE = ('middle_01_r', unreal.Vector(-15, 6.5, 7.5), -24.0, -12.0)   # down onto the knuckles


def _hide_backdrop():
    """Plain sky behind the hand - the landscape grid competes with the relief we are judging."""
    for a in ELL.get_all_level_actors():
        cls = a.get_class().get_name()
        if 'Landscape' in cls or a.get_actor_label() in ('Landscape', 'SM_SkySphere'):
            try:
                a.set_is_temporarily_hidden_in_editor(True)
            except Exception:
                a.set_actor_hidden_in_game(True)


def aim(framing):
    socket, offset, pitch, yaw = framing
    p = custom_comp.get_socket_transform(socket, unreal.RelativeTransformSpace.RTS_WORLD).translation
    ELL.set_level_viewport_camera_info(p + offset, unreal.Rotator(roll=0.0, pitch=pitch, yaw=yaw))


SHOTS = [
    # (file name, material key, pose, framing)
    ('rpt_skin_idle',      'skin',    'Idle',      WIDE),
    ('rpt_skin_curl',      'skin',    'IndexCurl', WIDE),
    ('rpt_skin_grasp',     'skin',    'Grasp',     WIDE),
    ('rpt_skin_close',     'skin',    'Grasp',     CLOSE),
    ('rpt_tension_idle',   'tension', 'Idle',      WIDE),
    ('rpt_tension_grasp',  'tension', 'Grasp',     WIDE),
    ('rpt_tension_close',  'tension', 'Grasp',     CLOSE),
    ('rpt_clay_grasp',     'clay',    'Grasp',     WIDE),
]


def shot(name):
    """Queue one HighResShot. It runs after this call returns and the editor ticks again."""
    path = os.path.join(D, name + '.png')
    if os.path.exists(path):
        os.remove(path)
    SLB.execute_console_command(None, 'HighResShot 1600x900 filename=%s' % name)


def prep(i):
    """Set material/pose/camera for SHOTS[i]. Call fire(i) on the NEXT call, not this one: a
    single-node animation only re-evaluates when the editor ticks, and a shot queued in the same
    call goes off on the tick that still has the previous pose on screen."""
    name, mat, pose, framing = SHOTS[i]
    _hide_backdrop()
    ELL.set_selected_level_actors([])          # no transform gizmo in the shot
    SLB.execute_console_command(None, 'ShowFlag.Grid 0')
    engine_comp.set_visibility(False)
    use_material(mat)
    set_pose(pose)
    aim(framing)
    print('prepped %d/%d %s (%s, %s)' % (i + 1, len(SHOTS), name, mat, pose))


def fire(i):
    shot(SHOTS[i][0])
    print('queued', SHOTS[i][0])


def verify():
    have = sorted(f[:-4] for f in os.listdir(D) if f.startswith('rpt_'))
    want = [s[0] for s in SHOTS]
    print('have   :', have)
    print('missing:', [w for w in want if w not in have])


_hide_backdrop()
print('%d shots: prep(i) then fire(i) in SEPARATE calls, i = 0..%d, then verify()' % (len(SHOTS), len(SHOTS) - 1))
