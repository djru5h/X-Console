#!/usr/bin/env python3
"""X-Console Granite (the GRANITE preset): six page skins drawn in the style of the user's generated picture
([Ru5h Skins]/Granite Skins/page_0.png): black speckled granite panels with thin bronze trim, dark stone title bars with
bronze edges, dark banner with a red X-, chrome CONSOLE and bronze-gold GRANITE over a bronze line; turning metal knobs
(black, pearl, pink, bronze, red) in black bezels with white ticks, dark value boxes with bronze rims, amber LED buttons
and option buttons, a navy drop-down with blue text, LED meters green / white / yellow / orange / red.

Made from tools/custom-pages/suede/metal_pages.py (Suede; same page plan, control positions, layout output, --strips hook).

  metal_pages.py <preview dir> <art dir> <layout dir> <plugin layout conf> [pages]
  metal_pages.py --strips <art dir> <colours file> <layout dir>      (the build runs this)
Run with /root/venv-skin/bin/python (numpy).
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
WHITE = (242, 240, 236)
BRONZE = (196, 158, 104)
GLOW = (255, 140, 20)       # amber glow
VAL = (244, 236, 222)
SECTION = 'GRANITE'  # the colours file's section (the preset)
SHOWN = 'GRANITE'      # the name on the banner

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

def m_text(x, y, txt, px, anchor='mm', w='Bold', sp=0, blur=0, stroke=0):
    m = new_mask(); d = ImageDraw.Draw(m); f = font(px, w)
    tw = text_w(txt, px, w, sp)
    x0 = x - (tw / 2 if anchor[0] == 'm' else tw if anchor[0] == 'r' else 0)
    va = anchor[1]
    cx = x0
    for ch in txt if sp else [txt]:
        d.text((cx * S, y * S), ch, font=f, fill=255, anchor='l' + va,
               stroke_width=int(round(stroke * S)), stroke_fill=255)
        cx += f.getlength(ch) / S + sp
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

TEX1 = TEX2 = SUEDE = None

def up2(a):
    """2x nearest upscale (Pillow 12.1.1 in WSL fails NEAREST resize of these, 2026-11-14)"""
    return np.ascontiguousarray(np.repeat(np.repeat(a, 2, axis=0), 2, axis=1))

def suede_grain(seed):
    """black granite: fine grain, scattered bright / dark specks, faint mottling (about -2..+3)"""
    r = np.random.default_rng(seed)
    n = r.normal(size=(H * S, W * S)).astype(np.float32)
    fine = np.asarray(Image.fromarray(((n * 40 + 128).clip(0, 255)).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7 * S)), np.float32)
    fine = (fine - fine.mean()) / fine.std()
    sp = r.random(size=(H * S // 2, W * S // 2)).astype(np.float32)
    speck = np.asarray(Image.fromarray(up2(((sp > 0.985) * 255 - (sp < 0.03) * 0).astype(np.uint8)))
                       .filter(ImageFilter.GaussianBlur(0.5 * S)), np.float32) / 255.0
    dark = np.asarray(Image.fromarray(up2(((sp < 0.06) * 255).astype(np.uint8)))
                      .filter(ImageFilter.GaussianBlur(0.8 * S)), np.float32) / 255.0
    mot = np.asarray(Image.fromarray(((r.normal(size=(H * S // 16, W * S // 16)) * 40 + 128).clip(0, 255)).astype(np.uint8))
                     .resize((W * S, H * S), Image.BICUBIC).filter(ImageFilter.GaussianBlur(5 * S)), np.float32)
    mot = (mot - mot.mean()) / mot.std()
    return (0.8 * fine + 0.45 * mot + 3.2 * speck - 1.6 * dark).astype(np.float32)

def load_textures():
    global TEX1, TEX2, SUEDE
    print('textures...', flush=True)
    TEX1 = brushed(11, 180)
    TEX2 = brushed(23, 120)
    SUEDE = suede_grain(41)
TINT = np.array([1.0, 1.0, 1.01], np.float32)
_xs = np.arange(W * S, dtype=np.float32)[None, :] / S
_ys = np.arange(H * S, dtype=np.float32)[:, None] / S
SHEEN = (1 + 0.05 * np.sin((_xs * 0.9 + _ys) / 170.0) + 0.04 * np.sin((_xs - _ys * 0.5) / 410.0))[..., None]
# the picture's diagonal light streaks across the dark panels
_u = _xs - _ys * 0.75
DIAG = (0.80 + 0.42 * np.exp(-((_u - 300) / 70.0) ** 2) + 0.30 * np.exp(-((_u - 520) / 45.0) ** 2)
        + 0.38 * np.exp(-((_u - 840) / 80.0) ** 2) + 0.26 * np.exp(-((_u - 1080) / 50.0) ** 2)
        + 0.30 * np.exp(-((_u - 1300) / 70.0) ** 2))[..., None]

def metal(y0, y1, c0, c1, tex, amp, diag=False):
    a = (vgrad(y0, y1, c0, c1) * TINT + tex[..., None] * amp) * SHEEN
    if diag:
        a = a * DIAG
    return np.clip(a, 0, 255)

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
def label(cv, x, y, t, px=15, anchor='mm', col=WHITE, sp=0.5):
    cv.mul(m_text(x + 0.6, y + 1.6, t, px, anchor, sp=sp, blur=0.8), 0.35)
    cv.over(col, m_text(x, y, t, px, anchor, sp=sp))

def light_text(cv, x, y, t, px=12, anchor='mm', col=WHITE, sp=0, w='SemiBold'):
    cv.over(col, m_text(x, y, t, px, anchor, w=w, sp=sp))

def grad_text(cv, x, y, t, px, c0, c1, anchor='lm', sp=1.5, stroke_col=(8, 8, 10), stroke=1.6, logo=False):
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
    m = m_text(x, y, t, px, anchor, sp=sp)
    cv.mul(m_text(x + 2, y + 3, t, px, anchor, sp=sp, blur=2.5), 0.3)
    cv.over(stroke_col, m_text(x, y, t, px, anchor, sp=sp, stroke=stroke), 0.95)
    cv.over(vgrad(y - px * 0.38, y + px * 0.38, c0, c1), m)
    return m

def rule(cv, x0, x1, y, col=(212, 214, 218), width=1.6):
    xs = np.arange(W * S, dtype=np.float32) / S
    fade = np.clip(np.minimum(xs - x0, x1 - xs) / 30.0, 0, 1)[None, :]
    cv.over((6, 6, 8), m_lines([(x0, y + 1.6, x1, y + 1.6)], 1.0) * fade, 0.55)
    cv.over(col, m_lines([(x0, y, x1, y)], width) * fade)
    cv.add((255, 255, 255), blur_np(m_lines([(x0, y, x1, y)], width) * fade, 2.0), 0.25)

def suede(y0, y1):
    a = vgrad(y0, y1, (46, 45, 44), (26, 25, 24)) + SUEDE[..., None] * 8
    return np.clip(a * DIAG ** 0.35, 0, 255)

def panel(cv, x, y, w, h, title, compact=False, right_label=None, center=False):
    px, py, pw, ph = x + 2, y + 2, w - 4, h - 4
    rad = 7
    outer = m_rrect(px, py, pw, ph, rad)
    cv.mul(m_rrect(px + 1, py + 4, pw, ph, rad, blur=5), 0.35)
    cv.over(metal(py, py + ph, (64, 60, 56), (20, 19, 18), TEX1, 9), outer)          # dark edge
    cv.over((6, 6, 7), m_rrect(px, py, pw, ph, rad, ring=1), 0.9)
    cv.over(BRONZE, m_rrect(px + 1.5, py + 1.5, pw - 3, ph - 3, rad - 1, ring=1.2), 0.85)   # bronze trim
    fx, fy, fw, fh = px + 3, py + 3, pw - 6, ph - 6
    face = m_rrect(fx, fy, fw, fh, rad - 2)
    cv.over(suede(fy, fy + fh), face)
    cv.mul(face * (1 - m_rrect(fx + 1.5, fy + 2.5, fw - 1, fh - 2, rad - 2, blur=2.5)), 0.4)
    # chrome-edged title bar with a screw at the right
    bh = 26 if compact else 36
    bx, by_, bw = fx + 6, fy + 5, fw - 12
    cv.mul(m_rrect(bx, by_ + 2, bw, bh, 4, blur=2), 0.5)
    cv.over(metal(by_, by_ + bh, (200, 170, 120), (84, 66, 44), TEX1, 9), m_rrect(bx, by_, bw, bh, 4))
    cv.over(vgrad(by_, by_ + bh, (40, 39, 38), (16, 15, 15)) + SUEDE[..., None] * 3, m_rrect(bx + 2, by_ + 2, bw - 4, bh - 4, 3))
    cv.add((255, 255, 255), m_rrect(bx + 3, by_ + 3, bw - 6, (bh - 4) * 0.4, 2), 0.05)
    ty = by_ + bh / 2
    label(cv, (px + pw / 2 if center else bx + 14), ty, title, 18 if compact else 23, ('mm' if center else 'lm'), sp=0.8)
    if right_label:
        label(cv, bx + bw - 12, ty + 1, right_label, 13, 'rm')

    return (fx, by_ + bh, fw, fy + fh - by_ - bh)

def screws(cv, pts):
    cv.mul(m_circles([(x + 0.8, y + 1.2, 6.2) for x, y in pts], blur=1.2), 0.45)
    cv.over((0, 0, 0), m_circles([(x, y, 5.6) for x, y in pts]))
    for x, y in pts:
        cv.over(vgrad(y - 5, y + 5, (240, 242, 245), (100, 103, 108)), m_circles([(x, y, 4.9)]))
    segs = []
    for x, y in pts:
        segs += [(x - 3.6, y, x + 3.6, y), (x, y - 3.6, x, y + 3.6)]
    cv.over((36, 38, 42), m_lines(segs, 1.2), 0.85)

LOGO_FIT = os.environ.get('XC_LOGO_FIT', 'fit')   # mid | fill | fit (preview https://claude.ai/artifact/WpSLWqU3YNBnHWvSSoMewA)
LOGO_ACCENT = None   # the logo's accent (None = the picture's red); the Theme Editor's BANNER LINE sets it (metal_banner.py)
def banner(cv, name, **_):
    """the X-CONSOLE logo banner (tools/custom-pages/xc_logo.py, user's logo 2026-11-11); the name like its HEARTS"""
    if LOGO_FIT == 'mid':      # swoosh top at the page top, the bar's lower edge and the X tip tucked behind the panels
        scale, top, px = 0.34, 18.0, 28
    elif LOGO_FIT == 'fit':    # the whole logo inside the banner: bar 39 px, swoosh within the top 65 px
        scale, top, px = 0.28, 11.4, 23
    else:                      # the bar fills the banner (62 px); the swoosh and X tips run past it
        scale, top, px = 62.0 / (xc_logo.BAR1 - xc_logo.BAR0), 0.0, 36
    nw = xc_logo.text_w(name, px * S) / S + px * 0.3
    t0, t1, xr = xc_logo.draw_bar(sys.modules[__name__], cv, nw, scale, top, LOGO_ACCENT, clear_loop=True)
    # the bar's fill = the panels' granite face (user 2026-11-12: "make the background of the banner match the
    # background of the panels"); the gradient spans a panel's height so the colour matches the panels' tops
    bm, i0, i1 = xc_logo.bg_mask(sys.modules[__name__], nw, scale, top)
    cv.over(suede(i0 - 6, i0 + 548), bm)
    cv.mul(bm * (1 - m_rrect(-10, i0 + 2.5, W + 20, i1 - i0, 2, blur=2.5)), 0.4)   # the panels' inner shadow
    cy = t0 + (t1 - t0) * 0.41
    c0, c1 = ((255, 80, 70), (180, 0, 0)) if LOGO_ACCENT is None else xc_logo.accent_grad(LOGO_ACCENT)
    grad_text(cv, xr, cy, name, px, c0, c1, anchor='rm', stroke_col=(255, 255, 255), stroke=1.6, logo=True)

def vbox(cv, cx, cy, w, h=22):
    x, y = cx - w / 2, cy - h / 2
    cv.mul(m_rrect(x - 1, y, w + 2, h + 2, 3, blur=2), 0.55)
    cv.over(vgrad(y, y + h, (10, 10, 10), (24, 23, 22)), m_rrect(x, y, w, h, 2.5))
    cv.over(BRONZE, m_rrect(x, y, w, h, 2.5, ring=1.4), 0.95)
    cv.mul(m_rrect(x, y, w, h, 2.5) * (1 - m_rrect(x + 1, y + 3, w, h, 2.5, blur=2)), 0.5)

METER_DY = 5          # IN/OUT meters moved down 5 px (user, 2026-11-11)
LED_SCALE = [(d, y + METER_DY) for d, y in [(6, 121), (0, 151), (-6, 181), (-12, 211), (-18, 241), (-24, 271), (-30, 301), (-36, 331), (-48, 391), (-60, 451)]]
LED_Y = np.linspace(119 + METER_DY, 453 + METER_DY, 30)

def led_db(y):
    ys = [p[1] for p in LED_SCALE]; ds = [p[0] for p in LED_SCALE]
    return float(np.interp(y, ys, ds))

METER_STOPS = None   # [(dB, (r,g,b)), ...] from the colours file's METERS, None = the picture's bands below
UNLIT = None

def led_col(db):
    if METER_STOPS:
        st = METER_STOPS
        if db <= st[0][0]:
            return st[0][1]
        for (d0, c0), (d1, c1) in zip(st, st[1:]):
            if db <= d1:
                t = (db - d0) / (d1 - d0) if d1 > d0 else 1.0
                return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
        return st[-1][1]
    if db > -1: return (236, 36, 28)        # the picture: red at 0 and up
    if db > -4: return (242, 92, 30)        # red-orange
    if db > -9: return (246, 146, 30)       # orange -6
    if db > -15: return (246, 218, 40)      # yellow -12
    if db > -21: return (238, 240, 236)     # white -18
    if db > -27: return (150, 222, 150)     # pale green -24
    return (44, 200, 64)                    # green below

def meter_well(cv, x0, scale_x, cols):
    wx, wy = cols[0] - 11, 111 + METER_DY
    ww, wh = cols[-1] - cols[0] + 22, 351
    cv.mul(m_rrect(wx - 1, wy - 1, ww + 2, wh + 3, 4, blur=2), 0.5)
    cv.over(vgrad(wy, wy + wh, (10, 10, 12), (17, 17, 19)), m_rrect(wx, wy, ww, wh, 3))
    cv.mul(m_rrect(wx, wy, ww, wh, 3) * (1 - m_rrect(wx + 2, wy + 3, ww, wh, 3, blur=2.5)), 0.4)
    cv.add((255, 255, 255), m_rrect(wx, wy, ww, wh, 3, ring=0.8) * ((np.arange(H * S, dtype=np.float32)[:, None] / S) > wy + wh / 2), 0.12)
    for db, y in LED_SCALE:
        light_text(cv, scale_x, y, ('+%d' % db) if db > 0 else str(db), 12.5, 'rm')
    for cx in cols:
        for y in LED_Y:
            c = np.asarray(led_col(led_db(y)), np.float32)
            cv.over(np.asarray(UNLIT, np.float32) if UNLIT else c * 0.16 + 8, m_rrect(cx - 6.5, y - 4, 13, 8, 1.2))
            cv.over((np.asarray(UNLIT, np.float32) * 1.25 + 6) if UNLIT else c * 0.28 + 10, m_rrect(cx - 6.5, y - 4, 13, 8, 1.2, ring=0.7), 0.6)

def meter_lit(cv, cols_levels):
    for cx, lev in cols_levels:
        for y in [y for y in LED_Y if led_db(y) <= lev]:
            c = led_col(led_db(y))
            m = m_rrect(cx - 6.5, y - 4, 13, 8, 1.2)
            cv.over(c, m)
            cv.add(c, blur_np(m, 2.0), 0.25)
            cv.add((255, 255, 255), m_rrect(cx - 5, y - 3, 10, 2.5, 1), 0.3)

def screen(cv, x, y, w, h, hl=(), vl=(), diag=False):
    cv.mul(m_rrect(x - 5, y - 4, w + 10, h + 10, 6, blur=3), 0.45)
    cv.over(vgrad(y - 4, y + h + 4, (200, 170, 120), (80, 62, 40)), m_rrect(x - 4, y - 4, w + 8, h + 8, 5))   # bronze bezel
    cv.over(vgrad(y, y + h, (16, 16, 18), (6, 6, 7)), m_rrect(x, y, w, h, 3))
    segs = [(x, yy, x + w, yy) for yy in hl] + [(xx, y, xx, y + h) for xx in vl]
    if segs:
        cv.over((84, 84, 90), m_lines(segs, 1.0), 0.45)
    if diag:
        d, n = [], 30
        for i in range(0, n, 2):
            d.append((x + w * i / n, y + h - h * i / n, x + w * (i + 1) / n, y + h - h * (i + 1) / n))
        cv.over((140, 140, 146), m_lines(d, 1.0), 0.55)
    cv.mul(m_rrect(x, y, w, h, 3) * (1 - m_rrect(x + 6, y + 6, w - 12, h - 12, 3, blur=8)), 0.55)
    cv.over((0, 0, 0), m_rrect(x, y, w, h, 3, ring=1), 0.8)

# ================================================================ custom pages for the build
TOP = 86
PFX = 'cp_gnmetal_'
CTRL = []
CUSTOM = {}   # knob looks from the Theme Editor (metal_knobs.look): name -> (base, tint, pointer) / chicken (top, bot)
STYLES = ['black', 'pearl', 'pink', 'bronze', 'red']   # the cap styles this page script draws (the editor lists them)
EXTRA = []

def tick_r(r):
    return r + max(8, r * 0.2)

def knob_bg(cv, cx, cy, r, lab, boxw=None, lpx=15, boxh=22):
    R = tick_r(r)
    segs = []
    for i in range(11):
        a = math.radians(-135 + 27 * i)
        segs.append((cx + (R - 1) * math.sin(a), cy - (R - 1) * math.cos(a), cx + (R + 5) * math.sin(a), cy - (R + 5) * math.cos(a)))
    cv.mul(m_lines([(a + 0.5, b + 1, c + 0.5, d + 1) for a, b, c, d in segs], 2.2, blur=0.8), 0.5)
    cv.over((246, 248, 252), m_lines(segs, 1.9))
    cv.mul(m_circles([(cx + 1, cy + 5, r + 3)], blur=6), 0.5)
    # the knob's body (doesn't turn): dark skirt, glowing blue ring
    cv.over(vgrad(cy - r, cy + r, (70, 70, 74), (4, 4, 5)), m_circles([(cx, cy, r)]))
    cv.over(vgrad(cy - r, cy + r, (8, 8, 9), (36, 36, 40)), m_circles([(cx, cy, r - 2.5)]))
    cv.add((255, 255, 255), m_circles([(cx, cy, r - 0.8)], ring=0.9) * (_ys < cy - r * 0.2), 0.3)
    cv.mul(m_circles([(cx, cy + 2, r * 0.8 + 1.5)], blur=2), 0.5)   # the cap's shadow on the skirt
    ly = cy + R + 5 + lpx * 0.8
    label(cv, cx, ly, lab, lpx)
    by = ly + lpx * 0.6 + boxh / 2 + 3
    vbox(cv, cx, by, boxw or max(78, 2 * r + 16), boxh)
    return by

def cap(cv, cx, cy, r, style='silver', val=0.5):
    """The turning part: brushed metal cap + pointer (val 0..1 = -135..+135 deg)."""
    rc = r * 0.80
    x0, y0 = int((cx - rc - 2) * S), int((cy - rc - 2) * S)
    x1, y1 = int((cx + rc + 2) * S), int((cy + rc + 2) * S)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32) / S
    dx, dy = xx - cx, yy - cy
    rr = np.sqrt(dx * dx + dy * dy)
    th = np.arctan2(dy, dx) - math.radians(-135 + 270 * val)
    rng = np.random.default_rng(int(r * 13) + len(style))
    fine = sum(rng.normal() * np.sin(k * th + rng.uniform(0, 6.28)) for k in range(40, 140, 3)) * 0.12
    base = CUSTOM[style][0] if style in CUSTOM else {'black': (50, 30), 'pearl': (196, 46), 'pink': (150, 52), 'bronze': (140, 56), 'red': (140, 52)}[style]
    b = base[0] + base[1] * (0.6 * np.cos(2 * (th + 0.75)) + 0.4 * np.cos(th + 2.2)) + fine * base[1] * 0.4
    b = b - 18 * (rr / rc) ** 3
    tint = CUSTOM[style][1] if style in CUSTOM else {'black': (1.0, 1.0, 1.0), 'pearl': (1.02, 1.0, 0.96), 'pink': (1.45, 0.42, 0.72), 'bronze': (1.25, 0.82, 0.52), 'red': (1.45, 0.26, 0.24)}[style]
    col = np.clip(b[..., None] * np.asarray(tint, np.float32), 0, 255)
    a = np.clip((rc - rr) * S + 0.5, 0, 1)[..., None]
    cv.a[y0:y1, x0:x1] = cv.a[y0:y1, x0:x1] * (1 - a) + col * a
    cv.over((10, 10, 14), m_circles([(cx, cy, rc)], ring=0.8), 0.7)
    ang = math.radians(-135 + 270 * val)
    p0 = (cx + 0.15 * rc * math.sin(ang), cy - 0.15 * rc * math.cos(ang))
    p1 = (cx + 0.92 * rc * math.sin(ang), cy - 0.92 * rc * math.cos(ang))
    pc = CUSTOM[style][2] if style in CUSTOM else ((24, 22, 22) if style == 'pearl' else (246, 246, 248))
    cv.over(pc, m_lines([(p0[0], p0[1], p1[0], p1[1])], max(2.4, rc * 0.10)))

