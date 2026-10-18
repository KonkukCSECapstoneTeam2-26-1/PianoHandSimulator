"""Bake the PianoHand skin texture set. Runs OUTSIDE the editor (needs numpy/PIL).

    python bake_skin_maps.py <skin_bake_data.json> <out_dir>

Needs numpy, Pillow and opencv-python (the 16-bit RGBA writer). Produces three PNGs that Scripts/import_skin_textures.py then imports as UE textures:

  T_PH_WrinkleMask.png   RGBA 16-bit, mesh UV space, NOT tiling (import as TC_HDR to keep the bits)
     R = weighted joint band  - where creases concentrate, per-finger weights applied
     G = clamp(d / S_RANGE, 0, 1), where d is the UNSIGNED distance ALONG the bone axis to the
         nearest joint band centre (cm). Unsigned and nearest-of-all-joints so it is continuous
         across the hand-over between two joints (see the comment in bake_wrinkle_mask)
     B = joint TYPE code: 0 none, 0.2 MCP, 0.4 PIP, 0.6 DIP, 0.8 thumb MP, 1.0 other (CMC,
         metacarpal, palm, wrist). The three finger joints wrinkle differently - the back of the
         PIP carries several irregular folds, the DIP one or two, the MCP only faint ones, and on
         the palm the PIP crease is double - so the shader needs to know which joint it is on.
         Rasterised NEAREST-vertex (not interpolated) and re-quantised after dilation, so a texel
         never lands between two codes. (This channel used to hold the unweighted raw band, which
         the shader never read.)
     A = 0.5 + 0.5 * dorsality - which SIDE of the joint a texel is on. +1 is the side that
         STRETCHES when the joint flexes (the back of the hand), -1 the side that COMPRESSES
         (the palm). Without this the shader has one crease gate for a band that wraps all the
         way around the joint, so it cannot do what skin actually does: the palm folds as you
         close, while the loose skin over a knuckle gathers as you OPEN and pulls taut as you
         close. Derivation: with flexion a negative rotation of angle theta about the bone's
         local +Z, a point at perpendicular offset h along u = cross(flexAxis, boneDir) changes
         its distance to the proximal segment by about -h*theta, so h > 0 stretches. u is
         therefore the dorsal direction, and dorsality is the cosine of the vertex's
         perpendicular offset against it, averaged over the vertex's influences so it stays
         continuous where the dominant bone changes.

     The band comes straight off the skin weights: with the two largest influences w0,w1,
     4*w0*w1 is 0 on rigid parts and 1 exactly on a joint's 50/50 blend line.

     G is the important one. An earlier version stored the crease DIRECTION and had the shader
     rotate UV space by it; that fails badly, because rotating a global coordinate by a per-pixel
     angle multiplies the angle's variation by the distance from the UV origin and the line field
     shatters into noise. Storing the along-bone coordinate instead means the shader only has to
     evaluate sin(s * frequency): the iso-lines of s are already perpendicular to the bone, so the
     creases run across the finger by construction, and s is smooth, so nothing shatters. s is
     signed and measured from the joint pivot, so it stays continuous across the joint and the
     creases mirror around it the way knuckle creases actually do.

  T_PH_SkinDetail_N.png  RGB tangent-space normal, seamlessly tiling
     Crossed +-60 deg groove network (the diamond micro-relief of real skin) over a fine
     pore/bump layer, domain-warped by periodic fbm so it does not read as a lattice.

  T_PH_Vein_N.png        RGBA tiling
     RGB = tangent-space normal of sparse raised vein ridges
     A   = vein mask (for base-colour tinting)

  T_PH_WrinkleMask2.png  RGBA 16-bit, mesh UV space, NOT tiling (v3 - crease shape, palm lines, identity)
     R = joint SEED, a per-joint hash in 0.05..0.95. Nearest-vertex (categorical): constant over a
         joint's band, so it never interpolates between two joints. The shader uses it to make every
         joint's fold count / phase / fork direction its own - the same pattern repeating on ten
         fingers is what reads as "procedural".
     G = clamp(d / PALM_RANGE, 0, 1), d = distance (cm) to the nearest of the three major palm
         creases (distal palmar, proximal palmar, thenar), 1 = far / not palm. The curves are not
         hand-authored: they are quadratic Beziers placed from the MCP / wrist bone landmarks in a
         hand-local frame (see palm_creases), so they move with the rig and survive a re-bake.
     B = that crease's depth at the nearest point (0..1): each curve tapers towards its ends, and the
         three curves do not share one depth. 0 away from the palm.
     A = L / L_RANGE, L = distance along the hand's distal axis from the wrist (cm), INTERPOLATED and
         continuous over the whole hand. The shader never reads its value - only its UV GRADIENT,
         which it dots with the gradient of mask 1's unsigned s to recover WHICH side of the nearest
         joint a texel is on (s grows with L distal of the band, against it proximal). That sign is
         what lets the primary crease bow towards the fingertip and fork at its ends. A per-vertex
         flag was tried first and failed: a categorical side bit flips on vertex-Voronoi borders, not
         on the s = 0 line, so sign * |s| jumped inside every triangle and the creases came out as a
         zig-zag. Two gradients of two smooth fields flip exactly where they should.

  T_PH_PalmRidge_N.png   RGB tangent-space normal, seamlessly tiling
     Papillary (fingerprint) ridges: one slowly meandering line family, period 1/40 tile. Real ridge
     spacing is ~0.5mm, so at 25cm per UV unit the shader tiles this ~12x.

All noise here is PERIODIC (lattice hashes taken mod the period), which is what makes the two
tiling maps seamless - a plain frac(sin(dot)) hash does not wrap.
"""
import json
import sys

