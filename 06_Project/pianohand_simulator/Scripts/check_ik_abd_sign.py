"""Which way does a +pitch delta on a MetaHuman finger root (xxx_01_r) spread the finger - toward the thumb or the pinky?

The IK program (02_IK, right hand) puts the thumb at z = -0.4 and the pinky at z = +0.8, fingers along +x, and applies
abduction as a rotation about +y. A positive angle turns +x toward -z, so IK abd_deg > 0 = toward the THUMB (radial).
import_ik_csv_to_anim.py writes pitch = SIGN['abd'] * abd_deg, composed in the bone's local frame (delta, then ref).
This script applies pitch = +20 deg to each finger root in the reference pose and measures where its child joint moves
along the index -> pinky MCP line. Output Log line '[abd sign] ... => SIGN abd should be +1 / -1'.

    exec(open(r'<project>/Scripts/check_ik_abd_sign.py').read())
"""
import unreal

REF_MESH = '/Game/Characters/MetaHumanHand/SKM_MH_Hand_R_Dense'
ML = unreal.MathLibrary
TEST_DEG = 20.0

mesh = unreal.load_asset(REF_MESH)
dyn = unreal.DynamicMesh()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property('lod_index', 0)
dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
    mesh, dyn, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
_, infos = unreal.GeometryScript_BoneWeights.get_all_bones_info(dyn)
by_name = {str(b.name): b for b in infos}
by_index = {b.index: b for b in infos}


# GeometryScriptBoneInfo has no global transform in 5.6: chain the local (parent-relative) transforms
_global_cache = {}


def global_of_index(index):
    if index < 0:
        return unreal.Transform()
    if index not in _global_cache:
        b = by_index[index]
        _global_cache[index] = ML.compose_transforms(b.local_transform, global_of_index(b.parent_index))
    return _global_cache[index]


def global_of(name):
    return global_of_index(by_name[name].index)


def child_pos(root, child, delta_pitch):
    """component-space position of `child` when `root` gets a local pitch delta (composed like the importer)"""
    r = by_name[root]
    parent_g = global_of_index(r.parent_index)
    local = r.local_transform
    rot = ML.compose_rotators(unreal.Rotator(roll=0.0, pitch=delta_pitch, yaw=0.0), local.rotation.rotator())
    new_local = unreal.Transform(local.translation, rot, local.scale3d)
    root_g = ML.compose_transforms(new_local, parent_g)
    child_g = ML.compose_transforms(by_name[child].local_transform, root_g)
    return child_g.translation


radial_to_ulnar = global_of('pinky_01_r').translation - global_of('index_01_r').translation
radial_to_ulnar = ML.normal(radial_to_ulnar)

votes = []
for f in ('index', 'middle', 'ring', 'pinky'):
    root, child = f + '_01_r', f + '_02_r'
    base = child_pos(root, child, 0.0)
    moved = child_pos(root, child, TEST_DEG)
    side = ML.dot_vector_vector(moved - base, radial_to_ulnar)          # < 0: toward the thumb, > 0: toward the pinky
    votes.append(side)
    unreal.log('[abd sign] %s: pitch +%.0f moves %s_02 by %+.3f cm along index->pinky (%s)' % (
        f, TEST_DEG, f, side, 'toward THUMB' if side < 0 else 'toward PINKY'))

toward_thumb = sum(1 for s in votes if s < 0)
sign = 1 if toward_thumb >= 3 else (-1 if toward_thumb <= 1 else 0)
unreal.log('[abd sign] UE pitch+ toward thumb on %d/4 fingers; IK abd+ = toward thumb => SIGN abd should be %s' % (
    toward_thumb, {1: '+1 (current, keep)', -1: '-1 (flip)', 0: 'undecided (fingers disagree)'}[sign]))