TOG_R = 23
TOG_IMG = 56

def toggle_bg(cv, cx, cy, lab, r=TOG_R):
    cv.mul(m_circles([(cx + 1, cy + 4, r + 3)], blur=5), 0.5)
    cv.over(vgrad(cy - r, cy + r, (170, 146, 108), (30, 26, 22)), m_circles([(cx, cy, r)]))
    cv.over(vgrad(cy - r, cy + r, (6, 6, 7), (36, 36, 40)), m_circles([(cx, cy, r - 3.5)]))
    cv.add((255, 255, 255), m_circles([(cx, cy - r * 0.35, r * 0.55)], blur=3) * m_circles([(cx, cy, r - 5)]), 0.07)
    label(cv, cx, cy + r + 19, lab, 16)

def led(cv, cx, cy, on):
    if on:
        cv.add(GLOW, m_circles([(cx, cy, 10)], blur=5), 1.3)
        cv.over((255, 196, 40), m_circles([(cx, cy, 8)]))
        cv.over((255, 248, 210), m_circles([(cx - 0.5, cy - 1, 3.2)], blur=1.0))
    else:
        cv.over((70, 44, 10), m_circles([(cx, cy, 8)]))
        cv.add((255, 255, 255), m_circles([(cx - 1.5, cy - 2.5, 2.2)], blur=1), 0.10)