import numpy as np
from PIL import Image

MASK_SIZE = 2048

# Half-range, in cm, of the signed along-bone coordinate stored in G. The shader multiplies back by
# this. G is 8 bits, so the range sets the resolution: +-2cm gives 0.016cm steps, which is what the
# fine PIP furrows (about 0.08cm wide) need; +-3cm was visibly stepped. The creases live within
# +-1cm of a joint anyway.
S_RANGE = 2.0
TILE_SIZE = 1024

# Half-range (cm) of the distance-to-palm-crease field in mask 2's G.
PALM_RANGE = 2.0

# Range (cm) of the along-hand coordinate stored in mask 2's A (wrist cap ~ -2 -> fingertips ~ 20).
L_RANGE = 24.0


def encode_seed(bone_index):
    """Mask 2 R: a per-joint hash in 0.05..0.95."""
    h = ((bone_index * 2654435761) & 0xFFFFFFFF) / float(0xFFFFFFFF)   # Knuth multiplicative hash
    return 0.05 + h * 0.9

# Per-joint crease weighting. The key matches the CHILD bone of the joint (the deeper one).
# Tune these to move where the wrinkles pile up.
FINGER_WEIGHTS = [
    ('_02_',        1.15),   # PIP - the most pronounced finger crease
    ('_01_',        1.00),   # MCP
    ('_03_',        0.90),   # DIP
    ('_metacarpal', 0.50),   # knuckle ridge across the back of the hand
    ('thumb_',      1.00),
    ('palm',        0.35),
    ('wrist',       0.35),
    ('hand_',       0.35),
]
DEFAULT_WEIGHT = 0.6

# Joint type code stored in mask B, keyed by the CHILD bone of the joint. Order matters: the thumb
# bones are also called *_01_/_02_/_03_ and get their own codes.
JOINT_TYPES = [
    ('thumb_01', 1.0),   # CMC, buried in the palm: treat as 'other'
    ('thumb_02', 0.8),   # thumb MP: prominent transverse folds, like a PIP
    ('thumb_03', 0.6),   # thumb IP: one clean line, like a DIP
    ('_01_',     0.2),   # MCP
    ('_02_',     0.4),   # PIP
    ('_03_',     0.6),   # DIP
]
DEFAULT_TYPE = 1.0       # metacarpal / palm / wrist


def joint_type(name):
    low = name.lower()
    for key, code in JOINT_TYPES:
        if key in low:
            return code
    return DEFAULT_TYPE


def joint_weight(name):
    low = name.lower()
    for key, w in FINGER_WEIGHTS:
        if key in low:
            return w
    return DEFAULT_WEIGHT


# ---------------------------------------------------------------------------------------------
# periodic value noise -> seamless tiling
# ---------------------------------------------------------------------------------------------

def _hash2(ix, iy, period, seed):
    """Integer lattice hash that wraps at `period`, so the field tiles exactly."""
    M = np.uint64(0xFFFFFFFF)
    ix = np.mod(ix, period).astype(np.uint64)
    iy = np.mod(iy, period).astype(np.uint64)
    h = (ix * np.uint64(374761393) + iy * np.uint64(668265263) + np.uint64(seed) * np.uint64(2246822519)) & M
    h = ((h ^ (h >> np.uint64(13))) * np.uint64(1274126177)) & M
    h = h ^ (h >> np.uint64(16))
    return (h & np.uint64(0xFFFFFF)).astype(np.float64) / float(0xFFFFFF)


def pnoise(x, y, period, seed):
    ix, iy = np.floor(x), np.floor(y)
    fx, fy = x - ix, y - iy
    fx = fx * fx * (3.0 - 2.0 * fx)
    fy = fy * fy * (3.0 - 2.0 * fy)
    a = _hash2(ix, iy, period, seed)
    b = _hash2(ix + 1, iy, period, seed)
    c = _hash2(ix, iy + 1, period, seed)
    d = _hash2(ix + 1, iy + 1, period, seed)
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def pfbm(x, y, period, seed, octaves=4):
    acc = np.zeros_like(x)
    amp, tot, per = 0.5, 0.0, period
    for o in range(octaves):
        acc += pnoise(x, y, per, seed + o * 17) * amp
        tot += amp
        x, y, per, amp = x * 2.0, y * 2.0, per * 2, amp * 0.5
    return acc / tot


