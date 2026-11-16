"""Knob caps whose light stays put while the cap turns (user 2026-11-15: "the lighting on the knobs rotates with the knob
when I turn them ... can we make it more realistic?").

Until now every metal-page knob was ONE picture (pointer up) that the skin spins for each of its 64 frames, so the sheen
lobes, bevel highlights and shadows baked into the picture turned with the knob. Here each knob gets its own 64-frame strip
(layout `strip=... frames=64`, which skin_assets / html_art already take), built from the same picture:

  - in polar coordinates round the cap centre, the picture's brightness is smoothed along the angle (SIGMA_DEG): what is
    broad (sheen lobes, the lit/shaded side, bevel highlights) is the LIGHT; what is fine (brushed grain, knurls, ridges)
    and the pointer (masked out of the estimate) is the CAP
  - frame k = the picture turned to its angle, times (light at rest / light turned with it), so the light goes back to
    where it was and only the grain and the pointer move.

Shaped caps drawn by realistic-caps-mock/real_caps.py (pointer, hexcap, blacktop/greytop/spuntop ...) are simply drawn at each
angle with their fixed light (cap_frame(ang)); HEXX photo caps go through the relight like the script caps.
Chicken-heads (Molten) are not round, so they keep turning as one picture for now.
"""
import math, os
import numpy as np
from PIL import Image

FRAMES = 64          # = skin_knob_frames in make_layout.py
SIGMA_DEG = 14.0     # angular smoothing: wider than this = light, narrower = the cap's own texture
PTR_DEG = 16.0       # pointer wedge kept out of the light estimate (wider near the centre, see _ptr_mask)
NA = 720             # angle samples
SUFFIX = '__fl%d' % FRAMES


def _bilinear(img, x, y):
    """img (h, w[, c]) sampled at float x, y (clamped)"""
    h, w = img.shape[:2]
    x = np.clip(x, 0, w - 1.001); y = np.clip(y, 0, h - 1.001)
    x0 = np.floor(x).astype(int); y0 = np.floor(y).astype(int)
    fx = x - x0; fy = y - y0
    if img.ndim == 3:
        fx = fx[..., None]; fy = fy[..., None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _gauss_circ(a, sigma_bins):
    """circular gaussian blur along axis 1"""
    n = a.shape[1]
    k = np.arange(n); k = np.minimum(k, n - k).astype(np.float64)
    g = np.exp(-0.5 * (k / max(sigma_bins, 1e-3)) ** 2); g /= g.sum()
    return np.real(np.fft.ifft(np.fft.fft(a, axis=1) * np.fft.fft(g)[None, :], axis=1))


def _gauss_rows(a, sigma):
    """plain gaussian blur along axis 0 (edges clamped)"""
    if sigma < 0.3:
        return a
    r = int(3 * sigma) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2); k /= k.sum()
    p = np.pad(a, ((r, r), (0, 0)), mode='edge')
    return sum(k[i] * p[i:i + a.shape[0]] for i in range(2 * r + 1))


def light_field(rgba):
    """(L, R): the picture's broad light as a function L(rho, phi) on a polar grid (rho px, NA angles, phi 0 = up, clockwise)
    and the cap radius in px"""
    n = rgba.shape[0]
    c = (n - 1) / 2.0
    al = rgba[..., 3] / 255.0
    yy, xx = np.mgrid[0:n, 0:n]
    rr = np.hypot(xx - c, yy - c)
    R = float(rr[al > 0.5].max()) if (al > 0.5).any() else n / 2.0
    Y = rgba[..., :3] @ np.array([0.299, 0.587, 0.114])
    NR = int(math.ceil(R)) + 2
    rho = np.arange(NR) + 0.5
    phi = np.arange(NA) * (2 * math.pi / NA)
    P, F = np.meshgrid(rho, phi, indexing='ij')
    sx, sy = c + P * np.sin(F), c - P * np.cos(F)
    Yp = _bilinear(Y, sx, sy)
    Ap = _bilinear(al, sx, sy)
    m = (Ap > 0.95).astype(np.float64)
    # pointer wedge round phi = 0: PTR_DEG, or wider near the centre where the pointer bar covers more angle
    half = np.maximum(math.radians(PTR_DEG), np.arctan2(0.09 * R, np.maximum(P, 1.0)))
    d = np.abs((F + math.pi) % (2 * math.pi) - math.pi)
    m[d < half] = 0
    sb = math.radians(SIGMA_DEG) / (2 * math.pi / NA)
    num = _gauss_rows(_gauss_circ(Yp * m, sb), 1.5)
    den = _gauss_rows(_gauss_circ(m, sb), 1.5)
    ring = (Yp * m).sum(1) / np.maximum(m.sum(1), 1e-6)          # fallback: the ring's mean
    L = np.where(den > 0.05, num / np.maximum(den, 1e-6), ring[:, None])
    return L, R