FIELD_ARROW = FIELD_GLOW = None   # a drop-down arrow's colour / glow from the Theme Editor (metal_dropdown.py); None = as drawn

def field(cv, cx, cy, w, h):
    x, y = cx - w / 2, cy - h / 2
    cv.mul(m_rrect(x - 1, y, w + 2, h + 3, 5, blur=3), 0.5)
    cv.over(vgrad(y, y + h, (6, 14, 28), (14, 26, 46)), m_rrect(x, y, w, h, 3))
    cv.over((176, 184, 196), m_rrect(x, y, w, h, 3, ring=1.8))
    tx, ty = x + w - 26, cy
    tri = new_mask()
    ImageDraw.Draw(tri).polygon([((tx - 10) * S, (ty - 6) * S), ((tx + 10) * S, (ty - 6) * S), (tx * S, (ty + 7) * S)], fill=255)
    cv.over(FIELD_ARROW or (40, 150, 240), to_np(tri))

GAIN_N = 40

def gain_slot(cv, cx, y0, y1, w=24):
    x = cx - w / 2
    cv.mul(m_rrect(x - 2, y0 - 2, w + 4, y1 - y0 + 5, 4, blur=2), 0.45)
    cv.over((10, 10, 12), m_rrect(x - 1, y0 - 1, w + 2, y1 - y0 + 2, 3))
    step = (y1 - y0) / GAIN_N
    for i in range(GAIN_N):
        cv.over((50, 32, 12), m_rrect(x + 2, y0 + i * step + 1, w - 4, step - 2, 1))

