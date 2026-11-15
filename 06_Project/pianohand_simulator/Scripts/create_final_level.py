"""Build /Game/PianoHand/Maps/L_PianoHandFinal: the merged scene (skinning + Chaos Flesh at the joints) with ONLY the
final hand visible.

    exec(open(r'<project>/Scripts/create_final_level.py').read())

Starts from Kyungmin's L_FleshTest (hand + Flesh actor + solver, already wired) and saves a COPY under a new name, so his
test level is never modified. In the copy:
  - PH_MH_Hand gets the skinning deformer with the demo settings (DETAIL / MASK_GROOVE / IMPLICIT of mh_hand_demo.py),
    saved with the level, so no attach script is needed before Play
  - the Flesh sources are hidden in game: the tetrahedral surface, its procedural mesh and the SKM_MH_Hand_R mesh that only
    drives the simulation. They keep simulating / animating; only PH_MH_Hand (the final result) is drawn
  - GC_HandFlesh_Dense (an old comparison geometry cache that is not in the repository) is hidden
  - the Flesh Input component: Enabled, Blend 1 (the strength is the deformer's FleshStrength), tip-error log off
At Play the deformer holds both hands at the reference pose for FleshCalibrationSeconds (Flesh rest capture), then the
animation starts. Output Log: "[SkinDeformer] ... Flesh correction on", "[FleshJoint] ..." (accuracy at the joints).
"""
import unreal

SRC_MAP = '/Game/PianoHand/Maps/L_FleshTest'
DST_MAP = '/Game/PianoHand/Maps/L_PianoHandFinal'
DEMO = unreal.Paths.project_dir() + 'Scripts/mh_hand_demo.py'
ANIM = globals().get('PH_FINAL_ANIM', None)      # e.g. '/Game/Characters/MetaHumanHand/A_MH_Hand_Cycle'; None keeps the level's clip

LES = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
EAS = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
UES = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)


def log(msg):
    unreal.log('[final level] ' + msg)
    print('[final level] ' + msg)


def demo_dicts():
    """DETAIL / MASK_GROOVE / IMPLICIT from mh_hand_demo.py, without running it (it respawns the hand)."""
    src = open(DEMO).read()
    out = {}
    for name in ('DETAIL', 'MASK_GROOVE', 'IMPLICIT'):
        start = src.index(name + ' = dict(')
        depth = 0
        i = start
        while True:
            ch = src[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
                if depth == 0:
                    break
            i += 1
        exec(src[start:i + 1], {}, out)
    return out


LES.load_level(SRC_MAP)
world = UES.get_editor_world()
if not unreal.EditorLoadingAndSavingUtils.save_map(world, DST_MAP):
    raise RuntimeError('could not save ' + DST_MAP)
LES.load_level(DST_MAP)                     # save_map writes the copy but leaves the editor in the source level
world = UES.get_editor_world()
log('working in ' + world.get_path_name())
if 'L_PianoHandFinal' not in world.get_path_name():
    raise RuntimeError('the editor is not in the copy - refusing to touch ' + world.get_path_name())

hand = None
for a in EAS.get_all_level_actors():
    label = a.get_actor_label()
    if label == 'PH_MH_Hand':
        hand = a
    if label == 'GC_HandFlesh_Dense':
        a.set_actor_hidden_in_game(True)
        a.set_is_temporarily_hidden_in_editor(True)
        log('hidden: GC_HandFlesh_Dense')
    for c in a.get_components_by_class(unreal.ActorComponent):
        cls = c.get_class().get_name()
        if cls == 'PianoHandFleshInputComponent':
            c.set_editor_property('enabled', True)
            c.set_editor_property('blend', 1.0)
            c.set_editor_property('log_tip_error', False)
            # the Flesh sources live on this actor: simulate, do not draw
            for pc in a.get_components_by_class(unreal.PrimitiveComponent):
                pc.set_editor_property('hidden_in_game', True)
                if isinstance(pc, unreal.SkeletalMeshComponent):
                    pc.set_editor_property('visibility_based_anim_tick_option',
                                           unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
                    if ANIM:
                        pd = unreal.SingleAnimationPlayData()
                        pd.set_editor_property('anim_to_play', unreal.load_asset(ANIM))
                        pd.set_editor_property('saved_looping', True); pd.set_editor_property('saved_playing', True)
                        pc.set_editor_property('animation_data', pd)
                log('hidden in game: %s.%s' % (label, pc.get_class().get_name()))
            a.set_is_temporarily_hidden_in_editor(True)

if hand is None:
    raise RuntimeError('PH_MH_Hand not in ' + SRC_MAP)
comp = hand.get_component_by_class(unreal.SkeletalMeshComponent)
d = unreal.PianoHandSkinningLibrary.get_custom_skin_deformer(comp)
if d is None:
    unreal.PianoHandSkinningLibrary.apply_custom_skinning(comp, unreal.PianoHandSkinMode.DUAL_QUATERNION, True, 4.0, True)
    d = unreal.PianoHandSkinningLibrary.get_custom_skin_deformer(comp)
dicts = demo_dicts()
for name in ('DETAIL', 'MASK_GROOVE', 'IMPLICIT'):
    for k, v in dicts[name].items():
        try:
            d.set_editor_property(k, v)
        except Exception as exc:
            log('skipped %s: %s' % (k, exc))
d.set_editor_property('wrinkle_mask', unreal.load_asset('/Game/PianoHand/Textures/T_PH_WrinkleMask'))
d.set_editor_property('implicit_skinning', True)
d.set_editor_property('contact_bulge', False)
d.set_editor_property('volume_bulge', 0.15)
d.set_editor_property('skin_mode', unreal.PianoHandSkinMode.DUAL_QUATERNION)
d.set_editor_property('detail_displacement', True)
d.set_editor_property('implicit_tracking', True)
d.set_editor_property('flesh_correction', True)
comp.set_material(0, unreal.load_asset('/Game/PianoHand/MI_PianoHandSkin'))
comp.set_editor_property('hidden_in_game', False)
comp.set_editor_property('visibility_based_anim_tick_option', unreal.VisibilityBasedAnimTickOption.ALWAYS_TICK_POSE_AND_REFRESH_BONES)
if ANIM:
    pd = unreal.SingleAnimationPlayData()
    pd.set_editor_property('anim_to_play', unreal.load_asset(ANIM))
    pd.set_editor_property('saved_looping', True); pd.set_editor_property('saved_playing', True)
    comp.set_editor_property('animation_data', pd)
ad = comp.get_editor_property('animation_data')
log('hand: deformer %s, flesh_correction %s, strength %.2f, animation %s' % (
    d.get_name(), d.get_editor_property('flesh_correction'), d.get_editor_property('flesh_strength'),
    ad.anim_to_play.get_name() if ad and ad.anim_to_play else None))

ok = unreal.EditorLoadingAndSavingUtils.save_map(UES.get_editor_world(), DST_MAP)
log('SAVE_MAP %s %s' % (ok, DST_MAP))
print('FINAL_LEVEL_DONE')
