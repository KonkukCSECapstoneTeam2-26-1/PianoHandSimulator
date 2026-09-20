"""Dump everything the offline map baker needs out of the hand mesh, as JSON.

Run inside the editor:
    exec(open(r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/export_skin_bake_data.py').read())

Writes Scripts/skin_bake_data.json:
    bones      [{name, parent, pos}]         ref-pose component-space bone origins
    uvs        [[u,v] x 3] per triangle      UV set 0
    tris       [[i0,i1,i2]]                  vertex ids
    pos        [[x,y,z]]                     ref-pose vertex positions
    weights    [[[boneIdx, w], ...]]         per vertex, sorted desc by weight

The mesh here is the BASE mesh on purpose: the dense mesh shares its UV layout, so one bake serves
both, and 3.2k verts rasterise in a second.
"""
import unreal, json, os

SRC = '/Game/Characters/MannequinsXR/Meshes/SKM_MannyXR_right'
OUT = r'C:/Git/PianoHandSimulator/06_Project/pianohand_simulator/Scripts/skin_bake_data.json'

src = unreal.load_asset(SRC)
dyn = unreal.DynamicMesh()
opts = unreal.GeometryScriptCopyMeshFromAssetOptions()
lod = unreal.GeometryScriptMeshReadLOD()
lod.set_editor_property('lod_index', 0)
dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(src, dyn, opts, lod)

Q = unreal.GeometryScript_MeshQueries
BW = unreal.GeometryScript_BoneWeights

num_tri = Q.get_num_triangle_i_ds(dyn)
num_vtx = Q.get_vertex_count(dyn)
print('tris=%d verts=%d' % (num_tri, num_vtx))

# --- bones -------------------------------------------------------------------------------------
dyn, bones_info = BW.get_all_bones_info(dyn)
bones = []
for b in bones_info:
    # world_transform is already component space in the ref pose - no parent accumulation needed
    t = b.get_editor_property('world_transform')
    p = t.translation
    bones.append({'name': str(b.get_editor_property('name')),
                  'parent': int(b.get_editor_property('parent_index')),
                  'pos': [float(p.x), float(p.y), float(p.z)]})

# --- geometry ----------------------------------------------------------------------------------
dyn, tri_list, _ = Q.get_all_triangle_indices(dyn, True)
tris = [[int(t.x), int(t.y), int(t.z)]
        for t in unreal.GeometryScript_List.convert_triangle_list_to_array(tri_list)]

dyn, pos_list, _ = Q.get_all_vertex_positions(dyn, True)
pos = [[float(p.x), float(p.y), float(p.z)]
       for p in unreal.GeometryScript_List.convert_vector_list_to_array(pos_list)]

uvs = []
for tid in range(num_tri):
    a, b, c, ok = Q.get_triangle_u_vs(dyn, 0, tid)
    uvs.append([[a.x, a.y], [b.x, b.y], [c.x, c.y]] if ok else None)

weights = []
for vid in range(num_vtx):
    dyn, bw, ok = BW.get_vertex_bone_weights(dyn, vid)
    w = sorted([[int(x.get_editor_property('bone_index')), float(x.get_editor_property('weight'))] for x in bw],
               key=lambda e: -e[1]) if ok else []
    weights.append(w[:4])

data = {'bones': bones, 'tris': tris, 'pos': pos, 'uvs': uvs, 'weights': weights}
with open(OUT, 'w') as f:
    json.dump(data, f)
print('wrote %s (%.1f MB)' % (OUT, os.path.getsize(OUT) / 1e6))