# ---------------------------------------------------------------- registering controls
def K(key, cx, cy, r, lab, style='black', v=0.5, t='', boxw=None, lpx=15, boxh=22, cv=None):
    by = knob_bg(cv, cx, cy, r, lab, boxw, lpx, boxh)
    CTRL.append(dict(kind='knob', key=key, lab=lab, cx=cx, cy=cy, r=r, style=style, v=v, t=t, by=by,
                     vs=17 if boxh >= 22 else 15, bw=int(boxw or max(78, 2 * r + 16))))

def T(key, cx, cy, lab, on=True, cv=None):
    toggle_bg(cv, cx, cy, lab)
    CTRL.append(dict(kind='toggle', key=key, cx=cx, cy=cy, on=on))

def E(key, cx, cy, sw, sh, opts, sel=0, vert=False, px=15, cv=None):
    c = dict(kind='enum_v' if vert else 'enum_h', key=key, cx=cx, cy=cy, sw=sw, sh=sh, opts=opts, sel=sel, px=px)
    CTRL.append(c)
    if cv is not None:   # the dark tray the option buttons sit in
        rs = seg_rects(c)
        x0 = min(r[0] for r in rs) - 3; y0 = min(r[1] for r in rs) - 3
        x1 = max(r[0] + r[2] for r in rs) + 3; y1 = max(r[1] + r[3] for r in rs) + 3
        cv.mul(m_rrect(x0, y0 + 1, x1 - x0, y1 - y0 + 2, 5, blur=3), 0.45)
        cv.over((8, 8, 10), m_rrect(x0, y0, x1 - x0, y1 - y0, 5))
        cv.add((255, 255, 255), m_rrect(x0, y0, x1 - x0, y1 - y0, 5, ring=0.8) * (_ys > (y0 + y1) / 2), 0.18)

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
        cv.over(vgrad(y, y + h, (232, 140, 36), (140, 62, 8)), m_rrect(x, y, w, h, 3))
        cv.add(GLOW, blur_np(m_rrect(x + 4, y + 4, w - 8, h - 8, 3), 4) * m_rrect(x, y, w, h, 3), 0.35)
        cv.over((255, 222, 150), m_rrect(x, y, w, h, 3, ring=1.0), 0.85)
    else:
        cv.over(vgrad(y, y + h, (58, 58, 62), (16, 16, 18)), m_rrect(x, y, w, h, 3))
        cv.over((2, 2, 3), m_rrect(x, y, w, h, 3, ring=1.0))
    cv.add((255, 255, 255), m_rrect(x + 2, y + 1, w - 4, h * 0.42, 2), 0.07)
    if txt:
        light_text(cv, x + w / 2, y + h / 2, txt, px, 'mm', w='Bold')

