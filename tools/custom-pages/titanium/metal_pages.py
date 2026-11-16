#!/usr/bin/env python3
"""X-Console: Titanium (TITANIUM): six page skins drawn in the style of the user's generated picture
(Titanium Skins/page_0.png), made from the Spades (Avalon) script: spun (radial-brushed) titanium panels with
light rays, chrome frames, dark title bars over a chrome rule, no screws, silver caps in black ticked bezels,
navy value boxes with cyan rims, dark brushed banner (black X- / chrome CONSOLE, chrome italic TITANIUM).

Writes per page N (0 PREAMP, 1 SHAPE, 2 EQ, 3 COMP, 4 OUTPUT, 5 INFO), 1280x628:
  bg_N.png    background only (what a custom page's art line would use; controls drawn on top)
  mock_N.png  the same with procedural knobs / buttons / lit meters, to judge the look
Control positions follow layout-gen2-spades.conf (screen y - 86), moved where the bigger
metal knobs needed room.  Run: /root/venv-skin/bin/python metal_pages.py <out dir>
"""
import sys, os, math, re
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import metal_knobs   # Theme Editor knob colours (tools/metal-knobs.txt), 2026-11-11
import metal_banner  # Theme Editor banner text colours (BANNER X- / TITLE / NAME / OUTLINE), 2026-11-11
import metal_dropdown  # Theme Editor drop-down colours (DROP-DOWN / TEXT / LIST TEXT), 2026-11-11
import metal_segs  # Theme Editor LIT BUTTONS / LIT BUTTON TEXT (2026-11-12)
import xc_logo  # the X-CONSOLE brand logo banner (all plugins 2026-11-12)
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 2                       # supersample
W, H = 1280, 628
FD = '/root/mpc-dev/mpc-vst-plugins/tools/html_art/fonts/'
INK = (242, 244, 248)       # label ink: white, outlined dark (label())
WHITE = (236, 240, 245)
BLUE = (64, 170, 255)
GLOW = (20, 110, 255)
VAL = (127, 212, 255)

_fc = {}
def font(px, w='Bold'):
    k = (px, w)
    if k not in _fc:
        _fc[k] = ImageFont.truetype(FD + 'TitilliumWeb-%s.ttf' % w, int(round(px * S)))
    return _fc[k]

# ---------------------------------------------------------------- masks
def new_mask():
    return Image.new('L', (W * S, H * S), 0)

def to_np(m, blur=0):
    if blur:
        m = m.filter(ImageFilter.GaussianBlur(blur * S))
    return np.asarray(m, np.float32) / 255.0

def blur_np(a, r):
    return to_np(Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8)), r)

def m_rrect(x, y, w, h, r, blur=0, ring=0):
    m = new_mask()
    box = [x * S, y * S, (x + w) * S - 1, (y + h) * S - 1]
    if ring:
        ImageDraw.Draw(m).rounded_rectangle(box, radius=r * S, outline=255, width=max(1, int(round(ring * S))))
    else:
        ImageDraw.Draw(m).rounded_rectangle(box, radius=r * S, fill=255)
    return to_np(m, blur)

