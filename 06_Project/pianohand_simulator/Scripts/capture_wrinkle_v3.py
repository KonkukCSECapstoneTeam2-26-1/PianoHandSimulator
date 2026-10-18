"""Capture the skin v3 image set (subsurface + crease shape + regional relief + palm lines + colour
response + distance fade + mask groove + proportions) from the editor viewport.

Run AFTER mh_hand_demo.py, in the editor (Windows or macOS):
    exec(open('<project>/Scripts/capture_wrinkle_v3.py').read())
    prep(0)   # one call: pose, light, material, parameters
    cam(0)    # the NEXT call: camera (socket transforms are only current on the next tick)
    fire(0)   # the call after that: HighResShot (after ~2 s, so the temporal history has settled)
    ...
    verify()

Three calls per shot, not one. HighResShot only runs when the editor ticks, and a blocking Python
call is not a tick; the actor roll set in prep() is only visible to GetSocketTransform on the next
tick; and the subsurface / TSR history needs a couple of frames after the camera moves or the
first frame is speckled. The editor window has to be in the foreground or the viewport does not
render and nothing is written.

The 'v2' entries recreate the previous shader (straight creases, one relief everywhere, no palm
lines, no colour response, Lit shading) for the before/after pairs. The shading model cannot be
switched per shot, so the v2 pairs are "v3 material with the v3-only features turned off".
"""
import os
import sys
import unreal

RES = '1920x1080'
D = os.path.join(unreal.Paths.project_saved_dir(), 'Screenshots', 'MacEditor' if sys.platform == 'darwin' else 'WindowsEditor')
ML = unreal.MathLibrary
SLB = unreal.SystemLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)

V3 = dict(CreaseBow=-0.2, PalmBow=0.15, SideTaper=0.2, ForkStrength=0.55, ForkAngle=0.35, SeedVariation=0.8,
          PrimaryWidth=0.14, PalmLineDepth=1.3, KnuckleStrengthMul=1.25, KnuckleTilingMul=0.7,
          SideStrengthMul=0.6, SideTilingMul=1.5, RidgeStrength=0.45, BlanchGain=0.9, FlushGain=0.7,
          CavityDarken=0.22, CavityAO=0.55, CavityRough=0.35, FadeStartCm=0.05, FadeEndCm=0.18)
# the v2 look: straight, un-seeded creases, one relief everywhere, no palm lines, no colour response,
# no cavity, no fade
V2 = dict(CreaseBow=0.0, PalmBow=0.0, SideTaper=0.0, ForkStrength=0.0, ForkAngle=0.0, SeedVariation=0.0,
          PrimaryWidth=0.27, PalmLineDepth=0.0, KnuckleStrengthMul=1.0, KnuckleTilingMul=1.0,
          SideStrengthMul=1.0, SideTilingMul=1.0, RidgeStrength=0.0, BlanchGain=0.0, FlushGain=0.0,
          CavityDarken=0.0, CavityAO=0.0, CavityRough=0.0, FadeStartCm=100.0, FadeEndCm=200.0)

MARKS['half'] = 0.55

#  name                  material   time     side      dist  params   extra
SHOTS = [
    ('v3_dorsal_idle',    'skin',    'idle',  'dorsal', 15.0, V3, None),
    ('v2_dorsal_idle',    'skin',    'idle',  'dorsal', 15.0, V2, None),
    ('v3_close_idle',     'skin',    'idle',  'close',  12.0, V3, None),
    ('v2_close_idle',     'skin',    'idle',  'close',  12.0, V2, None),
    ('v3_close_fist',     'skin',    'grasp', 'close',  15.0, V3, None),   # in a fist the knuckles rise into the 10cm near plane; 12.5 clips
    ('v3_dorsal_fist',    'skin',    'grasp', 'dorsal', 15.0, V3, None),
    ('v3_palm_open',      'skin',    'idle',  'palmar', 17.0, V3, None),
    ('v2_palm_open',      'skin',    'idle',  'palmar', 17.0, V2, None),
    ('v3_palm_close',     'skin',    'idle',  'palmclose', 13.0, V3, None),
    ('v3_palm_half',      'skin',    'half',  'palmar', 17.0, V3, None),
    ('v3_far',            'skin',    'idle',  'dorsal', 60.0, V3, None),
    ('v2_far',            'skin',    'idle',  'dorsal', 60.0, V2, None),
    ('v3_tension_idle',   'tension', 'idle',  'close',  12.0, V3, None),
    # Phase 6: creases from the simulated graph (Weiss 2023/2024) vs the v3 procedural furrows
    ('v4_graph_close',    'skin',    'idle',  'close',  12.0, V3, ('graph', True)),
    ('v4_proc_close',     'skin',    'idle',  'close',  12.0, V3, ('graph', False)),
    ('v4_graph_fist',     'skin',    'grasp', 'dorsal', 15.0, V3, ('graph', True)),
    ('v4_graph_released', 'skin',    'released', 'dorsal', 15.0, V3, ('graph', True)),
    # Phase 5: geometric groove on the primary crease (silhouette of a bent knuckle)
    ('v3_groove_on',      'clay',    'grasp', 'profile', 14.0, V3, ('groove', True)),
    ('v3_groove_off',     'clay',    'grasp', 'profile', 14.0, V3, ('groove', False)),
    # Phase 5: proportions
    ('v3_prop_default',   'skin',    'idle',  'dorsal', 17.0, V3, ('prop', None)),
    ('v3_prop_long',      'skin',    'idle',  'dorsal', 17.0, V3, ('prop', dict(index=(1.15, 1.15, 1.1), middle=(1.1, 1.1, 1.1), ring=(1.1, 1.1, 1.05), pinky=(0.9, 0.9, 0.9), palm_length=1.06))),
    ('v3_prop_wide',      'skin',    'idle',  'dorsal', 17.0, V3, ('prop', dict(palm_width=1.15, thickness=1.15, overall=1.0))),
    ('v3_prop_small',     'skin',    'idle',  'dorsal', 17.0, V3, ('prop', dict(overall=0.85))),
    ('v3_prop_long_fist', 'skin',    'grasp', 'dorsal', 17.0, V3, ('prop', dict(index=(1.15, 1.15, 1.1), middle=(1.1, 1.1, 1.1), ring=(1.1, 1.1, 1.05), pinky=(0.9, 0.9, 0.9), palm_length=1.06))),
    ('v3_prop_tension',   'tension', 'idle',  'dorsal', 17.0, V3, ('prop', dict(index=(1.2, 1.2, 1.2)))),
]


