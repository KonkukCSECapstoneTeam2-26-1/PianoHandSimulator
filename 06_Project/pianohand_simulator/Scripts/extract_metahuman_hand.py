"""Cut the right hand out of the MetaHuman template body and build a dense skeletal mesh for the
Phase 3 skinning pipeline.

    exec(open('<project>/Scripts/extract_metahuman_hand.py').read())      # Windows or macOS

Why MetaHuman rather than MannyXR: the MetaHuman hand chain carries per-joint helper bones
(_bulge, _half, _side_out, _side_inn, _pip, _dip, _mcp, _palm, _palmMid), so the joint band we
derive from skin weights (4*w0*w1) follows real anatomy instead of a single two-bone blend line.
The mesh also has clean non-overlapping UVs, which the wrinkle-mask bake needs.

Pipeline
  1. copy SKM_Body LOD 0 into a dynamic mesh (bone weights come along)
  2. keep a triangle when all three of its vertices carry >HAND_WEIGHT of their skin weight on
     hand_r's chain (hand / thumb / index / middle / ring / pinky / wrist bones on SIDE)
  3. delete every other triangle
  4. collapse helper-bone weights onto the primary joints (see below)
  5. repack the remaining UV islands into 0..1 - MetaHuman body UVs sit in UDIM tile u=1..2 and
     the hand is a small, sparse patch of it (a straight rescale of the bounding box still only
     covered 10% of the texture). Repacking moves and rotates whole islands without touching their
     internal parametrisation, so no new distortion and no new seams; nothing authored is lost
     because MetaHuman ships no baked body colour/normal to stay aligned with.
  6. PLANE-CUT the wrist (2026-10-13). The weight threshold in step 2 leaves a stair-stepped
     boundary of whole triangles that wanders 0.7 cm along the arm, and the PN tessellation then
     turns every step into a tooth - the "jagged wrist cap" visible in every screenshot since
     Phase 3b. A plane perpendicular to the hand bone, WRIST_CUT_CM proximal of hand_r, replaces
     that boundary with a straight one; the hole is filled flat.
  7. the cap is an interior surface nobody should see: its triangles get one constant UV (a single
     texel of the wrinkle mask, flat normal) and a rigid hand_r weight
  8. PN tessellate to give the geometric wrinkles vertices to live on. (A second plane cut after
     tessellation was tried and dropped: it leaves sliver triangles whose strain tensor explodes in
     the deformer, a fringe of spikes along the wrist.)
  9. write a new skeletal mesh asset on the same metahuman_base_skel

Why collapse the helper bones: the joint band both the compute shader and the offline baker use is
4*w0*w1 over the two largest influences - 0 on a rigid segment, 1 on the 50/50 blend line between
two segments. MetaHuman skins a hand vertex to ~7.5 bones, most of them helpers (_bulge, _half,
_side_out, _side_inn, _pip, _dip, _mcp, _palm, _slide) that belong to ONE segment, so the two
largest weights can both sit on the same joint and the band reads 1 in the middle of a flat
phalanx. The helpers are also driven by RigLogic, which our AnimSequence does not run, so at
playback they are rigid children of their parent and contribute nothing. Folding each helper's
weight into its nearest primary ancestor restores a clean 2-3 influence skin without changing the
deformation we actually get.

Produces /Game/Characters/MetaHumanHand/SKM_MH_Hand_R (+ _Dense).
"""
import time
import unreal

SRC = '/MetaHumanCharacter/Body/IdentityTemplate/SKM_Body'
DST_DIR = '/Game/Characters/MetaHumanHand'
BASE_NAME = 'SKM_MH_Hand_R'
DENSE_NAME = 'SKM_MH_Hand_R_Dense'

