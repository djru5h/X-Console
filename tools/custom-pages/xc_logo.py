"""The X-CONSOLE brand logo banner (user, 2026-11-11: "X-CONSOLE is a brand.. I have developed a logo for it ...
X-Console: Flannel: Replace the banner with the logo i provided.. use the same style for the text on the right side of the
banner as well").

The logo is pictures/Metallic X-Console Hearts Banner.png. logo/make_logo_rgba.py cut it out of its white background into
logo/xconsole_logo_rgba.png (same size, 2172 x 724). The banner is that picture rebuilt at page width:
  source x 0..1000      the X, the red swoosh and -CONSOLE on the black bar (as drawn)
  source x 1000..1700   the brushed middle, stretched to fill
  source x 1700..1760   its fade into the black right end, then column 1750 repeated for the name, then the end cap
                        2145..2172 (the picture's HEARTS is never copied)
The name on the right is drawn like the picture's HEARTS: Arial Black slanted, red gradient, dark edge, white stroke,
black outline (logo/ariblk.ttf).

  draw_bar(mod, cv, name_w, scale, top, accent)  the bar + logo; mod = the page script (W, H, S, Cv)
  recolour(img, accent)  the logo's red (swoosh, red faces of the X, the line and its glow) in another colour

Accent (user, 2026-11-11: "i want to be able to change the accent color in the logo. in this case, the color is red"):
each pixel splits into grey = max(G, B) and red = R - grey; the red part is repainted in the accent
(grey + red * accent / 255), so pure red becomes the accent, its shading and pink highlights keep their light, and
greys, whites and blacks don't change. accent None = the picture as drawn (DRAWN_ACCENT is the colour that stands for it).
  name_mask(mod, x, y, t, px, anchor, stroke)  a slanted Arial Black mask at S scale
"""
import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LOGO = os.path.join(HERE, 'logo', 'xconsole_logo_rgba.png')
FONT = os.path.join(HERE, 'logo', 'ariblk.ttf')
BAR0, BAR1 = 316, 456        # the picture's bar rows (chrome edge to chrome edge)
TOP0, BOT0 = 266, 508        # the whole logo (swoosh top .. X tip)
LEFT, MID1, FADE1 = 1000, 1700, 1760
FILL_COL, CAP0 = 1750, 2145
SLANT = 0.22
DRAWN_ACCENT = (232, 22, 20)   # the picture's red, for the Theme Editor's swatch
X_ACCENT = None   # the new logo's own accent (Theme Editor BANNER X-, set by metal_banner.py); None = follows accent
_src = None
_fc = {}


def _logo_old():
    global _src_old
    if _src_old is None:
        _src_old = Image.open(LOGO).convert('RGBA')
    return _src_old


# ---------------------------------------------------------------- the new logo (2026-11-14)
# User: "can we replace X-CONSOLE in the banner with this?" ([Ru5h Skins]/X-console logo.png, copied to
# logo/xconsole_logo2.png: chrome X + red swoosh + chrome CONSOLE on a clear background, 495 x 121). The old picture's
# X / -CONSOLE (source x 0..LEFT) is replaced by a plain bar (its top chrome edge, black inside, the trim + accent line +
# bottom band, from columns PLAIN_EDGE / PLAIN_BLACK) with the new logo pasted on it: NEW_K source px per logo px, left
# edge at NEW_X, its CONSOLE letters (logo rows NEW_L0..NEW_L1) centred on the bar's inside. The rest of the bar (brushed
# middle, fade, name, end cap) is unchanged. The logo's red takes the accent like before (recolour). XC_LOGO2=0 = old logo.
LOGO2 = os.path.join(HERE, 'logo', 'xconsole_logo2.png')
NEW_LOGO = os.environ.get('XC_LOGO2', '1') != '0'
NEW_K = float(os.environ.get('XC_LOGO2_K', '2.07'))
NEW_X = 8
NEW_L0, NEW_L1 = 44, 70
PLAIN_EDGE, PLAIN_BLACK = 985, 20
_src_old = None
_new_alpha = None


