"""Build the playable demo level from scratch: a plain (non World Partition) level with a key light, sky
light, sky atmosphere, the exposure volume, the MetaHuman hand with the custom deformer (mh_hand_demo.py)
and the play camera (setup_play_level.py), saved as /Game/PianoHand/Maps/L_PianoHandDemo.

    exec(open('<project>/Scripts/create_demo_level.py').read())

Why from scratch: the first save of the demo was made from the OpenWorld template level (World Partition
+ landscape), and in PIE the template's lights were not loaded - the play world rendered black. A plain
level has no streaming, so everything in it is simply there.
"""
import unreal, os
P = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) if '__file__' in globals() else '/Users/nunsori/Git/PianoHandSimulator/06_Project/pianohand_simulator'
MAP = '/Game/PianoHand/Maps/L_PianoHandDemo'
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
LVL = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)

eal = unreal.EditorAssetLibrary
if eal.does_asset_exist(MAP):
    # NEVER delete_asset() the level you are standing in (SIGSEGV in ULevelInstanceSubsystem::OnAssetsPreDelete,
    # 10-15 23:30) and new_level() refuses an existing path: open the existing plain map and empty it instead.
    LVL.load_level(MAP)
    for a in list(EAS.get_all_level_actors()):
        EAS.destroy_actor(a)
    print('REUSED_LEVEL', MAP)
else:
    print('NEW_LEVEL', LVL.new_level(MAP), MAP)    # empty level template: no world partition, no landscape
world = UES.get_editor_world()

sun = EAS.spawn_actor_from_class(unreal.DirectionalLight, unreal.Vector(0, 0, 300), unreal.Rotator(pitch=-38.0, yaw=60.0, roll=0.0))
sun.set_actor_label('DirectionalLight')          # tools/ph.py light_from() finds it by this label
sun.get_component_by_class(unreal.DirectionalLightComponent).set_intensity(6.0)
sun.get_component_by_class(unreal.DirectionalLightComponent).set_editor_property('atmosphere_sun_light', True)
sky = EAS.spawn_actor_from_class(unreal.SkyAtmosphere, unreal.Vector(0, 0, 0))
sky.set_actor_label('SkyAtmosphere')
skl = EAS.spawn_actor_from_class(unreal.SkyLight, unreal.Vector(0, 0, 200))
skl.set_actor_label('SkyLight')
slc = skl.get_component_by_class(unreal.SkyLightComponent)
slc.set_editor_property('real_time_capture', True)
slc.set_intensity(1.0)
ppv = EAS.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(0, 0, 0))
ppv.set_actor_label('PH_Exposure'); ppv.set_editor_property('unbound', True)
s = ppv.get_editor_property('settings')
# fixed exposure the way every capture of this project was made (tools/ph.py exposure(1.0)): histogram
# metering pinned to EV100 = 1 (ExtendDefaultLuminanceRange is on in DefaultEngine.ini), no bias
s.set_editor_property('override_auto_exposure_method', True); s.set_editor_property('auto_exposure_method', unreal.AutoExposureMethod.AEM_HISTOGRAM)
s.set_editor_property('override_auto_exposure_min_brightness', True); s.set_editor_property('auto_exposure_min_brightness', 1.0)
s.set_editor_property('override_auto_exposure_max_brightness', True); s.set_editor_property('auto_exposure_max_brightness', 1.0)
s.set_editor_property('override_auto_exposure_bias', True); s.set_editor_property('auto_exposure_bias', 0.0)
ppv.set_editor_property('settings', s)
print('lights + sky + exposure placed')

exec(open(os.path.join(P, 'Scripts', 'mh_hand_demo.py')).read())        # spawns PH_MH_Hand with the deformer
# key light like tools/ph.py light_from('dorsal', 6.0, 40.0): grazing onto the back of the hand
ML = unreal.MathLibrary
_hand = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == 'PH_MH_Hand')
_c = _hand.skeletal_mesh_component
_wr = _c.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD).rotation.rotator()
_dorsal = ML.multiply_vector_float(ML.get_right_vector(_wr), -1.0)
_r = ML.make_rot_from_x(ML.multiply_vector_float(_dorsal, -1.0))
sun.set_actor_rotation(unreal.Rotator(roll=0.0, pitch=min(_r.pitch + 10.0, -18.0), yaw=_r.yaw + 40.0), False)
print('sun aimed at the dorsum', sun.get_actor_rotation())
exec(open(os.path.join(P, 'Scripts', 'setup_play_level.py')).read())    # loop anim, PH_PlayCamera, save MAP
print('DEMO_LEVEL_DONE')