SIDE = '_r'
HAND_TOKENS = ('hand_', 'thumb_', 'index_', 'middle_', 'ring_', 'pinky_', 'wrist_')
HAND_WEIGHT = 0.5        # a vertex belongs to the hand when this much of its weight is on the chain
# bones the skinning is allowed to keep; every other hand bone folds into its nearest ancestor here
PRIMARY = set(['hand_r', 'thumb_01_r', 'thumb_02_r', 'thumb_03_r'] +
              ['%s_%s_r' % (f, j) for f in ('index', 'middle', 'ring', 'pinky')
               for j in ('metacarpal', '01', '02', '03')])
TESS_LEVEL = 3           # PN tessellation level; N => (N+1)^2 triangles per source triangle
PACK_RESOLUTION = 2048   # gutter width the UV repacker leaves between islands
CAP_UV = 0.02            # the single texel the wrist cap samples
SLIVER_EDGE_CM = 0.12    # edges shorter than this on the cut ring are collapsed (dense mesh edge ~0.15 cm)
WRIST_CUT_CM = 0.35      # cm proximal of the hand_r origin where the wrist is cut flat (the ragged
                         # weight boundary lies 0.5-1.2 cm proximal, so this takes all of it off)

Q = unreal.GeometryScript_MeshQueries
BW = unreal.GeometryScript_BoneWeights
SEL = unreal.GeometryScript_MeshSelection
EDIT = unreal.GeometryScript_MeshEdits
UVS = unreal.GeometryScript_UVs
LIST = unreal.GeometryScript_List
eal = unreal.EditorAssetLibrary

_log_lines = []


def log(msg):
    print(msg)
    _log_lines.append(str(msg))


def stats(label, mesh):
    log('%-8s tris=%-7d verts=%-7d uv_sets=%d' % (
        label, Q.get_num_triangle_i_ds(mesh), Q.get_vertex_count(mesh), Q.get_num_uv_sets(mesh)))


def is_hand_bone(name):
    return name.endswith(SIDE) and any(tok in name for tok in HAND_TOKENS)


def load_body_mesh():
    src = unreal.load_asset(SRC)
    if src is None:
        raise RuntimeError('MetaHuman body not found: ' + SRC + '  (is the MetaHumanCharacter plugin enabled?)')
    mesh = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property('lod_index', 0)
    mesh, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
        src, mesh, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    return src, mesh


def hand_vertex_mask(mesh):
    _, bones = BW.get_all_bones_info(mesh)
    chain = set(b.index for b in bones if is_hand_bone(str(b.name)))
    log('hand chain: %d bones' % len(chain))
    count = Q.get_num_vertex_i_ds(mesh)
    mask = bytearray(count)
    for vid in range(count):
        _, weights, ok = BW.get_vertex_bone_weights(mesh, vid)
        if not ok:
            continue
        if sum(e.weight for e in weights if e.bone_index in chain) > HAND_WEIGHT:
            mask[vid] = 1
    log('hand vertices: %d / %d' % (sum(mask), count))
    return mask


def collapse_helper_bones(mesh):
    """Fold every helper bone's weight into its nearest PRIMARY ancestor."""
    _, bones = BW.get_all_bones_info(mesh)
    parent = [b.parent_index for b in bones]
    names = [str(b.name) for b in bones]
    hand_index = names.index('hand' + SIDE)
    target = {}
    for i, name in enumerate(names):
        if not is_hand_bone(name):
            # forearm bones (lowerarm, its twist helpers): 30% of the wrist ring's weight. There is
            # no forearm in this mesh, and the cap is rigid on hand_r, so any wrist rotation in the
            # animation opened a strain step across the cut ring - the volume term turned it into a
            # fringe of spikes. The cut region is rigid with the hand.
            target[i] = hand_index
            continue
        walk = i
        while walk >= 0 and names[walk] not in PRIMARY:
            walk = parent[walk]
        target[i] = walk if walk >= 0 else i

    before = after = moved = 0
    count = Q.get_num_vertex_i_ds(mesh)
    for vid in range(count):
        _, weights, ok = BW.get_vertex_bone_weights(mesh, vid)
        if not ok or not weights:
            continue
        merged = {}
        for e in weights:
            dst = target[e.bone_index]
            merged[dst] = merged.get(dst, 0.0) + e.weight
        before += len(weights)
        after += len(merged)
        if len(merged) != len(weights):
            moved += 1
        total = sum(merged.values()) or 1.0
        out = []
        for idx, w in sorted(merged.items(), key=lambda kv: -kv[1])[:8]:
            entry = unreal.GeometryScriptBoneWeight()
            entry.set_editor_property('bone_index', idx)
            entry.set_editor_property('weight', w / total)
            out.append(entry)
        BW.set_vertex_bone_weights(mesh, vid, out)
    log('collapsed influences %.2f -> %.2f per vertex (%d vertices changed)' % (
        before / max(count, 1), after / max(count, 1), moved))
    return mesh