def _logo():
    global _src, _new_alpha
    if not NEW_LOGO:
        return _logo_old()
    if _src is None:
        old = np.asarray(_logo_old()).copy()
        col = old[:, PLAIN_EDGE].copy()
        col[IN0:IN1 - 3] = old[IN0:IN1 - 3, PLAIN_BLACK]            # black inside the bar (no brushed streaks)
        left = max(LEFT, 0)
        base = old.copy()
        base[:, :left] = col[:, None]
        # blend into the original fade at LEFT (columns left-24..left)
        for i, x in enumerate(range(left - 24, left)):
            t = i / 24.0
            base[:, x] = np.round(col * (1 - t) + old[:, x] * t).astype(np.uint8)
        img = Image.fromarray(base, 'RGBA')
        lg = Image.open(LOGO2).convert('RGBA')
        lg = lg.resize((int(round(lg.width * NEW_K)), int(round(lg.height * NEW_K))), Image.LANCZOS)
        y = int(round((IN0 + IN1) / 2.0 - (NEW_L0 + NEW_L1) / 2.0 * NEW_K))
        img.alpha_composite(lg, (NEW_X, y))
        al = Image.new('L', img.size, 0)
        al.paste(lg.getchannel('A'), (NEW_X, y))
        _new_alpha = al
        _src = img
    return _src


def _src_bg_mask_new():
    """new logo: the bar's inside everywhere (rows IN0..IN1) except under the logo (its alpha, so its shadow blends)"""
    _logo()
    a = np.asarray(_new_alpha, np.float32) / 255.0
    m = np.zeros(a.shape, np.float32)
    m[IN0:IN1 + 1] = 1
    m = m * (1 - a)
    return Image.fromarray(np.round(m * 255).astype(np.uint8), 'L')


def recolour(img, accent):
    if accent is None:
        return img
    a = np.asarray(img, np.float32)
    rgb = a[..., :3]
    grey = np.maximum(rgb[..., 1], rgb[..., 2])
    red = np.clip(rgb[..., 0] - grey, 0, None)[..., None]
    out = grey[..., None] + red * (np.asarray(accent, np.float32) / 255.0)
    return Image.fromarray(np.dstack([np.clip(np.round(out), 0, 255), a[..., 3:]]).astype(np.uint8), 'RGBA')


def accent_grad(accent):
    """the name's gradient for an accent (as the picture's HEARTS: lighter top, deeper bottom)"""
    c = np.asarray(accent, np.float32)
    return tuple(c + (255 - c) * 0.3), tuple(c * 0.7)


def bar_picture(page_w, scale, name_w, accent=None, clear_loop=False):
    """the banner as one RGBA picture at source resolution, page_w / scale wide; name_w = page px the name needs"""
    src = _logo_clear() if clear_loop and not NEW_LOGO else _logo()
    total = int(round(page_w / scale))
    fill = max(10, int(round(name_w / scale)) + 40)
    cap = src.width - CAP0
    mid = total - LEFT - (FADE1 - MID1) - fill - cap
    rows = (0, TOP0, src.width, BOT0)
    out = Image.new('RGBA', (total, BOT0 - TOP0), (0, 0, 0, 0))
    out.paste(src.crop((0, TOP0, LEFT, BOT0)), (0, 0))
    x = LEFT
    out.paste(src.crop((LEFT, TOP0, MID1, BOT0)).resize((max(1, mid), BOT0 - TOP0), Image.LANCZOS), (x, 0)); x += mid
    out.paste(src.crop((MID1, TOP0, FADE1, BOT0)), (x, 0)); x += FADE1 - MID1
    out.paste(src.crop((FILL_COL, TOP0, FILL_COL + 1, BOT0)).resize((fill, BOT0 - TOP0)), (x, 0)); x += fill
    out.paste(src.crop((CAP0, TOP0, src.width, BOT0)), (x, 0))
    pic = recolour(out, accent)
    if NEW_LOGO and X_ACCENT is not None and _new_alpha is not None:
        # the logo (X, swoosh, CONSOLE) in its own colour: Theme Editor BANNER X- (2026-11-15); the bar keeps BANNER LINE
        a = np.zeros((out.height, out.width, 1), np.float32)
        al = np.asarray(_new_alpha.crop((0, TOP0, LEFT, BOT0)), np.float32) / 255.0
        a[:, :min(LEFT, out.width), 0] = al[:, :min(LEFT, out.width)]
        lx = np.asarray(recolour(out, X_ACCENT), np.float32)
        pic = Image.fromarray(np.round(np.asarray(pic, np.float32) * (1 - a) + lx * a).astype(np.uint8), 'RGBA')
    return pic


