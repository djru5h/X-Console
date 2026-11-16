"""Mock: realistic knob caps, option B (a 64-picture strip per knob, light fixed, only the cap turns).

Each pixel gets a surface normal from a simple 3D shape (top face, bevel, skirt, dome...), then is lit by one fixed
studio light (upper left) + a fake soft-box environment, so highlights stay put while the knob turns.
Run: python real_caps.py outdir
"""
import sys, os, math, json
import numpy as np
from PIL import Image


L = np.array([-0.55, -0.62, 0.56]); L /= np.linalg.norm(L)       # light: upper left, 34 deg up (screen y down)
V = np.array([0.0, 0.0, 1.0])
H = L + V; H /= np.linalg.norm(H)

def norm(v):
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-6)

def env(n):
    """fake studio: reflection of the view off the normal -> brightness (soft box upper left, dim floor)"""
    r = 2 * n[..., 2:3] * n - V                          # reflect V about n
    up = -r[..., 1]                                      # screen up
    sky = 0.18 + 0.30 * np.clip(up, 0, 1) + 0.10 * np.clip(r[..., 2], 0, 1)
    box = np.exp(-((r @ L) - 1) ** 2 / 0.010)            # main soft box (where the light is)
    box2 = 0.45 * np.exp(-((r @ norm(np.array([0.7, -0.3, 0.65]))) - 1) ** 2 / 0.02)   # fill from the right
    return sky + 1.6 * box + box2

def shade(n, base, metal, rough, spec_tint=None):
    """base (..,3) 0..1; metal 0..1 (spec coloured by base); rough -> highlight width"""
    ndl = np.clip(n @ L, 0, 1)[..., None]
    ndh = np.clip(n @ H, 0, 1)[..., None]
    p = 2.0 / (rough * rough) - 2
    spec = ndh ** p * (p + 8) / 40.0
    st = base if spec_tint is None else spec_tint
    sc = metal * st + (1 - metal) * 0.9
    e = env(n)[..., None]
    diff = base * (0.18 + 0.82 * ndl) * (1 - 0.75 * metal)
    refl = sc * e * (0.35 + 0.65 * metal) * (0.55 if rough > 0.3 else 1.0)
    return diff + refl * 0.75 + sc * spec

def grid(n, box):
    c = (n - 1) / 2
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    s = box / n
    return (xx - c) * s, (yy - c) * s

def tex_rings(rho, seed):
    """spun / turned rings: depends only on radius, so it doesn't swim when the cap turns"""
    rng = np.random.default_rng(seed)
    t = np.zeros_like(rho)
    for k in range(18):
        t += rng.normal() * np.sin(rho * rng.uniform(4, 22) + rng.uniform(0, 6.3))
    return t / 18 * 2.2