def cut_to_hand(mesh, mask):
    _, tri_list, _ = Q.get_all_triangle_indices(mesh, True)
    tris = LIST.convert_triangle_list_to_array(tri_list)
    drop = [i for i, t in enumerate(tris) if not (mask[t.x] and mask[t.y] and mask[t.z])]
    _, selection = SEL.convert_index_array_to_mesh_selection(
        mesh, drop, unreal.GeometryScriptMeshSelectionType.TRIANGLES)
    mesh, deleted = EDIT.delete_selected_triangles_from_mesh(mesh, selection)
    log('deleted %d of %d triangles' % (deleted, len(tris)))
    return mesh


def _uv_area(mesh):
    r = Q.get_mesh_uv_area(mesh, 0)
    return float(r[1]) if isinstance(r, tuple) else float(r)


def _uv_islands(mesh):
    r = Q.get_num_uv_islands(mesh, 0)
    return int(r[1]) if isinstance(r, tuple) else int(r)


def normalize_weights(mesh, label):
    """Make every vertex's influences sum to 1. The plane cut interpolates weights onto the new
    ring vertices WITHOUT renormalising, so they skin to a fraction of the pose while their
    neighbours skin fully - a 0.2 cm step every other vertex along the ring, which the strain
    tensor reads as a huge deformation and the volume term turns into a fringe of spikes."""
    fixed = 0
    for vid in range(Q.get_num_vertex_i_ds(mesh)):
        _, weights, ok = BW.get_vertex_bone_weights(mesh, vid)
        if not ok or not weights:
            continue
        total = sum(e.weight for e in weights)
        if abs(total - 1.0) < 1e-4 or total <= 0.0:
            continue
        out = []
        for e in weights:
            entry = unreal.GeometryScriptBoneWeight()
            entry.set_editor_property('bone_index', e.bone_index)
            entry.set_editor_property('weight', e.weight / total)
            out.append(entry)
        BW.set_vertex_bone_weights(mesh, vid, out)
        fixed += 1
    log('%s: renormalised %d vertices' % (label, fixed))
    return mesh


def wrist_plane(mesh):
    """(point, distal direction) of the wrist cut plane, from the hand_r bone of the mesh."""
    _, bones = BW.get_all_bones_info(mesh)
    hand = next(b for b in bones if str(b.name) == 'hand_r')
    t = hand.world_transform
    fwd = unreal.MathLibrary.get_forward_vector(t.rotation.rotator())
    distal = unreal.MathLibrary.multiply_vector_float(fwd, -1.0)       # bones run down local -X
    point = t.translation + unreal.MathLibrary.multiply_vector_float(distal, -WRIST_CUT_CM)
    return point, distal


