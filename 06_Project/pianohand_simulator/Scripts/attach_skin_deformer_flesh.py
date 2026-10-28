"""Attach Sumin's skinning deformer to PH_MH_Hand in the open level (needed before the Flesh blend can run).

    exec(open(r'<project>/Scripts/attach_skin_deformer_flesh.py').read())

Only attaches the deformer and prints whether it is there; does not change her demo settings beyond the defaults of
PianoHandSkinningLibrary.apply_custom_skinning. Save the level afterwards (Ctrl+S) so PIE gets it.
"""
import unreal

ELL = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
LABEL = 'PH_MH_Hand'
DETAIL = dict(
    crease_depth=0.0, crease_sharpness=4.5, crease_compression_gain=0.9, crease_stretch_relief=2.2,
    wrinkle_amplitude=0.012, wrinkle_frequency=6.0, volume_bulge=0.35, tensor_smooth_iterations=3,
    bulge_gain=0.0, relax_gain=12.0, relax_tau=0.9, relax_crease_gain=0.03,
)

hand = next((a for a in ELL.get_all_level_actors() if a.get_actor_label() == LABEL), None)
if hand is None:
    unreal.log_warning('[attach deformer] no actor labelled ' + LABEL)
else:
    comp = hand.get_component_by_class(unreal.SkeletalMeshComponent)
    existing = unreal.PianoHandSkinningLibrary.get_custom_skin_deformer(comp)
    if existing is None:
        unreal.PianoHandSkinningLibrary.apply_custom_skinning(comp, unreal.PianoHandSkinMode.LINEAR_BLEND, True, 8.0, True)
        existing = unreal.PianoHandSkinningLibrary.get_custom_skin_deformer(comp)
        unreal.log('[attach deformer] attached to ' + LABEL + ': ' + str(existing))
    else:
        unreal.log('[attach deformer] already attached to ' + LABEL + ': ' + str(existing))
    # same tuning as Scripts/mh_hand_demo.py (DETAIL), otherwise the library defaults give lumpy skin
    for k, v in DETAIL.items():
        existing.set_editor_property(k, v)
    unreal.log('[attach deformer] hidden_in_game=' + str(comp.get_editor_property('hidden_in_game')))