def cap_frame(style, colour, ang, R=24.0, box=68.0, n=272):
    """one frame: cap radius R (screen px) in a box x box picture, drawn n x n; ang = pointer angle (rad, 0 = 12 o'clock).
    colour = (r, g, b), or ((r, g, b), (r, g, b)) = (colour, top colour) for caps with a second colour (pointer: skirt, insert)"""
    top_col = None
    if len(colour) == 2 and hasattr(colour[0], '__len__'):   # user 2026-11-15: pointer top colour as well as the skirt
        colour, top_col = colour
    if style in _HEXX_SRC:
        return hexx_photo_frame(style, colour, ang, R, box, n)
    if style in _SUEDE:
        return suede_photo_frame(style, colour, ang, R, box, n)
    x, y = grid(n, box)
    rho = np.hypot(x, y)
    phi = np.arctan2(y, x)                       # screen angle
    loc = phi - ang                              # angle in the cap's own frame (turns with it)
    col = np.array(colour, np.float32) / 255
    out = np.zeros((n, n, 3), np.float32)
    alpha = np.clip((R - rho) * (n / box) + 0.5, 0, 1)
    nz = np.zeros((n, n, 3), np.float32); nz[..., 2] = 1
    radial = np.stack([np.cos(phi), np.sin(phi), np.zeros_like(phi)], -1)
    tang = np.stack([-np.sin(phi), np.cos(phi), np.zeros_like(phi)], -1)
    rings = tex_rings(rho, 7)[..., None]
    # pointer in cap coordinates: along 12 o'clock of the cap
    px_ = rho * np.sin(loc + math.pi / 2)        # across the pointer
    py_ = rho * np.cos(loc + math.pi / 2)        # along (toward 12)
    if style == 'knurl':
        rt, rb = 0.70 * R, 0.80 * R              # top face edge, bevel edge, then knurled skirt to R
        top = rho < rt
        bev = (rho >= rt) & (rho < rb)
        sk = rho >= rb
        t = np.clip((rho - rt) / (rb - rt), 0, 1)[..., None]
        nb = norm(nz * (1 - 0.75 * t) + radial * 0.75 * t + 1e-6)
        ridge = np.sin(48 * loc)[..., None]
        ns = norm(nz * 0.30 + radial * 0.85 + tang * 0.75 * ridge)
        n_ = np.where(top[..., None], nz, np.where(bev[..., None], nb, ns))
        # brushed top: anisotropic streak across the centre toward the light (spun metal look)
        aniso = np.abs(np.cos(phi - math.atan2(L[1], L[0]))) ** 18 * np.clip(1 - rho / rt, 0, 1) ** 0.4
        o = shade(n_, col, 0.85, 0.30) * np.where(sk[..., None], 1.0, 1.65)
        o = o + top[..., None] * (aniso[..., None] * 0.35 * (col * 0.6 + 0.4) + rings * 0.035)
        o = o * np.where(sk[..., None], 0.80 + 0.20 * (ridge > 0), 1.0)
        # engraved pointer on the top face: dark groove, lit lower edge
        on = (np.abs(px_) < 1.25) & (py_ > 0.18 * R) & (py_ < 0.66 * R)
        edge = (np.abs(px_ + 1.0) < 0.5) & (py_ > 0.18 * R) & (py_ < 0.66 * R)
        kp = np.array([0.96, 0.96, 0.97]) if col.mean() < 0.6 else np.array([0.07, 0.07, 0.08])
        o = np.where(on[..., None], o * 0.2 + kp * 0.8, o)
        o = np.where(edge[..., None] & on[..., None], o * 0.75, o)
        rim_shadow = np.clip((rho - (R - 1.2)) / 1.2, 0, 1)[..., None]
        o = o * (1 - 0.6 * rim_shadow)
        out = o
    elif style == 'dome':
        rs = 0.82 * R                            # glossy dome to rs, flat ridged skirt to R
        dome = rho < rs
        u = np.clip(rho / rs, 0, 0.999)
        h = np.sqrt(1 - u * u) * 0.55 + 0.45
        g = u / np.sqrt(1 - u * u + 0.08) * 0.55
        nd = norm(nz + radial * g[..., None])
        ridge = np.sin(36 * loc)[..., None]
        ns = norm(nz * 0.55 + radial * 0.55 + tang * 0.45 * ridge)
        n_ = np.where(dome[..., None], nd, ns)
        o = shade(n_, col, 0.25, 0.12, spec_tint=np.array([1, 1, 1], np.float32))   # lacquer: white glints
        o = o + dome[..., None] * rings * 0.015
        sk = ~dome
        o = np.where(sk[..., None], shade(n_, col * 0.55, 0.9, 0.35) * (0.85 + 0.15 * (ridge > 0)), o)
        groove = np.abs(rho - rs) < 0.8
        o = np.where(groove[..., None], o * 0.35, o)
        # painted pointer that follows the dome
        on = (np.abs(px_) < 1.2) & (py_ > 0.30 * R) & (py_ < 0.76 * R)
        pc = np.array([0.97, 0.97, 0.98]) if col.mean() < 0.6 else np.array([0.08, 0.08, 0.09])
        o = np.where(on[..., None], pc * (0.55 + 0.45 * np.clip(nd @ L, 0, 1)[..., None]) + 0.25 * shade(nd, pc, 0, 0.12)[..., :] * 0.4, o)
        out = o
    elif style == 'chromerim':
        ri, rr = 0.66 * R, 0.86 * R              # coloured insert, chrome ring (rounded), thin dark edge to R
        ins = rho < ri
        ring = (rho >= ri) & (rho < rr)
        t = np.clip((rho - ri) / (rr - ri), 0, 1)
        s = (t - 0.5) * 2                        # -1..1 across the rounded ring
        nr = norm(nz * np.sqrt(np.clip(1 - s * s * 0.85, 0.05, 1))[..., None] + radial * (s * 0.9)[..., None])
        n_ = np.where(ring[..., None], nr, nz)
        o_ins = shade(nz, col, 0.9, 0.38) * 1.65 + rings * 0.05
        aniso = np.abs(np.cos(phi - math.atan2(L[1], L[0]))) ** 10 * np.clip(1 - rho / ri, 0, 1) ** 0.5
        o_ins = o_ins + aniso[..., None] * 0.28 * col
        chrome = shade(nr, np.array([0.80, 0.82, 0.86], np.float32), 1.0, 0.07) * 1.05
        knurl = np.sin(60 * loc)[..., None]
        nk = norm(nz * 0.25 + radial * 0.9 + tang * 0.6 * knurl)
        o_out = shade(nk, np.array([0.30, 0.31, 0.34], np.float32), 0.9, 0.3) * (0.8 + 0.2 * (knurl > 0))
        o = np.where(ins[..., None], o_ins, np.where(ring[..., None], chrome, o_out))
        sep = np.abs(rho - ri) < 0.6
        o = np.where(sep[..., None], o * 0.3, o)
        on = (np.abs(px_) < 1.3) & (py_ > 0.12 * R) & (py_ < 0.60 * R)
        pc = np.array([0.97, 0.97, 0.98]) if col.mean() < 0.62 else np.array([0.06, 0.06, 0.07])
        o = np.where(on[..., None], pc, o)
        out = o
    elif style == 'pointer':
        # user 2026-11-14 (assets/hexx and pointer knobs.png, top row): colour = the skirt (cream by default),
        # spun brass insert, scalloped skirt edge, black pointer line on the skirt from the insert up to the edge
        ri = 0.56 * R
        edge_r = R * (1 - 0.035 * (0.5 + 0.5 * np.cos(30 * loc)))      # scalloped outline
        alpha = np.clip((edge_r - rho) * (n / box) + 0.5, 0, 1)
        ins = rho < ri
        t = np.clip((rho - ri) / (edge_r - ri), 0, 1)
        # skirt: rises from the insert, rounded shoulder, drops at the edge
        g = (t * 1.6 - 0.35)
        flute = np.sin(30 * loc)[..., None] * np.clip((t - 0.6) / 0.4, 0, 1)[..., None]
        nsk = norm(nz + radial * g[..., None] * 0.9 + tang * 0.35 * flute)
        n_ = np.where(ins[..., None], nz, nsk)
        o_sk = shade(nsk, col, 0.05, 0.45) * 1.05
        brass = np.array([0.80, 0.62, 0.30], np.float32)
        if top_col is not None:   # the insert in another colour, as bright as the picked colour (brass = 0.63 measured)
            brass = np.array(top_col, np.float32) / 255 * 0.86
        aniso = np.abs(np.cos(phi - math.atan2(L[1], L[0]))) ** 8 * np.clip(1 - rho / ri, 0, 1) ** 0.4
        o_in = shade(nz, brass, 0.9, 0.35) * 1.55 + rings * 0.06 + aniso[..., None] * 0.35 * brass
        o = np.where(ins[..., None], o_in, o_sk)
        lip = np.abs(rho - ri) < 0.7
        o = np.where(lip[..., None], o * 0.45, o)
        on = (np.abs(px_) < 1.0) & (py_ > ri + 0.6) & (py_ < 0.97 * R)
        pc = np.array([0.05, 0.05, 0.05]) if col.mean() > 0.30 else np.array([0.94, 0.94, 0.94])   # white line on dark skirts
        o = np.where(on[..., None], pc, o)
        out = o * (1 - 0.5 * np.clip((rho - (edge_r - 1.2)) / 1.2, 0, 1)[..., None])
    elif style == 'hexcap':
        # user 2026-11-14 (assets/hexx and pointer knobs.png, bottom row): colour = the body (black by default), 7 rounded
        # lobes, white pointer bar on the top, blue ring round the base (the ring is round, so it doesn't swim as it turns)
        Rb = 0.82 * R
        rl = Rb * (1 + 0.10 * np.cos(7 * loc))                          # lobed outline
        u = np.clip(rho / rl, 0, 1.2)
        body = rho < rl
        g = np.clip((u - 0.45) / 0.55, 0, 1) ** 1.6 * 1.4
        dr = -Rb * 0.10 * 7 * np.sin(7 * loc) / np.maximum(rho, 1)      # outline slope -> sideways tilt on the lobes
        nb = norm(nz + radial * g[..., None] - tang * (dr * g * 0.8)[..., None])
        o_b = shade(nb, col, 0.15, 0.40) * 0.80 + rings * 0.01
        ring_c = np.array([0.20, 0.36, 0.50], np.float32)
        ring = (rho >= 0.98 * R - 1.3) & (rho < 0.98 * R + 0.2)
        o = np.where(body[..., None], o_b, np.where(ring[..., None], ring_c, 0))
        alpha = np.clip(np.maximum(body.astype(np.float32), ring.astype(np.float32)), 0, 1)
        alpha = np.maximum(np.clip((rl - rho) * (n / box) + 0.5, 0, 1), np.where(ring, 1.0, 0.0))
        on = (np.abs(px_) < 1.2) & (py_ > 0.10 * R) & (py_ < 0.62 * R)
        pc = np.array([0.96, 0.96, 0.95]) if col.mean() < 0.6 else np.array([0.06, 0.06, 0.07])
        o = np.where(on[..., None], pc, o)
        out = o * (1 - 0.55 * np.clip((rho - (rl - 1.4)) / 1.4, 0, 1)[..., None] * body[..., None])
    elif style in ('tabcap', 'tabcapblk'):
        # user 2026-11-14 (assets/hexx knobs 001.png top view, hexx knobs_slantView.png): HEXX 500-style knob, body with one
        # ear (the ear is the pointer), two small notches beside it, a textured coloured insert. colour = the insert;
        # tabcap = bead-blasted silver body, tabcapblk = black plastic body
        Rb, ri = 0.86 * R, 0.62 * R
        ear = (py_ > 0) & (np.abs(px_) < 0.40 * R) & (py_ < 0.95 * R)
        notch = (np.abs(np.abs(px_) - 0.46 * R) < 0.05 * R) & (py_ > 0.60 * R)
        body = ((rho < Rb) | ear) & ~notch
        alpha = body.astype(np.float32)
        from PIL import ImageFilter
        alpha = np.asarray(Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(n / box * 0.45))).astype(np.float32) / 255
        ins = rho < ri
        de_ear = np.minimum((0.95 * R - py_) / (0.05 * R), (0.40 * R - np.abs(px_)) / (0.05 * R))
        de = np.clip(np.where(ear, np.maximum(de_ear, (Rb - rho) / (0.10 * R)), (Rb - rho) / (0.10 * R)), 0, 1)   # 0 at the edge
        edge_n = norm(nz + radial * (1 - de)[..., None] * 1.1)
        bc = np.array([0.74, 0.75, 0.77], np.float32) if style == 'tabcap' else np.array([0.07, 0.07, 0.075], np.float32)
        grit = (np.sin(px_ * 7.3 + py_ * 3.1) * np.sin(py_ * 6.7 - px_ * 2.3) + np.sin(px_ * 13.1 - py_ * 11.7) * 0.6)[..., None]
        if style == 'tabcap':
            o_b = shade(edge_n, bc, 0.75, 0.55) * 1.35 + grit * 0.025
        else:
            o_b = shade(edge_n, bc, 0.1, 0.45) * 1.0 + grit * 0.008
        lipw = (rho >= ri) & (rho < ri + 0.07 * R)                       # the insert sits in a slightly raised lip
        o_b = np.where(lipw[..., None], o_b * (1.25 if style == 'tabcap' else 1.6) + 0.03, o_b)
        o_in = col * (0.66 + 0.12 * np.clip(nz @ L, 0, 1))[..., None] + grit * 0.03 * (0.3 + col.mean())   # matte, keeps its colour
        o = np.where(ins[..., None], o_in, o_b)
        o = np.where((np.abs(rho - ri) < 0.55)[..., None], o * 0.35, o)
        out = o
    elif style in ('colourtop', 'greytop'):
        # user 2026-11-14 (assets/mad knobs.png, OMTER rows 7-8): ribbed skirt (black / light grey) round a flat coloured
        # top, white pointer line from the top's edge to the rim. colour = the top
        rt = 0.68 * R
        top = rho < rt
        ridge = np.sin(24 * loc)[..., None]
        t = np.clip((rho - rt) / (R - rt), 0, 1)[..., None]
        ns = norm(nz * (0.9 - 0.6 * t) + radial * (0.3 + 0.6 * t) + tang * 0.45 * ridge * t)
        sc = np.array([0.06, 0.06, 0.065], np.float32) if style == 'colourtop' else np.array([0.50, 0.50, 0.48], np.float32)
        o_s = shade(ns, sc, 0.0, 0.6) * (0.85 + 0.15 * (ridge > 0))
        o_t = col * 0.68 + 0.04
        o = np.where(top[..., None], o_t, o_s)
        o = np.where((np.abs(rho - rt) < 0.6)[..., None], o * 0.5, o)
        on = (np.abs(px_) < 0.9) & (py_ > rt - 0.06 * R) & (py_ < 0.98 * R)
        pc = np.array([0.95, 0.95, 0.94]) if style == 'colourtop' else np.array([0.06, 0.06, 0.07])
        out = np.where(on[..., None], pc, o)
    elif style == 'spuntop':
        # user 2026-11-14 (assets/mad knobs.png, OMTER rows 2, 4, 6): knurled skirt in the colour round a spun aluminium
        # top with an engraved black pointer line
        rt = 0.72 * R
        top = rho < rt
        ridge = np.sin(40 * loc)[..., None]
        t = np.clip((rho - rt) / (R - rt), 0, 1)[..., None]
        ns = norm(nz * (0.7 - 0.4 * t) + radial * (0.5 + 0.4 * t) + tang * 0.6 * ridge)
        o_s = shade(ns, col, 0.2, 0.4) * (0.8 + 0.2 * (ridge > 0))
        al = np.array([0.82, 0.83, 0.85], np.float32)
        aniso = np.abs(np.cos(phi - math.atan2(L[1], L[0]))) ** 12 * np.clip(1 - rho / rt, 0, 1) ** 0.4
        o_t = shade(nz, al, 0.9, 0.3) * 1.5 + rings * 0.06 + aniso[..., None] * 0.35
        o = np.where(top[..., None], o_t, o_s)
        o = np.where((np.abs(rho - rt) < 0.6)[..., None], o * 0.4, o)
        on = (np.abs(px_) < 0.8) & (py_ > 0.15 * R) & (py_ < rt - 0.08 * R)
        out = np.where(on[..., None], np.array([0.05, 0.05, 0.05]), o)
    elif style == 'flat':                        # today's cap (the light turns with it), for comparison
        th = loc + math.pi / 2
        rng = np.random.default_rng(int(30 * 13) + 4)
        fine = sum(rng.normal() * np.sin(k * th + rng.uniform(0, 6.28)) for k in range(40, 140, 3)) * 0.12
        lum = max(0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2], 12.0)
        b0, b1 = lum + 6, min(60.0, max(26.0, 0.25 * lum + 18))
        rc = R
        b = b0 + b1 * (0.6 * np.cos(2 * (th + 0.75)) + 0.4 * np.cos(th + 2.2)) + fine * b1 * 0.4 - 18 * (rho / rc) ** 3
        o = np.clip(b[..., None] * (np.array(colour, np.float32) / lum), 0, 255) / 255
        on = (np.abs(px_) < max(2.4, rc * 0.10) / 2) & (py_ > 0.15 * rc) & (py_ < 0.92 * rc)
        lumc = 0.299 * colour[0] + 0.587 * colour[1] + 0.114 * colour[2]
        pcol = np.array([18, 18, 22]) / 255 if lumc > 150 else np.array([246, 246, 248]) / 255
        o = np.where(on[..., None], pcol, o)
        edge = np.clip(1 - np.abs(rho - rc) / 0.8, 0, 1)[..., None] * 0.7
        out = o * (1 - edge) + np.array([10, 10, 14]) / 255 * edge
    # filmic-ish curve, then picture
    out = 1 - np.exp(-np.clip(out, 0, None) * 1.25)
    out = out / (1 - math.exp(-1.25))
    rgba = np.concatenate([np.clip(out, 0, 1), alpha[..., None]], -1)
    return Image.fromarray((rgba * 255).astype(np.uint8), 'RGBA')