def in_out(cv):
    for (x, ttl, sx, cols, kx, lab, key, st) in [(0, 'IN', 33, (48, 76), 62, 'INPUT', 'in_gain', 'pearl'),
                                                 (1156, 'OUT', 1189, (1204, 1232), 1218, 'OUTPUT', 'out_vol', 'red')]:
        panel(cv, x, 66, 124, 556, ttl)
        meter_well(cv, x, sx, cols)
        K(key, kx, 517, 28, lab, st, 0.5, '0.0 dB', boxw=96, cv=cv)

# ---------------------------------------------------------------- pages (page coords; same plan as Avalon's)
def page_preamp(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 406, 556, 'TAPE / PREAMP')
    label(cv, 331, 158, 'TYPE', 16)
    E('pre_type', 331, 196, 104, 40, ['TAPE', 'TUBE', 'IRON'], 0, cv=cv)
    K('pre_color', 331, 318, 44, 'COLOR', 'pink', 0.3, '35 %', boxw=180, cv=cv)
    T('phase', 230, 505, 'PHASE INV', True, cv=cv); T('pre_on', 430, 505, 'ON', True, cv=cv)
    panel(cv, 538, 66, 386, 556, 'FILTER')
    K('lc_freq', 636, 200, 44, 'LOW CUT', 'black', 0.15, '40 Hz', boxw=150, cv=cv)
    K('hc_freq', 826, 200, 44, 'HIGH CUT', 'pearl', 0.85, '16.0 kHz', boxw=150, cv=cv)
    label(cv, 636, 342, 'SLOPE', 15); label(cv, 826, 342, 'SLOPE', 15)
    E('lc_slope', 636, 377, 40, 34, ['6', '12', '18', '24'], 1, cv=cv)
    E('hc_slope', 826, 377, 40, 34, ['6', '12', '18', '24'], 1, cv=cv)
    label(cv, 731, 418, 'dB / OCT', 14)
    T('flt_sc', 636, 505, 'TO S/C', True, cv=cv); T('flt_on', 826, 505, 'ON', True, cv=cv)
    panel(cv, 928, 66, 224, 556, 'NOISE')
    label(cv, 950, 158, 'WAVEFORM', 15, 'lm')
    PU('nz_color', 1040, 197, 184, 46, 'PINK,WHITE,BROWN,BLUE,VIOLET,GREY,CRACKLE', 'PINK', cv=cv)
    K('nz_level', 1040, 340, 44, 'LEVEL', 'bronze', 0.25, '-48.0 dB', boxw=150, cv=cv)
    T('nz_on', 1040, 505, 'ON', True, cv=cv)

