"""PianoHand Phase 1 demo: custom compute-shader skinning on the Emil skeletal mesh.

Run inside the editor (Python console / unreal-mcp execute_python):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/skin_deformer_demo.py').read())

Spawns two animated Emil meshes side by side:
  * PH_CustomSkin  (left, Y=0)   -> UPianoHandSkinDeformer (our CustomSkinningDeformer.usf kernel)
                                     + Phase 2 tension kernels writing Vertex Color (R stretch / G compression)
                                     + M_PianoHandTension material (grey = rest, red = stretch, blue = compression)
  * PH_EngineSkin  (right, Y=150)-> engine GPU skin cache (reference)

Set SHOW_TENSION = False to keep the mesh's own materials on the custom actor.
"""
import unreal

MESH = '/Game/ExampleContent/5_5_ChaosFlesh/Characters/Emil/Meshes/SKM_skin_coarse'
ANIM = '/Game/ExampleContent/5_5_ChaosFlesh/Characters/Emil/Animation/ANIM_Emil_MH_techROM'
MODE = unreal.PianoHandSkinMode.LINEAR_BLEND   # or DUAL_QUATERNION
SHOW_TENSION = True
TENSION_SCALE = 4.0                            # strain 0.25 (25% stretch) -> fully red
TENSION_MATERIAL = '/Game/PianoHand/M_PianoHandTension'   # created by create_tension_material.py

def spawn(label, y):
    for a in unreal.EditorLevelLibrary.get_all_level_actors():
        if a.get_actor_label() == label:
            unreal.EditorLevelLibrary.destroy_actor(a)
    actor = unreal.EditorLevelLibrary.spawn_actor_from_class(unreal.SkeletalMeshActor, unreal.Vector(0, y, 0), unreal.Rotator(0, 0, 0))
    actor.set_actor_label(label)
    comp = actor.skeletal_mesh_component
    comp.set_skeletal_mesh_asset(unreal.load_asset(MESH))
    comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
    comp.set_animation(unreal.load_asset(ANIM))          # UE 5.6: AnimationData.AnimToPlay is set via SetAnimation()
    comp.set_update_animation_in_editor(True)            # editor ticks the animation without PIE
    comp.set_update_cloth_in_editor(False)
    comp.play(True)
    return actor, comp

custom_actor, custom_comp = spawn('PH_CustomSkin', 0)
engine_actor, engine_comp = spawn('PH_EngineSkin', 150)

deformer = unreal.PianoHandSkinningLibrary.apply_custom_skinning(custom_comp, MODE, SHOW_TENSION, TENSION_SCALE)
print('custom deformer attached:', deformer)

if SHOW_TENSION:
    mat = unreal.load_asset(TENSION_MATERIAL)
    if mat is None:
        print('WARNING: %s not found - run create_tension_material.py first' % TENSION_MATERIAL)
    else:
        for slot in range(custom_comp.get_num_materials()):
            custom_comp.set_material(slot, mat)
        print('tension material applied to %d slot(s)' % custom_comp.get_num_materials())

center = custom_actor.get_actor_location()
unreal.EditorLevelLibrary.set_level_viewport_camera_info(
    center + unreal.Vector(-350, 75, 120), unreal.Rotator(-10, 0, 0))
print('demo spawned; check Output Log (LogPianoHand) for [SkinDeformer] layout line')