def plane_cut_wrist(mesh, fill, plane):
    """Cut everything proximal of the wrist plane. The frame's +Z is the side that is deleted.
    `plane` comes from wrist_plane() on the base mesh: the tessellated copy has no bone table."""
    point, distal = plane
    proximal = unreal.MathLibrary.multiply_vector_float(distal, -1.0)
    frame = unreal.Transform(point, unreal.MathLibrary.make_rot_from_z(proximal), unreal.Vector(1, 1, 1))
    opts = unreal.GeometryScriptMeshPlaneCutOptions()
    opts.set_editor_property('fill_holes', fill)
    opts.set_editor_property('fill_spans', False)
    before = Q.get_vertex_count(mesh)
    before_ids = set(tid for tid in range(Q.get_num_triangle_i_ds(mesh)) if Q.is_valid_triangle_id(mesh, tid))
    mesh = unreal.GeometryScript_MeshBooleans.apply_mesh_plane_cut(mesh, frame, opts)
    # The cut splits the boundary triangles into slivers; PN tessellation turns every sliver into a
    # spike (the "fur" along the wrist). Collapse edges shorter than SLIVER_EDGE_CM and recompute
    # the normals PN will interpolate from.
    dopts = unreal.GeometryScriptDegenerateTriangleOptions()
    dopts.set_editor_property('min_edge_length', SLIVER_EDGE_CM)
    dopts.set_editor_property('min_triangle_area', SLIVER_EDGE_CM * SLIVER_EDGE_CM * 0.1)
    dopts.set_editor_property('compact_on_completion', True)
    mesh = unreal.GeometryScript_MeshRepair.repair_mesh_degenerate_geometry(mesh, dopts)
    try:
        mesh = unreal.GeometryScript_Normals.recompute_normals(mesh, unreal.GeometryScriptCalculateNormalsOptions())
    except Exception as exc:
        log('recompute_normals skipped: %s' % exc)
    after = Q.get_vertex_count(mesh)
    if after < before * 0.5:
        raise RuntimeError('plane cut removed the hand (%d -> %d verts): the kept side is wrong' % (before, after))
    cap = [tid for tid in range(Q.get_num_triangle_i_ds(mesh))
           if Q.is_valid_triangle_id(mesh, tid) and tid not in before_ids] if fill else []
    if fill and not cap:
        # the plane cut's own fill gives up on a boundary with more than one loop (the tessellated
        # cap ring); the generic hole filler does not
        ids = set(tid for tid in range(Q.get_num_triangle_i_ds(mesh)) if Q.is_valid_triangle_id(mesh, tid))
        mesh, filled, failed = unreal.GeometryScript_MeshRepair.fill_all_mesh_holes(mesh, unreal.GeometryScriptFillHolesOptions())
        cap = [tid for tid in range(Q.get_num_triangle_i_ds(mesh)) if Q.is_valid_triangle_id(mesh, tid) and tid not in ids]
        log('  hole filler: %d filled, %d failed' % (filled, failed))
    log('wrist plane cut %.2f cm proximal of hand_r: %d -> %d verts, %d cap tris' % (WRIST_CUT_CM, before, after, len(cap)))
    return mesh, cap


def flatten_cap(mesh, cap):
    """The cap is an interior surface nobody should see: one constant UV (a single mask texel,
    flat normal) and a rigid hand_r weight for any vertex the fill created."""
    before_verts = Q.get_num_vertex_i_ds(mesh)

    flat = unreal.Vector2D(CAP_UV, CAP_UV)
    tri_uv = unreal.GeometryScriptUVTriangle()
    tri_uv.set_editor_property('uv0', flat)
    tri_uv.set_editor_property('uv1', flat)
    tri_uv.set_editor_property('uv2', flat)
    for tid in cap:
        UVS.set_mesh_triangle_u_vs(mesh, 0, tid, tri_uv)

    try:
        _, bones = BW.get_all_bones_info(mesh)
        hand_index = next(b.index for b in bones if str(b.name) == 'hand_r')
    except Exception:
        hand_index = flatten_cap.hand_index
    flatten_cap.hand_index = hand_index
    rigid = unreal.GeometryScriptBoneWeight()
    rigid.set_editor_property('bone_index', hand_index)
    rigid.set_editor_property('weight', 1.0)
    fixed = 0
    for vid in range(Q.get_num_vertex_i_ds(mesh)):
        _, weights, ok = BW.get_vertex_bone_weights(mesh, vid)
        if ok and not weights:
            BW.set_vertex_bone_weights(mesh, vid, [rigid])
            fixed += 1
    log('cap flattened: %d cap tris, %d vertices weighted to hand_r' % (len(cap), fixed))
    return mesh