def height_to_normal(h, strength):
    """Central-difference a tiling height field into a tangent-space normal (wraps at the edges)."""
    dx = (np.roll(h, -1, axis=1) - np.roll(h, 1, axis=1)) * 0.5
    dy = (np.roll(h, -1, axis=0) - np.roll(h, 1, axis=0)) * 0.5
    n = np.dstack([-dx * strength, -dy * strength, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    return n


def encode_normal(n):
    return np.clip((n * 0.5 + 0.5) * 255.0, 0, 255).astype(np.uint8)


# ---------------------------------------------------------------------------------------------
# 1) wrinkle concentration + crease direction, rasterised in mesh UV space
# ---------------------------------------------------------------------------------------------

def bake_wrinkle_mask(data, size):
    bones = data['bones']
    pos = np.array(data['pos'], dtype=np.float64)
    tris = np.array(data['tris'], dtype=np.int64)
    uvs = data['uvs']
    weights = data['weights']
    bone_pos = np.array([b['pos'] for b in bones], dtype=np.float64)
    bone_parent = [b['parent'] for b in bones]
    bone_name = [b['name'] for b in bones]
    bone_dorsal = _dorsal_axes(bones)

    n_vtx = len(pos)
    band = np.zeros(n_vtx)
    band_w = np.zeros(n_vtx)
    along = np.zeros(n_vtx)
    dorsal = np.zeros(n_vtx)
    jtype = np.zeros(n_vtx)
    joint_of = np.full(n_vtx, -1, dtype=np.int64)   # child bone naming the joint, for the recentre

    for v, w in enumerate(weights):
        w = [e for e in w if e[1] > 0.0]
        if not w:
            continue
        # Which side of the joint, averaged over every influence so the value stays continuous
        # where the dominant bone hands over. Each influence votes in ITS OWN bone frame.
        acc = tot = 0.0
        for bi, bw in w:
            u, fwd = bone_dorsal[bi]
            r = pos[v] - bone_pos[bi]
            perp = r - fwd * float(r @ fwd)
            n = np.linalg.norm(perp)
            if n > 1e-6:
                acc += bw * float(perp @ u) / n
                tot += bw
        dorsal[v] = acc / tot if tot > 1e-9 else 0.0
        if len(w) < 2:
            # rigidly bound: typed by the joint at the proximal end of its own bone, so the
            # code stays continuous up to the band of the next joint
            jtype[v] = joint_type(bone_name[w[0][0]])
            continue
        (b0, w0), (b1, w1) = w[0], w[1]
        raw = min(1.0, 4.0 * w0 * w1)
        band[v] = raw
        # the joint sits between b0 and b1; the deeper bone names it and is the pivot
        child = b1 if bone_parent[b1] == b0 else (b0 if bone_parent[b0] == b1 else
                                                 (b0 if _depth(bone_parent, b0) > _depth(bone_parent, b1) else b1))
        band_w[v] = raw * joint_weight(bone_name[child])
        jtype[v] = joint_type(bone_name[child])
        joint_of[v] = child
        par = bone_parent[child]
        if par >= 0:
            axis = bone_pos[child] - bone_pos[par]
            n = np.linalg.norm(axis)
            if n > 1e-6:
                # signed distance along the bone from the joint pivot - zero ON the joint, so the
                # crease pattern is continuous across it instead of restarting per segment
                along[v] = float((pos[v] - bone_pos[child]) @ (axis / n))

    # Recentre s on the BAND, not on the bone pivot. The 50/50 skin-weight line of a MetaHuman
    # finger joint sits ~0.5cm proximal of the pivot, and the shader puts its main palm crease and
    # mirrors its knuckle folds about s = 0 - so without this the deepest crease lands at the edge
    # of the band where it is barely visible. Per joint, the band-weighted mean of s is subtracted.
    # The along-bone axis of a joint is the BISECTOR of the two segments it joins (a mitre), not the
    # parent segment alone. MetaHuman's reference pose has the fingers slightly curled (12-20 deg at
    # the PIPs), so a plane square to the proximal phalanx cuts the middle phalanx obliquely: the
    # crease then ran at a slant across the finger and, where the slanted band met the side of the
    # finger at a shallow angle, the material drew a wide dark wedge (first seen on the index PIP).
    # Square to the bisector it is off by half the bend on each side, and there is no seam.
    children_of = {}
    for b, par in enumerate(bone_parent):
        children_of.setdefault(par, []).append(b)

    def joint_axis(child):
        par = bone_parent[child]
        a1 = bone_pos[child] - bone_pos[par]
        n1 = np.linalg.norm(a1)
        if n1 < 1e-6:
            return None
        a1 = a1 / n1
        kids = [k for k in children_of.get(child, []) if np.linalg.norm(bone_pos[k] - bone_pos[child]) > 1e-6]
        if kids:
            a2 = bone_pos[kids[0]] - bone_pos[child]
            a2 = a2 / np.linalg.norm(a2)
            ax = a1 + a2
            n = np.linalg.norm(ax)
            if n > 1e-6:
                return ax / n
        return a1

    # re-measure the first-pass 'along' with the mitre axis so the recentre below uses the same frame
    for v in range(n_vtx):
        child = joint_of[v]
        if child >= 0:
            ax = joint_axis(int(child))
            if ax is not None:
                along[v] = float((pos[v] - bone_pos[child]) @ ax)

    offset = {}
    for child in np.unique(joint_of[joint_of >= 0]):
        sel = joint_of == child
        w = band[sel] ** 4
        if w.sum() > 1e-9:
            offset[int(child)] = float((along[sel] * w).sum() / w.sum())

    # Store the UNSIGNED distance to the NEAREST band centre, over every joint a vertex could
    # belong to (its dominant bone's own joint and that bone's children). The old signed,
    # per-joint value jumped mid-phalanx where the second influence hands over from the parent to
    # the child bone - and the hand-over is not equidistant from the two bands, so the jump was
    # ~0.4cm and the shader's finite difference drew it as a thin zig-zag line. A min over
    # continuous distances is continuous. The crease model only ever used |s| (the primary crease
    # and the fold family are symmetric about the joint), so nothing is lost.
    seed = np.full(n_vtx, 0.05)            # mask 2 R
    to_frame, _ = _hand_frame(bones)
    along_hand = np.array([to_frame(p)[0] for p in pos])   # mask 2 A: distal coordinate, cm
    axis_of = {}
    for child, off in offset.items():
        ax = joint_axis(int(child))
        if ax is not None:
            axis_of[child] = (ax, bone_pos[child] + ax * off)
    for v, w in enumerate(weights):
        w = [e for e in w if e[1] > 0.0]
        if not w:
            continue
        dom = w[0][0]
        # Only joints on the dominant bone's OWN chain: the joint at its proximal end (named by dom)
        # and at its distal end (dom's children). The second influence used to be a candidate too,
        # but at the sides of a finger that influence can belong to the NEIGHBOURING finger, whose
        # joint band then measures as "0 cm away" along its own oblique axis over a wide patch of
        # skin - which the shader drew as a deep triangular wedge beside the index PIP. A parent or
        # child second influence is on the same chain and is already covered.
        cands = [dom] + children_of.get(dom, [])
        if len(w) > 1 and (bone_parent[w[1][0]] == dom or bone_parent[dom] == w[1][0]):
            cands += [w[1][0]] + children_of.get(w[1][0], [])
        best = None
        for j in cands:
            if j not in axis_of:
                continue
            ax, ctr = axis_of[j]
            d = abs(float((pos[v] - ctr) @ ax))
            if best is None or d < best[0]:
                best = (d, j)
        if best is not None:
            along[v] = best[0]
            jtype[v] = joint_type(bone_name[best[1]])
            seed[v] = encode_seed(int(best[1]))
        else:
            seed[v] = encode_seed(int(dom))

    palm_flag = palm_vertex_flags(data, pos, weights, bone_name)

    acc = np.zeros((size, size, 4), dtype=np.float32)
    cov = np.zeros((size, size), dtype=np.float32)

    for t, (i0, i1, i2) in enumerate(tris):
        uv = uvs[t]
        if uv is None:
            continue
        pts = [np.array(x, dtype=np.float64) for x in uv]
        vals = [(band_w[vi], along[vi], jtype[vi], dorsal[vi]) for vi in (i0, i1, i2)]
        _raster(acc, cov, size, pts, vals, nearest=(2,))

    mask = np.zeros((size, size, 4), dtype=np.float32)
    hit = cov > 0
    mask[hit] = acc[hit] / cov[hit][:, None]
    mask = _dilate(mask, hit, 6)
    # the type code must never sit between two codes: re-quantise after the dilation blur
    mask[..., 2] = np.round(mask[..., 2] * 5.0) / 5.0

    # 16 bits per channel. G is a coordinate that the shader turns into furrows ~0.08cm wide; at 8
    # bits over +-S_RANGE a level is 0.016cm and the furrows come out visibly stepped.
    out = np.zeros((size, size, 4), dtype=np.uint16)
    out[..., 0] = np.clip(mask[..., 0], 0, 1) * 65535
    out[..., 1] = np.clip(mask[..., 1] / S_RANGE, 0, 1) * 65535
    out[..., 2] = np.clip(mask[..., 2], 0, 1) * 65535
    out[..., 3] = np.clip(mask[..., 3] * 0.5 + 0.5, 0, 1) * 65535

    # ---- mask 2: seed (categorical), palm crease distance, palm crease depth, along-hand coordinate
    # The palm crease distance is computed PER TEXEL from the texel's interpolated hand-frame
    # position, not per vertex: the base mesh has 4.8k vertices, and a distance field sampled at
    # them and interpolated across 0.6 cm triangles has an iso-line that zig-zags along the
    # triangle edges - a sawtooth along every palm crease at 4K.
    to_frame_fn, _ = _hand_frame(bones)
    frame_xyz = np.array([to_frame_fn(p) for p in pos])
    acc2 = np.zeros((size, size, 4), dtype=np.float32)
    cov2 = np.zeros((size, size), dtype=np.float32)
    accf = np.zeros((size, size, 4), dtype=np.float32)    # hand-frame x, y, z (interpolated), palm flag (nearest)
    covf = np.zeros((size, size), dtype=np.float32)
    for t, (i0, i1, i2) in enumerate(tris):
        uv = uvs[t]
        if uv is None:
            continue
        pts = [np.array(x, dtype=np.float64) for x in uv]
        vals = [(seed[vi], 0.0, 0.0, along_hand[vi]) for vi in (i0, i1, i2)]
        _raster(acc2, cov2, size, pts, vals, nearest=(0,))
        fvals = [(frame_xyz[vi][0], frame_xyz[vi][1], frame_xyz[vi][2], palm_flag[vi]) for vi in (i0, i1, i2)]
        _raster(accf, covf, size, pts, fvals, nearest=(3,))
    mask2 = np.zeros((size, size, 4), dtype=np.float32)
    hit2 = cov2 > 0
    mask2[hit2] = acc2[hit2] / cov2[hit2][:, None]
    framef = np.zeros((size, size, 4), dtype=np.float32)
    framef[hit2] = accf[hit2] / covf[hit2][:, None]
    palm_d, palm_amp = palm_crease_texels(bones, framef, hit2)
    mask2[..., 1] = palm_d
    mask2[..., 2] = palm_amp
    mask2[..., 1][~hit2] = PALM_RANGE          # empty texels read as "far from any palm crease"
    mask2 = _dilate(mask2, hit2, 6)

    out2 = np.zeros((size, size, 4), dtype=np.uint16)
    out2[..., 0] = np.clip(mask2[..., 0], 0, 1) * 65535
    out2[..., 1] = np.clip(mask2[..., 1] / PALM_RANGE, 0, 1) * 65535
    out2[..., 2] = np.clip(mask2[..., 2], 0, 1) * 65535
    out2[..., 3] = np.clip((mask2[..., 3] + 2.0) / L_RANGE, 0, 1) * 65535   # wrist cap sits ~2cm proximal of hand_r
    return out, out2, float(hit.mean())


# ---------------------------------------------------------------------------------------------
# 1b) the three major palm creases, from bone landmarks
# ---------------------------------------------------------------------------------------------

def _hand_frame(bones):
    """Origin at hand_r; x points distally (wrist -> fingers), y across the palm towards the LITTLE
    finger (the thumb is at negative y), z towards the back of the hand. All unit, component space."""
    by_name = {b['name']: b for b in bones}
    hand = by_name['hand_r']
    origin = np.array(hand['pos'], dtype=np.float64)
    fwd = np.array(hand['fwd'], dtype=np.float64)
    flex = np.array(hand['flex'], dtype=np.float64)
    fwd /= np.linalg.norm(fwd)
    dorsal = np.cross(flex, fwd)
    dorsal /= np.linalg.norm(dorsal)
    ulnar = np.cross(dorsal, fwd)
    ulnar /= np.linalg.norm(ulnar)

    def to_frame(p):
        r = np.asarray(p, dtype=np.float64) - origin
        return np.array([r @ fwd, r @ ulnar, r @ dorsal])
    return to_frame, by_name


def _bezier(p0, p1, p2, n=2000):   # dense: the texel distance field is to the nearest POINT, so the spacing must be far under the furrow width
    t = np.linspace(0.0, 1.0, n)[:, None]
    return (1 - t) ** 2 * p0 + 2 * (1 - t) * t * p1 + t ** 2 * p2


def palm_creases(bones):
    """The distal palmar, proximal palmar and thenar creases as polylines in the hand frame (x, y),
    each with a depth profile along its length. Placed from the MCP joints and the wrist.

    Anatomy, palm up, right hand: the distal palmar crease starts at the ulnar edge about 1.5cm
    proximal of the little-finger MCP, runs radially under the ring and middle MCPs about 1-1.5cm
    proximal of the joints and fades out between the index and middle fingers. The proximal palmar
    crease starts at the radial edge below the index MCP, crosses the palm more obliquely and fades
    under the ring / little fingers. The thenar crease leaves the same radial start, bows around
    the ball of the thumb and runs down to the middle of the wrist. The last two often meet at the
    radial end, which is why they share it here."""
    to_frame, by_name = _hand_frame(bones)
    mcp = {k: to_frame(by_name[k + '_01_r']['pos'])[:2] for k in ('index', 'middle', 'ring', 'pinky')}
    wrist = np.array([0.6, -0.2])

    distal = _bezier(
        np.array([mcp['pinky'][0] - 1.5, mcp['pinky'][1] + 0.5]),
        np.array([(mcp['ring'][0] + mcp['middle'][0]) * 0.5 - 0.9, (mcp['ring'][1] + mcp['middle'][1]) * 0.5 + 0.2]),
        np.array([(mcp['index'][0] + mcp['middle'][0]) * 0.5 - 1.3, (mcp['index'][1] + mcp['middle'][1]) * 0.5 - 0.3]))
    radial_start = np.array([mcp['index'][0] - 1.4, mcp['index'][1] - 1.1])
    proximal = _bezier(
        radial_start,
        np.array([mcp['middle'][0] - 2.4, mcp['middle'][1] - 0.2]),
        np.array([mcp['ring'][0] - 3.3, mcp['pinky'][1] - 0.6]))
    thenar = _bezier(
        radial_start + np.array([-0.3, 0.0]),
        np.array([wrist[0] + 2.6, mcp['index'][1] - 1.8]),
        wrist + np.array([0.6, 0.0]))   # 10-18: ends 1.2 cm distal of hand_r, inside the wrist gate

    def taper(n, head, tail, depth):
        t = np.linspace(0.0, 1.0, n)
        return depth * np.clip(np.minimum(t / max(head, 1e-3), (1.0 - t) / max(tail, 1e-3)), 0.0, 1.0) ** 0.7

    return [
        (distal,   taper(len(distal),   0.12, 0.45, 1.0)),    # fades gently towards the index side
        (proximal, taper(len(proximal), 0.15, 0.35, 0.9)),
        (thenar,   taper(len(thenar),   0.20, 0.25, 0.8)),
    ]


def palm_vertex_flags(data, pos, weights, bone_name):
    """1 on vertices whose dominant bone is a palm bone (hand, metacarpals, thumb base, proximal
    phalanges), 0 elsewhere. Rasterised nearest-vertex, it gates where the palm creases may be drawn."""
    palm_bones = {i for i, nm in enumerate(bone_name)
                  if nm.lower() in ('hand_r', 'thumb_01_r') or 'metacarpal' in nm.lower() or nm.lower().endswith('_01_r')}
    flag = np.zeros(len(pos))
    for v, w in enumerate(weights):
        w = [e for e in w if e[1] > 0.0]
        if w and w[0][0] in palm_bones:
            flag[v] = 1.0
    return flag


def palm_crease_texels(bones, framef, hit):
    """Per texel: distance (cm, in the palm plane) to the nearest palm crease and that crease's depth
    there, from the texel's interpolated hand-frame position. Only texels on the PALMAR side
    (z < -0.25) of palm bones take part; everything else reads as PALM_RANGE / 0."""
    from scipy.spatial import cKDTree
    size = framef.shape[0]
    dist = np.full((size, size), PALM_RANGE, dtype=np.float32)
    amp = np.zeros((size, size), dtype=np.float32)
    curves = palm_creases(bones)
    pts = np.concatenate([c for c, _ in curves])
    amps = np.concatenate([a for _, a in curves])
    # 10-18: the hard palmar threshold (z < -0.25) and the nearest-vertex palm flag cut the thenar crease
    # with a sawtooth edge where it wraps onto the radial side of the wrist - from the play camera that
    # read as a slit in the skin. Both gates are smooth now: the amplitude fades out towards the side of
    # the hand (z -0.7 .. -0.2) and towards the wrist (x 0.6 .. 1.6 cm distal of hand_r); the flag only
    # keeps the field off the fingers.
    z = framef[..., 2]
    x = framef[..., 0]
    side_gate = np.clip((-0.2 - z) / 0.5, 0.0, 1.0)
    side_gate = side_gate * side_gate * (3.0 - 2.0 * side_gate)
    wrist_gate = np.clip((x - 0.6) / 1.0, 0.0, 1.0)
    wrist_gate = wrist_gate * wrist_gate * (3.0 - 2.0 * wrist_gate)
    sel = hit & (framef[..., 3] > 0.5) & (side_gate > 1e-3) & (wrist_gate > 1e-3)
    if sel.any():
        q = framef[sel][:, :2]
        d, k = cKDTree(pts).query(q)
        dist[sel] = np.minimum(d, PALM_RANGE)
        amp[sel] = amps[k] * side_gate[sel] * wrist_gate[sel]
    return dist, amp


def _dorsal_axes(bones):
    """Per bone: (dorsal direction, bone direction), both unit, in component space."""
    out = []
    for b in bones:
        fwd = np.array(b.get('fwd', [1.0, 0.0, 0.0]), dtype=np.float64)
        flex = np.array(b.get('flex', [0.0, 0.0, 1.0]), dtype=np.float64)
        nf = np.linalg.norm(fwd)
        fwd = fwd / nf if nf > 1e-9 else np.array([1.0, 0.0, 0.0])
        u = np.cross(flex, fwd)
        nu = np.linalg.norm(u)
        u = u / nu if nu > 1e-9 else np.array([0.0, 0.0, 1.0])
        out.append((u, fwd))
    return out


def _depth(parents, b):
    d = 0
    while parents[b] >= 0 and d < 64:
        b = parents[b]
        d += 1
    return d


def _raster(acc, cov, size, uv, vals, nearest=()):
    """Scanline-free barycentric rasteriser over the triangle's UV bounding box.

    Channels listed in `nearest` take the value of the closest vertex (largest barycentric weight)
    instead of interpolating - for categorical data such as the joint type code."""
    # UE's UV origin is the TOP-left of the texture and V grows downward, which is already the
    # image row order - do NOT flip V here. Flipping it puts the bake in the wrong half of the
    # atlas and the material then samples empty texels (a flat, uniform mask).
    pts = np.array([[u[0] * size, u[1] * size] for u in uv])
    x0, y0 = np.floor(pts.min(axis=0)).astype(int) - 1
    x1, y1 = np.ceil(pts.max(axis=0)).astype(int) + 1
    x0, y0 = max(x0, 0), max(y0, 0)
    x1, y1 = min(x1, size), min(y1, size)
    if x1 <= x0 or y1 <= y0:
        return

    xs = np.arange(x0, x1) + 0.5
    ys = np.arange(y0, y1) + 0.5
    gx, gy = np.meshgrid(xs, ys)

    (ax, ay), (bx, by), (cx, cy) = pts
    det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
    if abs(det) < 1e-12:
        return
    l0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / det
    l1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / det
    l2 = 1.0 - l0 - l1
    inside = (l0 >= -1e-6) & (l1 >= -1e-6) & (l2 >= -1e-6)
    if not inside.any():
        return

    v = np.array(vals)          # 3 x 4
    near = np.argmax(np.stack([l0, l1, l2]), axis=0)
    for ch in range(4):
        if ch in nearest:
            val = np.choose(near, [np.full_like(l0, v[0, ch]), np.full_like(l0, v[1, ch]), np.full_like(l0, v[2, ch])])
        else:
            val = l0 * v[0, ch] + l1 * v[1, ch] + l2 * v[2, ch]
        acc[y0:y1, x0:x1, ch] += np.where(inside, val, 0.0)
    cov[y0:y1, x0:x1] += inside.astype(np.float64)


def _dilate(img, hit, iterations):
    """Bleed covered texels outward so bilinear filtering never samples an empty texel at a UV seam."""
    img = img.copy()
    filled = hit.copy()
    for _ in range(iterations):
        acc = np.zeros_like(img)
        cnt = np.zeros(filled.shape, dtype=np.float64)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            s = np.roll(np.roll(img, dy, 0), dx, 1)
            m = np.roll(np.roll(filled, dy, 0), dx, 1)
            acc += s * m[..., None]
            cnt += m
        new = (~filled) & (cnt > 0)
        img[new] = acc[new] / cnt[new][:, None]
        filled |= new
    return img


# ---------------------------------------------------------------------------------------------
# 2) tiling skin detail normal
# ---------------------------------------------------------------------------------------------

def bake_skin_detail(size):
    u = (np.arange(size) + 0.5) / size
    gx, gy = np.meshgrid(u, u)
    P = 16                                    # noise lattice period in tile units

    wx = (pfbm(gx * P, gy * P, P, 11) - 0.5) * 2.4
    wy = (pfbm(gx * P + 3.7, gy * P + 9.1, P, 29) - 0.5) * 2.4

    # crossed groove network: +-60 deg line sets, union (max) -> a mesh of grooves, not dots
    fx, fy = gx * P + wx, gy * P + wy
    d1 = 0.5 * fx + 0.866 * fy
    d2 = 0.5 * fx - 0.866 * fy
    n1 = 1.0 - np.abs(np.sin(d1 * np.pi * 2.0))
    n2 = 1.0 - np.abs(np.sin(d2 * np.pi * 2.0))
    grooves = -np.power(np.clip(np.maximum(n1, n2), 0, 1), 3.0)
    grooves *= np.clip(0.45 + (pfbm(gx * P * 0.5, gy * P * 0.5, P, 5) - 0.5) * 2.5, 0, 1)

    pores = (pfbm(gx * P * 4, gy * P * 4, P * 4, 77, octaves=2) - 0.5) * 0.35

    h = grooves + pores
    # Strength is picked so the steepest slope lands near 0.5 (about 27 degrees). A groove here is
    # ~10 texels wide with a height step of ~0.3, so a central difference gives ~0.3 per texel -
    # anything above ~2 here turns skin into hammered metal.
    n = height_to_normal(h, strength=1.7)
    return encode_normal(n)


# ---------------------------------------------------------------------------------------------
# 3) tiling vein normal + mask
# ---------------------------------------------------------------------------------------------

def bake_veins(size):
    u = (np.arange(size) + 0.5) / size
    gx, gy = np.meshgrid(u, u)
    P = 8

    wx = (pfbm(gx * P, gy * P, P, 101) - 0.5) * 3.0
    wy = (pfbm(gx * P + 5.3, gy * P + 1.9, P, 211) - 0.5) * 3.0

    # one sparse, wide, meandering ridge set - veins branch far less than creases
    s = np.sin((gx * P + wx) * np.pi * 2.0 * 0.6 + (gy * P + wy) * np.pi * 0.7)
    ridge = np.power(np.clip(1.0 - np.abs(s), 0, 1), 7.0)
    ridge *= np.clip(0.2 + (pfbm(gx * P * 0.5, gy * P * 0.5, P, 3) - 0.5) * 3.0, 0, 1)

    # veins are wider and shallower than creases, so they take a slightly higher gain for the
    # same visual slope
    n = height_to_normal(ridge, strength=2.8)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., :3] = encode_normal(n)
    out[..., 3] = np.clip(ridge / max(ridge.max(), 1e-6), 0, 1) * 255
    return out


# ---------------------------------------------------------------------------------------------
# 4) tiling palm (papillary) ridge normal
# ---------------------------------------------------------------------------------------------

def bake_palm_ridges(size):
    """Fingerprint-style ridges: ONE line family (unlike the crossed grooves of the back of the
    hand) whose direction drifts slowly, so the field reads as flowing ridges and not a grating.
    The ridge count per tile (40) is what the shader's RidgeTiling is calibrated against."""
    u = (np.arange(size) + 0.5) / size
    gx, gy = np.meshgrid(u, u)
    P = 8
    RIDGES = 40.0
    # slow 2D warp: bends the ridges into the meanders of a real print without breaking periodicity
    wx = (pfbm(gx * P, gy * P, P, 401, octaves=3) - 0.5) * 2.0
    wy = (pfbm(gx * P + 2.9, gy * P + 7.3, P, 409, octaves=3) - 0.5) * 2.0
    phase = (gx * P + wx) * (RIDGES / P) + 0.35 * (gy * P + wy) * (RIDGES / P)
    ridge = np.sin(phase * np.pi * 2.0)
    # rounded crests, slightly sharper valleys (sweat-gland pores sit on the crests; not modelled)
    h = np.sign(ridge) * np.abs(ridge) ** 0.8 * 0.5
    # local interruptions - ridge endings and bifurcations, which every print has
    # kept mild: a print is ridges everywhere with SHORT interruptions, not islands of ridges
    gaps = np.clip((pfbm(gx * P * 3, gy * P * 3, P * 3, 421, octaves=2) - 0.5) * 4.0 + 1.0, 0.45, 1)
    h *= gaps
    n = height_to_normal(h, strength=2.2)
    return encode_normal(n)


def main():
    src, out_dir = sys.argv[1], sys.argv[2]
    data = json.load(open(src))

    mask, mask2, coverage = bake_wrinkle_mask(data, MASK_SIZE)
    # PIL cannot write 16-bit RGBA; OpenCV can (it wants BGRA order)
    import cv2
    cv2.imwrite(out_dir + '/T_PH_WrinkleMask.png', mask[..., [2, 1, 0, 3]])
    print('T_PH_WrinkleMask  %dx%d  UV coverage %.1f%%  (G range 0..%.1fcm unsigned, B = joint type, A = dorsal side)'
          % (MASK_SIZE, MASK_SIZE, coverage * 100, S_RANGE))
    cv2.imwrite(out_dir + '/T_PH_WrinkleMask2.png', mask2[..., [2, 1, 0, 3]])
    print('T_PH_WrinkleMask2 %dx%d  (R = joint seed, G = palm crease distance 0..%.1fcm, B = palm crease depth, A = along-hand / %.0fcm)'
          % (MASK_SIZE, MASK_SIZE, PALM_RANGE, L_RANGE))

    Image.fromarray(bake_palm_ridges(TILE_SIZE), 'RGB').save(out_dir + '/T_PH_PalmRidge_N.png')
    print('T_PH_PalmRidge_N  %dx%d  tiling' % (TILE_SIZE, TILE_SIZE))

    Image.fromarray(bake_skin_detail(TILE_SIZE), 'RGB').save(out_dir + '/T_PH_SkinDetail_N.png')
    print('T_PH_SkinDetail_N %dx%d  tiling' % (TILE_SIZE, TILE_SIZE))

    Image.fromarray(bake_veins(TILE_SIZE), 'RGBA').save(out_dir + '/T_PH_Vein_N.png')
    print('T_PH_Vein_N       %dx%d  tiling (A = vein mask)' % (TILE_SIZE, TILE_SIZE))


if __name__ == '__main__':
    main()
