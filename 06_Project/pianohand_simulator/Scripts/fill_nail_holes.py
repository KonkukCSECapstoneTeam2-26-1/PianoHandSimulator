"""Close the nail-bed holes of the extracted MetaHuman hand meshes in place.

    exec(open('<project>/Scripts/fill_nail_holes.py').read())

The MetaHumanCharacter identity template body (SKM_Body) has no nails: the nail beds are open holes
in the mesh, and extract_metahuman_hand.py kept them. Seen from the fingertip side they read as dark
cavities. This fills every remaining hole (the wrist is already capped) and gives the new triangles
the UV and the bone weights of the hole's rim, so the cap skins and shades like the skin around it.
The result is written to a NEW asset next to the source (<name>_Nails); the source is never deleted
or overwritten. EXPERIMENTAL (2026-10-15): the first version deleted the source and re-created it
in place, and create_new_skeletal_mesh_asset_from_mesh crashed the editor on the 4-triangle base
cap ("Critical error" right after the build), which lost the working-tree SKM_MH_Hand_R (restored
from git cfb8b69, the pre-wrist-fix extraction). Run only with the editor's assets saved and with
tools/crashcheck.sh watching; do not point the demo at the _Nails asset until it is verified.
"""
import time
import unreal

Q = unreal.GeometryScript_MeshQueries
BW = unreal.GeometryScript_BoneWeights
UVS = unreal.GeometryScript_UVs
eal = unreal.EditorAssetLibrary
DST_DIR = '/Game/Characters/MetaHumanHand'
NAMES = ['SKM_MH_Hand_R', 'SKM_MH_Hand_R_Dense']


def log(msg):
    unreal.log('[fill_nail_holes] ' + msg)


def load(path):
    asset = unreal.load_asset(path)
    mesh = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property('lod_index', 0)
    mesh, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
        asset, mesh, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return asset, mesh


def fill(mesh):
    n_verts = Q.get_num_vertex_i_ds(mesh)
    n_tris = Q.get_num_triangle_i_ds(mesh)
    before = set(t for t in range(n_tris) if Q.is_valid_triangle_id(mesh, t))
    opts = unreal.GeometryScriptFillHolesOptions()
    opts.set_editor_property('fill_method', unreal.GeometryScriptFillHolesMethod.POLYGON_TRIANGULATION)
    mesh, filled, failed = unreal.GeometryScript_MeshRepair.fill_all_mesh_holes(mesh, opts)
    new_tris = [t for t in range(Q.get_num_triangle_i_ds(mesh)) if Q.is_valid_triangle_id(mesh, t) and t not in before]
    log('holes: %d filled, %d failed -> %d new triangles, %d new vertices' % (
        filled, failed, len(new_tris), Q.get_num_vertex_i_ds(mesh) - n_verts))
    if not new_tris:
        return mesh, 0
    # per-vertex UV of the old vertices (split UVs collapse to one of their values, fine for a cap)
    res = UVS.get_mesh_per_vertex_u_vs(mesh, 0)
    uv_list = res[1]                                   # (mesh, uv_list, is_valid, has_gaps, has_splits)
    uvs = list(uv_list.convert_uv_list_to_array())
    assigned_uv = {}
    assigned_w = {}
    # new vertices take the UV / weights of an old vertex in the same triangle; triangles made only
    # of new vertices (the fan centre) inherit from a neighbouring one in a second pass
    for _ in range(3):
        for tid in new_tris:
            res = Q.get_triangle_indices(mesh, tid)
            ids = res[0] if isinstance(res, tuple) else res
            vids = [ids.x, ids.y, ids.z]
            olds = [v for v in vids if v < n_verts]
            donors = olds + [v for v in vids if v in assigned_uv]
            if not donors:
                continue
            d = donors[0]
            duv = uvs[d] if d < n_verts else assigned_uv[d]
            if d < n_verts:
                _, dw, ok = BW.get_vertex_bone_weights(mesh, d)
                dw = list(dw) if ok else []
            else:
                dw = assigned_w[d]
            for v in vids:
                if v >= n_verts and v not in assigned_uv:
                    assigned_uv[v] = duv
                    assigned_w[v] = dw
    fixed = 0
    for v, w in assigned_w.items():
        if w:
            BW.set_vertex_bone_weights(mesh, v, w)
            fixed += 1
    for tid in new_tris:
        res = Q.get_triangle_indices(mesh, tid)
        ids = res[0] if isinstance(res, tuple) else res
        vids = [ids.x, ids.y, ids.z]
        tri_uv = unreal.GeometryScriptUVTriangle()
        for k, v in enumerate(vids):
            uv = uvs[v] if v < n_verts else assigned_uv.get(v, unreal.Vector2D(0.02, 0.02))
            tri_uv.set_editor_property('uv%d' % k, uv)
        UVS.set_mesh_triangle_u_vs(mesh, 0, tid, tri_uv)
    log('cap vertices weighted: %d, cap triangles UV-ed: %d' % (fixed, len(new_tris)))
    return mesh, len(new_tris)


def write_back(asset, mesh, name):
    path = DST_DIR + '/' + name + '_Nails'          # never touch the source asset
    skeleton = asset.get_editor_property('skeleton')
    materials = asset.get_editor_property('materials')
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewSkeletalMeshAssetOptions()
    opts.set_editor_property('use_mesh_bone_proportions', False)
    opts.set_editor_property('use_original_vertex_order', False)
    opts.set_editor_property('enable_recompute_normals', True)
    opts.set_editor_property('enable_recompute_tangents', True)
    opts.set_editor_property('apply_nanite_settings', False)
    new_asset, outcome = unreal.GeometryScript_NewAssetUtils.create_new_skeletal_mesh_asset_from_mesh(mesh, skeleton, path, opts)
    log('%s -> %s (%s)' % (name, new_asset, outcome))
    if new_asset is not None:
        try:
            new_asset.set_editor_property('materials', materials)
        except Exception as exc:
            log('material slot copy skipped: %s' % exc)
        eal.save_asset(path)
    return new_asset


def run():
    t0 = time.time()
    for name in NAMES:
        asset, mesh = load(DST_DIR + '/' + name)
        log('%s: %d tris %d verts' % (name, Q.get_num_triangle_i_ds(mesh), Q.get_num_vertex_i_ds(mesh)))
        mesh, n_new = fill(mesh)
        if n_new > 0:
            write_back(asset, mesh, name)
    log('done in %.1fs' % (time.time() - t0))
    print('NAILS_DONE')


run()