def page_shape(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 386, 556, 'TRANSIENT')
    K('sh_punch', 321, 210, 48, 'PUNCH', 'pink', 0.6, '+20 %', boxw=160, cv=cv)
    K('sh_sustain', 321, 412, 48, 'SUSTAIN', 'pearl', 0.45, '-10 %', boxw=160, cv=cv)
    panel(cv, 518, 66, 634, 556, 'GATE / EXPANDER')
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
    sm = dict(lpx=13, boxh=20, boxw=88, cv=cv)
    K('gate_thr', 990, 156, 26, 'THRESHOLD', 'black', 0.3, '-40.0 dB', **sm)
    K('gate_range', 1092, 156, 26, 'RANGE', 'black', 0.6, '-40 dB', **sm)
    K('gate_ratio', 990, 294, 26, 'EXP RATIO', 'bronze', 0.2, '2.0:1', **sm)
    K('gate_hold', 1092, 294, 26, 'HOLD', 'pearl', 0.3, '20 ms', **sm)
    K('gate_rel', 990, 432, 26, 'RELEASE', 'black', 0.4, '120 ms', **sm)
    label(cv, 643, 496, 'MODE', 15)
    E('gate_mode', 643, 530, 75, 38, ['GATE', 'EXP'], 0, cv=cv)
    T('gate_fast', 793, 522, 'FAST ATT', False, cv=cv); T('sh_on', 883, 522, 'ON', True, cv=cv)
    EXTRA.extend(keep_art('SHAPE', 'tc_logo') + keep_art('SHAPE', 'upic_'))   # the maker's logo / CURVE PICTURE (live in the build)
    EXTRA.extend(keep('SHAPE', ('gtc_',)))
    EXTRA.append('meter cx=883 cy=364 w=24 h=296 key=m_shape strip=art/%sgain_shape.png frames=41' % PFX)

EQ_F = [(221, '30'), (273, '50'), (344, '100'), (415, '200'), (508, '500'), (579, '1k'), (650, '2k'), (743, '5k'), (814, '10k')]

def page_eq(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 1024, 384, 'EQUALIZER', compact=True)
    screen(cv, 180, 110, 704, 330, hl=[113 + 54 * i for i in range(1, 6)], vl=[x for x, _ in EQ_F])
    for i, t in enumerate(['0', '-12', '-24', '-36', '-48', '-60', '-72']):
        label(cv, 173, 113 + 54 * i, t, 12, 'rm')
    for x, t in EQ_F:
        light_text(cv, x, 430, t, 12, 'mm', col=(200, 190, 176))
    label(cv, 1019, 140, 'VIEW', 15)
    E('sp_view', 1019, 175, 100, 38, ['FFT', 'BARS'], 0, cv=cv)
    label(cv, 1019, 238, 'PEAK HOLD', 15)
    E('pk_hold', 1019, 273, 42, 36, ['OFF', '1s', '3s', '6s', '∞'], 2, px=14, cv=cv)
    label(cv, 958, 382, 'GRANITE', 15)
    toggle_bg(cv, 1086, 372, 'ON'); CTRL.append(dict(kind='toggle', key='eq_on', cx=1086, cy=372, on=True))
    bands = [(128, 252, 'LF', 'lf', [('gain', 174, 'GAIN'), ('freq', 254, 'FREQ')], 330),
             (384, 252, 'LMF', 'lmf', [('gain', 430, 'GAIN'), ('freq', 510, 'FREQ'), ('q', 590, 'Q')], None),
             (640, 252, 'HMF', 'hmf', [('gain', 686, 'GAIN'), ('freq', 766, 'FREQ'), ('q', 846, 'Q')], None),
             (896, 256, 'HF', 'hf', [('gain', 942, 'GAIN'), ('freq', 1022, 'FREQ')], 1098)]
    sv = {'gain': ('bronze', 0.5, '0.0 dB'), 'freq': ('black', 0.55, '1.0 kHz'), 'q': ('pearl', 0.3, '0.7')}
    for x, w, t, b, knobs, tx in bands:
        panel(cv, x, 454, w, 168, t, compact=True, right_label='TYPE' if tx else None)
        for p, kx, kl in knobs:
            st, v, tt = sv[p]
            K('eq_%s_%s' % (b, p), kx, 534, 20, kl, st, v, tt, boxw=68, lpx=13, boxh=20, cv=cv)
        if tx:
            E('eq_%s_type' % b, tx, 548, 64, 26, ['SHELF', 'BELL', 'CUT'], 0, vert=True, px=13, cv=cv)
    EXTRA.extend(keep_art('EQ', 'upic_') + keep_art('EQ', 'eq_logo'))   # EQ PICTURE (live in the build)
    EXTRA.extend(keep('EQ', ('spc_', 'spk_', 'eqc_')))

