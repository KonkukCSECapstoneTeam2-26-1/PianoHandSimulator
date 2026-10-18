"""Graph-based wrinkle synthesis for the hand (Weiss et al. 2023, "Graph-Based Synthesis for Skin
Micro Wrinkles", SGP / CGF 42(5)), driven by the baked joint / palm fields. Runs OUTSIDE the
editor (needs numpy, scipy, Pillow, opencv-python).

    python simulate_wrinkle_graph.py <skin_bake_data.json> <Textures dir> <out dir> [--seed N]

Why a graph and not a formula
------------------------------
Up to v3 every crease was a periodic function of the baked along-bone coordinate s. A formula has
a domain, and where the domain ends the line ends: creases cut off at the sides of the fingers,
kinked where a sign flipped, and repeated the same shape on ten fingers. Weiss et al. instead
treat wrinkles as PATHS on a graph: pores are nodes, k-nearest-neighbour links are candidate
wrinkles, and an iterative "trail formation" walk (Helbing et al. 1997/2001) deposits weight on
the edges it uses, preferring to continue a strong incoming edge (long connected lines), avoiding
T-junctions and crossings, and following an orientation prior. Lines then start, branch and end
the way trails do - on the graph, never at a formula's border.

What this tool changes relative to the paper
---------------------------------------------
The paper's orientation prior is the facial flow line field and its deposit is uniform. Here both
come from our bakes:
  * orientation prior   = the iso-lines of the joint coordinate s (perpendicular to the bone) on the
                          fingers, and the iso-lines of the palm-crease distance field on the palm
  * deposit propensity  = where creases belong: the joint band (scaled per joint type), the palm
                          crease depth profile, and a faint floor everywhere so a fine network can
                          still form
Two levels are simulated: a coarse one for the primary knuckle creases and palm lines, a fine one
for the secondary fold family. Both are written out as vector primitives, NOT as an image.

Output
------
  wrinkle_graph.json           every kept edge: uv0, uv1, weight, level, joint type - for inspection or
                               artist editing (a point moved here is a wrinkle moved on the hand)
  T_PH_WrinkleGraph_Cells.png  RGBA16: per UV cell (GRID x GRID): start index / count into the edge table.
                               (R, G) = start lo/hi 8-bit halves as 16-bit values, B = count, A = unused
  T_PH_WrinkleGraph_Edges0.png RGBA16: per table entry: endpoints relative to the cell centre, in cell
                               units, mapped from [-REL_RANGE, REL_RANGE] to [0, 1]
  T_PH_WrinkleGraph_Edges1.png RGBA16: per table entry: (weight, width_cm / WIDTH_RANGE, angle / pi, level)
  wrinkle_graph_debug.png      the graph drawn over the UV coverage, coarse level red, fine level green
These are lookup TABLES of line segments that the material evaluates analytically per pixel (distance
to segment -> Bando profile, mellow-max blend, analytic gradient). They are resolution independent and
can be regenerated at runtime; nothing is rasterised.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy.spatial import cKDTree

MASK_SIZE = 2048
S_RANGE = 2.0          # must match bake_skin_maps.S_RANGE
PALM_RANGE = 2.0       # must match bake_skin_maps.PALM_RANGE
GRID = 512             # UV cells for the lookup table
REL_RANGE = 6.0        # endpoints are stored relative to the cell centre, in cell units, within +-this
WIDTH_RANGE = 0.5      # cm, max encodable wrinkle width
TABLE_WIDTH = 4096     # texels per row of the edge table

# ---- simulation levels ---------------------------------------------------------------------------
# spacing_cm: Poisson disk node distance. k: neighbours per node. iters: trail iterations.
# depth: multiplier on the edge weight when drawn. width_cm: Bando w of the line at full weight.
LEVELS = [
    # primary: the 1-3 long transverse lines over a joint (PIP strongest), and the palm lines
    dict(name='primary',   spacing_cm=0.22, k=7, iters=600, walk_frac=0.04, depth=1.0,  width_cm=0.18,
         alpha_dist=1.2, alpha_cont=0.95, alpha_sim=2.5, alpha_cross=2.5, alpha_deposit=0.5, alpha_decay=0.5, sharpness=2.5, prior_power=3.0,
         base_strength=0.03, sigma=0.22, keep=0.68, propensity_floor=0.0,  band_power=3.0,
         joint_gain=dict(MCP=0.6, PIP=1.0, DIP=0.6, THUMB=0.7, OTHER=0.0), palm_gain=0.0, reach_cm=0.6,
         min_len_cm=0.9, prune_len_cm=0.6, taper_cm=0.35),
    # secondary: the faint parallel lines around them, still transverse, shallower and narrower
    dict(name='secondary', spacing_cm=0.13, k=7, iters=400, walk_frac=0.04, depth=0.28, width_cm=0.09,
         alpha_dist=1.0, alpha_cont=0.9,  alpha_sim=1.6, alpha_cross=1.2, alpha_deposit=0.5, alpha_decay=0.5, sharpness=2.0, prior_power=2.0,
         base_strength=0.08, sigma=0.3, keep=0.55, propensity_floor=0.0, band_power=2.0,
         joint_gain=dict(MCP=0.9,  PIP=1.0, DIP=0.5, THUMB=0.8, OTHER=0.0), palm_gain=0.0, reach_cm=1.1,
         min_len_cm=0.5, prune_len_cm=0.4, taper_cm=0.25),
    # fine network (10-15): the dense, shallow mesh of lines that covers the whole back of a finger -
    # mostly transverse, plus two diagonal families that make the diamond pattern between the creases.
    # LATTICE levels (lattice=True): no trail walk. The trail formation only ever kept a few hundred
    # short dashes per family (it saturates the few best-aligned edges and starves the rest), so the
    # network read as sparse scratches and, in the palmar joint bands, as rows of beads. A lattice
    # keeps EVERY Poisson edge that lies within sigma of the family direction, weighted by alignment,
    # the dorsal-finger floor and a per-node noise - the dense, slightly irregular crosshatch of the
    # reference (Commons fist PIP close-up: one line every ~0.1 cm). Dorsal fingers only
    # (dorsal_floor; joint_gain 0 so nothing forms on the palmar side).
    dict(name='fine_t',  spacing_cm=0.08, k=6, depth=0.14, width_cm=0.07, lattice=True, sigma=0.50, keep=0.10,
         noise_lo=0.45, joint_gain=dict(MCP=0.0, PIP=0.0, DIP=0.0, THUMB=0.0, OTHER=0.0), palm_gain=0.0, reach_cm=1.4,
         base_strength=0.0, propensity_floor=0.0, band_power=1.0, dorsal_floor=0.55, angle_offset=0.0,
         min_len_cm=0.50, prune_len_cm=0.25, taper_cm=0.10, max_len_cm=1.4),
    dict(name='fine_x1', spacing_cm=0.12, k=6, depth=0.06, width_cm=0.065, lattice=True, sigma=0.40, keep=0.09,
         noise_lo=0.45, joint_gain=dict(MCP=0.0, PIP=0.0, DIP=0.0, THUMB=0.0, OTHER=0.0), palm_gain=0.0, reach_cm=1.4,
         base_strength=0.0, propensity_floor=0.0, band_power=1.0, dorsal_floor=0.5, angle_offset=0.75,
         min_len_cm=0.50, prune_len_cm=0.25, taper_cm=0.10, max_len_cm=0.9),
    dict(name='fine_x2', spacing_cm=0.12, k=6, depth=0.06, width_cm=0.065, lattice=True, sigma=0.40, keep=0.09,
         noise_lo=0.45, joint_gain=dict(MCP=0.0, PIP=0.0, DIP=0.0, THUMB=0.0, OTHER=0.0), palm_gain=0.0, reach_cm=1.4,
         base_strength=0.0, propensity_floor=0.0, band_power=1.0, dorsal_floor=0.5, angle_offset=-0.75,
         min_len_cm=0.50, prune_len_cm=0.25, taper_cm=0.10, max_len_cm=0.9),
]
JOINT_CODES = {0: 'NONE', 1: 'MCP', 2: 'PIP', 3: 'DIP', 4: 'THUMB', 5: 'OTHER'}


# ---------------------------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------------------------

def load_mask(path):
    import cv2
    m = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if m is None:
        raise SystemExit('cannot read ' + path)
    m = m.astype(np.float32) / 65535.0
    return m[..., [2, 1, 0, 3]]      # BGRA -> RGBA


def sample(img, uv):
    """Bilinear sample of an HxWxC image at UV (V down, like UE), uv: (N,2)."""
    h, w = img.shape[:2]
    x = np.clip(uv[:, 0] * w - 0.5, 0, w - 1.001)
    y = np.clip(uv[:, 1] * h - 0.5, 0, h - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = (x - x0)[:, None]; fy = (y - y0)[:, None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def coverage_and_scale(data):
    """UV coverage (bool image) and the median cm-per-UV of the mesh."""
    tris = data['tris']; uvs = data['uvs']; pos = np.array(data['pos'])
    img = Image.new('L', (MASK_SIZE, MASK_SIZE), 0)
    dr = ImageDraw.Draw(img)
    ratios = []
    for t, tri in enumerate(tris):
        uv = uvs[t]
        if uv is None:
            continue
        dr.polygon([(u * MASK_SIZE, v * MASK_SIZE) for u, v in uv], fill=255)
        p = pos[tri]
        e3 = np.linalg.norm(p[1] - p[0]); e2 = np.linalg.norm(np.array(uv[1]) - np.array(uv[0]))
        if e2 > 1e-7:
            ratios.append(e3 / e2)
    cov = np.array(img) > 0
    return cov, float(np.median(ratios))


# ---------------------------------------------------------------------------------------------
# nodes and graph
# ---------------------------------------------------------------------------------------------

def poisson_disk(cov, spacing_uv, rng, max_nodes=200000):
    """Bridson Poisson disk sampling restricted to the covered texels, spacing in UV units."""
    cell = spacing_uv / math.sqrt(2.0)
    n = int(math.ceil(1.0 / cell))
    grid = -np.ones((n, n), dtype=np.int64)
    pts = []
    active = []
    h = cov.shape[0]

    def covered(p):
        x = int(p[0] * h); y = int(p[1] * h)
        return 0 <= x < h and 0 <= y < h and cov[y, x]

    def fits(p):
        gx, gy = int(p[0] / cell), int(p[1] / cell)
        x0, x1 = max(gx - 2, 0), min(gx + 3, n); y0, y1 = max(gy - 2, 0), min(gy + 3, n)
        for yy in range(y0, y1):
            for xx in range(x0, x1):
                j = grid[yy, xx]
                if j >= 0:
                    q = pts[j]
                    if (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < spacing_uv * spacing_uv:
                        return False
        return True

    # seeds: one per covered coarse block so every island gets started
    ys, xs = np.nonzero(cov)
    order = rng.permutation(len(ys))
    seeded = set()
    for i in order:
        p = (xs[i] / h + rng.random() / h, ys[i] / h + rng.random() / h)
        key = (int(p[0] * 32), int(p[1] * 32))
        if key in seeded:
            continue
        if fits(p):
            seeded.add(key)
            grid[int(p[1] / cell), int(p[0] / cell)] = len(pts)
            pts.append(p); active.append(len(pts) - 1)
    while active and len(pts) < max_nodes:
        ai = rng.integers(len(active))
        base = pts[active[ai]]
        found = False
        for _ in range(20):
            r = spacing_uv * (1.0 + rng.random())
            a = rng.random() * 2 * math.pi
            p = (base[0] + r * math.cos(a), base[1] + r * math.sin(a))
            if not (0 <= p[0] < 1 and 0 <= p[1] < 1) or not covered(p) or not fits(p):
                continue
            grid[int(p[1] / cell), int(p[0] / cell)] = len(pts)
            pts.append(p); active.append(len(pts) - 1)
            found = True
            break
        if not found:
            active[ai] = active[-1]; active.pop()
    return np.array(pts, dtype=np.float64)


def build_graph(nodes, k, cov, max_len_uv):
    """k-NN edges, dropped when they leave the covered UV area (cross a seam) or are too long."""
    tree = cKDTree(nodes)
    d, idx = tree.query(nodes, k=k + 1)
    edges = set()
    h = cov.shape[0]
    for i in range(len(nodes)):
        for j, dist in zip(idx[i, 1:], d[i, 1:]):
            if dist > max_len_uv:
                continue
            a, b = (i, j) if i < j else (j, i)
            if (a, b) in edges:
                continue
            # the midpoint and quarter points must be covered: an edge across a UV seam is not a wrinkle
            ok = True
            for t in (0.25, 0.5, 0.75):
                p = nodes[a] * (1 - t) + nodes[b] * t
                x, y = int(p[0] * h), int(p[1] * h)
                if not (0 <= x < h and 0 <= y < h and cov[y, x]):
                    ok = False; break
            if ok:
                edges.add((a, b))
    return np.array(sorted(edges), dtype=np.int64)


def half_edges(nodes, edges):
    """Half-edge tables: for every node a padded list of (target, edge index, angle, length)."""
    n = len(nodes)
    out = [[] for _ in range(n)]
    for e, (a, b) in enumerate(edges):
        out[a].append((b, e)); out[b].append((a, e))
    kmax = max(len(o) for o in out)
    tgt = -np.ones((n, kmax), dtype=np.int64); eid = -np.ones((n, kmax), dtype=np.int64)
    for i, o in enumerate(out):
        for j, (t, e) in enumerate(o):
            tgt[i, j] = t; eid[i, j] = e
    valid = tgt >= 0
    src = np.repeat(np.arange(n)[:, None], kmax, axis=1)
    delta = np.where(valid[..., None], nodes[np.where(valid, tgt, 0)] - nodes[src], 0.0)
    ang = np.arctan2(delta[..., 1], delta[..., 0])
    length = np.linalg.norm(delta, axis=-1)
    return tgt, eid, ang, length, valid


def edge_crossings(nodes, edges, cell_uv):
    """For every edge, the indices of edges that cross it (segment intersection test per grid cell)."""
    n = len(edges)
    p0 = nodes[edges[:, 0]]; p1 = nodes[edges[:, 1]]
    g = int(math.ceil(1.0 / cell_uv))
    buckets = {}
    lo = np.floor(np.minimum(p0, p1) / cell_uv).astype(int); hi = np.floor(np.maximum(p0, p1) / cell_uv).astype(int)
    for e in range(n):
        for y in range(lo[e, 1], hi[e, 1] + 1):
            for x in range(lo[e, 0], hi[e, 0] + 1):
                buckets.setdefault((x, y), []).append(e)
    cross = [[] for _ in range(n)]

    def ccw(a, b, c):
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    seen = set()
    for lst in buckets.values():
        for i in range(len(lst)):
            for j in range(i + 1, len(lst)):
                a, b = lst[i], lst[j]
                key = (a, b) if a < b else (b, a)
                if key in seen:
                    continue
                seen.add(key)
                ea, eb = edges[a], edges[b]
                if len(set(ea) & set(eb)):
                    continue       # share a node: not a crossing
                A, B, C, D = p0[a], p1[a], p0[b], p1[b]
                if ccw(A, C, D) != ccw(B, C, D) and ccw(A, B, C) != ccw(A, B, D):
                    cross[a].append(b); cross[b].append(a)
    return cross


# ---------------------------------------------------------------------------------------------
# fields at the nodes: orientation prior and deposit propensity
# ---------------------------------------------------------------------------------------------

def segment_length_field(data):
    """(uv points, factor) for every triangle corner: the length of the vertex's dominant phalanx
    relative to the middle finger's proximal phalanx. A longer segment carries a wider band of folds
    (reach scales with it) - the pinky's creases sit closer together than the middle finger's."""
    bones = data['bones']; pos = np.array(data['pos']); W = data['weights']
    name2i = {b['name']: i for i, b in enumerate(bones)}
    def blen(n):
        if n not in name2i: return None
        b = bones[name2i[n]]; kids = [k for k in bones if k['parent'] == name2i[n]]
        if kids: return float(np.linalg.norm(np.array(kids[0]['pos']) - np.array(b['pos'])))
        par = bones[b['parent']]; return 0.75 * float(np.linalg.norm(np.array(b['pos']) - np.array(par['pos'])))
    ref = blen('middle_01_r') or 4.3
    fac = np.ones(len(bones))
    for i, b in enumerate(bones):
        L = blen(b['name']) if any(k in b['name'] for k in ('_01_', '_02_', '_03_', 'thumb')) else None
        if L: fac[i] = float(np.clip(L / ref, 0.55, 1.15))
    vfac = np.array([fac[w[0][0]] if w and w[0][1] > 0 else 1.0 for w in W])
    pts, vals = [], []
    for t, tri in enumerate(data['tris']):
        uv = data['uvs'][t]
        if uv is None: continue
        for k, vi in enumerate(tri):
            pts.append(uv[k]); vals.append(vfac[vi])
    return cKDTree(np.array(pts)), np.array(vals)


def node_fields(nodes, mask1, mask2, level, cm_per_uv, seg_field=None):
    """Per node: preferred angle (undirected), base strength, propensity."""
    m1 = sample(mask1, nodes); m2 = sample(mask2, nodes)
    segf = np.ones(len(nodes))
    if seg_field is not None:
        tree, vals = seg_field
        _, idx = tree.query(nodes); segf = vals[idx]
    band = m1[:, 0]; s_cm = m1[:, 1] * S_RANGE; jt = np.round(m1[:, 2] * 5).astype(int)
    palm_d = m2[:, 1] * PALM_RANGE; palm_amp = m2[:, 2]
    # gradients of the two coordinate fields, by central differences on the masks (UV units)
    eps = 3.0 / MASK_SIZE
    # Bone direction from the along-hand coordinate L (mask 2 A): smooth and monotonic everywhere.
    # (The unsigned joint distance s has a vanishing, direction-flipping gradient exactly on the band
    # centre - the one place the primary crease has to be oriented - so it is useless for this.)
    gl = (sample(mask2, nodes + [eps, 0])[:, 3] - sample(mask2, nodes - [eps, 0])[:, 3],
          sample(mask2, nodes + [0, eps])[:, 3] - sample(mask2, nodes - [0, eps])[:, 3])
    gp = (sample(mask2, nodes + [eps, 0])[:, 1] - sample(mask2, nodes - [eps, 0])[:, 1],
          sample(mask2, nodes + [0, eps])[:, 1] - sample(mask2, nodes - [0, eps])[:, 1])
    gl = np.stack(gl, 1); gp = np.stack(gp, 1)
    # the crease runs ACROSS the bone, i.e. perpendicular to the gradient of L; palm lines run along
    # the iso-lines of their distance field, i.e. perpendicular to its gradient
    ang_joint = np.arctan2(gl[:, 1], gl[:, 0]) + math.pi / 2
    ang_palm = np.arctan2(gp[:, 1], gp[:, 0]) + math.pi / 2
    have_s = np.linalg.norm(gl, axis=1) > 1e-6
    have_p = np.linalg.norm(gp, axis=1) > 1e-5

    gain = np.array([level['joint_gain'].get(JOINT_CODES.get(int(c), 'OTHER'), 0.2) for c in jt])
    reach_cm = level['reach_cm'] * segf          # per-finger: scales with the phalanx length
    reach = 1.0 - np.clip((s_cm - reach_cm * 0.5) / (reach_cm * 0.5), 0, 1)
    joint_prop = np.clip(band, 0, 1) ** level['band_power'] * gain * reach
    palm_prop = palm_amp * np.clip(1.0 - palm_d / 0.6, 0, 1) * level['palm_gain']

    prop = np.maximum(joint_prop, palm_prop) + level['propensity_floor']
    # fine levels: a floor over the back of the FINGERS (dorsal side of mask 1, beyond the MCP row)
    if level.get('dorsal_floor', 0.0) > 0.0:
        dorsal = np.clip((m1[:, 3] * 2.0 - 1.0) * 1.5 + 0.5, 0, 1)
        along_cm = m2[:, 3] * 24.0
        # from ~1 cm past the MCP row: over the knuckle band itself the lattice read as crumpled skin (10-15)
        finger = np.clip((along_cm - 9.5) / 1.5, 0, 1)
        prop = np.maximum(prop, level['dorsal_floor'] * dorsal * finger)
    use_palm = palm_prop > joint_prop
    ang = np.where(use_palm & have_p, ang_palm, np.where(have_s, ang_joint, 0.0)) + level.get('angle_offset', 0.0)
    base = np.where((use_palm & have_p) | have_s, level['base_strength'], 1.0)
    return ang, base, prop, jt


# ---------------------------------------------------------------------------------------------
# trail formation on the graph (Weiss et al. 2023 eq. 3-8)
# ---------------------------------------------------------------------------------------------

def angdiff_pi(a, b):
    """|a - b| modulo pi (undirected)."""
    d = np.abs(a - b) % math.pi
    return np.minimum(d, math.pi - d)


def angdiff_2pi(a, b):
    d = np.abs(a - b) % (2 * math.pi)
    return np.minimum(d, 2 * math.pi - d)


def simulate(nodes, edges, level, ang_pref, base_strength, prop, rng, cm_per_uv):
    tgt, eid, ang, length, valid = half_edges(nodes, edges)
    n, kmax = tgt.shape
    W = np.zeros(len(edges))
    cross = edge_crossings(nodes, edges, level['spacing_cm'] / cm_per_uv * 2.0)
    cross_idx = -np.ones((len(edges), max(1, max(len(c) for c in cross))), dtype=np.int64)
    for e, c in enumerate(cross):
        cross_idx[e, :len(c)] = c
    cross_valid = cross_idx >= 0

    sigma = level['sigma']; cspread = 0.3
    dist_uv = np.where(valid, length, 1.0)
    dist_cm = dist_uv * cm_per_uv / level['spacing_cm']        # ~1 at the nominal spacing
    # orientation prior per half-edge (eq. 1), using the source node's preferred angle
    ppref = base_strength[:, None] + np.exp(-(angdiff_pi(ang, ang_pref[:, None]) ** 2) / (sigma ** 2))
    # per-half-edge propensity: the mean of the two incident nodes
    prop_h = 0.5 * (prop[:, None] + prop[np.where(valid, tgt, 0)])
    dt = 0.03
    E = len(edges)

    for it in range(level['iters']):
        Wh = W[np.where(valid, eid, 0)] * valid                 # weight of each half-edge
        # continuation reward / T-junction penalty (eq. 4): compare every half-edge with its siblings
        pcont = np.zeros_like(Wh)
        for j in range(kmax):
            other_ang = ang[:, j][:, None]; other_w = Wh[:, j][:, None]
            same = np.zeros((n, kmax), dtype=bool); same[:, j] = True
            d_cont = angdiff_2pi(ang, other_ang + math.pi)
            d_sim = angdiff_2pi(ang, other_ang)
            term = other_w * (level['alpha_cont'] * np.exp(-d_cont ** 2 / (2 * cspread ** 2))
                              - level['alpha_sim'] * np.exp(-d_sim ** 2 / (2 * cspread ** 2)))
            pcont += np.where(same, 0.0, term)
        pcross = np.zeros(E)
        if level['alpha_cross'] > 0:
            pcross = (W[np.where(cross_valid, cross_idx, 0)] * cross_valid).sum(axis=1)
        pcross_h = pcross[np.where(valid, eid, 0)]
        P = np.maximum(0.0, (1.0 / dist_cm ** level['alpha_dist'])
                       * (pcont + (1.0 - level['alpha_cont']) * ppref - level['alpha_cross'] * pcross_h))
        # The paper adds the orientation prior (facial micro wrinkles are only loosely oriented). A
        # knuckle crease is not: it runs across the bone or it is not a knuckle crease. So the prior
        # also MULTIPLIES, which keeps the continuation reward from steering a trail off-axis.
        P = P * ppref ** level['prior_power']
        P = (P * prop_h * valid) ** level['sharpness']          # walk where creases belong; sharpened
        # start the walks where creases belong, a few per cent of the edge count per step so that
        # only repeatedly chosen edges saturate (uniform, many walks per step saturate everything)
        n_walks = max(int(E * level['walk_frac']), 50)
        rows = rng.choice(n, size=n_walks, p=prop / prop.sum()) if prop.sum() > 0 else rng.integers(0, n, size=n_walks)
        Pr = P[rows]
        tot = Pr.sum(axis=1)
        ok = tot > 1e-9
        rows = rows[ok]; Pr = Pr[ok] / tot[ok][:, None]
        u = rng.random(len(rows))
        pick = (Pr.cumsum(axis=1) < u[:, None]).sum(axis=1)
        pick = np.minimum(pick, kmax - 1)
        e_sel = eid[rows, pick]
        e_sel = e_sel[e_sel >= 0]
        # deposit (eq. 7), saturating at 1; the same edge picked twice this step deposits twice
        dep = dt * level['alpha_deposit']
        np.add.at(W, e_sel, dep * (1.0 - W[e_sel]))
        np.clip(W, 0, 1, out=W)
        # decay (eq. 8)
        W *= (1.0 - dt * level['alpha_decay'] * len(e_sel) / E)
    return W


def lattice_weights(nodes, edges, level, ang_pref, prop, rng):
    """Lattice levels: every edge weighted by how well it lies along the family direction at its two
    nodes, by the propensity there and by a per-node noise (so the crosshatch is dense but not even)."""
    a, b = edges[:, 0], edges[:, 1]
    d = nodes[b] - nodes[a]
    ang = np.arctan2(d[:, 1], d[:, 0])
    sa = np.exp(-angdiff_pi(ang, ang_pref[a]) ** 2 / level['sigma'] ** 2)
    sb = np.exp(-angdiff_pi(ang, ang_pref[b]) ** 2 / level['sigma'] ** 2)
    noise = rng.uniform(level.get('noise_lo', 0.5), 1.0, len(nodes))
    W = np.sqrt(sa * sb) * 0.5 * (prop[a] + prop[b]) * np.sqrt(noise[a] * noise[b])
    return np.clip(W, 0.0, 1.0)


# ---------------------------------------------------------------------------------------------
# chains: the kept edges as smooth polylines (what the reference photos show)
# ---------------------------------------------------------------------------------------------
#
# The raw trails are polylines through Poisson nodes, so each kept edge meets the next at an angle
# of up to 60 degrees; drawn as straight segments they read as a zig-zag. A real knuckle crease
# (Commons: "Hand in closed fist black background") is a long, smooth, low-amplitude line running the
# whole width of the finger, with one or two short side branches at most. So the kept edges are
# first chained (walk from endpoints / junctions, continuing through the straightest neighbour),
# short dangling branches are pruned, each chain is Chaikin-smoothed twice and resampled, and the
# weight tapers towards the chain ends so the line fades out instead of stopping.

def extract_chains(nodes, edges, W, keep, min_len, prune_len, rng):
    import collections
    kept = [tuple(e) for e, k in zip(edges.tolist(), keep) if k]
    wmap = {tuple(e): float(w) for e, k, w in zip(edges.tolist(), keep, W) if k}
    adj = collections.defaultdict(list)
    for a, b in kept:
        adj[a].append(b); adj[b].append(a)

    def straightest(prev, cur, used):
        best, bd = None, 9.0
        d0 = nodes[cur] - nodes[prev]
        for n in adj[cur]:
            e = (min(cur, n), max(cur, n))
            if n == prev or e in used:
                continue
            d1 = nodes[n] - nodes[cur]
            ang = math.acos(max(-1.0, min(1.0, float(np.dot(d0, d1) / (np.linalg.norm(d0) * np.linalg.norm(d1) + 1e-12)))))
            if ang < bd:
                best, bd = n, ang
        return best if bd < math.radians(75) else None

    used = set()
    chains = []
    # start at nodes of degree != 2 first (endpoints and junctions), then whatever is left (loops)
    starts = sorted(adj.keys(), key=lambda v: (len(adj[v]) == 2, rng.random()))
    for s0 in starts:
        for n0 in list(adj[s0]):
            e0 = (min(s0, n0), max(s0, n0))
            if e0 in used:
                continue
            chain = [s0, n0]; used.add(e0)
            prev, cur = s0, n0
            while True:
                nxt = straightest(prev, cur, used)
                if nxt is None:
                    break
                used.add((min(cur, nxt), max(cur, nxt)))
                chain.append(nxt); prev, cur = cur, nxt
            chains.append(chain)
    # prune: a chain that hangs off a junction and is shorter than prune_len is a stub, not a branch
    out = []
    for c in chains:
        length = sum(np.linalg.norm(nodes[c[i + 1]] - nodes[c[i]]) for i in range(len(c) - 1))
        touches = (len(adj[c[0]]) > 1) + (len(adj[c[-1]]) > 1)
        if length < min_len or (touches >= 1 and length < prune_len and len(c) <= 3):
            continue
        out.append((c, np.mean([wmap[(min(c[i], c[i + 1]), max(c[i], c[i + 1]))] for i in range(len(c) - 1)])))
    return out


def smooth_chain(pts, iters=2):
    P = np.asarray(pts, dtype=np.float64)
    for _ in range(iters):
        if len(P) < 3:
            break
        Q = [P[0]]
        for i in range(len(P) - 1):
            Q.append(P[i] * 0.75 + P[i + 1] * 0.25); Q.append(P[i] * 0.25 + P[i + 1] * 0.75)
        Q.append(P[-1]); P = np.array(Q)
    return P


def resample(P, step):
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    total = seg.sum()
    if total < 1e-9:
        return P
    n = max(int(total / step) + 1, 2)
    t = np.concatenate([[0], np.cumsum(seg)]) / total
    u = np.linspace(0, 1, n)
    return np.stack([np.interp(u, t, P[:, k]) for k in range(2)], 1)


# ---------------------------------------------------------------------------------------------
# output: json, lookup tables, debug image
# ---------------------------------------------------------------------------------------------

def pack_tables(all_edges, out_dir):
    """Cell grid + edge table as 16-bit PNGs (data, not images)."""
    import cv2
    cell = 1.0 / GRID
    entries = [[] for _ in range(GRID * GRID)]
    for e in all_edges:
        p0 = np.array(e['uv0']); p1 = np.array(e['uv1'])
        margin = 2.0 * e['width_cm'] / e['cm_per_uv']
        lo = np.floor((np.minimum(p0, p1) - margin) / cell).astype(int)
        hi = np.floor((np.maximum(p0, p1) + margin) / cell).astype(int)
        for y in range(max(lo[1], 0), min(hi[1], GRID - 1) + 1):
            for x in range(max(lo[0], 0), min(hi[0], GRID - 1) + 1):
                entries[y * GRID + x].append(e)
    total = sum(len(l) for l in entries)
    rows = int(math.ceil(total / TABLE_WIDTH)) + 1
    E0 = np.zeros((rows, TABLE_WIDTH, 4), dtype=np.float64)
    E1 = np.zeros((rows, TABLE_WIDTH, 4), dtype=np.float64)
    C = np.zeros((GRID, GRID, 4), dtype=np.float64)
    i = 0
    maxcount = 0
    for ci, lst in enumerate(entries):
        y, x = divmod(ci, GRID)
        start = i
        centre = np.array([(x + 0.5) * cell, (y + 0.5) * cell])
        for e in lst:
            r0 = (np.array(e['uv0']) - centre) / cell; r1 = (np.array(e['uv1']) - centre) / cell
            r0 = np.clip(r0, -REL_RANGE, REL_RANGE); r1 = np.clip(r1, -REL_RANGE, REL_RANGE)
            E0[i // TABLE_WIDTH, i % TABLE_WIDTH] = [(r0[0] + REL_RANGE) / (2 * REL_RANGE), (r0[1] + REL_RANGE) / (2 * REL_RANGE),
                                                    (r1[0] + REL_RANGE) / (2 * REL_RANGE), (r1[1] + REL_RANGE) / (2 * REL_RANGE)]
            E1[i // TABLE_WIDTH, i % TABLE_WIDTH] = [e['weight'], min(e['width_cm'] / WIDTH_RANGE, 1.0),
                                                    (e['angle'] % math.pi) / math.pi, e['level'] / 4.0]   # level index / 4 (16-bit PNG is [0,1])
            i += 1
        count = len(lst)
        maxcount = max(maxcount, count)
        C[y, x] = [(start & 0xFF) / 255.0, ((start >> 8) & 0xFF) / 255.0, min(count, 255) / 255.0, ((start >> 16) & 0xFF) / 255.0]
    to16 = lambda a: np.clip(a, 0, 1) * 65535
    cv2.imwrite(os.path.join(out_dir, 'T_PH_WrinkleGraph_Cells.png'), to16(C[..., [2, 1, 0, 3]]).astype(np.uint16))
    cv2.imwrite(os.path.join(out_dir, 'T_PH_WrinkleGraph_Edges0.png'), to16(E0[..., [2, 1, 0, 3]]).astype(np.uint16))
    cv2.imwrite(os.path.join(out_dir, 'T_PH_WrinkleGraph_Edges1.png'), to16(E1[..., [2, 1, 0, 3]]).astype(np.uint16))
    print('tables: %d entries over %d cells (max %d per cell), edge table %dx%d' % (total, GRID * GRID, maxcount, TABLE_WIDTH, rows))


def debug_image(cov, all_edges, path, prior=None):
    img = Image.fromarray((cov * 40).astype(np.uint8)).convert('RGB')
    dr = ImageDraw.Draw(img)
    if prior is not None:
        nodes, ang, prop = prior
        for p, a, w in zip(nodes, ang, prop):
            if w < 0.1:
                continue
            d = np.array([math.cos(a), math.sin(a)]) * 0.004
            q0 = (p - d) * MASK_SIZE; q1 = (p + d) * MASK_SIZE
            dr.line([(q0[0], q0[1]), (q1[0], q1[1])], fill=(70, 70, 160), width=1)
    for e in sorted(all_edges, key=lambda e: e['level']):
        c = (255, int(80 * (1 - e['weight'])), 60) if e['level'] == 0 else (60, 220, 90)
        w = 3 if e['level'] == 0 else 1
        dr.line([(e['uv0'][0] * MASK_SIZE, e['uv0'][1] * MASK_SIZE), (e['uv1'][0] * MASK_SIZE, e['uv1'][1] * MASK_SIZE)],
                fill=tuple(int(v * (0.35 + 0.65 * e['weight'])) for v in c), width=w)
    img.save(path)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    seed = 7
    for a in sys.argv[1:]:
        if a.startswith('--seed'):
            seed = int(a.split('=')[1]) if '=' in a else int(sys.argv[sys.argv.index(a) + 1])
    src, tex_dir, out_dir = args[0], args[1], args[2]
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(seed)
    data = json.load(open(src))
    mask1 = load_mask(os.path.join(tex_dir, 'T_PH_WrinkleMask.png'))
    mask2 = load_mask(os.path.join(tex_dir, 'T_PH_WrinkleMask2.png'))
    cov, cm_per_uv = coverage_and_scale(data)
    # shrink the coverage by a texel or two so nodes stay off the island borders
    import cv2
    cov_in = cv2.erode(cov.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    print('coverage %.1f%%, %.1f cm per UV unit' % (cov.mean() * 100, cm_per_uv))

    all_edges = []
    prior_dbg = None
    seg_field = segment_length_field(data)
    for li, level in enumerate(LEVELS):
        spacing_uv = level['spacing_cm'] / cm_per_uv
        nodes = poisson_disk(cov_in, spacing_uv, rng)
        edges = build_graph(nodes, level['k'], cov_in, spacing_uv * 2.2)
        ang_pref, base, prop, jt = node_fields(nodes, mask1, mask2, level, cm_per_uv, seg_field)
        print('[%s] %d nodes, %d candidate edges, propensity>0.1 on %.1f%% of nodes' % (level['name'], len(nodes), len(edges), (prop > 0.1).mean() * 100))
        if li == 0:
            prior_dbg = (nodes, ang_pref, prop)
        if level.get('lattice'):
            W = lattice_weights(nodes, edges, level, ang_pref, prop, rng)
        else:
            W = simulate(nodes, edges, level, ang_pref, base, prop, rng, cm_per_uv)
        keep = W >= level['keep']
        print('[%s] kept %d edges (weight >= %.2f), mean weight %.2f' % (level['name'], keep.sum(), level['keep'], W[keep].mean() if keep.any() else 0))
        chains = extract_chains(nodes, edges, W, keep, min_len=level['min_len_cm'] / cm_per_uv,
                                prune_len=level['prune_len_cm'] / cm_per_uv, rng=rng)
        print('[%s] %d chains after pruning' % (level['name'], len(chains)))
        # lattice levels: the weight varies ALONG a chain (per-node noise and alignment), so a line
        # swells and fades over its length instead of being one uniform scratch (10-15)
        node_w = None
        if level.get('lattice'):
            node_w = np.zeros(len(nodes)); node_n = np.zeros(len(nodes))
            for (a, b), wv, k in zip(edges, W, keep):
                if k:
                    node_w[a] += wv; node_w[b] += wv; node_n[a] += 1; node_n[b] += 1
            node_w = node_w / np.maximum(node_n, 1)
        # lattice levels: a chain longer than max_len_cm is cut into strokes of random length (0.6 .. max)
        # with their own tapers - the reference lines are short and broken, not finger-long scratches (10-15)
        pieces = []
        for c, w in chains:
            P = resample(smooth_chain(nodes[c], 2), level['spacing_cm'] * 0.9 / cm_per_uv)
            max_len = level.get('max_len_cm', 0.0)
            if max_len <= 0.0 or len(P) < 3:
                pieces.append((c, w, P)); continue
            seg = np.linalg.norm(np.diff(P, axis=0), axis=1) * cm_per_uv
            start = 0; acc = 0.0; target = rng.uniform(0.6 * max_len, max_len)
            for i, L in enumerate(seg):
                acc += L
                if acc >= target and i + 1 < len(seg):
                    pieces.append((c, w, P[start:i + 2])); start = i + 1; acc = 0.0
                    target = rng.uniform(0.6 * max_len, max_len)
            if len(P) - start >= 2:
                pieces.append((c, w, P[start:]))
        for c, w, P in pieces:
            n = len(P) - 1
            total = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()) * cm_per_uv
            for i in range(n):
                p0, p1 = P[i], P[i + 1]
                # taper over the last `taper_cm` of each end so the line fades out, never stops
                along = (i + 0.5) / n * total
                tap = min(1.0, along / level['taper_cm'], (total - along) / level['taper_cm'])
                tap = tap * tap * (3 - 2 * tap)
                ci = min(int(i / n * (len(c) - 1)), len(c) - 1)
                jt_mid = int(round(float(jt[c[ci]])))
                w_seg = float(node_w[c[ci]]) if node_w is not None else float(w)
                all_edges.append(dict(uv0=[float(p0[0]), float(p0[1])], uv1=[float(p1[0]), float(p1[1])],
                                      weight=w_seg * level['depth'] * tap, width_cm=level['width_cm'],
                                      angle=float(math.atan2(p1[1] - p0[1], p1[0] - p0[0])), level=li,
                                      joint=jt_mid, cm_per_uv=cm_per_uv))
    json.dump(dict(cm_per_uv=cm_per_uv, grid=GRID, rel_range=REL_RANGE, width_range=WIDTH_RANGE, table_width=TABLE_WIDTH,
                   levels=[l['name'] for l in LEVELS],
                   edges=[{k: v for k, v in e.items() if k != 'cm_per_uv'} for e in all_edges]),
              open(os.path.join(out_dir, 'wrinkle_graph.json'), 'w'))
    pack_tables(all_edges, out_dir)
    debug_image(cov, all_edges, os.path.join(out_dir, 'wrinkle_graph_debug.png'), prior_dbg)
    print('wrote', out_dir)


if __name__ == '__main__':
    main()
