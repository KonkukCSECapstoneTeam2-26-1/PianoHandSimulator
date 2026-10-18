"""Densify the hand skeletal mesh so the Phase 3 geometric wrinkles have vertices to live on.

Run inside the editor (needs the GeometryScripting plugin enabled in the .uproject):
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/subdivide_hand.py').read())

Why not Nanite tessellation: our skinning writes into the GPU-skin passthrough vertex factory, which a
Nanite mesh does not render through, so turning Nanite on would bypass the whole custom pipeline
(and r.Nanite.AllowTessellation is off by default in 5.6 anyway). The way to raise real geometric
density and keep the pipeline is to subdivide the asset, carrying the skin weights across - PN
tessellation does that and keeps the silhouette smooth.

Produces /Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right_Dense.
"""
import unreal

SRC = '/Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right'
DST_PKG = '/Game/Characters/MannequinsXR/Meshes'
DST_NAME = 'SKM_MannyXR_right_Dense'
DST = DST_PKG + '/' + DST_NAME
TESS_LEVEL = 3            # PN tessellation level; N => (N+1)^2 triangles per source triangle

eal = unreal.EditorAssetLibrary

def _stats(label, m):
    q = unreal.GeometryScript_MeshQueries
    tris = q.get_num_triangle_i_ds(m)
    verts = q.get_vertex_count(m)
    try:
        has_w = unreal.GeometryScript_BoneWeights.mesh_has_bone_weights(m)
    except Exception as e:
        has_w = 'n/a (%s)' % e
    print('%-7s tris=%d verts=%d  bone weights=%s' % (label, tris, verts, has_w))


src = unreal.load_asset(SRC)
if src is None:
    raise RuntimeError('source mesh not found: ' + SRC)

# 1) skeletal mesh LOD 0 -> dynamic mesh (bone weights come along)
dyn = unreal.DynamicMesh()
opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property('lod_index', 0)
dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(src, dyn, opts, lod)
_stats('source', dyn)

# 2) PN tessellate - smooth subdivision that keeps the silhouette and interpolates attributes
tess = unreal.GeometryScriptPNTessellateOptions()
dyn = unreal.GeometryScript_MeshSubdivide.apply_pn_tessellation(dyn, tess, TESS_LEVEL)
_stats('dense', dyn)

# 3) dynamic mesh -> new skeletal mesh asset reusing the same skeleton
if eal.does_asset_exist(DST):
    eal.delete_asset(DST)

create_opts = unreal.GeometryScriptCreateNewSkeletalMeshAssetOptions()
create_opts.set_editor_property('use_mesh_bone_proportions', False)
create_opts.set_editor_property('use_original_vertex_order', False)
create_opts.set_editor_property('enable_recompute_normals', True)
create_opts.set_editor_property('enable_recompute_tangents', True)
create_opts.set_editor_property('apply_nanite_settings', False)
# carry the source material slots over so the dense mesh renders with the same slots
try:
    create_opts.set_editor_property('materials', [m.material_interface for m in src.get_editor_property('materials')])
except Exception as e:
    print('materials option skipped:', e)

new_mesh, outcome = unreal.GeometryScript_NewAssetUtils.create_new_skeletal_mesh_asset_from_mesh(
    dyn, src.get_editor_property('skeleton'), DST, create_opts)
print('create outcome:', outcome, '->', new_mesh)

if new_mesh is not None:
    try:
        new_mesh.set_editor_property('materials', src.get_editor_property('materials'))
    except Exception as e:
        print('material slot copy skipped:', e)
    eal.save_asset(DST)
    print('saved', DST)