def _field_at(L, rho, phi):
    """sample the polar field at cartesian rho/phi arrays (phi wraps)"""
    NR = L.shape[0]
    fi = (phi % (2 * math.pi)) / (2 * math.pi) * NA
    ri = np.clip(rho - 0.5, 0, NR - 1.001)
    Lw = np.concatenate([L, L[:, :1]], axis=1)                   # wrap one column for interpolation
    return _bilinear(Lw, fi, ri)


def relight_frames(pic, frames=FRAMES, a0=-135.0, a1=135.0):
    """pic: PIL RGBA, pointer up, its light as drawn. -> list of PIL frames, pointer at a0..a1 deg (clockwise from up),
    the light where the picture has it"""
    rgba = np.asarray(pic.convert('RGBA')).astype(np.float64)
    n = rgba.shape[0]
    c = (n - 1) / 2.0
    L, R = light_field(rgba)
    yy, xx = np.mgrid[0:n, 0:n]
    rho = np.hypot(xx - c, yy - c)
    phi = np.arctan2(xx - c, -(yy - c))                          # 0 = up, clockwise
    Lrest = _field_at(L, rho, phi)
    # the pointer (paint or a notch, it stands out from the light near 12 o'clock) only takes part of the correction, so a
    # white line doesn't go grey on the shaded side
    Y = rgba[..., :3] @ np.array([0.299, 0.587, 0.114])
    dphi = np.abs((phi + math.pi) % (2 * math.pi) - math.pi)
    wedge = dphi < np.maximum(math.radians(PTR_DEG), np.arctan2(0.09 * R, np.maximum(rho, 1.0)))
    pm = np.clip((np.abs(Y - Lrest) - 25.0) / 30.0, 0, 1) * wedge * (rgba[..., 3] > 128)
    pmask = Image.fromarray((pm * 255).astype(np.uint8), 'L')
    out = []
    for k in range(frames):
        a = a0 + (a1 - a0) * k / (frames - 1)
        rot = np.asarray(pic.rotate(-a, resample=Image.BICUBIC)).astype(np.float64)
        Lturn = _field_at(L, rho, phi - math.radians(a))         # the drawn light, turned with the cap
        g = np.clip((Lrest + 6.0) / (Lturn + 6.0), 0.2, 5.0)
        w = np.asarray(pmask.rotate(-a, resample=Image.BILINEAR)).astype(np.float64) / 255.0
        g = g ** (1.0 - 0.75 * w)
        g = np.where(rho <= R + 1, g, 1.0)
        rgb = np.clip(rot[..., :3] * g[..., None], 0, 255)
        out.append(Image.fromarray(np.dstack([rgb, rot[..., 3]]).round().astype(np.uint8), 'RGBA'))
    return out


def stack(frames_):
    w, h = frames_[0].size
    st = Image.new('RGBA', (w, h * len(frames_)), (0, 0, 0, 0))
    for i, f in enumerate(frames_):
        st.paste(f, (0, i * h))
    return st


def strip_path(img_path):
    b, e = os.path.splitext(img_path)
    return b + SUFFIX + e


def make_strip(src, dst=None, shaped=None, frames=FRAMES):
    """src picture -> its fixed-light strip (cached by mtime). shaped: (real_caps module, shape, colour, R, box, n) to draw
    each frame at its angle instead of relighting"""
    dst = dst or strip_path(src)
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        return dst
    if shaped is not None:
        rc, shape, col, R, box, n = shaped
        if shape in getattr(rc, 'PHOTO', getattr(rc, '_HEXX_SRC', {})):   # photo cut caps (HEXX, Neve) are relit
            fr = relight_frames(Image.open(src), frames)
        else:
            fr = [rc.cap_frame(shape, col, math.radians(-135 + 270 * k / (frames - 1)), R=R, box=box, n=n) for k in range(frames)]
    else:
        fr = relight_frames(Image.open(src), frames)
    stack(fr).save(dst, optimize=False, compress_level=6)
    return dst
