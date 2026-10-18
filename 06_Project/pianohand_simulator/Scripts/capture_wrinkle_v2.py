"""Capture the wrinkle-detail v2 image set (strain tensor + per-joint furrows) from the editor viewport.

Run AFTER mh_hand_demo.py, in the editor:
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/capture_wrinkle_v2.py').read())
    prep(0)   # one call
    fire(0)   # the NEXT call
    ...

Same prep/fire split as capture_43_shots.py: HighResShot only runs when the editor ticks, and it
does not tick inside a blocking Python call. The editor window also has to be restored (not
minimised) or the viewport never renders and nothing is written.

The 'v1' entries re-create the look of the previous shader for the before/after pairs: every joint
on one pattern (no per-joint folds, no Bando profile, no side folds, isotropic micro relief).
"""
import os
import unreal

D = r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Saved/Screenshots/WindowsEditor'
RES = '2560x1440'
ELL = unreal.EditorLevelLibrary
SLB = unreal.SystemLibrary

V2 = dict(CreaseFrequency=1.3, FurrowWidth=0.25, Irregularity=1.0, SecondaryDepth=0.4, JointReach=1.2,
          CompressNarrow=2.0, StretchWiden=2.0, CreaseDepth=0.35, DetailStrength=0.55,
          FoldsMCP=1.1, FoldsPIP=2.2, FoldsDIP=0.8, DepthMCP=0.55, DepthPIP=1.0, DepthDIP=0.75,
          PalmSplit=0.3, SideFolds=0.25, MicroAniso=1.0, MicroFlatten=0.5)
# one pattern for every joint, every fold at full depth, no strain coupling, no micro anisotropy,
# no side folds - the previous look
V1 = dict(CreaseFrequency=1.15, FurrowWidth=0.5, Irregularity=0.0, SecondaryDepth=1.0, JointReach=2.0,
          CompressNarrow=0.0, StretchWiden=0.0, CreaseDepth=0.45, DetailStrength=0.8,
          FoldsMCP=1.0, FoldsPIP=1.0, FoldsDIP=1.0, DepthMCP=1.0, DepthPIP=1.0, DepthDIP=1.0,
          PalmSplit=0.0, SideFolds=0.0, MicroAniso=0.0, MicroFlatten=0.0)

#  name                  material   time        side      dist  params
SHOTS = [
    ('w2_tension_open',   'tension', 'idle',     'dorsal', 15.0, V2),
    ('w2_tension_fist',   'tension', 'grasp',    'dorsal', 15.0, V2),
    ('w2_tension_palm',   'tension', 'closing',  'palmar', 17.0, V2),
    ('w2_v1_open',        'skin',    'idle',     'dorsal', 15.0, V1),
    ('w2_v1_fist',        'skin',    'grasp',    'dorsal', 15.0, V1),
    ('w2_v2_open',        'skin',    'idle',     'dorsal', 15.0, V2),
    ('w2_v2_fist',        'skin',    'grasp',    'dorsal', 15.0, V2),
    ('w2_v2_released',    'skin',    'released', 'dorsal', 15.0, V2),
    # close-ups aim at the middle finger PIP; the viewport near plane is 10cm, so never closer than ~12
    ('w2_v1_close',       'skin',    'idle',     'close',  13.0, V1),
    ('w2_v2_close',       'skin',    'idle',     'close',  13.0, V2),
    # (no posed close-ups: in a fist the knuckles rise into the 10cm near plane, and a released
    #  hand reaches towards the camera - w2_v2_fist / w2_v2_released at 15cm are the usable ones)
    # palm: by 'closing' the fingers already curl right over and only their backs face the camera,
    # so the palmar creases are photographed a little earlier in the cycle (see MARKS['half'])
    ('w2_v1_palm',        'skin',    'half',     'palmar', 17.0, V1),
    ('w2_v2_palm',        'skin',    'half',     'palmar', 17.0, V2),
    ('w2_v2_palm_open',   'skin',    'idle',     'palmar', 17.0, V2),
]


MARKS['half'] = 0.55   # fingers just starting to flex: palm creases visible, pads still facing out


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


def light_from(side):
    """Light the side being photographed, with the sun kept ABOVE the horizon.

    The palm faces down in this pose, so lighting it directly would put the sun below the horizon
    and the sky atmosphere goes black. Instead the hand ACTOR is rolled 180 deg for palm shots so
    the palm faces up; view() follows the bones, so the camera comes along.
    """
    ML = unreal.MathLibrary
    hand_actor.set_actor_rotation(unreal.Rotator(roll=180.0 if side == 'palmar' else 0.0, pitch=0.0, yaw=0.0), False)
    wrist = hand_comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
    rot = wrist.rotation.rotator()
    dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)
    face = dorsal if side == 'dorsal' else ML.multiply_vector_float(dorsal, -1.0)
    travel = ML.multiply_vector_float(face, -1.0)        # light travels INTO the face we look at
    r = ML.make_rot_from_x(travel)
    # oblique, not head-on: relief only reads under grazing light. Never below the horizon.
    pitch = min(r.pitch + 10.0, -18.0)
    for a in ELL.get_all_level_actors():
        if a.get_actor_label() == 'DirectionalLight':
            a.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=pitch, yaw=r.yaw + 50.0), False)
            a.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(3.5)


def view_close(dist=13.0, bone='middle_02_r'):
    """Dorsal close-up on one joint. Direction from hand_r like view(), target on the joint itself."""
    ML = unreal.MathLibrary
    wrist = hand_comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
    rot = wrist.rotation.rotator()
    dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)
    target = hand_comp.get_socket_transform(bone, unreal.RelativeTransformSpace.RTS_WORLD).translation
    eye = target + ML.multiply_vector_float(dorsal, dist)
    ELL.set_level_viewport_camera_info(eye, ML.find_look_at_rotation(eye, target))
    print('view -> close on %s, %.0fcm' % (bone, dist))


def prep(i):
    name, mat, when, side, dist, params = SHOTS[i]
    _clean_backdrop()
    # fixed exposure: auto exposure keys on the sky and washes the skin out to plaster
    SLB.execute_console_command(None, 'r.DefaultFeature.AutoExposure 0')
    use_material(mat)
    set_skin(**params)
    mark(when)
    light_from('dorsal' if side == 'close' else side)
    if side == 'close':
        view_close(dist)
    else:
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
    have = sorted(f[:-4] for f in os.listdir(D) if f.startswith('w2_'))
    want = [s[0] for s in SHOTS]
    print('have   :', have)
    print('missing:', [w for w in want if w not in have])


_clean_backdrop()
print('%d shots @ %s. prep(i) then fire(i) in SEPARATE calls, i = 0..%d, then verify()'
      % (len(SHOTS), RES, len(SHOTS) - 1))