# 2026-11-15, user: "they must be the shape of these knobs" (assets/hexx knobs 001.png). tabcap / tabcapblk are now cut
# straight out of that photo (ref_hexx_tab_top.png): knob 1 (silver body) and knob 2 (black body). The insert is re-tinted
# to the wanted colour keeping the photo's grain; the left ear is the pointer, so the cut is turned to put it at 12.
_HEXX_SRC = {'tabcap': 0, 'tabcapblk': 1}
_hexx_cache = {}

def _hexx_sprite(style):
    if style in _hexx_cache:
        return _hexx_cache[style]
    ref = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref_hexx_tab_top.png')).convert('RGBA')
    a = np.asarray(ref).astype(np.float32)
    fg = (a[..., 3] > 40) & (a[..., :3].max(-1) > 18)
    xs = np.where(fg.any(0))[0]
    segs, s0, pv = [], xs[0], xs[0]
    for x in xs[1:]:
        if x > pv + 3:
            segs.append((s0, pv)); s0 = x
        pv = x
    segs.append((s0, pv))
    x0, x1 = segs[_HEXX_SRC[style]]
    sub = a[:, x0 - 6:x1 + 7]
    rgb = sub[..., :3] / 255
    mx, mn = rgb.max(-1), rgb.min(-1)
    sat = (mx - mn) / np.maximum(mx, 1e-3)
    ins = (sat > 0.45) & (sub[..., 3] > 200)               # the coloured insert (blue / green)
    yy, xx = np.nonzero(ins)
    cy, cx = yy.mean(), xx.mean()
    ri = math.sqrt(ins.sum() / math.pi)
    Y, X = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    rr = np.hypot(X - cx, Y - cy)
    body_r = rr[(sub[..., 3] > 128)]
    ext = np.percentile(body_r, 99.9)                        # ear tip
    disc = rr < ri - 1.5
    # insert as a grain map: luminance relative to its mean
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    grain = np.where(disc, lum / max(lum[disc].mean(), 1e-3), 1.0)
    edge = np.clip((ri + 2.5 - rr) / 2.0, 0, 1)             # 1 inside the insert, fades over its rim
    _hexx_cache[style] = (sub, grain, edge, cx, cy, ri, ext)
    return _hexx_cache[style]