def draw_bar(mod, cv, name_w, scale, top, accent=None, clear_loop=False):
    """paste the bar; top = page y of the bar's top edge. Returns (bar top, bar bottom, right end x) in page px"""
    pic = bar_picture(mod.W, scale, name_w, accent, clear_loop)
    k = scale * mod.S
    pic = pic.resize((int(round(pic.width * k)), int(round(pic.height * k))), Image.LANCZOS)
    cv.rgba(pic, 0, top - (BAR0 - TOP0) * scale)
    return top, top + (BAR1 - BAR0) * scale, mod.W - (_logo().width - CAP0 + 10) * scale


def font(px):
    if px not in _fc:
        _fc[px] = ImageFont.truetype(FONT, int(round(px)))
    return _fc[px]


def text_w(t, px):
    return font(px).getlength(t)


def name_mask(mod, x, y, t, px, anchor='rm', stroke=0, blur=0):
    """slanted Arial Black, (x, y) = the anchor point of the upright text (y = the middle of the capitals)"""
    S = mod.S
    f = font(px * S)
    tw = f.getlength(t) / S
    x0 = x - (tw / 2 if anchor[0] == 'm' else tw if anchor[0] == 'r' else 0)
    m = Image.new('L', (mod.W * S, mod.H * S), 0)
    ImageDraw.Draw(m).text((x0 * S, y * S), t, font=f, fill=255, anchor='lm',
                           stroke_width=int(round(stroke * S)), stroke_fill=255)
    # slant about the text's middle line; shift left by half the lean so the anchor stays put
    m = m.transform(m.size, Image.AFFINE, (1, SLANT, -SLANT * y * S, 0, 1, 0), Image.BICUBIC)
    return mod.to_np(m, blur)


# ---------------------------------------------------------------- the bar's background (2026-11-12)
# Granite: "make the background of the banner match the background of the panels". bg_mask() is where the bar's own fill
# shows (inside the chrome edges, above the accent line): the black around the X / -CONSOLE and the whole brushed middle,
# fade and end; not the logo's letters, the X, the swoosh or the red glow.
IN0, IN1 = 327, 421          # source rows inside the bar (below the top chrome edge .. above the accent line)
_bgm = None


def _src_bg_mask():
    global _bgm
    if _bgm is None:
        a = np.asarray(_logo(), np.float32)
        rgb = a[..., :3]
        lum = rgb.mean(axis=2)
        red = np.clip(rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]), 0, None)
        dark = np.clip((70.0 - lum) / 50.0, 0, 1) * (1 - np.clip(red / 30.0, 0, 1))
        xs = np.arange(a.shape[1], dtype=np.float32)[None, :]
        right = np.clip((xs - 990.0) / 20.0, 0, 1)          # past -CONSOLE: all of it is background
        m = dark * (1 - right) + right
        rows = np.zeros(a.shape[0], np.float32)
        rows[IN0:IN1 + 1] = 1
        m = m * rows[:, None]
        _bgm = Image.fromarray(np.round(m * 255).astype(np.uint8), 'L')
    return _bgm


