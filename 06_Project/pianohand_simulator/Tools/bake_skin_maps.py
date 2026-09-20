"""Bake the PianoHand skin texture set. Runs OUTSIDE the editor (needs numpy/PIL).

    python bake_skin_maps.py <skin_bake_data.json> <out_dir>

Produces three PNGs that Scripts/import_skin_textures.py then imports as UE textures:

  T_PH_WrinkleMask.png   RGBA, mesh UV space, NOT tiling
     R = weighted joint band  - where creases concentrate, per-finger weights applied
     G = 0.5 + 0.5 * clamp(s / S_RANGE, -1, 1), where s is the signed distance ALONG the joint's
         bone axis, measured from the joint pivot (cm)
     B = raw joint band (4*w0*w1), unweighted
     A = 1

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

All noise here is PERIODIC (lattice hashes taken mod the period), which is what makes the two
tiling maps seamless - a plain frac(sin(dot)) hash does not wrap.
"""
import json
import sys

import numpy as np
from PIL import Image

MASK_SIZE = 2048

# Half-range, in cm, of the signed along-bone coordinate stored in G. Finger segments are 2-4cm,
# so +-3cm covers a whole segment either side of a knuckle. The shader multiplies back by this.
S_RANGE = 3.0
TILE_SIZE = 1024

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

    n_vtx = len(pos)
    band = np.zeros(n_vtx)
    band_w = np.zeros(n_vtx)
    along = np.zeros(n_vtx)

    for v, w in enumerate(weights):
        w = [e for e in w if e[1] > 0.0]
        if len(w) < 2:
            continue
        (b0, w0), (b1, w1) = w[0], w[1]
        raw = min(1.0, 4.0 * w0 * w1)
        band[v] = raw
        # the joint sits between b0 and b1; the deeper bone names it and is the pivot
        child = b1 if bone_parent[b1] == b0 else (b0 if bone_parent[b0] == b1 else
                                                 (b0 if _depth(bone_parent, b0) > _depth(bone_parent, b1) else b1))
        band_w[v] = raw * joint_weight(bone_name[child])
        par = bone_parent[child]
        if par >= 0:
            axis = bone_pos[child] - bone_pos[par]
            n = np.linalg.norm(axis)
            if n > 1e-6:
                # signed distance along the bone from the joint pivot - zero ON the joint, so the
                # crease pattern is continuous across it instead of restarting per segment
                along[v] = float((pos[v] - bone_pos[child]) @ (axis / n))

    acc = np.zeros((size, size, 4), dtype=np.float32)
    cov = np.zeros((size, size), dtype=np.float32)

    for t, (i0, i1, i2) in enumerate(tris):
        uv = uvs[t]
        if uv is None:
            continue
        pts = [np.array(x, dtype=np.float64) for x in uv]
        vals = [(band_w[vi], along[vi], band[vi], 1.0) for vi in (i0, i1, i2)]
        _raster(acc, cov, size, pts, vals)

    mask = np.zeros((size, size, 4), dtype=np.float32)
    hit = cov > 0
    mask[hit] = acc[hit] / cov[hit][:, None]
    mask = _dilate(mask, hit, 6)

    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., 0] = np.clip(mask[..., 0], 0, 1) * 255
    out[..., 1] = np.clip(mask[..., 1] / S_RANGE * 0.5 + 0.5, 0, 1) * 255
    out[..., 2] = np.clip(mask[..., 2], 0, 1) * 255
    out[..., 3] = 255
    return out, float(hit.mean())


def _depth(parents, b):
    d = 0
    while parents[b] >= 0 and d < 64:
        b = parents[b]
        d += 1
    return d


def _raster(acc, cov, size, uv, vals):
    """Scanline-free barycentric rasteriser over the triangle's UV bounding box."""
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
    for ch in range(4):
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


def main():
    src, out_dir = sys.argv[1], sys.argv[2]
    data = json.load(open(src))

    mask, coverage = bake_wrinkle_mask(data, MASK_SIZE)
    Image.fromarray(mask, 'RGBA').save(out_dir + '/T_PH_WrinkleMask.png')
    print('T_PH_WrinkleMask  %dx%d  UV coverage %.1f%%  (G range +-%.1fcm)'
          % (MASK_SIZE, MASK_SIZE, coverage * 100, S_RANGE))

    Image.fromarray(bake_skin_detail(TILE_SIZE), 'RGB').save(out_dir + '/T_PH_SkinDetail_N.png')
    print('T_PH_SkinDetail_N %dx%d  tiling' % (TILE_SIZE, TILE_SIZE))

    Image.fromarray(bake_veins(TILE_SIZE), 'RGBA').save(out_dir + '/T_PH_Vein_N.png')
    print('T_PH_Vein_N       %dx%d  tiling (A = vein mask)' % (TILE_SIZE, TILE_SIZE))


if __name__ == '__main__':
    main()