def repack_uvs(mesh):
    before, _, _ = Q.get_uv_set_bounding_box(mesh, 0)
    area_before = _uv_area(mesh)
    opts = unreal.GeometryScriptRepackUVsOptions()
    opts.set_editor_property('target_image_width', PACK_RESOLUTION)
    opts.set_editor_property('optimize_island_rotation', True)
    mesh = UVS.repack_mesh_u_vs(mesh, 0, opts)
    after, _, _ = Q.get_uv_set_bounding_box(mesh, 0)
    log('uv islands=%d  bbox %.3f..%.3f x %.3f..%.3f -> %.3f..%.3f x %.3f..%.3f  area %.3f -> %.3f'
        % (_uv_islands(mesh),
           before.min.x, before.max.x, before.min.y, before.max.y,
           after.min.x, after.max.x, after.min.y, after.max.y,
           area_before, _uv_area(mesh)))
    return mesh


def write_asset(src, mesh, name):
    path = DST_DIR + '/' + name
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    opts = unreal.GeometryScriptCreateNewSkeletalMeshAssetOptions()
    opts.set_editor_property('use_mesh_bone_proportions', False)
    opts.set_editor_property('use_original_vertex_order', False)
    opts.set_editor_property('enable_recompute_normals', True)
    opts.set_editor_property('enable_recompute_tangents', True)
    opts.set_editor_property('apply_nanite_settings', False)   # Nanite bypasses the passthrough vertex factory
    asset, outcome = unreal.GeometryScript_NewAssetUtils.create_new_skeletal_mesh_asset_from_mesh(
        mesh, src.get_editor_property('skeleton'), path, opts)
    log('%s -> %s (%s)' % (name, asset, outcome))
    if asset is not None:
        try:
            asset.set_editor_property('materials', src.get_editor_property('materials'))
        except Exception as exc:
            log('material slot copy skipped: %s' % exc)
        eal.save_asset(path)
    return asset


def run():
    start = time.time()
    src, mesh = load_body_mesh()
    stats('body', mesh)
    mesh = cut_to_hand(mesh, hand_vertex_mask(mesh))
    stats('hand', mesh)
    mesh = collapse_helper_bones(mesh)
    plane = wrist_plane(mesh)
    mesh, _ = plane_cut_wrist(mesh, False, plane)      # straight open boundary
    mesh = normalize_weights(mesh, 'after cut')
    mesh = repack_uvs(mesh)                            # the cap is not part of the packing
    mesh, cap = plane_cut_wrist(mesh, True, plane)     # no-op cut, fills the hole flat
    mesh = flatten_cap(mesh, cap)
    mesh = normalize_weights(mesh, 'base')
    stats('base', mesh)
    write_asset(src, mesh, BASE_NAME)

    mesh = unreal.GeometryScript_MeshSubdivide.apply_pn_tessellation(
        mesh, unreal.GeometryScriptPNTessellateOptions(), TESS_LEVEL)
    # No second cut: slicing the tessellated ring leaves sliver triangles whose strain tensor explodes
    # in the deformer (a fringe of spikes along the wrist). The PN bulge on the cap ring is a smooth
    # bevel and is left alone.
    mesh = normalize_weights(mesh, 'dense')
    stats('dense', mesh)
    write_asset(src, mesh, DENSE_NAME)
    log('done in %.1fs' % (time.time() - start))


try:
    run()
finally:
    import os
    here = os.path.join(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()), 'Scripts')
    try:
        with open(os.path.join(here, 'mh_hand_extract.log'), 'w', encoding='utf-8') as fh:
            fh.write('\n'.join(_log_lines))
    except Exception as exc:
        print('log write failed:', exc)