# keep > 0 (Hearts, 2026-11-12: "make the background of the banner match the background of the layer beneath it"): on a
# light fill the dark mask above also takes the letters' black outlines and leaves a grey strip after -CONSOLE, so the
# white letters vanish. Instead: letters = bright or red pixels left of x 990; background = everything farther than
# `keep` source px from them, so each letter keeps a thin band of its own dark outline and the rest takes the fill.
_bgk = {}
LROW0, LROW1 = 318, 441      # keep > 0: rows also filled left of the red line (see _src_bg_mask_keep)
LEXT0, LEXT1 = 430, 470


def _src_bg_mask_keep(keep):
    if keep not in _bgk:
        from PIL import ImageFilter
        a = np.asarray(_logo(), np.float32)
        rgb = a[..., :3]
        lum = rgb.mean(axis=2)
        red = np.clip(rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2]), 0, None)
        al = a[..., 3] / 255.0
        let = np.clip((lum - 110.0) / 40.0, 0, 1) * al
        # red counts only where it is bright (R > ~170): the swoosh and the X's red faces, not the dim red glow on the
        # black bar left of the X (Hearts 2026-11-12: "remnants of the original banner background on the left side of
        # the X"); red parts keep a thinner (2 px) dark edge than the white letters
        redl = np.clip((red - 20.0) / 30.0, 0, 1) * np.clip((rgb[..., 0] - 170.0) / 40.0, 0, 1) * al
        xs = np.arange(a.shape[1], dtype=np.float32)[None, :]
        right = np.clip((xs - 990.0) / 20.0, 0, 1)
        Lw = Image.fromarray(np.round(let * (1 - right) * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(2 * keep + 1))
        Lr = Image.fromarray(np.round(redl * (1 - right) * 255).astype(np.uint8), 'L').filter(ImageFilter.MaxFilter(5))
        L = Image.fromarray(np.maximum(np.asarray(Lw), np.asarray(Lr)), 'L').filter(ImageFilter.GaussianBlur(1.5))
        m = 1 - np.asarray(L, np.float32) / 255.0
        m = np.maximum(m, right)
        rows = np.zeros(a.shape[0], np.float32)
        rows[IN0:IN1 + 1] = 1
        # left of the red line's start (source x ~450, under the X) the picture has no red line or chrome trim: rows
        # 318..441 are solid black there, riding the swoosh (Hearts 2026-11-12, after c1286: "the black area is still on
        # the left side of the X, riding the swoosh"). There the fill also covers those rows (fade x 430..470).
        ext = np.zeros(a.shape[0], np.float32)
        ext[LROW0:LROW1 + 1] = 1
        lx = 1 - np.clip((xs - LEXT0) / float(LEXT1 - LEXT0), 0, 1)
        rows2 = np.maximum(rows[:, None], ext[:, None] * lx)
        m = m * rows2
        _bgk[keep] =Image.fromarray(np.round(m * 255).astype(np.uint8), 'L')
    return _bgk[keep]


# flood > 0 (Spades, 2026-11-14: "Make the background of the banner the same as the silver brushmetal finish background
# of the panels. Pay special attention to the X ... make sure not to leave any remnants of the current background"):
# the keep mask leaves black wedges in the X's concave corners (square dilation), a dark strip under the top chrome edge,
# the letters' drop shadows, the black inside the O's and the black band under the bottom trim. Instead the background
# is flood-filled: dark, un-red pixels in the bar (rows FR0..FR1, inside the outer grey edges) reached from known
# background (the bar's left end, the brushed middle, the bottom black band, and any deep black area such as the O
# counters). Dark faces closed in by the X's chrome edges are never reached, so the X keeps its shading. Everything
# past -CONSOLE between the trims is background. Then the filled area is shrunk by `flood` px (diamond, so no corner
# wedges): every shape keeps an even thin dark outline. The chrome / red trim lines stay.
FR0, FR1 = 317, 453
TRIM_RUN, XK, X_END = 150, 2, 360    # outline: trim lines = runs this long; X / swoosh outline XK px left of X_END
_bgf = {}


def _src_bg_mask_flood(k):
    if k not in _bgf:
        from PIL import ImageFilter
        a = np.asarray(_logo(), np.float32)
        rgb = a[..., :3] * a[..., 3:] / 255.0
        lum = rgb.mean(axis=2)
        red = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
        ys = np.arange(lum.shape[0])[:, None]
        xs = np.arange(lum.shape[1])[None, :]
        rows = (ys >= FR0) & (ys <= FR1)
        inner = (ys >= IN0) & (ys <= IN1 - 2)
        glow = (red > 15) & (rgb[..., 0] < 170) & (np.maximum(rgb[..., 1], rgb[..., 2]) < 60)   # the dim red glow
        P = ((lum < np.where(xs < 340, 45.0, 100.0)) | glow) & ~((red > 40) & (rgb[..., 0] > 150)) & rows   # passable: black (not the X's grey faces)
        P |= (xs >= 995) & inner                                            # past -CONSOLE: brushed fade -> fill
        P |= (xs >= 975) & (xs < 995) & inner & (lum < 160)                 # the fade's first light streaks
        seed = np.asarray(Image.fromarray(((lum < 18) & P).astype(np.uint8) * 255, 'L')
                          .filter(ImageFilter.MinFilter(17))) > 0              # deep black (O counters, big areas)
        seed[330:419, 0:30] = True; seed[330:419, 1000:1700] = True; seed[443:452, :] = True
        seed[317:320, :] = True; seed[433:436, :] = True        # the thin black bands between the trim lines (c1347)
        B = seed & P
        while True:                                                         # flood through passable pixels
            n = B.copy()
            n[1:] |= B[:-1]; n[:-1] |= B[1:]; n[:, 1:] |= B[:, :-1]; n[:, :-1] |= B[:, 1:]
            n &= P
            if (n == B).all():
                break
            B = n
        # outline (c1347, user on c1346: "there is still a remnant right here" on the X): only round the shapes, not
        # along the horizontal trim lines (runs of >= TRIM_RUN px), and only XK px round the X / swoosh (x < X_END),
        # so the narrow black channels between the X's arms and the swoosh take the fill too; k px round -CONSOLE
        NB = ~B
        line = np.zeros_like(NB)
        for y in range(NB.shape[0]):
            r = NB[y]
            if not r.any():
                continue
            d = np.diff(np.concatenate([[0], r.astype(np.int8), [0]]))
            for s, e in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):
                if e - s >= TRIM_RUN:
                    line[y, s:e] = True
        line[:FR0] = True; line[FR1 + 1:] = True
        O = NB & ~line
        for i in range(k):
            n = O.copy()
            n[1:] |= O[:-1]; n[:-1] |= O[1:]; n[:, 1:] |= O[:, :-1]; n[:, :-1] |= O[:, 1:]
            if i >= XK:
                n[:, :X_END] = O[:, :X_END]
            O = n
        B = B & ~O
        _bgf[k] = Image.fromarray(B.astype(np.uint8) * 255, 'L').filter(ImageFilter.GaussianBlur(1.2))
    return _bgf[k]