def hexx_photo_frame(style, colour, ang, R=24.0, box=68.0, n=272):
    sub, grain, edge, cx, cy, ri, ext = _hexx_sprite(style)
    col = np.array(colour, np.float32) / 255
    lc = float(col @ np.array([0.299, 0.587, 0.114], np.float32))
    g = 1 + (grain - 1) * (0.35 if lc > 0.8 else 0.6)
    tint = np.clip(col[None, None, :] * (0.92 * g)[..., None] + (g[..., None] - 1) * 0.12, 0, 1) * 255
    rgb = sub[..., :3] * (1 - edge[..., None]) + tint * edge[..., None]
    im = Image.fromarray(np.concatenate([rgb, sub[..., 3:]], -1).clip(0, 255).astype(np.uint8), 'RGBA')
    # centre on the insert, square canvas, ear (left) to 12 o'clock, then the knob's own angle
    half = int(math.ceil(ext)) + 4
    c = Image.new('RGBA', (2 * half, 2 * half), (0, 0, 0, 0))
    c.alpha_composite(im, (int(round(half - cx)), int(round(half - cy))))
    c = c.rotate(-90 - math.degrees(ang), resample=Image.BICUBIC)
    k = n / box                                              # picture px per screen px
    side = max(1, int(round(2 * half * (R * 0.98 / ext) * k)))
    c = c.resize((side, side), Image.LANCZOS)
    out = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    out.alpha_composite(c, ((n - side) // 2, (n - side) // 2))
    return out


# 2026-11-15, user: "add these knobs to the collection" (assets/suede knobs.png = ref_suede_knobs.png, clear background):
# 1 blue ear knob on a grey skirt, 2/3 knurled silver ring + grey fluted cap, 4 grey fluted cap on a grey skirt, 5 red ear
# knob. Cut straight from the photo like the HEXX caps. style -> (knob index, pointer angle in the photo (deg clockwise from
# 12; None = find the cream mark), what the colour repaints: 'sat' = the coloured body, ('disc', f) = the cap inside f*skirt)
_SUEDE = {'suedeear': (0, 180.0, 'sat'), 'suedeknurl': (1, 180.0, ('disc', 0.69)), 'suedefluted': (3, None, ('disc', 0.75))}
SUEDE_DRAWN = {'suedeknurl': None, 'suedefluted': None}   # filled in: the photo's own cap colour (= no repaint)
_suede_cache = {}


def _suede_sprite(style):
    if style in _suede_cache:
        return _suede_cache[style]
    idx, pang, mode = _SUEDE[style]
    ref = Image.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ref_suede_knobs.png')).convert('RGBA')
    a = np.asarray(ref).astype(np.float32)
    fg = (a[..., 3] > 40) & (a[..., :3].max(-1) > 18)
    xs = np.where(fg.any(0))[0]
    segs, s0, pv = [], xs[0], xs[0]
    for x in xs[1:]:
        if x > pv + 3:
            segs.append((s0, pv)); s0 = x
        pv = x
    segs.append((s0, pv))
    x0, x1 = segs[idx]
    sub = a[:, x0 - 6:x1 + 7].copy()
    m = fg[:, x0 - 6:x1 + 7]
    w = m.sum(1)
    rows = np.where(w >= w.max() - 1)[0]
    cy = rows.mean()                                    # the skirt's widest rows (the ear runs past it up and down)
    cols = np.where(m[int(round(cy))])[0]
    cx = (cols[0] + cols[-1]) / 2.0
    rs = (cols[-1] - cols[0]) / 2.0                     # skirt radius
    Y, X = np.mgrid[0:sub.shape[0], 0:sub.shape[1]]
    rr = np.hypot(X - cx, Y - cy)
    ext = np.percentile(rr[sub[..., 3] > 128], 99.9)
    rgb = sub[..., :3] / 255
    lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    from PIL import ImageFilter
    cr = (rgb[..., 0] > 0.70) & (rgb[..., 2] > 0.5) & (rgb[..., 0] - rgb[..., 2] > 0.04) & (rr < 0.75 * rs) & (sub[..., 3] > 200)
    if pang is None:                                    # the cream pointer mark
        yy, xx = np.nonzero(cr)
        pang = math.degrees(math.atan2((xx - cx).mean(), -(yy - cy).mean()))
    elif style == 'suedeknurl' and cr.any():
        # the knurled knob: the ring's dark line is the pointer, so the cap's cream mark is painted out with the cap
        # 12 degrees round (same radius, same texture)
        d = np.asarray(Image.fromarray((cr * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(7)), np.float32) / 255
        d = np.asarray(Image.fromarray((d * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0)), np.float32)[..., None] / 255
        t = math.radians(12)
        sx = np.clip(np.round(cx + (X - cx) * math.cos(t) - (Y - cy) * math.sin(t)), 0, sub.shape[1] - 1).astype(int)
        sy = np.clip(np.round(cy + (X - cx) * math.sin(t) + (Y - cy) * math.cos(t)), 0, sub.shape[0] - 1).astype(int)
        sub[..., :3] = sub[..., :3] * (1 - d) + sub[sy, sx, :3] * d
        rgb = sub[..., :3] / 255
        lum = rgb @ np.array([0.299, 0.587, 0.114], np.float32)
    if mode == 'sat':
        mx, mn = rgb.max(-1), rgb.min(-1)
        sat = (mx - mn) / np.maximum(mx, 1e-3)
        msk = ((sat > 0.35) & (sub[..., 3] > 200)).astype(np.float32)
        msk = np.asarray(Image.fromarray((msk * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255
    else:
        msk = np.clip((mode[1] * rs + 1.5 - rr) / 3.0, 0, 1) * (sub[..., 3] > 200)
        if style == 'suedefluted':   # the cream pointer keeps its colour
            keep = np.asarray(Image.fromarray((cr * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3)), np.float32) / 255
            msk = msk * (1 - keep)
    sel = msk > 0.9
    grain = np.where(msk > 0, lum / max(lum[sel].mean(), 1e-3), 1.0)
    own = tuple(int(round(v)) for v in (sub[..., :3][sel].mean(0)))
    if style in SUEDE_DRAWN:
        SUEDE_DRAWN[style] = own
    _suede_cache[style] = (sub, grain, msk, cx, cy, ext, pang, own)
    return _suede_cache[style]


def suede_photo_frame(style, colour, ang, R=24.0, box=68.0, n=272):
    sub, grain, msk, cx, cy, ext, pang, own = _suede_sprite(style)
    rgb = sub[..., :3]
    if colour is not None and tuple(int(c) for c in colour) != own:
        col = np.array(colour, np.float32) / 255
        lc = float(col @ np.array([0.299, 0.587, 0.114], np.float32))
        g = 1 + (grain - 1) * (0.35 if lc > 0.8 else 0.6)
        tint = np.clip(col[None, None, :] * (0.92 * g)[..., None] + (g[..., None] - 1) * 0.12, 0, 1) * 255
        rgb = rgb * (1 - msk[..., None]) + tint * msk[..., None]
    im = Image.fromarray(np.concatenate([rgb, sub[..., 3:]], -1).clip(0, 255).astype(np.uint8), 'RGBA')
    half = int(math.ceil(ext)) + 4
    c = Image.new('RGBA', (2 * half, 2 * half), (0, 0, 0, 0))
    c.alpha_composite(im, (int(round(half - cx)), int(round(half - cy))))
    c = c.rotate(pang - math.degrees(ang), resample=Image.BICUBIC)   # the photo's pointer to 12, then the knob's angle
    k = n / box
    side = max(1, int(round(2 * half * (R * 0.98 / ext) * k)))
    c = c.resize((side, side), Image.LANCZOS)
    out = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    out.alpha_composite(c, ((n - side) // 2, (n - side) // 2))
    return out


PHOTO = set(_HEXX_SRC) | set(_SUEDE)   # photo cut caps (fixed_light relights them instead of redrawing per frame)


def with_shadow(im, R, box, n):
    """soft contact shadow under the cap (static: in the build it would go in the page background)"""
    from PIL import ImageFilter
    a = np.zeros((n, n), np.float32)
    x, y = grid(n, box)
    a = np.clip((R + 1.5 - np.hypot(x - 1.2, y - 2.6)) * (n / box) * 0.5, 0, 1) * 0.65
    sh = Image.fromarray((a * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(n / box * 2.4))
    base = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    base.putalpha(sh)
    base.alpha_composite(im)
    return base

STYLES = ['flat', 'knurl', 'dome', 'chromerim', 'pointer', 'hexcap', 'tabcap', 'tabcapblk', 'colourtop', 'greytop', 'spuntop', 'suedeear', 'suedeknurl', 'suedefluted']   # 2026-11-15: suede* (assets/suede knobs.png); 2026-11-14: pointer + hexcap (assets/hexx and pointer knobs.png); tabcap/tabcapblk (assets/hexx knobs*.png); colourtop/greytop/spuntop (assets/mad knobs.png)
def main():
    OUT = sys.argv[1]
    os.makedirs(OUT, exist_ok=True)
    COLOURS = {'silver': (196, 198, 204), 'red': (200, 30, 28), 'cobalt': (40, 82, 192), 'brass': (196, 164, 84), 'black': (44, 45, 48)}
    FR = 64
    SHOW = 112                                       # px per frame on the page (2x a 56 px knob)
    info = {}
    for st in STYLES:
        for cn, c in COLOURS.items():
            frames = []
            for i in range(FR):
                ang = math.radians(-135 + 270 * i / (FR - 1))
                im = cap_frame(st, c, ang)
                im = with_shadow(im, 24.0, 68.0, 272)
                frames.append(im.resize((SHOW, SHOW), Image.LANCZOS))
            strip = Image.new('RGBA', (SHOW, SHOW * FR), (0, 0, 0, 0))
            for i, f in enumerate(frames):
                strip.alpha_composite(f, (0, i * SHOW))
            strip.save(os.path.join(OUT, '%s_%s.png' % (st, cn)), optimize=True)
            print(st, cn, flush=True)
    # size check at device size: a 28 px knob (Flannel INPUT) -> cap picture 2*28+8 = 64 px at the skin's 2x = 128? use 64 and 128
    sizes = {}
    for st in STYLES[1:]:
        for px in (64, 128):
            strip = Image.new('RGBA', (px, px * FR), (0, 0, 0, 0))
            for i in range(FR):
                ang = math.radians(-135 + 270 * i / (FR - 1))
                strip.alpha_composite(cap_frame(st, COLOURS['red'], ang, n=px * 2).resize((px, px), Image.LANCZOS), (0, i * px))
            p = os.path.join(OUT, '_size_%s_%d.png' % (st, px))
            strip.save(p, optimize=True)
            sizes['%s_%d' % (st, px)] = os.path.getsize(p)
    json.dump({'sizes': sizes, 'frames': FR, 'show': SHOW, 'styles': STYLES, 'colours': list(COLOURS)}, open(os.path.join(OUT, 'info.json'), 'w'))
    print(sizes)


if __name__ == "__main__":
    main()
