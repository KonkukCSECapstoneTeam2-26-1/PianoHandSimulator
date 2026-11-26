"""Turn deformer stages on PH_MH_Hand on/off from the Output Log (Python) - for finding which stage makes an artefact.

Works on the Play-In-Editor world while playing, otherwise on the editor level. Load once, then call stage():

    exec(open(r'<project>/Scripts/skin_stage_toggle.py').read())
    stage('flesh_correction', False)      # bool stages
    stage('wrinkle_amplitude', 0.0)       # float stages
    stage()                               # print the current values

Stages worth trying for 'wrinkled finger segments': flesh_correction, detail_displacement, wrinkle_amplitude,
palmar_pad_height, palmar_fold2_depth, implicit_skinning, volume_bulge.
"""
import unreal

STAGES = ('flesh_correction', 'detail_displacement', 'wrinkle_amplitude', 'palmar_pad_height',
          'palmar_fold2_depth', 'implicit_skinning', 'volume_bulge')


def _world():
    ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    return ues.get_game_world() or ues.get_editor_world()


def _deformer():
    world = _world()
    for a in unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor):
        if a.get_actor_label() == 'PH_MH_Hand' or a.get_name().startswith('PH_MH_Hand'):
            comp = a.get_component_by_class(unreal.SkeletalMeshComponent)
            d = unreal.PianoHandSkinningLibrary.get_custom_skin_deformer(comp) if comp else None
            if d is not None:
                return d, world
    raise RuntimeError('PH_MH_Hand with a custom skin deformer not found in ' + world.get_name())


def stage(name=None, value=None):
    d, world = _deformer()
    if name is not None:
        old = d.get_editor_property(name)
        d.set_editor_property(name, type(old)(value))
        unreal.log('[stage] %s: %s -> %s (%s)' % (name, old, d.get_editor_property(name), world.get_name()))
    unreal.log('[stage] ' + ' | '.join('%s=%s' % (s, d.get_editor_property(s)) for s in STAGES))