def bg_mask(mod, name_w, scale, top, keep=0, flood=0):
    """the bar background as a page mask at S scale (same layout as draw_bar); also returns the inner rows (page y)"""
    src = (_src_bg_mask_new() if NEW_LOGO else _src_bg_mask_flood(flood) if flood else _src_bg_mask_keep(keep) if keep
           else (_bgm or _src_bg_mask()))
    total = int(round(mod.W / scale))
    fill = max(10, int(round(name_w / scale)) + 40)
    cap = src.width - CAP0
    mid = total - LEFT - (FADE1 - MID1) - fill - cap
    out = Image.new('L', (total, BOT0 - TOP0), 0)
    out.paste(src.crop((0, TOP0, LEFT, BOT0)), (0, 0))
    x = LEFT
    out.paste(src.crop((LEFT, TOP0, MID1, BOT0)).resize((max(1, mid), BOT0 - TOP0), Image.LANCZOS), (x, 0)); x += mid
    out.paste(src.crop((MID1, TOP0, FADE1, BOT0)), (x, 0)); x += FADE1 - MID1
    out.paste(src.crop((FILL_COL, TOP0, FILL_COL + 1, BOT0)).resize((fill, BOT0 - TOP0)), (x, 0)); x += fill
    out.paste(src.crop((CAP0, TOP0, src.width, BOT0)), (x, 0))
    k = scale * mod.S
    out = out.resize((int(round(out.width * k)), int(round(out.height * k))), Image.LANCZOS)
    m = np.zeros((mod.H * mod.S, mod.W * mod.S), np.float32)
    Y = int(round((top - (BAR0 - TOP0) * scale) * mod.S))
    o = np.asarray(out, np.float32) / 255.0
    y0, y1 = max(0, Y), min(m.shape[0], Y + o.shape[0])
    w = min(m.shape[1], o.shape[1])
    m[y0:y1, :w] = o[y0 - Y:y1 - Y, :w]
    return m, top + (IN0 - BAR0) * scale, top + (IN1 - BAR0) * scale