def m_circles(pts, blur=0, ring=0):
    """pts: list of (cx, cy, r)"""
    m = new_mask(); d = ImageDraw.Draw(m)
    for cx, cy, r in pts:
        box = [(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S]
        if ring:
            d.ellipse(box, outline=255, width=max(1, int(round(ring * S))))
        else:
            d.ellipse(box, fill=255)
    return to_np(m, blur)

def m_lines(segs, width, blur=0):
    m = new_mask(); d = ImageDraw.Draw(m)
    for (x0, y0, x1, y1) in segs:
        d.line([x0 * S, y0 * S, x1 * S, y1 * S], fill=255, width=max(1, int(round(width * S))))
    return to_np(m, blur)

def text_w(txt, px, w='Bold', sp=0):
    f = font(px, w)
    return f.getlength(txt) / S + sp * max(0, len(txt) - 1)

def m_text(x, y, txt, px, anchor='mm', w='Bold', sp=0, blur=0, stroke=0, ital=0.0):
    m = new_mask(); d = ImageDraw.Draw(m); f = font(px, w)
    tw = text_w(txt, px, w, sp)
    x0 = x - (tw / 2 if anchor[0] == 'm' else tw if anchor[0] == 'r' else 0)
    if ital and anchor[0] == 'r':
        x0 -= ital * px * 0.4     # keep the slanted tops inside the right edge
    va = anchor[1]
    cx = x0
    for ch in txt if sp else [txt]:
        d.text((cx * S, y * S), ch, font=f, fill=255, anchor='l' + va,
               stroke_width=int(round(stroke * S)), stroke_fill=255)
        cx += f.getlength(ch) / S + sp
    if ital:   # slant: tops lean right (x_in = x_out + ital * (y - centre))
        m = m.transform(m.size, Image.AFFINE, (1, ital, -ital * y * S, 0, 1, 0), resample=Image.BICUBIC)
    return to_np(m, blur)

# ---------------------------------------------------------------- colour arrays
def vgrad(y0, y1, c0, c1):
    ys = np.arange(H * S, dtype=np.float32) / S
    t = np.clip((ys - y0) / max(1e-3, y1 - y0), 0, 1)[:, None, None]
    return np.asarray(c0, np.float32) * (1 - t) + np.asarray(c1, np.float32) * t

def boxblur_x(a, L):
    c = np.cumsum(np.concatenate([a[:, -L:], a], axis=1), axis=1)
    return (c[:, L:] - c[:, :-L]) / L

def brushed(seed, L):
    r = np.random.default_rng(seed)
    b = boxblur_x(r.normal(size=(H * S, W * S)).astype(np.float32), L * S) * math.sqrt(L * S)
    f = boxblur_x(r.normal(size=(H * S, W * S)).astype(np.float32), 6 * S) * math.sqrt(6 * S)
    t = 0.8 * b + 0.35 * f
    return (t / t.std()).astype(np.float32)

TEX1 = TEX2 = None   # brushed textures, made by load_textures() (the --strips run needs none)

def load_textures():
    global TEX1, TEX2
    print('textures...', flush=True)
    TEX1 = brushed(11, 180)
    TEX2 = brushed(23, 120)
TINT = np.array([0.965, 0.985, 1.02], np.float32)
_xs = np.arange(W * S, dtype=np.float32)[None, :] / S
_ys = np.arange(H * S, dtype=np.float32)[:, None] / S
SHEEN = (1 + 0.06 * np.sin((_xs * 0.9 + _ys) / 170.0) + 0.04 * np.sin((_xs - _ys * 0.5) / 410.0))[..., None]

def metal(y0, y1, c0, c1, tex, amp):
    return np.clip((vgrad(y0, y1, c0, c1) * TINT + tex[..., None] * amp) * SHEEN, 0, 255)

class Cv:
    def __init__(s):
        s.a = np.zeros((H * S, W * S, 3), np.float32)
    def over(s, col, m, alpha=1.0):
        m = (m * alpha)[..., None]
        s.a = s.a * (1 - m) + np.asarray(col, np.float32) * m
    def mul(s, m, f):
        s.a *= (1 - m[..., None] * (1 - f))
    def add(s, col, m, k=1.0):
        s.a += np.asarray(col, np.float32) * (m * k)[..., None]
    def rgba(s, im, x, y):
        """paste a PIL RGBA picture (already at S scale) with its top-left at page (x, y)"""
        a = np.asarray(im, np.float32)
        X, Y = int(round(x * S)), int(round(y * S))
        h, w = a.shape[:2]
        x0, y0, x1, y1 = max(0, X), max(0, Y), min(W * S, X + w), min(H * S, Y + h)
        if x1 <= x0 or y1 <= y0:
            return
        sub = a[y0 - Y:y1 - Y, x0 - X:x1 - X]
        al = sub[..., 3:4] / 255.0
        s.a[y0:y1, x0:x1] = s.a[y0:y1, x0:x1] * (1 - al) + sub[..., :3] * al
    def copy(s):
        c = Cv.__new__(Cv); c.a = s.a.copy(); return c
    def save(s, path):
        Image.fromarray(np.clip(s.a, 0, 255).astype(np.uint8)).resize((W, H), Image.LANCZOS).save(path)

# ---------------------------------------------------------------- pieces
def label(cv, x, y, t, px=15, anchor='mm', col=INK, sp=0.5):
    """white lettering with a dark outline + drop shadow (the picture's labels on the bright metal)"""
    cv.mul(m_text(x + 0.8, y + 1.6, t, px, anchor, sp=sp, blur=1.4, stroke=0.8), 0.45)
    cv.over((12, 13, 16), m_text(x, y, t, px, anchor, sp=sp, stroke=max(1.0, px * 0.07)), 0.9)
    cv.over(col, m_text(x, y, t, px, anchor, sp=sp))

def light_text(cv, x, y, t, px=12, anchor='mm', col=WHITE, sp=0, w='SemiBold'):
    cv.over(col, m_text(x, y, t, px, anchor, w=w, sp=sp))

def grad_text(cv, x, y, t, px, c0, c1, anchor='lm', sp=1.5, stroke_col=(8, 10, 14), stroke=1.6, stroke_a=0.9, ital=0.0, logo=False):
    if logo:   # the logo banner's name: slanted Arial Black like the logo's HEARTS
        nm = lambda st=0, blur=0, dx=0, dy=0: xc_logo.name_mask(sys.modules[__name__], x + dx, y + dy, t, px, anchor, st, blur)
        cv.mul(nm(stroke + 2.2, 2.5, 1.5, 2.5), 0.35)
        cv.over((0, 0, 0), nm(stroke + 1.3))
        cv.over(stroke_col, nm(stroke))
        cv.over((60, 0, 0), nm(0.5))
        m = nm()
        cv.over(vgrad(y - px * 0.36, y + px * 0.36, c0, c1), m)
        cv.add((255, 255, 255), m * np.clip((y - px * 0.05 - np.arange(H * S, dtype=np.float32)[:, None] / S) / (px * 0.3), 0, 1), 0.12)
        return m
    m = m_text(x, y, t, px, anchor, sp=sp, ital=ital)
    cv.mul(m_text(x + 2, y + 3, t, px, anchor, sp=sp, blur=2.5, ital=ital), 0.25)
    cv.over(stroke_col, m_text(x, y, t, px, anchor, sp=sp, stroke=stroke, ital=ital), stroke_a)
    cv.over(vgrad(y - px * 0.38, y + px * 0.38, c0, c1), m)
    return m

def screws(cv, pts):
    body = m_circles([(x, y, 4.6) for x, y in pts])
    cv.mul(m_circles([(x + 0.8, y + 1.2, 5.2) for x, y in pts], blur=1.2), 0.45)
    cv.over((0, 0, 0), body)
    for x, y in pts:
        m = m_circles([(x, y, 3.9)])
        cv.over(vgrad(y - 4, y + 4, (235, 238, 242), (95, 99, 106)), m)
    segs = []
    for i, (x, y) in enumerate(pts):
        a = math.radians(25 + 47 * i)
        segs.append((x - 3.2 * math.cos(a), y - 3.2 * math.sin(a), x + 3.2 * math.cos(a), y + 3.2 * math.sin(a)))
    cv.over((40, 42, 48), m_lines(segs, 1.1), 0.85)

def spun(x, y, w, h, base=150, amp=1.0, seed=0, cx=None, cy=None):
    """Spun (radial-brushed) titanium on a full-canvas array, drawn over the box x,y,w,h only: fine concentric
    rings + bright light rays from the centre, darker wedges between (the picture's panels)."""
    col = np.zeros((H * S, W * S, 3), np.float32)
    x0, y0 = max(0, int(x * S)), max(0, int(y * S))
    x1, y1 = min(W * S, int((x + w) * S) + 1), min(H * S, int((y + h) * S) + 1)
    cx = x + w / 2 if cx is None else cx
    cy = y + h * 0.42 if cy is None else cy
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / S
    dx, dy = xx - cx, yy - cy
    rr = np.sqrt(dx * dx + dy * dy)
    th = np.arctan2(dy, dx)
    R = math.hypot(w, h) / 2
    rng = np.random.default_rng(seed + 101)
    # rings: noise along the radius (quarter-pixel bins), lightly smoothed
    nb = int(R * 4) + 8
    ring = rng.normal(size=nb).astype(np.float32)
    ring = np.convolve(ring, np.ones(3, np.float32) / 3, mode='same')
    ring = ring / (ring.std() + 1e-6)
    rn = ring[np.clip((rr * 4).astype(int), 0, nb - 1)]
    # light: two broad lobes (the spun-metal "bow tie") + a few sharp rays
    lobes = 0.55 * np.cos(2 * (th + 0.55)) + 0.25 * np.cos(2 * (th - 0.35))
    rays = 0
    for a, p, k in [(-1.45, 40, 0.9), (1.7, 60, 0.7), (0.05, 30, 0.55), (-2.6, 50, 0.6), (2.75, 80, 0.5), (-0.75, 120, 0.45)]:
        rays = rays + k * np.abs(np.cos((th - a) / 2)) ** p
    near = np.exp(-(rr / (R * 0.55)) ** 2)
    b = base + amp * (50 * lobes + 78 * rays * (0.4 + 0.6 * near) + 5 * rn - 34 * (rr / R) ** 1.5 + 10 * near)
    col[y0:y1, x0:x1] = np.clip(b[..., None] * np.asarray([0.985, 0.99, 1.0], np.float32), 0, 255)
    return col

def panel(cv, x, y, w, h, title, compact=False, right_label=None, center=False):
    px, py, pw, ph = x + 2, y + 2, w - 4, h - 4
    rad = 9
    outer = m_rrect(px, py, pw, ph, rad)
    cv.mul(m_rrect(px + 1, py + 4, pw, ph, rad, blur=5), 0.45)
    # chrome frame: a bright brushed band round the face
    cv.over(metal(py, py + ph, (226, 228, 232), (120, 123, 128), TEX1, 18), outer)
    cv.add((255, 255, 255), outer * (1 - m_rrect(px + 1.5, py + 1.5, pw, ph, rad, blur=0.6)), 0.40)
    cv.mul(outer * (1 - m_rrect(px - 1.5, py - 1.5, pw, ph, rad, blur=0.6)), 0.40)
    cv.over((8, 9, 11), m_rrect(px, py, pw, ph, rad, ring=1.1), 0.9)
    # the spun face inside the frame
    fx, fy, fw, fh = px + 5, py + 5, pw - 10, ph - 10
    face = m_rrect(fx, fy, fw, fh, 7)
    cv.over(spun(fx, fy, fw, fh, 128 if not compact else 124, seed=int(x * 7 + y)), face)
    cv.mul(face * (1 - m_rrect(fx + 1.5, fy + 2.5, fw - 1, fh - 2, 7, blur=2.5)), 0.45)
    cv.over((20, 21, 24), m_rrect(fx, fy, fw, fh, 7, ring=0.9), 0.7)
    # dark title bar (brushed, recessed) + a chrome rule under it
    ry = py + (31 if compact else 36)
    tb = m_rrect(fx + 3, fy + 3, fw - 6, ry - fy - 6, 5)
    cv.over(metal(fy, ry, (92, 94, 98), (44, 46, 50), TEX1, 10), tb, 0.88)
    cv.add((255, 255, 255), tb * (1 - m_rrect(fx + 3, fy + 4.2, fw - 6, ry - fy - 6, 5, blur=0.5)), 0.30)
    cv.over((6, 7, 9), m_rrect(fx + 3, fy + 3, fw - 6, ry - fy - 6, 5, ring=0.8), 0.7)
    ty = (fy + 3 + ry - 3) / 2 + 0.5
    label(cv, (px + pw / 2 if center else px + 20), ty, title, 21 if not compact else 18, ('mm' if center else 'lm'), sp=1.0)
    if right_label:
        label(cv, px + pw - 18, ty + 1, right_label, 13, 'rm')
    x0, x1 = fx + 6, fx + fw - 6
    cv.over((10, 11, 13), m_lines([(x0, ry - 0.2, x1, ry - 0.2)], 1.2), 0.75)
    cv.over((236, 238, 242), m_lines([(x0, ry + 1.4, x1, ry + 1.4)], 1.6))
    cv.mul(m_lines([(x0, ry + 3.2, x1, ry + 3.2)], 1.4, blur=0.8), 0.6)
    return (fx, ry + 4, fw, fy + fh - ry - 4)

LOGO_FIT = os.environ.get('XC_LOGO_FIT', 'fit')   # mid | fill | fit (preview https://claude.ai/artifact/WpSLWqU3YNBnHWvSSoMewA)
if os.environ.get('XC_TI_LOGO') == '1':   # only with the logo banner: metal_banner treats a LOGO_ACCENT script as a logo one (name follows BANNER LINE)
    LOGO_ACCENT = None   # the logo's accent (None = the picture's red); the Theme Editor's BANNER LINE sets it (metal_banner.py)
LOGO_RED = (0, 0, 0)   # the left logo's red parts (user 2026-11-15: black); None = the picture's red
def banner(cv, name, blue_name=False, **_):
    """no X-CONSOLE logo (user 2026-11-15: "remove x-console logo from banner and change the banner background to
    that of the panels"): the banner is the panels' spun titanium face (spun()), the chrome rule under it, the name
    on the right in chrome italic as before the logo. XC_TI_LOGO=1 = the logo banner (banner_logo)."""
    if os.environ.get('XC_TI_LOGO') == '1':
        return banner_logo(cv, name)
    hb = 62
    m = m_rrect(0, 0, W, hb, 0)
    cv.over(spun(0, 0, W, hb, 128, seed=7, cx=W / 2, cy=hb * 0.42), m)
    cv.mul(m * (1 - m_rrect(-10, 1.5, W + 20, hb, 0, blur=2.5)), 0.40)   # the panels' inner shadow along the top
    # chrome rule under the banner (as the panels' frames)
    cv.over((4, 4, 6), m_lines([(0, hb - 4.6, W, hb - 4.6)], 1.4), 0.9)
    cv.over((205, 208, 214), m_lines([(0, hb - 2.6, W, hb - 2.6)], 1.8))
    cv.over((6, 6, 8), m_lines([(0, hb - 0.8, W, hb - 0.8)], 1.4), 0.9)
    # the X-CONSOLE logo on the left (user 2026-11-15: "put this logo in the left side of the banner"; [Ru5h Skins]/X-console
    # logo.png = logo/xconsole_logo2.png). Then "make the logo the same size as it is on the other plugins. Also, MAKE THE
    # RED PARTS OF THE LOGO BLACK": the size and place of the other 9 (xc_logo 'fit': scale 0.28 x NEW_K source px, left
    # edge NEW_X, CONSOLE rows centred on the bar's inside, bar top 11.4), red -> LOGO_RED via xc_logo.recolour (as BANNER X-)
    sc, top = 0.28, 11.4
    lg = xc_logo.recolour(Image.open(xc_logo.LOGO2).convert('RGBA'), LOGO_RED)
    k = xc_logo.NEW_K * sc
    lg = lg.resize((int(round(lg.width * k * S)), int(round(lg.height * k * S))), Image.LANCZOS)
    ysrc = (xc_logo.IN0 + xc_logo.IN1) / 2.0 - (xc_logo.NEW_L0 + xc_logo.NEW_L1) / 2.0 * xc_logo.NEW_K
    lx, ly = xc_logo.NEW_X * sc, top + (ysrc - xc_logo.BAR0) * sc
    sh = np.zeros((H * S, W * S), np.float32)
    al = np.asarray(lg.getchannel('A'), np.float32) / 255.0
    X0, Y0 = int(round((lx + 1.5) * S)), int(round((ly + 2.5) * S))
    y0 = max(0, Y0)
    sh[y0:Y0 + al.shape[0], X0:X0 + al.shape[1]] = al[y0 - Y0:H * S - Y0, :W * S - X0]
    cv.mul(blur_np(sh, 3.0), 0.45)
    cv.rgba(lg, lx, ly)
    ty = 29   # dark outline: the light spun metal behind it (a white stroke washed the name out)
    if blue_name:
        grad_text(cv, 1256, ty + 1, name, 32, (120, 210, 255), (25, 105, 215), anchor='rm', sp=2, stroke_col=(14, 15, 18), stroke=1.6)
    else:
        grad_text(cv, 1256, ty + 1, name, 32, (252, 253, 255), (118, 122, 130), anchor='rm', sp=2, stroke_col=(14, 15, 18), stroke=1.6, stroke_a=1.0, ital=0.22)
        cv.over((20, 22, 26), m_text(1256, ty + 1, name, 32, 'rm', sp=2, ital=0.22) * (1 - m_text(1256 - 0.6, ty + 0.4, name, 32, 'rm', sp=2, ital=0.22)), 0.55)

def banner_logo(cv, name, **_):
    """the X-CONSOLE logo banner (tools/custom-pages/xc_logo.py, user's logo 2026-11-11); the name like its HEARTS"""
    if LOGO_FIT == 'mid':      # swoosh top at the page top, the bar's lower edge and the X tip tucked behind the panels
        scale, top, px = 0.34, 18.0, 28
    elif LOGO_FIT == 'fit':    # the whole logo inside the banner: bar 39 px, swoosh within the top 65 px
        scale, top, px = 0.28, 11.4, 23
    else:                      # the bar fills the banner (62 px); the swoosh and X tips run past it
        scale, top, px = 62.0 / (xc_logo.BAR1 - xc_logo.BAR0), 0.0, 36
    nw = xc_logo.text_w(name, px * S) / S + px * 0.3
    t0, t1, xr = xc_logo.draw_bar(sys.modules[__name__], cv, nw, scale, top, LOGO_ACCENT, clear_loop=True)
    cy = t0 + (t1 - t0) * 0.41
    c0, c1 = ((255, 80, 70), (180, 0, 0)) if LOGO_ACCENT is None else xc_logo.accent_grad(LOGO_ACCENT)
    grad_text(cv, xr, cy, name, px, c0, c1, anchor='rm', stroke_col=(255, 255, 255), stroke=1.6, logo=True)

def vbox(cv, cx, cy, w, h=22):
    x, y = cx - w / 2, cy - h / 2
    cv.mul(m_rrect(x - 1, y, w + 2, h + 2, 5, blur=2), 0.55)
    cv.over(vgrad(y, y + h, (6, 11, 22), (13, 21, 37)), m_rrect(x, y, w, h, 4))
    ring = m_rrect(x, y, w, h, 4, ring=1.3)
    cv.add(GLOW, blur_np(ring, 3), 0.9)
    cv.over((55, 155, 255), ring, 0.95)
    cv.mul(m_rrect(x, y, w, h, 4) * (1 - m_rrect(x + 1, y + 3, w, h, 4, blur=2)), 0.5)

def knob_bg(cv, cx, cy, r, lab, boxw=None, lpx=15, boxh=22, dots=True):
    R = r + max(8, r * 0.2)
    cv.mul(m_circles([(cx + 1, cy + 5, r + 3)], blur=6), 0.4)
    if dots:
        pts = []
        for i in range(11):
            a = math.radians(-135 + 27 * i)
            pts.append((cx + R * math.sin(a), cy - R * math.cos(a)))
        cv.mul(m_circles([(x + 0.5, y + 0.8, 2.3) for x, y in pts], blur=0.8), 0.5)
        cv.over((250, 252, 255), m_circles([(x, y, 1.8) for x, y in pts]))
    ly = cy + R + lpx * 0.85
    label(cv, cx, ly, lab, lpx)
    by = ly + lpx * 0.6 + boxh / 2 + 3
    vbox(cv, cx, by, boxw or max(78, 2 * r + 16), boxh)
    return by

def toggle_bg(cv, cx, cy, lab, r=22):
    cv.mul(m_circles([(cx + 1, cy + 4, r + 2)], blur=5), 0.45)
    label(cv, cx, cy + r + 18, lab, 16)

LED_SCALE = [(6, 121), (0, 151), (-6, 181), (-12, 211), (-18, 241), (-24, 271), (-30, 301), (-36, 331), (-48, 391), (-60, 451)]
LED_Y = np.linspace(119, 453, 30)

def led_db(y):
    ys = [p[1] for p in LED_SCALE]; ds = [p[0] for p in LED_SCALE]
    return float(np.interp(y, ys, ds))

METER_STOPS = None   # [(dB, (r,g,b)), ...] from the colours file's METERS, None = the metal bands below
UNLIT = None         # (r,g,b) from UNLIT METER SEGMENTS, None = a dim tint of each LED's colour

def led_col(db):
    if METER_STOPS:   # as make_art._led_col: first colour below the first stop, a fade between, last above
        st = METER_STOPS
        if db <= st[0][0]:
            return st[0][1]
        for (d0, c0), (d1, c1) in zip(st, st[1:]):
            if db <= d1:
                t = (db - d0) / (d1 - d0) if d1 > d0 else 1.0
                return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
        return st[-1][1]
    if db > 1: return (240, 30, 28)       # the picture: red, orange, yellow, white, green
    if db > -9: return (250, 120, 20)
    if db > -20: return (250, 225, 30)
    if db > -31: return (240, 242, 245)
    return (30, 200, 40)

def meter_well(cv, x0, scale_x, cols):
    wx, wy, ww, wh = x0 + 12, 111, 100, 351
    cv.mul(m_rrect(wx - 1, wy - 1, ww + 2, wh + 3, 7, blur=2), 0.5)
    cv.over(vgrad(wy, wy + wh, (9, 11, 15), (16, 19, 24)), m_rrect(wx, wy, ww, wh, 6))
    cv.mul(m_rrect(wx, wy, ww, wh, 6) * (1 - m_rrect(wx + 2, wy + 4, ww, wh, 6, blur=3)), 0.4)
    cv.over((30, 60, 100), m_rrect(wx, wy, ww, wh, 6, ring=1), 0.55)
    for db, y in LED_SCALE:
        light_text(cv, scale_x, y, ('+%d' % db) if db > 0 else str(db), 12.5, 'rm')
    for cx in cols:
        for y in LED_Y:
            c = np.asarray(led_col(led_db(y)), np.float32)
            cv.over(np.asarray(UNLIT, np.float32) if UNLIT else c * 0.17 + 8, m_rrect(cx - 6.5, y - 4, 13, 8, 1.5))
            cv.over((np.asarray(UNLIT, np.float32) * 1.25 + 6) if UNLIT else c * 0.30 + 10, m_rrect(cx - 6.5, y - 4, 13, 8, 1.5, ring=0.7), 0.6)

def meter_lit(cv, cols_levels):
    for cx, lev in cols_levels:
        lit = [y for y in LED_Y if led_db(y) <= lev]
        for y in lit:
            c = led_col(led_db(y))
            m = m_rrect(cx - 6.5, y - 4, 13, 8, 1.5)
            cv.over(c, m)
            cv.add((255, 255, 255), m_rrect(cx - 5, y - 3, 10, 2.5, 1), 0.25)

def in_out(cv, mock=False):
    for (x, ttl, sx, cols, kx, lab) in [(0, 'IN', 37, (48, 76), 62, 'INPUT'), (1156, 'OUT', 1193, (1204, 1232), 1218, 'OUTPUT')]:
        panel(cv, x, 66, 124, 556, ttl)
        meter_well(cv, x, sx, cols)
        knob_bg(cv, kx, 514, 32, lab, boxw=92)

def screen(cv, x, y, w, h, hl=(), vl=(), diag=False):
    cv.mul(m_rrect(x - 5, y - 4, w + 10, h + 10, 7, blur=3), 0.45)
    cv.over(vgrad(y - 4, y + h + 4, (30, 33, 38), (8, 9, 11)), m_rrect(x - 4, y - 4, w + 8, h + 8, 6))
    cv.add((255, 255, 255), m_rrect(x - 4, y - 4, w + 8, h + 8, 6, ring=0.8) * (_ys > y + h / 2), 0.15)
    cv.over(vgrad(y, y + h, (5, 9, 17), (10, 18, 32)), m_rrect(x, y, w, h, 3))
    segs = [(x, yy, x + w, yy) for yy in hl] + [(xx, y, xx, y + h) for xx in vl]
    if segs:
        cv.over((40, 64, 96), m_lines(segs, 1.0), 0.6)
    if diag:
        d = []
        n = 30
        for i in range(n):
            if i % 2 == 0:
                d.append((x + w * i / n, y + h - h * i / n, x + w * (i + 1) / n, y + h - h * (i + 1) / n))
        cv.over((90, 130, 175), m_lines(d, 1.0), 0.6)
    # glass vignette + top reflection
    cv.mul(m_rrect(x, y, w, h, 3) * (1 - m_rrect(x + 6, y + 6, w - 12, h - 12, 3, blur=8)), 0.55)
    cv.over((60, 140, 255), m_rrect(x, y, w, h, 3, ring=1), 0.45)

def gain_slot(cv, cx, y0, y1, w=24):
    x = cx - w / 2
    cv.mul(m_rrect(x - 2, y0 - 2, w + 4, y1 - y0 + 5, 4, blur=2), 0.45)
    cv.over((10, 12, 16), m_rrect(x - 1, y0 - 1, w + 2, y1 - y0 + 2, 4))
    n = 20
    step = (y1 - y0) / n
    for i in range(n):
        yy = y0 + i * step + 1.5
        cv.over((24, 34, 46), m_rrect(x + 2, yy, w - 4, step - 3, 1.5))

# ---------------------------------------------------------------- procedural controls (mock only)

# ================================================================ v2: custom pages for the build (2026-11-10)
# Static parts of every control (knob body + blue rim + dot ring, button sockets, drop-down fields, value boxes, labels)
# are in the background; the turning knob cap, the button LED, the option-button faces and the LED/gain meter strips
# are separate pictures; <TAB>.layout lines place them (screen coords = page y + 86).
TOP = 86
PFX = 'cp_timetal_'
CTRL = []          # controls on the page being drawn
CUSTOM = {}   # knob looks from the Theme Editor (metal_knobs.look): name -> (base, tint, pointer) / chicken (top, bot)
STYLES = ['silver', 'black', 'red', 'pink']   # the cap styles this page script draws (the editor lists them)
EXTRA = []         # layout lines kept from the plugin's own layout (curves, spectrum, logos)

def knob_bg(cv, cx, cy, r, lab, boxw=None, lpx=15, boxh=22, dots=True):
    R = r + max(8, r * 0.2)
    cv.mul(m_circles([(cx + 1, cy + 5, r + 3)], blur=6), 0.5)
    if dots:   # tick marks round the bezel (11 over 270 degrees, the ends and the middle longer)
        segs, segl = [], []
        for i in range(11):
            a = math.radians(-135 + 27 * i)
            r0, r1 = r + 3, R + (4 if i in (0, 5, 10) else 1.5)
            sa, ca = math.sin(a), math.cos(a)
            segs.append((cx + r0 * sa, cy - r0 * ca, cx + r1 * sa, cy - r1 * ca))
        tw = max(1.4, r * 0.035)
        cv.mul(m_lines([(a + 0.5, b + 0.9, c + 0.5, d + 0.9) for a, b, c, d in segs], tw + 1.0, blur=0.6), 0.45)
        cv.over((248, 249, 252), m_lines(segs, tw))
    # the knob's body (doesn't turn): black knurled rubber bezel with a thin steel edge
    body = m_circles([(cx, cy, r)])
    cv.over(vgrad(cy - r, cy + r, (58, 60, 64), (4, 4, 5)), body)
    knurl = []
    for i in range(72):
        a = 2 * math.pi * i / 72
        knurl.append((cx + (r * 0.84) * math.cos(a), cy + (r * 0.84) * math.sin(a), cx + (r - 1.2) * math.cos(a), cy + (r - 1.2) * math.sin(a)))
    cv.over((0, 0, 0), m_lines(knurl, max(0.8, r * 0.022)) * body, 0.45)
    edge = m_circles([(cx, cy, r)], ring=1.1)
    cv.over((150, 154, 160), edge, 0.55)
    cv.mul(m_circles([(cx, cy + 2, r * 0.8 + 1.5)], blur=2), 0.45)   # the cap's shadow on the skirt
    ly = cy + R + lpx * 0.85
    label(cv, cx, ly, lab, lpx)
    by = ly + lpx * 0.6 + boxh / 2 + 3
    vbox(cv, cx, by, boxw or max(78, 2 * r + 16), boxh)
    return by

def cap(cv, cx, cy, r, style='silver', val=0.5):
    """The turning part: brushed metal cap + pointer (val 0..1 = -135..+135 deg)."""
    if style not in CUSTOM:   # Titanium: its own caps are all spun silver (the picture); the editor's colours / extra caps show
        style = 'silver'
    rc = r * 0.80
    x0, y0 = int((cx - rc - 2) * S), int((cy - rc - 2) * S)
    x1, y1 = int((cx + rc + 2) * S), int((cy + rc + 2) * S)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / S
    dx, dy = xx - cx, yy - cy
    rr = np.sqrt(dx * dx + dy * dy)
    th = np.arctan2(dy, dx)
    # the cap's own frame: angles relative to its pointer, so the turning picture keeps its look
    th = th - math.radians(-135 + 270 * val)
    rng = np.random.default_rng(int(r * 13) + len(style))
    fine = sum(rng.normal() * np.sin(k * th + rng.uniform(0, 6.28)) for k in range(40, 140, 3)) * 0.12
    base = CUSTOM[style][0] if style in CUSTOM else {'silver': (175, 60), 'black': (62, 34), 'red': (150, 55), 'pink': (150, 55)}[style]
    b = base[0] + base[1] * (0.6 * np.cos(2 * (th + 0.75)) + 0.4 * np.cos(th + 2.2)) + fine * base[1] * 0.4
    b = b - 18 * (rr / rc) ** 3
    tint = CUSTOM[style][1] if style in CUSTOM else {'silver': (1.0, 1.01, 1.04), 'black': (1.0, 1.02, 1.06), 'red': (1.35, 0.28, 0.25), 'pink': (1.3, 0.3, 0.62)}[style]
    col = np.clip(b[..., None] * np.asarray(tint, np.float32), 0, 255)
    a = np.clip((rc - rr) * S + 0.5, 0, 1)[..., None]
    cv.a[y0:y1, x0:x1] = cv.a[y0:y1, x0:x1] * (1 - a) + col * a
    cv.over((15, 15, 18), m_circles([(cx, cy, rc)], ring=0.8), 0.7)
    ang = math.radians(-135 + 270 * val)
    p0 = (cx + 0.18 * rc * math.sin(ang), cy - 0.18 * rc * math.cos(ang))
    p1 = (cx + 0.9 * rc * math.sin(ang), cy - 0.9 * rc * math.cos(ang))
    pc = CUSTOM[style][2] if style in CUSTOM else ((240, 242, 246) if style == 'black' else (12, 12, 15))
    cv.over(pc, m_lines([(p0[0], p0[1], p1[0], p1[1])], max(2.2, rc * 0.09)))

TOG_R = 22
TOG_IMG = 56       # the LED picture's size (screen px)

def toggle_bg(cv, cx, cy, lab, r=TOG_R):
    cv.mul(m_circles([(cx + 1, cy + 4, r + 2)], blur=5), 0.45)
    cv.over(vgrad(cy - r, cy + r, (110, 115, 122), (16, 18, 22)), m_circles([(cx, cy, r)]))
    cv.over(vgrad(cy - r, cy + r, (14, 15, 18), (52, 56, 62)), m_circles([(cx, cy, r - 3.5)]))
    label(cv, cx, cy + r + 18, lab, 16)

def led(cv, cx, cy, on):
    if on:
        cv.add(GLOW, m_circles([(cx, cy, 9)], blur=6), 1.8)
        cv.over((70, 175, 255), m_circles([(cx, cy, 6.5)]))
        cv.over((230, 245, 255), m_circles([(cx, cy, 2.6)], blur=0.8))
    else:
        cv.over((12, 38, 66), m_circles([(cx, cy, 6.5)]))
        cv.add((255, 255, 255), m_circles([(cx - 1.5, cy - 2, 2)], blur=1), 0.08)

FIELD_ARROW = FIELD_GLOW = None   # a drop-down arrow's colour / glow from the Theme Editor (metal_dropdown.py); None = as drawn

def field(cv, cx, cy, w, h):
    """A drop-down's field without text (the plugin writes the choice; popup field=none)."""
    x, y = cx - w / 2, cy - h / 2
    cv.mul(m_rrect(x - 1, y, w + 2, h + 3, 6, blur=3), 0.5)
    cv.over(vgrad(y, y + h, (4, 8, 16), (10, 16, 28)), m_rrect(x, y, w, h, 5))
    ring = m_rrect(x, y, w, h, 5, ring=1.6)
    cv.add(GLOW, blur_np(ring, 4), 1.5)
    cv.over((80, 175, 255), ring)
    tx, ty = x + w - 24, cy
    tri = new_mask()
    ImageDraw.Draw(tri).polygon([((tx - 8) * S, (ty - 4.5) * S), ((tx + 8) * S, (ty - 4.5) * S), (tx * S, (ty + 5.5) * S)], fill=255)
    cv.over(FIELD_ARROW or (240, 244, 250), to_np(tri))

GAIN_N = 40

def gain_slot(cv, cx, y0, y1, w=24):
    x = cx - w / 2
    cv.mul(m_rrect(x - 2, y0 - 2, w + 4, y1 - y0 + 5, 4, blur=2), 0.45)
    cv.over((10, 12, 16), m_rrect(x - 1, y0 - 1, w + 2, y1 - y0 + 2, 4))
    step = (y1 - y0) / GAIN_N
    for i in range(GAIN_N):
        cv.over((24, 34, 46), m_rrect(x + 2, y0 + i * step + 1, w - 4, step - 2, 1))

# ---------------------------------------------------------------- registering controls
def K(key, cx, cy, r, lab, style='silver', v=0.5, t='', boxw=None, lpx=15, boxh=22, cv=None):
    by = knob_bg(cv, cx, cy, r, lab, boxw, lpx, boxh)
    CTRL.append(dict(kind='knob', key=key, lab=lab, cx=cx, cy=cy, r=r, style=style, v=v, t=t, by=by, vs=17 if boxh >= 22 else 15, bw=int(boxw or max(78, 2 * r + 16))))

def T(key, cx, cy, lab, on=True, cv=None):
    toggle_bg(cv, cx, cy, lab)
    CTRL.append(dict(kind='toggle', key=key, cx=cx, cy=cy, on=on))

def E(key, cx, cy, sw, sh, opts, sel=0, vert=False, px=15):
    CTRL.append(dict(kind='enum_v' if vert else 'enum_h', key=key, cx=cx, cy=cy, sw=sw, sh=sh, opts=opts, sel=sel, px=px))

def PU(key, cx, cy, w, h, opts, t, cv=None):
    field(cv, cx, cy, w, h)
    CTRL.append(dict(kind='popup', key=key, cx=cx, cy=cy, w=w, h=h, opts=opts, t=t))

def seg_rects(c):
    n, sw, sh, gap = len(c['opts']), c['sw'], c['sh'], 2
    if c['kind'] == 'enum_v':
        y0 = c['cy'] - (n * (sh + gap)) // 2
        return [(c['cx'] - sw // 2, y0 + i * (sh + gap), sw, sh) for i in range(n)]
    x0 = c['cx'] - (n * sw + (n - 1) * gap) // 2
    return [(x0 + i * (sw + gap), c['cy'] - sh // 2, sw, sh) for i in range(n)]

def seg(cv, x, y, w, h, txt, on, px=15):
    if on:
        cv.over(vgrad(y, y + h, (30, 92, 160), (8, 30, 64)), m_rrect(x, y, w, h, 5))
        ring = m_rrect(x, y, w, h, 5, ring=1.4)
        cv.add(GLOW, blur_np(ring, 3) * m_rrect(x, y, w, h, 5), 1.4)
        cv.over((90, 185, 255), ring)
    else:
        cv.over(vgrad(y, y + h, (52, 56, 62), (14, 15, 18)), m_rrect(x, y, w, h, 5))
        cv.over((4, 5, 6), m_rrect(x, y, w, h, 5, ring=1.0))
    cv.add((255, 255, 255), m_rrect(x + 2, y + 1, w - 4, h * 0.45, 4), 0.06)
    if txt:
        light_text(cv, x + w / 2, y + h / 2, txt, px, 'mm', w='Bold')

def in_out(cv):
    for (x, ttl, sx, cols, kx, lab, key, st) in [(0, 'IN', 37, (48, 76), 62, 'INPUT', 'in_gain', 'silver'),
                                                 (1156, 'OUT', 1193, (1204, 1232), 1218, 'OUTPUT', 'out_vol', 'red')]:
        panel(cv, x, 66, 124, 556, ttl)
        meter_well(cv, x, sx, cols)
        K(key, kx, 514, 32, lab, st, 0.5, '0.0 dB', boxw=92, cv=cv)

# ---------------------------------------------------------------- pages (page coords)
def page_preamp(cv):
    banner(cv, 'TITANIUM'); in_out(cv)
    panel(cv, 128, 66, 406, 556, 'TAPE / PREAMP')
    label(cv, 331, 162, 'TYPE', 16)
    E('pre_type', 331, 200, 100, 40, ['TAPE', 'TUBE', 'IRON'], 0)
    K('pre_color', 331, 330, 50, 'COLOR', 'silver', 0.3, '35 %', boxw=150, cv=cv)
    T('phase', 230, 505, 'PHASE INV', False, cv=cv); T('pre_on', 430, 505, 'ON', True, cv=cv)
    panel(cv, 538, 66, 386, 556, 'FILTER')
    K('lc_freq', 636, 212, 48, 'LOW CUT', 'black', 0.15, '40 Hz', boxw=140, cv=cv)
    K('hc_freq', 826, 212, 48, 'HIGH CUT', 'silver', 0.85, '16.0 kHz', boxw=140, cv=cv)
    label(cv, 636, 345, 'SLOPE', 15); label(cv, 826, 345, 'SLOPE', 15)
    E('lc_slope', 636, 377, 40, 34, ['6', '12', '18', '24'], 1)
    E('hc_slope', 826, 377, 40, 34, ['6', '12', '18', '24'], 2)
    label(cv, 731, 414, 'dB / OCT', 14)
    T('flt_sc', 636, 505, 'TO S/C', False, cv=cv); T('flt_on', 826, 505, 'ON', True, cv=cv)
    panel(cv, 928, 66, 224, 556, 'NOISE')
    label(cv, 950, 166, 'WAVEFORM', 15, 'lm')
    PU('nz_color', 1040, 205, 184, 46, 'PINK,WHITE,BROWN,BLUE,VIOLET,GREY,CRACKLE', 'PINK', cv=cv)
    K('nz_level', 1040, 340, 48, 'LEVEL', 'pink', 0.25, '-48.0 dB', boxw=140, cv=cv)
    T('nz_on', 1040, 505, 'ON', True, cv=cv)

def page_shape(cv):
    banner(cv, 'TITANIUM'); in_out(cv)
    # TITANIUM's SHAPE: DE-ESSER (gate_thr = THRESHOLD, gate_hold = FREQUENCY) + HF LIMITER (gate_fast, sh_on)
    panel(cv, 128, 66, 386, 556, 'DE-ESSER')
    K('gate_thr', 321, 215, 54, 'THRESHOLD', 'silver', 0.4, '-20.0 dB', boxw=150, cv=cv)
    K('gate_hold', 321, 415, 54, 'FREQUENCY', 'silver', 0.55, '6.0 kHz', boxw=150, cv=cv)
    panel(cv, 518, 66, 634, 556, 'HF LIMITER')
    screen(cv, 555, 128, 300, 300, hl=(226, 324), vl=(655, 755), diag=True)
    for t, y in [('0', 131), ('-20', 229), ('-40', 327), ('-60', 425)]:
        label(cv, 548, y, t, 12, 'rm')
    for t, x in [('-60', 562), ('-40', 655), ('-20', 755), ('0', 852)]:
        label(cv, x, 442, t, 12)
    label(cv, 705, 460, 'INPUT dBFS', 12)
    gain_slot(cv, 883, 130, 426)
    for t, y in [('+20', 131), ('0', 281), ('-20', 425)]:
        label(cv, 900, y, t, 12, 'lm')
    label(cv, 883, 444, 'GAIN', 12)
    T('gate_fast', 1040, 250, 'HF LIMITER', True, cv=cv)
    T('sh_on', 1040, 420, 'ON', True, cv=cv)
    EXTRA.extend(keep('SHAPE', ('gtc_',)))
    EXTRA.append('meter cx=883 cy=364 w=24 h=296 key=m_shape strip=art/%sgain_shape.png frames=41' % PFX)

EQ_F = [(221, '30'), (273, '50'), (344, '100'), (415, '200'), (508, '500'), (579, '1k'), (650, '2k'), (743, '5k'), (814, '10k')]

def page_eq(cv):
    banner(cv, 'TITANIUM'); in_out(cv)
    panel(cv, 128, 66, 1024, 384, 'EQUALIZER')
    screen(cv, 180, 110, 704, 330, hl=[113 + 54 * i for i in range(1, 6)], vl=[x for x, _ in EQ_F])
    for i, t in enumerate(['0', '-12', '-24', '-36', '-48', '-60', '-72']):
        label(cv, 173, 113 + 54 * i, t, 12, 'rm')
    for x, t in EQ_F:
        light_text(cv, x, 430, t, 12, 'mm', col=(150, 185, 220))
    label(cv, 1019, 140, 'VIEW', 15)
    E('sp_view', 1019, 175, 100, 38, ['FFT', 'BARS'], 0)
    label(cv, 1019, 238, 'PEAK HOLD', 15)
    E('pk_hold', 1019, 273, 42, 36, ['OFF', '1s', '3s', '6s', '∞'], 2, px=14)
    label(cv, 952, 382, 'TITANIUM EQ', 19)
    toggle_bg(cv, 1086, 372, 'ON'); CTRL.append(dict(kind='toggle', key='eq_on', cx=1086, cy=372, on=True))
    bands = [(128, 252, 'LF', 'lf', [('gain', 174, 'GAIN'), ('freq', 254, 'FREQ')], 330),
             (384, 252, 'LMF', 'lmf', [('gain', 430, 'GAIN'), ('freq', 510, 'FREQ'), ('q', 590, 'Q')], None),
             (640, 252, 'HMF', 'hmf', [('gain', 686, 'GAIN'), ('freq', 766, 'FREQ'), ('q', 846, 'Q')], None),
             (896, 256, 'HF', 'hf', [('gain', 942, 'GAIN'), ('freq', 1022, 'FREQ')], 1098)]
    sv = {'gain': ('black', 0.5, '0.0 dB'), 'freq': ('silver', 0.55, '1.0 kHz'), 'q': ('silver', 0.3, '0.7')}
    for x, w, t, b, knobs, tx in bands:
        panel(cv, x, 454, w, 168, t, compact=True, right_label='TYPE' if tx else None)
        for p, kx, kl in knobs:
            st, v, tt = sv[p]
            K('eq_%s_%s' % (b, p), kx, 534, 22, kl, st, v, tt, boxw=68, lpx=13, boxh=20, cv=cv)
        if tx:
            E('eq_%s_type' % b, tx, 546, 64, 26, ['SHELF', 'BELL', 'CUT'], 0, vert=True, px=13)
    EXTRA.extend(keep('EQ', ('spc_', 'spk_', 'eqc_')))
    # public repo: no logo picture over the EQ screen (add an art line for your own here)

def page_comp(cv):
    banner(cv, 'TITANIUM'); in_out(cv)
    panel(cv, 128, 66, 610, 556, 'COMPRESSOR')
    for key, x, y, r, l, st, v, t in [('cmp_att', 273, 190, 40, 'ATTACK', 'black', 0.3, '10 ms'),
                                      ('cmp_ratio', 433, 190, 40, 'RATIO', 'black', 0.4, '4.0:1'),
                                      ('cmp_knee', 593, 190, 30, 'KNEE', 'silver', 0.5, '6 dB'),
                                      ('cmp_rel', 273, 352, 40, 'RELEASE', 'black', 0.45, '250 ms'),
                                      ('cmp_thr', 433, 352, 50, 'COMPRESSION', 'silver', 0.35, '-18.0 dB'),
                                      ('cmp_makeup', 593, 352, 30, 'MAKE-UP', 'black', 0.3, '+3.0 dB'),
                                      ('cmp_mix', 273, 512, 30, 'WET/DRY', 'silver', 1.0, '100 %'),
                                      ('cmp_sc_hpf', 433, 512, 30, 'S/C HPF', 'silver', 0.1, '60 Hz')]:
        K(key, x, y, r, l, st, v, t, boxw=110 if r >= 40 else 96, cv=cv)
    T('cmp_fast', 593, 510, 'FAST ATT', False, cv=cv)
    panel(cv, 742, 66, 410, 556, 'GAIN REDUCTION')
    screen(cv, 779, 128, 300, 300, hl=(226, 324), vl=(879, 979), diag=True)
    for t, y in [('0', 131), ('-20', 229), ('-40', 327), ('-60', 425)]:
        label(cv, 772, y, t, 12, 'rm')
    for t, x in [('-60', 786), ('-40', 879), ('-20', 979), ('0', 1076)]:
        label(cv, x, 442, t, 12)
    label(cv, 929, 460, 'INPUT dBFS', 12)
    gain_slot(cv, 1105, 130, 426)
    for t, y in [('0', 131), ('-10', 281), ('-20', 425)]:
        label(cv, 1122, y, t, 12, 'lm')
    label(cv, 1105, 444, 'GR', 12)
    label(cv, 885, 498, 'DETECT', 15)
    E('cmp_det', 885, 532, 100, 38, ['RMS', 'PEAK'], 0)
    T('cmp_on', 1065, 522, 'ON', True, cv=cv)
    EXTRA.extend(keep('COMP', ('ctc_',)))
    EXTRA.append('meter cx=1105 cy=364 w=24 h=296 key=m_gr strip=art/%sgain_gr.png frames=41' % PFX)

def page_output(cv):
    banner(cv, 'TITANIUM'); in_out(cv)
    panel(cv, 128, 66, 406, 556, 'DRIVE')
    K('drv_amt', 331, 215, 50, 'DRIVE', 'silver', 0.3, '20 %', boxw=140, cv=cv)
    K('drv_char', 331, 396, 42, 'CHARACTER', 'black', 0.5, '50 %', boxw=140, cv=cv)
    label(cv, 270, 440, '2ND', 12); label(cv, 392, 440, '3RD', 12)
    label(cv, 231, 532, 'POSITION', 15)
    E('drv_pos', 231, 570, 80, 38, ['POST', 'PRE'], 0)
    T('drv_on', 431, 550, 'ON', True, cv=cv)
    panel(cv, 538, 66, 305, 556, 'OUTPUT')
    K('out_pan', 690, 215, 44, 'PAN', 'silver', 0.5, 'C', boxw=130, cv=cv)
    K('out_width', 690, 405, 44, 'WIDTH', 'black', 0.5, '100 %', boxw=130, cv=cv)
    panel(cv, 847, 66, 305, 556, 'ROUTING')
    label(cv, 872, 166, 'ORDER', 15, 'lm')
    PU('order', 1000, 207, 260, 46, 'SHP>EQ>CMP,SHP>CMP>EQ,EQ>SHP>CMP,EQ>CMP>SHP,CMP>SHP>EQ,CMP>EQ>SHP', 'SHP>EQ>CMP', cv=cv)
    label(cv, 1000, 272, 'SHAPE  /  EQ  /  COMP', 14)
    T('bypass', 1000, 535, 'BYPASS', False, cv=cv)

def page_info(cv):
    banner(cv, 'TITANIUM', blue_name=True); in_out(cv)
    panel(cv, 128, 66, 1024, 556, 'INFO', center=True)   # title bar back, INFO centred (user 2026-11-14)
    EXTRA.append('#infotext cy=%d step=40' % (TOP + 162))   # no name / CHANNEL STRIP / panel title (user 2026-11-12): INFO TEXT starts near the panel top

PAGES = [('PREAMP', page_preamp), ('SHAPE', page_shape), ('EQ', page_eq), ('COMP', page_comp), ('OUTPUT', page_output), ('INFO', page_info)]

# ---------------------------------------------------------------- the plugin's own layout (kept lines)
CONF = None
def keep(tab, prefixes):
    out, cur = [], None
    for ln in open(CONF).read().splitlines():
        if ln.startswith('[tab '):
            cur = ln[5:-1]
            continue
        if cur == tab and ln.startswith('meter ') and any(' key=' + p in ln for p in prefixes):
            out.append(ln)
    if not out:
        raise SystemExit('no %s lines for %s in %s' % (prefixes, tab, CONF))
    return out

# ---------------------------------------------------------------- pictures
def extract(draw, x, y, w, h):
    """Draw on black and on white, crop (page coords, w x h), return RGBA at S x (alpha from the difference)."""
    b, wh = Cv(), Cv()
    wh.a[:] = 255
    draw(b); draw(wh)
    sl = (slice(int(round(y * S)), int(round((y + h) * S))), slice(int(round(x * S)), int(round((x + w) * S))))
    B, Wt = b.a[sl], wh.a[sl]
    a = np.clip(1 - (Wt - B).mean(axis=2) / 255.0, 0, 1)
    col = np.clip(B / np.maximum(a, 1e-3)[..., None], 0, 255)
    rgba = np.dstack([col, a * 255]).astype(np.uint8)
    return Image.fromarray(rgba, 'RGBA')

def strip(frames, path):
    w, h = frames[0].size
    s = Image.new('RGBA', (w, h * len(frames)))
    for i, f in enumerate(frames):
        s.paste(f, (0, i * h))
    s.save(path)

LEDX, LEDW, LEDY0, LEDY1 = 48, 16, 113, 459

def led_strips(art, tab):
    global W, H
    keep = (W, H)
    W, H = 128, 470   # a small canvas: the well and its LEDs only (fast)
    try:
        _led_strips(art, tab)
    finally:
        W, H = keep

def _led_strips(art, tab):
    off, on = Cv(), Cv()
    for c in (off, on):
        meter_well(c, 0, 37, (48,))
    meter_lit(on, [(48, 99)])
    sl = (slice(LEDY0 * S, LEDY1 * S), slice((LEDX - LEDW // 2) * S, (LEDX + LEDW // 2) * S))
    A, L = off.a[sl], on.a[sl]
    ys = sorted(LED_Y, reverse=True)          # bottom LED first
    def rows(y):
        return int(round((y - 5.75 - LEDY0) * S)), int(round((y + 5.75 - LEDY0) * S))
    small = lambda arr: Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA').resize((LEDW, LEDY1 - LEDY0), Image.LANCZOS)
    bar, pk = [], []
    for f in range(31):
        fr = A.copy()
        p = np.zeros(A.shape[:2] + (4,), np.float32)
        for i, y in enumerate(ys[:f]):
            r0, r1 = rows(y)
            fr[r0:r1] = L[r0:r1]
            if i == f - 1:
                p[r0:r1, :, :3] = L[r0:r1]; p[r0:r1, :, 3] = 255
        bar.append(small(fr))
        pk.append(Image.fromarray(p.astype(np.uint8), 'RGBA').resize((LEDW, LEDY1 - LEDY0), Image.LANCZOS))
    strip(bar, os.path.join(art, PFX + 'led_bar_%s.png' % tab.lower()))
    strip(pk, os.path.join(art, PFX + 'led_pk_%s.png' % tab.lower()))

def gain_strips(art):
    w, h, k = 24, 296, 4
    step = h * k / GAIN_N
    def frame(lit):
        im = Image.new('RGBA', (w * k, h * k), (10, 12, 16, 255))
        d = ImageDraw.Draw(im)
        for i in range(GAIN_N):
            y0 = i * step + 1 * k
            box = [2 * k, y0, (w - 2) * k - 1, y0 + step - 2 * k]
            if i in lit:
                d.rounded_rectangle(box, radius=k, fill=(55, 165, 255))
                d.rectangle([3 * k, y0 + k, (w - 3) * k - 1, y0 + step * 0.4], fill=(150, 210, 255))
            else:
                d.rounded_rectangle(box, radius=k, fill=(24, 34, 46))
        return im.resize((w, h), Image.LANCZOS)
    half = GAIN_N // 2
    shape = []
    for f in range(41):
        if f >= 20:
            lit = set(range(half - (f - 20), half))
        else:
            lit = set(range(half, half + (20 - f)))
        shape.append(frame(lit))
    strip(shape, os.path.join(art, PFX + 'gain_shape.png'))
    strip([frame(set(range(f))) for f in range(41)], os.path.join(art, PFX + 'gain_gr.png'))

def control_pictures(art, done):
    """Pictures + layout lines for CTRL (this page)."""
    lines = []
    for c in CTRL:
        k = c['kind']
        if k == 'knob':
            rw = int(round(c['by'] - c['cy'] - 15))      # the value (ns=0) is centred at cy + r + 15
            box = 2 * rw + 8
            name = PFX + 'knob_%s.png' % c['key']
            img = extract(lambda cv, c=c: cap(cv, 640, 314, c['r'], c['style'], 0.5),
                          640 - box / 2, 314 - box / 2, box, box)
            img.save(os.path.join(art, name))
            lines.append('knob cx=%d cy=%d r=%d key=%s ns=0 vs=%d bw=%d vcase=none ink_dim=7fd4ff img=art/%s'
                         % (c['cx'], c['cy'] + TOP, rw, c['key'], c['vs'], c['bw'], name))
        elif k == 'toggle':
            if 'led' not in done:
                for on in (0, 1):
                    extract(lambda cv, on=on: led(cv, 640, 300, on), 640 - TOG_IMG / 2, 300 - TOG_IMG / 2, TOG_IMG, TOG_IMG) \
                        .save(os.path.join(art, PFX + 'led_%s.png' % ('on' if on else 'off')))
                done.add('led')
            lines.append('toggle cx=%d cy=%d key=%s ns=0 w=%d h=%d img=art/%sled_off.png img_on=art/%sled_on.png'
                         % (c['cx'], c['cy'] + TOP, c['key'], TOG_IMG, TOG_IMG, PFX, PFX))
        elif k in ('enum_h', 'enum_v'):
            sz = '%dx%d' % (c['sw'], c['sh'])
            if sz not in done:
                for on in (0, 1):
                    extract(lambda cv, on=on: seg(cv, 600, 300, c['sw'], c['sh'], '', on), 600, 300, c['sw'], c['sh']) \
                        .save(os.path.join(art, PFX + 'seg_%s_%s.png' % (sz, 'on' if on else 'off')))
                done.add(sz)
            lines.append('%s cx=%d cy=%d sw=%d sh=%d key=%s label="" options="%s" seg_tx=ffffff img=art/%sseg_%s_off.png img_on=art/%sseg_%s_on.png'
                         % (k, c['cx'], c['cy'] + TOP, c['sw'], c['sh'], c['key'], ','.join(c['opts']), PFX, sz, PFX, sz))
        elif k == 'popup':
            lines.append('popup cx=%d cy=%d w=%d h=%d key=%s label="" field=none options="%s" accent=2f9fd0 opens=_v field_ink=5fd0ff list_ink=ffffff'
                         % (c['cx'], c['cy'] + TOP, c['w'], c['h'], c['key'], c['opts']))
    return lines

def meter_lines(tab):
    out = []
    for key, pk, cx in (('m_in_l', 'm_pk_in_l', 48), ('m_in_r', 'm_pk_in_r', 76), ('m_out_l', 'm_pk_out_l', 1204), ('m_out_r', 'm_pk_out_r', 1232)):
        cy = (LEDY0 + LEDY1) // 2 + TOP
        out.append('meter cx=%d cy=%d w=%d h=%d key=%s strip=art/%sled_bar_%s.png frames=31' % (cx, cy, LEDW, LEDY1 - LEDY0, key, PFX, tab.lower()))
        out.append('meter cx=%d cy=%d w=%d h=%d key=%s strip=art/%sled_pk_%s.png frames=31' % (cx, cy, LEDW, LEDY1 - LEDY0, pk, PFX, tab.lower()))
    return out

# ---------------------------------------------------------------- mock (the page as it should look)
def mock(cv):
    meter_lit(cv, [(48, -14), (76, -11), (1204, -16), (1232, -13)])
    for c in CTRL:
        k = c['kind']
        if k == 'knob':
            cap(cv, c['cx'], c['cy'], c['r'], c['style'], c['v'])
            light_text(cv, c['cx'], c['by'], c['t'], c['vs'], 'mm', col=VAL, w='SemiBold')
        elif k == 'toggle':
            led(cv, c['cx'], c['cy'], c['on'])
        elif k in ('enum_h', 'enum_v'):
            for i, (x, y, w, h) in enumerate(seg_rects(c)):
                seg(cv, x, y, w, h, c['opts'][i], i == c['sel'], c['px'])
        elif k == 'popup':
            light_text(cv, c['cx'], c['cy'], c['t'], 17, 'mm', col=(95, 208, 255), w='Bold')

# ---------------------------------------------------------------- Theme Editor colours (2026-11-10)
# The colours file's [TITANIUM] "<PAGE> / METERS" (else "ALL / METERS") and [ALL PRESETS] "PANEL / UNLIT METER SEGMENTS".
# A value equal to the built-in one (what the build writes for an untouched place) keeps the metal look: the build's
# own rule (user_theme.py: only values away from built-in change anything).
FILE_PAGE = {'INFO': 'SETUP'}   # the INFO tab is the colours file's SETUP page
BUILTIN_METERS = {'SETUP': '-18 #2f9fd0, -12 #ebebf0, 0 #e23428'}
BUILTIN_METERS_DEFAULT = '-48 #00b400, -18 #ebebf0, -12 #ffe600, 0 #ff8000, 3 #e23428'   # metal default (no build value equals it)
BUILTIN_UNLIT = '#26282e'

def read_colours(path):
    vals, sect = {}, None
    if not path or not os.path.exists(path):
        return vals
    for raw in open(path, encoding='utf-8-sig'):
        ln = raw.strip()
        if not ln or ln.startswith('#'):
            continue
        if ln.startswith('[') and ln.endswith(']'):
            sect = ' '.join(ln[1:-1].split()).upper()
            continue
        if '=' not in ln or '/' not in ln.split('=', 1)[0]:
            continue
        left, v = ln.split('=', 1)
        v = re.sub(r'\s+#\s.*$', '', v).strip()
        pg, nm = left.split('/', 1)
        vals[(sect, ' '.join(pg.split()).upper(), ' '.join(nm.split()).upper())] = v
    return vals

def _norm(v):
    return ' '.join(v.replace(',', ' , ').split()).lower()

def _hex(c):
    c = c.strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', c):
        return None
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))

def parse_meters(v):
    raw = []
    for part in v.split(','):
        bits = part.split()
        if len(bits) != 2:
            return None
        try:
            db = float(bits[0])
        except ValueError:
            return None
        cs, fade = bits[1], True
        if cs.endswith('!'):
            cs, fade = cs[:-1], False
        c = _hex(cs)
        if c is None:
            return None
        raw.append((db, c, fade))
    if not raw or any(b[0] < a[0] for a, b in zip(raw, raw[1:])):
        return None
    stops = []
    for i, (db, col, fade) in enumerate(raw):
        stops.append((db, col))
        if not fade and i + 1 < len(raw):
            stops.append((raw[i + 1][0], col))
    return stops

def editor_meters(vals, tab):
    """sets METER_STOPS / UNLIT for this tab; returns a line saying what was used"""
    global METER_STOPS, UNLIT
    pg = FILE_PAGE.get(tab, tab)
    v = vals.get(('TITANIUM', pg, 'METERS'), vals.get(('TITANIUM', 'ALL', 'METERS')))
    METER_STOPS = None
    if v is not None and _norm(v) != _norm(BUILTIN_METERS.get(pg, BUILTIN_METERS_DEFAULT)):
        METER_STOPS = parse_meters(v)
        if METER_STOPS is None:
            print('  %s: METERS "%s" is not a gradient (dB #colour, ...); metal colours kept' % (tab, v), flush=True)
    u = vals.get(('ALL PRESETS', 'PANEL', 'UNLIT METER SEGMENTS'))
    UNLIT = _hex(u) if u and _norm(u) != _norm(BUILTIN_UNLIT) else None
    return '%s meters: %s, unlit: %s' % (tab, ('editor (%s)' % v) if METER_STOPS else 'metal',
                                         ('#' + u.lstrip('#')) if UNLIT else 'metal')

def strips_only(art, colours, lay):
    """--strips: redraw each page's LED strips from the colours file and point its .layout at them (the build runs this)"""
    vals = read_colours(colours)
    for tab, _ in PAGES:
        print(' ', editor_meters(vals, tab), flush=True)
        led_strips(art, tab)
        lp = os.path.join(lay, tab + '.layout')
        if os.path.exists(lp):
            t = open(lp).read()
            t = re.sub(r'strip=art/%sled_(bar|pk)(_[a-z]+)?\.png' % PFX,
                       lambda m: 'strip=art/%sled_%s_%s.png' % (PFX, m.group(1), tab.lower()), t)
            open(lp, 'w').write(t)

def main():
    global CONF
    if sys.argv[1] == '--strips':
        strips_only(*sys.argv[2:5])
        metal_knobs.apply(sys.modules[__name__], sys.argv[2], sys.argv[4])   # the editor's knob colours
        metal_banner.apply(sys.modules[__name__], sys.argv[2], sys.argv[4], sys.argv[3])   # the editor's banner text colours
        metal_dropdown.apply(sys.modules[__name__], sys.argv[2], sys.argv[4], sys.argv[3])   # the editor's drop-down colours
        metal_segs.apply(sys.modules[__name__], sys.argv[2], sys.argv[4], sys.argv[3])   # the editor's lit button colours
        return
    if sys.argv[1] == '--knobs':   # metal_pages.py --knobs <layout conf> <layout dir>: knobs.txt only
        metal_knobs.knobs_only(sys.modules[__name__], sys.argv[2], sys.argv[3])
        return
    load_textures()
    out, art, lay, CONF = sys.argv[1:5]
    vals = read_colours(os.environ.get('XC_COLOURS', ''))
    only = [int(a) for a in sys.argv[5:]] or range(6)
    for d in (out, art, lay):
        os.makedirs(d, exist_ok=True)
    done = set()
    SEEN = {}
    gain_strips(art)
    for n in only:
        tab, fn = PAGES[n]
        print('page', n, tab, flush=True)
        CTRL.clear(); EXTRA.clear()
        print(' ', editor_meters(vals, tab), flush=True)
        led_strips(art, tab)
        cv = Cv()
        cv.a[:] = metal(0, H, (40, 41, 44), (20, 21, 23), TEX1, 5)
        fn(cv)
        bgname = PFX + 'bg_%s.png' % tab.lower()
        cv.save(os.path.join(art, bgname))
        cv.save(os.path.join(out, 'bg_%d.png' % n))
        m = cv.copy(); mock(m); m.save(os.path.join(out, 'mock_%d.png' % n))
        lines = ['art file="art/%s" x=0 y=%d w=%d h=%d' % (bgname, TOP, W, H)] + EXTRA + meter_lines(tab) + control_pictures(art, done)
        open(os.path.join(lay, tab + '.layout'), 'w').write('\n'.join(lines) + '\n')
        SEEN[tab] = [dict(c) for c in CTRL if c['kind'] == 'knob']
        print('  %d lines, %d controls' % (len(lines), len(CTRL)), flush=True)
    metal_knobs.save_list(sys.modules[__name__], lay, SEEN)   # knobs.txt for the Theme Editor
    metal_knobs.apply(sys.modules[__name__], art, lay)
    metal_dropdown.apply(sys.modules[__name__], art, lay, os.environ.get('XC_COLOURS', ''))
    metal_segs.apply(sys.modules[__name__], art, lay, os.environ.get('XC_COLOURS', ''))

if __name__ == '__main__':
    main()
