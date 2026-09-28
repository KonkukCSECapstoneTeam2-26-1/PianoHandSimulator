"""Capture the 4.3 report image set from the editor viewport.

Run AFTER mh_hand_demo.py, in the editor:
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/capture_43_shots.py').read())
    prep(0)   # one call
    fire(0)   # the NEXT call - see below
    prep(1) ... fire(1) ...

HighResShot is queued and only runs when the editor TICKS, and the editor does not tick while a
blocking Python call is running. A shot fired in the same call that changed the pose therefore
captures the PREVIOUS pose, and two shots queued in one call overwrite each other. Hence the
prep/fire split, one per call.

The landscape and sky sphere are hidden and the grid is off: a tiled floor competes with exactly
the surface relief these images exist to show.
"""
import os
import unreal

D = r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Saved/Screenshots/WindowsEditor'
RES = '2560x1440'
ELL = unreal.EditorLevelLibrary
SLB = unreal.SystemLibrary

# the tuned values this section documents
NEW = dict(PalmarBase=0.30, PalmarCompress=2.6, PalmarIron=1.2, PalmarRelax=0.8,
           DorsalBase=0.40, DorsalIron=5.0, DorsalRelax=4.0, SideSharpness=2.0)
# the single-gate behaviour from before the dorsal/palmar split, for the before/after pair:
# the old gate on the back of the hand was WrinkleBase - Stretch * StretchSmooth, which is the
# same shape as the dorsal gate with these two values.
OLD = dict(DorsalBase=0.16, DorsalIron=1.4, DorsalRelax=2.0)

#  name                 material   time       side      dist  params
SHOTS = [
    ('r43_clay',        'clay',    'idle',    'dorsal', 15.0, NEW),
    ('r43_tension_open','tension', 'idle',    'dorsal', 15.0, NEW),
    ('r43_tension_fist','tension', 'grasp',   'dorsal', 15.0, NEW),
    ('r43_old_open',    'skin',    'idle',    'dorsal', 15.0, OLD),
    ('r43_old_fist',    'skin',    'grasp',   'dorsal', 15.0, OLD),
    ('r43_new_open',    'skin',    'idle',    'dorsal', 15.0, NEW),
    ('r43_new_fist',    'skin',    'grasp',   'dorsal', 15.0, NEW),
    ('r43_new_released','skin',    'released','dorsal', 15.0, NEW),
    ('r43_palm_open',   'skin',    'idle',    'palmar', 17.0, NEW),
    ('r43_palm_close',  'skin',    'closing', 'palmar', 17.0, NEW),
    ('r43_close',       'skin',    'idle',    'dorsal',  9.0, NEW),
]


def _clean_backdrop():
    for a in ELL.get_all_level_actors():
        cls = a.get_class().get_name()
        if 'Landscape' in cls or a.get_actor_label() in ('Landscape', 'SM_SkySphere'):
            try:
                a.set_is_temporarily_hidden_in_editor(True)
            except Exception:
                a.set_actor_hidden_in_game(True)
    ELL.set_selected_level_actors([])
    SLB.execute_console_command(None, 'ShowFlag.Grid 0')


def prep(i):
    name, mat, when, side, dist, params = SHOTS[i]
    _clean_backdrop()
    use_material(mat)
    set_skin(**params)
    mark(when)
    view(side, dist)
    print('prep %d/%d  %s' % (i + 1, len(SHOTS), name))


def fire(i):
    name = SHOTS[i][0]
    path = os.path.join(D, name + '.png')
    if os.path.exists(path):
        os.remove(path)
    SLB.execute_console_command(None, 'HighResShot %s filename=%s' % (RES, name))
    print('queued', name)


def verify():
    have = sorted(f[:-4] for f in os.listdir(D) if f.startswith('r43_'))
    want = [s[0] for s in SHOTS]
    print('have   :', have)
    print('missing:', [w for w in want if w not in have])


_clean_backdrop()
print('%d shots @ %s. prep(i) then fire(i) in SEPARATE calls, i = 0..%d, then verify()'
      % (len(SHOTS), RES, len(SHOTS) - 1))