# ---------------------------------------------------------------- the white inside the swoosh loop (2026-11-12)
# Granite: "the X in the banner has a small circular area of white at the top right corner ... make that white area
# transparent". It is the picture's white background, closed in by the swoosh loop (source x ~440..580, y ~286..314),
# so make_logo_rgba.py's cut-out never reached it. clear_loop: flood-fill from inside the loop over un-red, not-black
# pixels above the bar's chrome edge, then colour-to-alpha against white there (white -> clear, its grey shading ->
# see-through black, so the shadow stays).
LOOP_SEED = (530, 304)
LOOP_BOX = (430, 280, 590, 315)   # x0, y0, x1, y1 (y1 = above the bar's top chrome line)
_srcc = None


def _logo_clear():
    global _srcc
    if _srcc is None:
        a = np.asarray(_logo(), np.float32).copy()
        x0, y0, x1, y1 = LOOP_BOX
        sub = a[y0:y1, x0:x1]
        rgb = sub[..., :3]
        mn = rgb.min(axis=2)
        red = rgb[..., 0] - np.maximum(rgb[..., 1], rgb[..., 2])
        ok = (red < 25) & (mn > 40) & (sub[..., 3] > 200)
        reg = np.zeros(ok.shape, bool)
        st = [(LOOP_SEED[1] - y0, LOOP_SEED[0] - x0)]
        while st:
            y, x = st.pop()
            if 0 <= y < ok.shape[0] and 0 <= x < ok.shape[1] and ok[y, x] and not reg[y, x]:
                reg[y, x] = True
                st += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]
        # take in the 1-px anti-aliased rim too
        rim = reg.copy()
        rim[1:] |= reg[:-1]; rim[:-1] |= reg[1:]; rim[:, 1:] |= reg[:, :-1]; rim[:, :-1] |= reg[:, 1:]
        rim &= (red < 60)
        al = np.clip(1 - mn / 255.0, 0, 1)                       # white -> 0, black -> 1
        col = np.clip((rgb - 255 * (1 - al[..., None])) / np.maximum(al[..., None], 1e-3), 0, 255)
        sub[..., :3] = np.where(rim[..., None], col, rgb)
        sub[..., 3] = np.where(rim, sub[..., 3] * al, sub[..., 3])
        a[y0:y1, x0:x1] = sub
        # under the loop the bar's top edge rows (315, 316) are still the white background; elsewhere the cut-out left
        # them nearly clear: copy the edge from a plain column (900) where the loop was cleared and the pixel isn't red
        cols = np.nonzero(reg.any(axis=0))[0] + x0
        for y in (y1, y1 + 1):
            for x in cols:
                p = a[y, x]
                if p[0] - max(p[1], p[2]) < 25:
                    a[y, x] = a[y, 900]
        _srcc = Image.fromarray(np.round(a).astype(np.uint8), 'RGBA')
    return _srcc