def page_comp(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 610, 556, 'COMPRESSOR')
    for key, x, y, r, l, st, v, t in [('cmp_att', 273, 186, 36, 'ATTACK', 'black', 0.3, '10 ms'),
                                      ('cmp_ratio', 433, 186, 36, 'RATIO', 'black', 0.4, '4.0:1'),
                                      ('cmp_knee', 593, 186, 28, 'KNEE', 'pearl', 0.5, '6 dB'),
                                      ('cmp_rel', 273, 348, 36, 'RELEASE', 'black', 0.45, '250 ms'),
                                      ('cmp_thr', 433, 348, 42, 'COMPRESSION', 'pink', 0.35, '-18.0 dB'),
                                      ('cmp_makeup', 593, 348, 28, 'MAKE-UP', 'bronze', 0.3, '+3.0 dB'),
                                      ('cmp_mix', 273, 508, 28, 'WET/DRY', 'pearl', 1.0, '100 %'),
                                      ('cmp_sc_hpf', 433, 508, 28, 'S/C HPF', 'black', 0.1, '60 Hz')]:
        K(key, x, y, r, l, st, v, t, boxw=120 if r >= 36 else 100, cv=cv)
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
    E('cmp_det', 885, 532, 100, 38, ['RMS', 'PEAK'], 0, cv=cv)
    T('cmp_on', 1065, 522, 'ON', True, cv=cv)
    EXTRA.extend(keep_art('COMP', 'tc_logo') + keep_art('COMP', 'upic_'))
    EXTRA.extend(keep('COMP', ('ctc_',)))
    EXTRA.append('meter cx=1105 cy=364 w=24 h=296 key=m_gr strip=art/%sgain_gr.png frames=41' % PFX)

def page_output(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 406, 556, 'DRIVE')
    K('drv_amt', 331, 205, 44, 'DRIVE', 'bronze', 0.3, '20 %', boxw=150, cv=cv)
    K('drv_char', 331, 384, 38, 'CHARACTER', 'pearl', 0.5, '50 %', boxw=150, cv=cv)
    label(cv, 268, 430, '2ND', 12); label(cv, 394, 430, '3RD', 12)
    label(cv, 231, 532, 'POSITION', 15)
    E('drv_pos', 231, 570, 80, 38, ['POST', 'PRE'], 0, cv=cv)
    T('drv_on', 431, 550, 'ON', True, cv=cv)
    panel(cv, 538, 66, 305, 556, 'OUTPUT')
    K('out_pan', 690, 205, 40, 'PAN', 'black', 0.5, 'C', boxw=140, cv=cv)
    K('out_width', 690, 395, 40, 'WIDTH', 'pearl', 0.5, '100 %', boxw=140, cv=cv)
    panel(cv, 847, 66, 305, 556, 'ROUTING')
    label(cv, 872, 158, 'ORDER', 15, 'lm')
    PU('order', 1000, 199, 260, 46, 'SHP>EQ>CMP,SHP>CMP>EQ,EQ>SHP>CMP,EQ>CMP>SHP,CMP>SHP>EQ,CMP>EQ>SHP', 'SHP>EQ>CMP', cv=cv)
    label(cv, 1000, 264, 'SHAPE  /  EQ  /  COMP', 14)
    T('bypass', 1000, 535, 'BYPASS', False, cv=cv)

def page_info(cv):
    banner(cv, SHOWN); in_out(cv)
    panel(cv, 128, 66, 1024, 556, 'INFO', center=True)   # title bar back, INFO centred (user 2026-11-14)
    EXTRA.append('#infotext cy=%d step=34' % (TOP + 162))   # no name / CHANNEL STRIP / panel title (user 2026-11-12): INFO TEXT starts near the panel top

PAGES = [('PREAMP', page_preamp), ('SHAPE', page_shape), ('EQ', page_eq), ('COMP', page_comp), ('OUTPUT', page_output), ('INFO', page_info)]

# ---------------------------------------------------------------- the plugin's own layout (kept lines)
CONF = None
def _tab_lines(tab):
    cur = None
    for ln in open(CONF).read().splitlines():
        if ln.startswith('[tab '):
            cur = ln[5:-1]
            continue
        if cur == tab:
            yield ln

def keep(tab, prefixes):
    out = [ln for ln in _tab_lines(tab) if ln.startswith('meter ') and any(' key=' + p in ln for p in prefixes)]
    if not out:
        raise SystemExit('no %s lines for %s in %s' % (prefixes, tab, CONF))
    return out

def keep_art(tab, sub):
    return [ln for ln in _tab_lines(tab) if ln.startswith('art ') and sub in ln]

