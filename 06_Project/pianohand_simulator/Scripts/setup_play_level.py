"""Make the demo playable: the hand loops A_MH_Hand_Cycle on BeginPlay, a camera auto-activates for
player 0 framed like the Vaillant 2013 video, and the level is saved as /Game/PianoHand/Maps/L_PianoHandDemo.

    exec(open('<project>/Scripts/setup_play_level.py').read())

Run after mh_hand_demo.py (the PH_MH_Hand actor with its PianoHandSkinDeformer must exist). The deformer is
outered to the skeletal mesh component, so it is saved with the level and duplicated into PIE; the implicit
skinning data is rebuilt lazily by the PIE instance on its first frame (~1 s hitch).
"""
import unreal
ML = unreal.MathLibrary
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
MAP = '/Game/PianoHand/Maps/L_PianoHandDemo'
ANIM = '/Game/Characters/MetaHumanHand/A_MH_Hand_Cycle'

hand = next(a for a in EAS.get_all_level_actors() if a.get_actor_label() == 'PH_MH_Hand')
comp = hand.skeletal_mesh_component
# --- animation: single node, looping, playing - stored in AnimationData so BeginPlay (PIE / game) starts it
pd = unreal.SingleAnimationPlayData()
pd.set_editor_property('anim_to_play', unreal.load_asset(ANIM))
pd.set_editor_property('saved_looping', True)
pd.set_editor_property('saved_playing', True)
pd.set_editor_property('saved_position', 0.0)
pd.set_editor_property('saved_play_rate', 1.0)
comp.set_editor_property('animation_mode', unreal.AnimationMode.ANIMATION_SINGLE_NODE)
comp.set_editor_property('animation_data', pd)
comp.set_animation(unreal.load_asset(ANIM))
comp.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
comp.play(True)
print('hand: looping', ANIM)

# --- camera: thumb side, a little above the back of the hand, fingers to screen-left (ref_view2 in tools/ph.py)
wrist = comp.get_socket_transform('hand_r', unreal.RelativeTransformSpace.RTS_WORLD)
rot = wrist.rotation.rotator()
dorsal = ML.multiply_vector_float(ML.get_right_vector(rot), -1.0)
side = ML.get_up_vector(rot)
distal = ML.get_forward_vector(rot)
mid = comp.get_socket_transform('middle_01_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
if ML.dot_vector_vector(distal, mid - wrist.translation) < 0:
    distal = ML.multiply_vector_float(distal, -1.0)
thumb = comp.get_socket_transform('thumb_01_r', unreal.RelativeTransformSpace.RTS_WORLD).translation
if ML.dot_vector_vector(side, thumb - wrist.translation) < 0:
    side = ML.multiply_vector_float(side, -1.0)
target = wrist.translation + ML.multiply_vector_float(distal, 6.5)
d = ML.normal(ML.multiply_vector_float(side, 0.75) + ML.multiply_vector_float(dorsal, 0.45) + ML.multiply_vector_float(distal, 0.3))
eye = target + ML.multiply_vector_float(d, 16.0)
cam_rot = ML.make_rot_from_xy(ML.normal(target - eye), ML.multiply_vector_float(distal, -1.0))
for a in EAS.get_all_level_actors():
    if a.get_actor_label() == 'PH_PlayCamera':
        EAS.destroy_actor(a)
cam = EAS.spawn_actor_from_class(unreal.CameraActor, eye, cam_rot)
cam.set_actor_label('PH_PlayCamera')
cam.set_editor_property('auto_activate_for_player', unreal.AutoReceiveInput.PLAYER0)
cc = cam.get_component_by_class(unreal.CameraComponent)
cc.set_editor_property('field_of_view', 60.0)
cc.set_editor_property('constrain_aspect_ratio', False)
print('camera at', eye, cam_rot)

# --- a neutral backdrop behind the hand (the sky atmosphere is black below the horizon and the camera looks down)
for a in EAS.get_all_level_actors():
    if a.get_actor_label() == 'PH_Backdrop':
        EAS.destroy_actor(a)
bd_pos = target - ML.multiply_vector_float(d, 45.0) + unreal.Vector(0, 0, -10.0)
bd = EAS.spawn_actor_from_class(unreal.StaticMeshActor, bd_pos, ML.make_rot_from_z(d))   # plane normal (+Z) faces the camera
bd.set_actor_label('PH_Backdrop')
bd.set_actor_scale3d(unreal.Vector(4.0, 4.0, 1.0))                                        # 400 x 400 cm
bmc = bd.get_component_by_class(unreal.StaticMeshComponent)
bmc.set_static_mesh(unreal.load_asset('/Engine/BasicShapes/Plane'))
bmc.set_material(0, unreal.load_asset('/Engine/BasicShapes/BasicShapeMaterial'))
bmc.set_editor_property('cast_shadow', False)
print('backdrop at', bd_pos)

# --- no grid / no backdrop plane in play, and no auto exposure drift
world = UES.get_editor_world()
unreal.SystemLibrary.execute_console_command(world, 'r.DefaultFeature.AutoExposure 0')

# --- save as a real map (the demo runs in an untitled temp level)
ok = unreal.EditorLoadingAndSavingUtils.save_map(world, MAP)
print('SAVE_MAP', ok, MAP)
print('PLAY_LEVEL_DONE')
