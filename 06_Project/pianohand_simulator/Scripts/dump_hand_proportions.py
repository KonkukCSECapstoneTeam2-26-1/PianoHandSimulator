"""Dump MetaHuman right-hand segment lengths so the IK program can use the same proportions.

Run in the editor (Output Log > Python console):
    exec(open(r'<project>/Scripts/dump_hand_proportions.py').read())

Lengths are |parent-relative translation| of the child bone in the reference pose (cm), i.e. the distance between
consecutive joints. Result is printed and written to Saved/hand_proportions.txt (IK-ratio table included).
"""
import os

import unreal

REF_MESH = '/Game/Characters/MetaHumanHand/SKM_MH_Hand_R_Dense'
FINGERS = ['index', 'middle', 'ring', 'pinky']


def load_bones():
    mesh = unreal.load_asset(REF_MESH)
    dyn = unreal.DynamicMesh()
    lod = unreal.GeometryScriptMeshReadLOD()
    lod.set_editor_property('lod_index', 0)
    dyn, _ = unreal.GeometryScript_AssetUtils.copy_mesh_from_skeletal_mesh(
        mesh, dyn, unreal.GeometryScriptCopyMeshFromAssetOptions(), lod)
    _, bones = unreal.GeometryScript_BoneWeights.get_all_bones_info(dyn)
    return {str(b.name): b for b in bones}


def run():
    bones = load_bones()

    def seg(name):
        b = bones.get(name)
        return b.local_transform.translation.length() if b else None

    def pos(name):
        """component-space position by chaining parent-relative transforms (translation only, rotation applied)"""
        chain = []
        cur = bones.get(name)
        by_index = {b.index: b for b in bones.values()}
        while cur is not None:
            chain.append(cur)
            cur = by_index.get(cur.parent_index) if cur.parent_index >= 0 else None
        t = unreal.Transform()
        for b in chain:                      # child -> root
            t = unreal.MathLibrary.compose_transforms(t, b.local_transform)
        return t.translation

    lines = ['bone segment lengths, cm (reference pose of %s)' % REF_MESH.split('/')[-1],
             '%-8s %9s %9s %9s %9s | ratio 01:02:03' % ('finger', 'meta', '01->02', '02->03', '03->tip')]
    rows = {}
    for f in ['thumb'] + FINGERS:
        names = ['%s_%s_r' % (f, s) for s in ('01', '02', '03')]
        meta = seg('%s_metacarpal_r' % f) if f != 'thumb' else None
        l12, l23 = seg(names[1]), seg(names[2])
        # the tip has no bone; use the farthest vertex-free estimate = dist(03, nearest child) if present, else None
        tip = None
        for cand in ('%s_04_r' % f, '%s_tip_r' % f, '%s_end_r' % f):
            if cand in bones:
                tip = seg(cand)
                break
        rows[f] = (meta, l12, l23, tip)
        fmt = lambda v: '%9.2f' % v if v is not None else '%9s' % '-'
        ratio = ''
        if l12 and l23 and tip:
            s = l12 + l23 + tip
            ratio = '%.3f : %.3f : %.3f' % (l12 / s, l23 / s, tip / s)
        lines.append('%-8s %s %s %s %s | %s' % (f, fmt(meta), fmt(l12), fmt(l23), fmt(tip), ratio))

    # knuckle spacing across the palm and palm length
    hand = pos('hand_r')
    lines.append('')
    lines.append('palm (hand_r -> <finger>_01_r) and knuckle spacing, cm')
    knuckles = {}
    for f in FINGERS:
        k = pos('%s_01_r' % f)
        knuckles[f] = k
        lines.append('%-8s palm length %.2f   (x,y,z from hand_r: %.2f, %.2f, %.2f)' % (
            f, (k - hand).length(), k.x - hand.x, k.y - hand.y, k.z - hand.z))
    for a, b in zip(FINGERS, FINGERS[1:]):
        lines.append('knuckle gap %s-%s: %.2f' % (a, b, (knuckles[a] - knuckles[b]).length()))

    text = '\n'.join(lines)
    print(text)
    out = os.path.join(unreal.Paths.project_saved_dir(), 'hand_proportions.txt')
    with open(out, 'w', encoding='utf-8') as fh:
        fh.write(text + '\n')
    print('-> ' + out)


run()