def _clean_backdrop():
    for a in EAS.get_all_level_actors():
        cls = a.get_class().get_name()
        if 'Landscape' in cls or a.get_actor_label() in ('Landscape', 'SM_SkySphere'):
            try:
                a.set_is_temporarily_hidden_in_editor(True)
            except Exception:
                a.set_actor_hidden_in_game(True)
    EAS.set_selected_level_actors([])
    SLB.execute_console_command(None, 'ShowFlag.Grid 0')


def fixed_exposure(ev=1.5):
    """An unbound post-process volume pinning the exposure: auto exposure keys on the sky and washes
    the skin out to plaster."""
    ppv = None
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == 'PH_Exposure':
            ppv = a
    if ppv is None:
        ppv = EAS.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
        ppv.set_actor_label('PH_Exposure')
    ppv.set_editor_property('unbound', True)
    st = ppv.get_editor_property('settings')
    st.set_editor_property('override_auto_exposure_method', True)
    st.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_HISTOGRAM)
    st.set_editor_property('override_auto_exposure_min_brightness', True)
    st.set_editor_property('override_auto_exposure_max_brightness', True)
    st.set_editor_property('auto_exposure_min_brightness', float(ev))
    st.set_editor_property('auto_exposure_max_brightness', float(ev))
    ppv.set_editor_property('settings', st)


def light_from(side, intensity=6.0, yaw_off=70.0, pitch=-38.0):
    """Grazing light onto the face being photographed. The palm faces down in this pose, so for
    palm shots the ACTOR is rolled 180 deg (the sun must stay above the horizon)."""
    hand_actor.set_actor_rotation(unreal.Rotator(roll=180.0 if side in ('palmar', 'palmclose') else 0.0, pitch=0.0, yaw=0.0), False)
    wrist = hand_comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
    rot = wrist.rotation.rotator()
    dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)
    face = dorsal if side in ('dorsal', 'close', 'profile') else ML.multiply_vector_float(dorsal, -1.0)
    travel = ML.multiply_vector_float(face, -1.0)
    r = ML.make_rot_from_x(travel)
    for a in EAS.get_all_level_actors():
        if a.get_actor_label() == 'DirectionalLight':
            a.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=pitch, yaw=r.yaw + yaw_off), False)
            a.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(intensity)


def _frame(side, dist):
    wrist = hand_comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
    rot = wrist.rotation.rotator()
    dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)
    if side == 'close':
        target = hand_comp.get_socket_transform('middle_02_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
        d = dorsal
    elif side == 'palmclose':
        target = hand_comp.get_socket_transform('middle_metacarpal_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
        d = ML.multiply_vector_float(dorsal, -1.0)
    elif side == 'profile':
        # from the thumb side, so the knuckle silhouette is against the sky
        target = hand_comp.get_socket_transform('middle_02_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
        d = ML.multiply_vector_float(ML.get_up_vector(rot), -1.0)
    else:
        knuck = hand_comp.get_socket_transform('middle_02_r', unreal.RelativeTransformSpace.RTS_WORLD)
        target = (wrist.translation + knuck.translation) * 0.5
        d = dorsal if side == 'dorsal' else ML.multiply_vector_float(dorsal, -1.0)
    eye = target + ML.multiply_vector_float(d, dist)
    UES.set_level_viewport_camera_info(eye, ML.find_look_at_rotation(eye, target))


def prep(i):
    name, mat, when, side, dist, params, extra = SHOTS[i]
    _clean_backdrop()
    fixed_exposure(1.5)
    SLB.execute_console_command(None, 'r.DefaultFeature.AutoExposure 0')
    use_material(mat)
    set_skin(**params)
    reset_proportions()
    use_mask_groove(True)
    if extra is not None:
        kind, value = extra
        if kind == 'graph':
            set_skin(GraphCreases=1.0 if value else 0.0)
        elif kind == 'groove':
            use_mask_groove(value)
            set_detail(crease_depth=0.0 if value else 0.06, mask_crease_depth=0.08)
        elif kind == 'prop' and value is not None:
            set_proportions(**value)
    mark(when)
    light_from(side)
    print('prep %d/%d  %s   -> next: cam(%d)' % (i + 1, len(SHOTS), name, i))


def cam(i):
    name, mat, when, side, dist, params, extra = SHOTS[i]
    _frame(side, dist)
    print('cam %s   -> next (after ~2s): fire(%d)' % (name, i))


def fire(i):
    name = SHOTS[i][0]
    path = os.path.join(D, name + '.png')
    if os.path.exists(path):
        os.remove(path)
    SLB.execute_console_command(None, 'HighResShot %s filename=%s' % (RES, name))
    print('queued', name)


def verify():
    have = sorted(f[:-4] for f in os.listdir(D) if f.startswith('v3_') or f.startswith('v2_')) if os.path.isdir(D) else []
    want = [s[0] for s in SHOTS]
    print('have   :', have)
    print('missing:', [w for w in want if w not in have])


_clean_backdrop()