# ---------------------------------------------------------------- pictures
def extract(draw, x, y, w, h):
    b, wh = Cv(), Cv()
    wh.a[:] = 255
    draw(b); draw(wh)
    sl = (slice(int(round(y * S)), int(round((y + h) * S))), slice(int(round(x * S)), int(round((x + w) * S))))
    B, Wt = b.a[sl], wh.a[sl]
    a = np.clip(1 - (Wt - B).mean(axis=2) / 255.0, 0, 1)
    col = np.clip(B / np.maximum(a, 1e-3)[..., None], 0, 255)
    return Image.fromarray(np.dstack([col, a * 255]).astype(np.uint8), 'RGBA')

def strip(frames, path):
    w, h = frames[0].size
    s = Image.new('RGBA', (w, h * len(frames)))
    for i, f in enumerate(frames):
        s.paste(f, (0, i * h))
    s.save(path)

LEDX, LEDW, LEDY0, LEDY1 = 48, 16, 113 + METER_DY, 459 + METER_DY

def led_strips(art, tab):
    global W, H
    keep_wh = (W, H)
    W, H = 128, 470
    try:
        _led_strips(art, tab)
    finally:
        W, H = keep_wh

def _led_strips(art, tab):
    off, on = Cv(), Cv()
    for c in (off, on):
        meter_well(c, 0, 33, (48, 76))
    meter_lit(on, [(48, 99)])
    sl = (slice(LEDY0 * S, LEDY1 * S), slice((LEDX - LEDW // 2) * S, (LEDX + LEDW // 2) * S))
    Aoff, L = off.a[sl], on.a[sl]
    ys = sorted(LED_Y, reverse=True)
    def rows(y):
        return int(round((y - 5.75 - LEDY0) * S)), int(round((y + 5.75 - LEDY0) * S))
    small = lambda arr: Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA').resize((LEDW, LEDY1 - LEDY0), Image.LANCZOS)
    bar, pk = [], []
    for f in range(31):
        fr = Aoff.copy()
        p = np.zeros(Aoff.shape[:2] + (4,), np.float32)
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
        im = Image.new('RGBA', (w * k, h * k), (10, 10, 12, 255))
        d = ImageDraw.Draw(im)
        for i in range(GAIN_N):
            y0 = i * step + 1 * k
            box = [2 * k, y0, (w - 2) * k - 1, y0 + step - 2 * k]
            if i in lit:
                d.rounded_rectangle(box, radius=k, fill=(250, 170, 40))
                d.rectangle([3 * k, y0 + k, (w - 3) * k - 1, y0 + step * 0.4], fill=(255, 226, 150))
            else:
                d.rounded_rectangle(box, radius=k, fill=(50, 32, 12))
        return im.resize((w, h), Image.LANCZOS)
    half = GAIN_N // 2
    shape = []
    for f in range(41):
        lit = set(range(half - (f - 20), half)) if f >= 20 else set(range(half, half + (20 - f)))
        shape.append(frame(lit))
    strip(shape, os.path.join(art, PFX + 'gain_shape.png'))
    strip([frame(set(range(f))) for f in range(41)], os.path.join(art, PFX + 'gain_gr.png'))

def control_pictures(art, done):
    lines = []
    for c in CTRL:
        k = c['kind']
        if k == 'knob':
            rw = int(round(c['by'] - c['cy'] - 15))      # the value (ns=0) is centred at cy + r + 15
            box = (2 * rw + 8) * S
            name = PFX + 'knob_%s.png' % c['key']
            im = extract(lambda cv, c=c: cap(cv, 640, 314, c['r'], c['style'], 0.5),
                         640 - box / S / 2, 314 - box / S / 2, box / S, box / S)
            im.save(os.path.join(art, name))
            lines.append('knob cx=%d cy=%d r=%d key=%s ns=0 vs=%d bw=%d vcase=none ink_dim=f4ecde img=art/%s'
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
            lines.append('popup cx=%d cy=%d w=%d h=%d key=%s label="" field=none options="%s" accent=c8862a opens=_v field_ink=3ca0f0 list_ink=ffffff'
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
            light_text(cv, c['cx'] - 18, c['cy'], c['t'], 18, 'mm', col=(60, 160, 240), w='Bold')

# ---------------------------------------------------------------- Theme Editor colours (as Avalon's)
FILE_PAGE = {'INFO': 'SETUP'}
BUILTIN_METERS = {'SETUP': '-18 #2f9fd0, -12 #ebebf0, 0 #e23428'}
BUILTIN_METERS_DEFAULT = '-12 #46c85a, -6 #f0d634, 0 #e23428'   # make_art.LED_GRANITE
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
    global METER_STOPS, UNLIT
    pg = FILE_PAGE.get(tab, tab)
    v = vals.get((SECTION, pg, 'METERS'), vals.get((SECTION, 'ALL', 'METERS')))
    METER_STOPS = None
    if v is not None and _norm(v) != _norm(BUILTIN_METERS.get(pg, BUILTIN_METERS_DEFAULT)):
        METER_STOPS = parse_meters(v)
        if METER_STOPS is None:
            print('  %s: METERS "%s" is not a gradient (dB #colour, ...); metal colours kept' % (tab, v), flush=True)
    u = vals.get(('ALL SHOWNS', 'PANEL', 'UNLIT METER SEGMENTS'))
    UNLIT = _hex(u) if u and _norm(u) != _norm(BUILTIN_UNLIT) else None
    return '%s meters: %s, unlit: %s' % (tab, ('editor (%s)' % v) if METER_STOPS else 'metal',
                                         ('#' + u.lstrip('#')) if UNLIT else 'metal')

def strips_only(art, colours, lay):
    vals = read_colours(colours)
    os.makedirs(art, exist_ok=True)
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
        cv.a[:] = metal(0, H, (44, 42, 40), (16, 15, 14), TEX1, 8)
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
