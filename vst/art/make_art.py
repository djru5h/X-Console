"""X-Console artwork that the layout can't draw itself: section ON buttons, the EQ screen backdrop and meter filmstrips.
Called by make_layout.py. Needs Pillow (the mpc-vst-html-art image has it)."""
import glob
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

BLUE = (63, 182, 232)
ORANGE = (240, 120, 40)
OFF = (38, 40, 46)


def _font(px):
    for pat in ("/mv/tools/html_art/fonts/TitilliumWeb-SemiBold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/**/*.ttf"):
        for f in glob.glob(pat, recursive=True):
            try:
                return ImageFont.truetype(f, px)
            except OSError:
                pass
    return ImageFont.load_default()


# the buttons' LED colours (btn_on_white.svg: HEARTS's EQ ON lights white, user 2026-11-03); user_theme.py adds its own
BTN_LEDS = {"btn_off.svg": "#20343e", "btn_on.svg": "#4fc3f7", "btn_on_white.svg": "#f6f7f8", "btn_on_red.svg": "#e0352b",
            "btn_on_lightbrown.svg": "#c89c72", "btn_on_gold.svg": "#e2b444", "btn_on_darkblue.svg": "#3a64d8", "btn_on_darkred.svg": "#b8282a"}


def _buttons(d):
    """Round dark push button, a blue LED in its face when on (the hardware's section ON buttons)."""
    for name, led in BTN_LEDS.items():
        _btn_svg(d, name, led)


def _btn_svg(d, name, led):
    if True:
        glow = ('<circle cx="28" cy="28" r="14" fill="%s" opacity="0.35" filter="url(#g)"/>' % led if name != "btn_off.svg" else "")
        open(os.path.join(d, name), "w").write(
            '<svg xmlns="http://www.w3.org/2000/svg" width="56" height="56" viewBox="0 0 56 56">'
            '<defs><radialGradient id="r" cx="40%" cy="35%" r="70%"><stop offset="0" stop-color="#4a4a52"/>'
            '<stop offset="1" stop-color="#1c1c20"/></radialGradient><filter id="g"><feGaussianBlur stdDeviation="3"/></filter></defs>'
            '<circle cx="28" cy="29" r="26" fill="#000" opacity="0.45"/>'
            '<circle cx="28" cy="28" r="25" fill="url(#r)" stroke="#0c0c0e" stroke-width="1.5"/>'
            + glow + '<circle cx="28" cy="28" r="5" fill="%s"/></svg>' % led)


def _eq_screen(d, size, name="eq_screen.svg", bg="#000000", grid="#21414f", label="#4f7d90", zero="#3a6a7e", minor="#1b3542", grid_only=False):
    """Backdrop of the EQ curve display: a dark screen with a frequency and gain grid (the live curve goes on top later)."""
    w, h = size
    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (w, h, w, h),
         '<rect x="0" y="0" width="%d" height="%d" rx="6" fill="%s" stroke="#000" stroke-width="2"/>' % (w, h, bg)]
    if grid_only:   # the grid and labels alone, drawn over a picture on the screen (the FLANNEL's #TOWN logo)
        s = s[:1]
    for f in (30, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
        x = w * math.log(f / 20) / math.log(1000)
        s.append('<line x1="%.1f" y1="4" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"/>' % (x, x, h - 4, grid))
        lab = "%dk" % (f // 1000) if f >= 1000 else str(f)
        s.append('<text x="%.1f" y="%d" font-size="11" fill="%s" text-anchor="middle" font-family="Titillium Web">%s</text>' % (x, h - 6, label, lab))
    for g in (-12, -6, 0, 6, 12):
        y = h / 2 - g * (h / 2 - 10) / 18
        s.append('<line x1="4" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (y, w - 4, y, zero if g == 0 else minor))
    s.append("</svg>")
    open(os.path.join(d, name), "w").write("".join(s))


EQ_LOGO_W, EQ_LOGO_ALPHA = 480, 0.05   # the #TOWN logo on the FLANNEL's EQ screen: width, opacity (user, 2026-11-03)


HEXX_LOGO_ALPHA = EQ_LOGO_ALPHA * 3.375   # HEXX's logos: 50% more visible each time (0.19.0 7.5%, 0.19.1 11.25%, 0.19.2 16.875%)


def _eq_logo(d, size, src_name="logo_town_eq_src.png", name="eq_logo.png", max_h=None, alpha=EQ_LOGO_ALPHA):
    """The user's #TOWN logo (art/logo_town_eq_src.png, PoundTown_TRANSPARENT.png) cropped to its drawing, EQ_LOGO_W wide,
    faded to EQ_LOGO_ALPHA, centred on a transparent canvas the size of the EQ screen."""
    if not os.path.exists(os.path.join(d, src_name)):
        return   # public repo: logo pictures are not included; drop your own in art/ to show one
    src = Image.open(os.path.join(d, src_name)).convert("RGBA")
    src = src.crop(src.getchannel("A").getbbox())
    w = EQ_LOGO_W
    h = round(src.height * w / src.width)
    if max_h and h > max_h:   # a squarer logo (MOCHA's UA): fit the height instead
        w, h = round(src.width * max_h / src.height), max_h
    lg = src.resize((w, h), Image.LANCZOS)
    lg.putalpha(lg.getchannel("A").point(lambda v: round(v * alpha)))
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.alpha_composite(lg, ((size[0] - w) // 2, (size[1] - h) // 2))
    out.save(os.path.join(d, name))


LED_BLUE = (BLUE, (235, 235, 240), ORANGE)                       # the meters' zones: under -9 dB, -9..0, 0 dBFS and up
LED_WHITE, LED_RED = (235, 235, 240), (226, 52, 40)
LED_GREEN, LED_YELLOW = (70, 200, 90), (240, 214, 52)
# gradients: [(dBFS, colour), ...], solid below the first stop and above the last, blended between (the segment's middle)
LED_HEARTS = [(-18.0, LED_WHITE), (0.0, LED_RED)]                         # HEARTS: white to -18, red from 0 (user, 2026-11-03)
LED_FLANNEL = [(-18.0, (47, 159, 208)), (-12.0, LED_WHITE), (0.0, LED_RED)]   # FLANNEL: blue, to white by -12, to red at 0 (user, 0.9.4)
LED_SUEDE = [(-18.0, (150, 170, 190)), (-6.0, LED_WHITE), (0.0, LED_RED)]   # SUEDE: blue-grey, white, red from 0
LED_SANDSTONE = [(-30.0, (212, 165, 55)), (-18.0, LED_WHITE), (0.0, LED_RED)]   # SANDSTONE: gold to -30, white by -18, red at 0 (user, 2026-11-04, 0.10.3)
LED_ORANGE = (240, 136, 36)
# HEXX (user, 2026-11-05, 0.19.0): blue -60..-24, white -18..-6, orange -6..0, red at 0, fading from one to the next (as
# MOCHA's: orange full by -3; was dark blue to -30, white by -18, red at 0)
# 0.19.1 (user): blue -60..-24, white -18..-12, pink -6..0, red at 0 (was white to -6, orange -6..0)
LED_PINK = (238, 98, 170)
# 0.19.2 (user): "identical to SPADES's except grey is replaced with blue": blue to -30, white by -18, red at 0
LED_HEXX = [(-30.0, (42, 82, 190)), (-18.0, LED_WHITE), (0.0, LED_RED)]
# MOLTEN (user, 2026-11-04, 0.12.4): white -60..-24, yellow -24..-12, orange -12..0, red from 0, fading from one to the next
# (my reading: each colour full by the middle of its zone; was dark red to -30, white by -18, red at 0)
LED_MOLTEN = [(-24.0, LED_WHITE), (-18.0, LED_YELLOW), (-12.0, LED_YELLOW), (-6.0, LED_ORANGE), (-1.0, LED_ORANGE), (0.0, LED_RED)]
# MOCHA (user, 2026-11-04, 0.14.2): green -60..-18, yellow -18..-6, orange -6..0, red at 0, fading from one to the next
# (as MOLTEN's: each colour full by the middle of its zone; light brown -> white -> red in 0.14.1)
LED_MOCHA = [(-18.0, LED_GREEN), (-12.0, LED_YELLOW), (-3.0, LED_ORANGE), (-1.0, LED_ORANGE), (0.0, LED_RED)]
LED_SPADES = [(-30.0, (120, 122, 128)), (-18.0, LED_WHITE), (0.0, LED_RED)]   # SPADES (0.13.1): grey to -30, white by -18, red at 0
LED_GRANITE = [(-12.0, LED_GREEN), (-6.0, LED_YELLOW), (0.0, LED_RED)]     # GRANITE EQ: green to -12, yellow, red from 0 (user)


def _led_col(k, n, cols):
    if isinstance(cols, list):   # a gradient, on the meter's -60..+6 dBFS scale
        db = -60.0 + (k + 0.5) * 66.0 / n
        if db <= cols[0][0]:
            return cols[0][1]
        for (d0, c0), (d1, c1) in zip(cols, cols[1:]):
            if db <= d1:
                t = (db - d0) / (d1 - d0)
                return tuple(round(a + (b - a) * t) for a, b in zip(c0, c1))
        return cols[-1][1]
    return cols[2] if k >= n - 3 else cols[1] if k >= n - 7 else cols[0]


def _led_bar(d, frames, name="led_bar.png", cols=LED_BLUE):
    """Vertical LED meter, 14 x 330 a frame: frame i lights i of (frames - 1) segments from the bottom."""
    w, h, n = 14, 330, frames - 1
    seg_h = h / n
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    dr = ImageDraw.Draw(strip)
    for fi in range(frames):
        for k in range(n):
            y1 = fi * h + h - (k + 1) * seg_h + 1.5
            col = _led_col(k, n, cols) if k < fi else OFF
            dr.rounded_rectangle([1, y1, w - 2, y1 + seg_h - 3], radius=2, fill=col)
    strip.save(os.path.join(d, name))


def _led_pk(d, frames, name="led_pk.png", cols=LED_BLUE):
    """PEAK HOLD over the LED meter, 14 x 330 a frame: frame i lights segment i - 1 (from the bottom) alone, in that
    segment's colour, where led_bar.png's frame i has its top lit one; frame 0 shows nothing."""
    w, h, n = 14, 330, frames - 1
    seg_h = h / n
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    dr = ImageDraw.Draw(strip)
    for fi in range(1, frames):
        k = fi - 1
        y1 = fi * h + h - (k + 1) * seg_h + 1.5
        dr.rounded_rectangle([1, y1, w - 2, y1 + seg_h - 3], radius=2, fill=_led_col(k, n, cols))
    strip.save(os.path.join(d, name))


def _sp_pk(d, w, h, levels, name, col):
    """PEAK HOLD on the spectrum: frame k = a 2 px dash at level k's height (the spectrum edge's), 1 px in from each
    side so the columns read as a dotted line; frame 0 shows nothing."""
    strip = Image.new("RGBA", (w, h * levels), (0, 0, 0, 0))
    dr = ImageDraw.Draw(strip)
    for k in range(1, levels):
        y = k * h + int(round(_sp_y(k, h, levels)))
        dr.rectangle([1, y - 1, w - 2, y], fill=col)
    strip.save(os.path.join(d, name))


def _gr_bar(d, frames):
    """Gate reduction, 40 x 300 a frame, lit from the top down."""
    w, h, n = 40, 300, frames - 1
    seg_h = h / n
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    dr = ImageDraw.Draw(strip)
    for fi in range(frames):
        for k in range(n):
            y1 = fi * h + k * seg_h + 1.5
            dr.rounded_rectangle([2, y1, w - 3, y1 + seg_h - 3], radius=3, fill=ORANGE if k < fi else OFF)
    strip.save(os.path.join(d, "gr_bar.png"))


def _vu(d, frames):
    """Gain-reduction VU on a dark screen: needle rests at 0 on the right and swings left to 20 dB. 360 x 200 a frame."""
    w, h, ss = 360, 200, 3
    W, H = w * ss, h * ss
    cx, cy, R = W / 2, H * 1.18, H * 0.95
    marks = (0, 1, 2, 3, 5, 7, 10, 15, 20)

    def ang(db):          # degrees from vertical, + to the right
        return 42 - 84 * math.sqrt(db / 20.0)
    face = Image.new("RGBA", (W, H), (11, 13, 17, 255))
    dr = ImageDraw.Draw(face)
    dr.rounded_rectangle([0, 0, W - 1, H - 1], radius=10 * ss, outline=(0, 0, 0, 255), width=3 * ss)
    # scale band: blue, orange past 10 dB
    for a0, a1, col in ((ang(10), ang(0), BLUE), (ang(20), ang(10), ORANGE)):
        bb = [cx - R, cy - R, cx + R, cy + R]
        dr.arc(bb, start=-90 + a0, end=-90 + a1, fill=col + (255,), width=10 * ss)
    font = _font(15 * ss)
    for db in marks:
        th = math.radians(ang(db))
        x0, y0 = cx + (R - 6 * ss) * math.sin(th), cy - (R - 6 * ss) * math.cos(th)
        x1, y1 = cx + (R + 12 * ss) * math.sin(th), cy - (R + 12 * ss) * math.cos(th)
        dr.line([x0, y0, x1, y1], fill=(235, 235, 240, 255), width=2 * ss)
        tx, ty = cx + (R + 30 * ss) * math.sin(th), cy - (R + 30 * ss) * math.cos(th)
        dr.text((tx, ty), str(db), font=font, fill=(235, 235, 240, 255), anchor="mm")
    dr.text((W / 2, H * 0.62), "GR  dB", font=_font(14 * ss), fill=(150, 160, 175, 255), anchor="mm")
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    for fi in range(frames):
        im = face.copy()
        di = ImageDraw.Draw(im)
        th = math.radians(ang(20.0 * fi / (frames - 1)))
        di.line([cx + R * 0.30 * math.sin(th), cy - R * 0.30 * math.cos(th), cx + (R + 4 * ss) * math.sin(th), cy - (R + 4 * ss) * math.cos(th)],
                fill=(255, 255, 255, 255), width=3 * ss)
        strip.paste(im.resize((w, h), Image.LANCZOS), (0, fi * h))
    strip.save(os.path.join(d, "vu.png"))


def _bar(d, size):
    """The preset bar: a plain panel box (a titled frame would draw its title rule through the drop-down)."""
    w, h = size
    open(os.path.join(d, "preset_bar.svg"), "w").write(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        '<rect x="1" y="1" width="%d" height="%d" rx="4" fill="#323137" stroke="#8c8b93" stroke-width="1.2"/></svg>'
        % (w, h, w, h, w - 2, h - 2))


def _eq_col(d, w, h, frames, name="eq_col.png", line=(127, 214, 255, 255), fill=(63, 182, 232, 45)):
    """One column of the live EQ curve: frame k is (k - (frames-1)/2) dB, -18..+18. A see-through fill from the 0 dB line
    to the level and a bright cap, so 44 columns side by side read as the curve over the screen's grid."""
    half = (frames - 1) // 2
    ss = 4
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    for k in range(frames):
        db = k - half
        im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
        dr = ImageDraw.Draw(im)
        y0 = h * ss / 2
        y = y0 - db * (h * ss / 2 - 6 * ss) / 18.0
        top, bot = min(y, y0), max(y, y0)
        if bot - top > 1:
            dr.rectangle([0, top, w * ss, bot], fill=fill)
        dr.rectangle([0, y - 1.5 * ss, w * ss, y + 1.5 * ss], fill=line)
        strip.paste(im.resize((w, h), Image.LANCZOS), (0, k * h))
    strip.save(os.path.join(d, name))


SP_FILL, SP_EDGE, SP_FILL_ALPHA = (70, 190, 104), (160, 244, 170), 70   # YES-SL 9000's spectrum: see-through green, light edge
JOIN_W = 2                                                              # the join's width, in the column's last pixels


def _sp_y(k, h, levels):
    """the edge's centre for level k (0 = the floor, along the bottom; levels-1 = 0 dBFS, at the top)"""
    return (h - 3) - k / (levels - 1) * (h - 6)


def _sp_level(w, h, k, levels, fill=None, edge=None):
    """a see-through green fill up from the bottom with a 3 px light edge on it (level 0: the edge alone, at the bottom)"""
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    y = int(round(_sp_y(k, h, levels)))
    if k > 0:
        dr.rectangle([0, y, w - 1, h - 1], fill=fill or (SP_FILL + (SP_FILL_ALPHA,)))
    dr.rectangle([0, y - 1, w - 1, y + 1], fill=edge or (SP_EDGE + (255,)))
    return im


def _sp_col(d, w, h, levels, name="sp_col.png", fill=None, edge=None):
    """Gen1 spectrum column: frame k = level k."""
    strip = Image.new("RGBA", (w, h * levels), (0, 0, 0, 0))
    for k in range(levels):
        strip.paste(_sp_level(w, h, k, levels, fill, edge), (0, k * h))
    strip.save(os.path.join(d, name))


def _sp_sloped(w, h, k, k2, levels, fcol=None, ecol=None):
    """one Gen2 spectrum frame: a straight edge from level k at the column's left side to level k2 at its right side (the
    right neighbour's level), the see-through fill under it. The neighbour starts at k2, so the columns join into one
    sloped outline. Drawn 4x and scaled down, so the slant is smooth. fcol / ecol: fill and edge colours (default green)."""
    ss = 4
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ya, yb = _sp_y(k, h, levels) * ss, _sp_y(k2, h, levels) * ss
    if k > 0 or k2 > 0:
        ImageDraw.Draw(im).polygon([(0, ya), (w * ss, yb), (w * ss, h * ss), (0, h * ss)], fill=fcol or (SP_FILL + (SP_FILL_ALPHA,)))
    edge = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    # the edge runs a little past both sides, so neighbouring columns overlap at the joint instead of leaving a notch
    ImageDraw.Draw(edge).line([(-ss, ya - (yb - ya) / w), (w * ss + ss, yb + (yb - ya) / w)], fill=ecol or (SP_EDGE + (255,)), width=3 * ss)
    im.alpha_composite(edge)
    return im.resize((w, h), Image.LANCZOS)


def _sp_join(d, w, h, levels, join, tiles, name="sp_join", fill=None, edge=None):
    """Gen2 spectrum column: frame = level x (2 join + 1) + (dj + join), drawn as a sloped edge from the level to the right
    neighbour's level (k + dj, clamped to +-join), so the columns read as one outline (user, 2026-11-03: option 2 of the
    sloped mock). Cut into `tiles` strips of h / tiles px each (sp_join_t0.png at the top), each under Gen2's ~56,000 px."""
    n = 2 * join + 1
    th = h // tiles
    tstrips = [Image.new("RGBA", (w, th * levels * n), (0, 0, 0, 0)) for _ in range(tiles)]
    for k in range(levels):
        for j in range(n):
            k2 = min(max(k + j - join, 0), levels - 1)
            im = _sp_sloped(w, h, k, k2, levels, fill, edge)
            for t in range(tiles):
                tstrips[t].paste(im.crop((0, t * th, w, t * th + th)), (0, (k * n + j) * th))
    for t in range(tiles):
        tstrips[t].save(os.path.join(d, "%s_t%d.png" % (name, t)))


EQ_LINE, EQ_FILL = (127, 214, 255, 255), (63, 182, 232, 45)   # the curve's line and its see-through fill to the 0 dB line


def _eq_y(k, h, frames):
    """the curve's line for level k (k - (frames-1)/2 dB, -18..+18) at 4x"""
    half = (frames - 1) // 2
    return (h / 2 - (k - half) * (h / 2 - 6) / 18.0) * 4


def _eq_sloped(w, h, k, k2, frames, eline=None, efill=None):
    """one Gen2 curve frame: a straight 3 px line from level k at the column's left side to level k2 at its right side, the
    fill between it and the 0 dB line pixel column by pixel column (so a crossing through 0 dB fills both triangles)."""
    ss = 4
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    ya, yb, y0 = _eq_y(k, h, frames), _eq_y(k2, h, frames), h * ss / 2
    for x in range(w * ss):
        y = ya + (yb - ya) * (x + 0.5) / (w * ss)
        if abs(y - y0) > 1:
            dr.line([(x, min(y, y0)), (x, max(y, y0))], fill=efill or EQ_FILL)
    line = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(line).line([(-ss, ya - (yb - ya) / w), (w * ss + ss, yb + (yb - ya) / w)], fill=eline or EQ_LINE, width=3 * ss)
    im.alpha_composite(line)
    return im.resize((w, h), Image.LANCZOS)


def _eq_join(d, w, h, frames, join, tiles, name="eq_join", eline=None, efill=None):
    """Gen2 curve column: frame = level x (2 join + 1) + (dj + join), sloped to the right neighbour's level (k + dj,
    clamped to +-join), cut into `tiles` strips of h / tiles px (eq_join_t0.png at the top)."""
    n = 2 * join + 1
    th = h // tiles
    tstrips = [Image.new("RGBA", (w, th * frames * n), (0, 0, 0, 0)) for _ in range(tiles)]
    for k in range(frames):
        for j in range(n):
            im = _eq_sloped(w, h, k, min(max(k + j - join, 0), frames - 1), frames, eline, efill)
            for t in range(tiles):
                tstrips[t].paste(im.crop((0, t * th, w, t * th + th)), (0, (k * n + j) * th))
    for t in range(tiles):
        tstrips[t].save(os.path.join(d, "%s_t%d.png" % (name, t)))


BAR_FILL, BAR_EDGE = (70, 210, 120, 95), (120, 240, 160, 200)   # the 0.2.0 bars: a see-through green bar, a lighter top
KNOB_BROWN_TOP, KNOB_BROWN_MID = (156, 112, 76), (124, 87, 58)   # the brown knob cap's own shades (YES-SL 9000's "brown")
BROWN_FILL, BROWN_EDGE = KNOB_BROWN_MID + (150,), KNOB_BROWN_TOP + (255,)   # the GRANITE's spectrum line: the knobs' brown (user, 2026-11-03)
BROWN_BAR, BROWN_TOP = KNOB_BROWN_MID + (170,), KNOB_BROWN_TOP + (255,)     # and its bars
HEARTS_RED = (214, 64, 48)                                                  # the red of Weiss's logo swoosh
HEARTS_FILL, HEARTS_EDGE = HEARTS_RED + (120,), (250, 132, 112, 255)          # HEARTS's spectrum line
HEARTS_BAR, HEARTS_TOP = HEARTS_RED + (150,), (250, 142, 122, 255)            # and its bars
HEARTS_PK = (250, 214, 204, 235)                                            # its held peaks
BLUE_FILL, BLUE_EDGE = (47, 159, 208, 110), (127, 214, 255, 255)   # the FLANNEL's spectrum, blue (user, 2026-11-04, 0.9.4)
BLUE_BAR, BLUE_TOP = (47, 159, 208, 150), (140, 214, 250, 255)
SUEDE_FILL, SUEDE_EDGE = (122, 146, 168, 120), (196, 214, 230, 255)   # SUEDE (0.9.0): a blue-grey spectrum line
SUEDE_BAR, SUEDE_TOP = (122, 146, 168, 150), (206, 222, 236, 255)    # its bars
SUEDE_PK = (236, 96, 82, 235)                                       # its held peaks, red
SUEDE_SCREEN = dict(bg="#000000", grid="#2a3a47", label="#8193a3", zero="#4a5f70", minor="#1b2730")
GOLD_FILL, GOLD_EDGE = (200, 160, 64, 115), (244, 214, 130, 255)   # SANDSTONE (0.10.0): a gold spectrum line
GOLD_BAR, GOLD_TOP = (200, 160, 64, 150), (248, 222, 146, 255)    # its bars
GOLD_PK = (252, 236, 186, 235)                                    # its held peaks, pale gold
GOLD_SCREEN = dict(bg="#000000", grid="#3a3120", label="#a38c5c", zero="#5e4e2c", minor="#231e13")
HEXX_FILL, HEXX_EDGE = (42, 82, 190, 120), (120, 156, 240, 255)   # HEXX (0.11.0): a dark blue spectrum line
HEXX_BAR, HEXX_TOP = (42, 82, 190, 150), (130, 164, 244, 255)     # its bars
HEXX_PK = (60, 128, 255, 240)                                    # its held peaks, blue (user, 2026-11-05, 0.19.0; white before)
HEXX_SCREEN = dict(bg="#000000", grid="#1e2c52", label="#6f86bc", zero="#34497e", minor="#141d38")
LA_FILL, LA_EDGE = (200, 156, 114, 120), (230, 196, 156, 255)  # MOCHA (0.14.1, light brown theme): a light brown spectrum
LA_BAR, LA_TOP = (200, 156, 114, 150), (236, 206, 170, 255)   # its bars
LA_PK = (244, 238, 228, 235)                                  # its held peaks, white
LA_SCREEN = dict(bg="#000000", grid="#3a2c20", label="#b89c80", zero="#5a4430", minor="#1e1710")
AV_FILL, AV_EDGE = (150, 152, 158, 110), (236, 238, 242, 255)  # SPADES (0.13.1, black theme): a white spectrum line, grey fill
AV_BAR, AV_TOP = (150, 152, 158, 140), (240, 242, 246, 255)   # its bars
AV_PK = (226, 52, 40, 235)                                    # its held peaks, red
AV_SCREEN = dict(bg="#000000", grid="#1e1e20", label="#9a9aa0", zero="#3a3a3e", minor="#101011")
CH_FILL, CH_EDGE = (163, 32, 32, 120), (232, 104, 98, 255)   # MOLTEN (0.12.0): a dark red spectrum line
CH_BAR, CH_TOP = (163, 32, 32, 150), (238, 116, 108, 255)     # its bars
CH_PK = (240, 236, 234, 235)                                  # its held peaks, white
CH_SCREEN = dict(bg="#000000", grid="#44191c", label="#b27c7e", zero="#6a2a2e", minor="#24100f")
HEARTS_SCREEN = dict(bg="#000000", grid="#2b2e33", label="#80868e", zero="#4a4f56", minor="#1c1e22")   # a neutral dark screen


def _sp_bar_pic(w, h, k, levels, fill=None, top=None):
    """one spectrum bar for level k: 1 px gaps either side, filled up from the bottom, a 2 px top; level 0 is empty"""
    ss = 4
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    if k > 0:
        dr = ImageDraw.Draw(im)
        y = (h - 2) * ss - k / (levels - 1) * (h - 6) * ss
        dr.rectangle([1 * ss, y, (w - 1) * ss, (h - 2) * ss], fill=fill or BAR_FILL)
        dr.rectangle([1 * ss, y, (w - 1) * ss, y + 2 * ss], fill=top or BAR_EDGE)
    return im.resize((w, h), Image.LANCZOS)


def _sp_bars(d, w, h, levels, join, tiles, suffix="", fill=None, top=None):
    """the bars for both builds, frame for frame with the line's strips: Gen1 sp_bar1.png (frame = level), Gen2
    sp_bars_t*.png (frame = level x (2 join + 1) + join + j: the join is ignored, so the same values draw bars)"""
    one = Image.new("RGBA", (w, h * levels), (0, 0, 0, 0))
    pics = [_sp_bar_pic(w, h, k, levels, fill, top) for k in range(levels)]
    for k in range(levels):
        one.paste(pics[k], (0, k * h))
    one.save(os.path.join(d, "sp_bar1%s.png" % suffix))
    n, th = 2 * join + 1, h // tiles
    for t in range(tiles):
        strip = Image.new("RGBA", (w, th * levels * n), (0, 0, 0, 0))
        for k in range(levels):
            tile = pics[k].crop((0, t * th, w, t * th + th))
            for j in range(n):
                strip.paste(tile, (0, (k * n + j) * th))
        strip.save(os.path.join(d, "sp_bars%s_t%d.png" % (suffix, t)))


# SSL-style knob caps, drawn as YES-SL 9000's make_art.py draws them (same function and colours, so the brown is the
# same picture), plus light blue: face top, face bottom, pointer
CAPS = {
    "black": ((70, 72, 76), (28, 29, 32), (240, 240, 236)),
    "blue": ((84, 128, 196), (38, 70, 128), (245, 245, 240)),
    "lightblue": ((150, 200, 240), (78, 140, 200), (245, 245, 240)),
    "lightbluegrey": ((150, 200, 240), (78, 140, 200), (96, 98, 102)),
    "lightblueblack": ((150, 200, 240), (78, 140, 200), (30, 30, 30)),   # light blue, black pointer (HEXX INPUT, FREQs, WET/DRY, 0.11.2)
    "blacklightblue": ((70, 72, 76), (28, 29, 32), (150, 200, 240)),     # black, light blue pointer (HEXX LOW CUT, S/C HPF, 0.11.2)   # light blue with a grey pointer (ATTACK, RATIO, RELEASE, FLANNEL)
    "darkblue": ((52, 78, 140), (22, 36, 82), (245, 245, 240)),
    "darkgreen": ((54, 108, 68), (20, 58, 32), (245, 245, 240)),
    "green": ((86, 160, 104), (36, 94, 56), (245, 245, 240)),
    "lightgreen": ((156, 216, 168), (84, 156, 104), (245, 245, 240)),   # as light blue (HOLD, RELEASE, FLANNEL)
    "red": ((214, 86, 72), (140, 38, 32), (245, 245, 240)),
    "grey": ((206, 206, 200), (138, 138, 134), (30, 30, 30)),
    "darkgrey": ((118, 120, 124), (66, 68, 72), (245, 245, 240)),   # YES-SL 9000's (LF FREQ, FLANNEL)
    "greygreen": ((206, 206, 200), (138, 138, 134), (40, 150, 70)),   # the grey cap with a green pointer (EXP RATIO, GRANITE)
    "greybrown": ((206, 206, 200), (138, 138, 134), (124, 82, 50)),   # the grey cap with a brown pointer (SUSTAIN, GRANITE)
    "greyblue": ((206, 206, 200), (138, 138, 134), (56, 96, 186)),    # the grey cap with a blue pointer (LMF Q, GRANITE)
    "greypink": ((206, 206, 200), (138, 138, 134), (222, 92, 150)),   # the grey cap with a pink pointer (ATTACK, RATIO, RELEASE, GRANITE)
    "lightbrown": ((200, 156, 114), (146, 104, 70), (245, 240, 230)),
    "tanbrown": ((226, 204, 166), (176, 148, 108), (112, 74, 44)),    # tan with a brown pointer (WET/DRY, GRANITE)
    "tanblack": ((226, 204, 166), (176, 148, 108), (30, 30, 30)),     # tan with a black pointer (WET/DRY, FLANNEL)
    "darkbrown": ((112, 78, 52), (58, 38, 24), (245, 240, 230)),
    "darkpink": ((196, 84, 136), (118, 34, 74), (245, 245, 240)),
    "white": ((242, 240, 232), (186, 184, 176), (200, 40, 32)),
    "whiteblack": ((242, 240, 232), (186, 184, 176), (24, 24, 26)),   # Empirical Labs (0.16.0): white, black pointer
    "brown": ((156, 112, 76), (94, 62, 40), (245, 240, 230)),
    "pink": ((240, 140, 180), (176, 66, 112), (245, 245, 240)),
    "bluegrey": ((150, 168, 186), (78, 96, 116), (245, 245, 240)),   # SUEDE (0.9.0)
    "gold": ((232, 196, 104), (156, 116, 40), (24, 22, 18)),         # SANDSTONE (0.10.0): gold, black pointer
    "blackgold": ((70, 72, 76), (28, 29, 32), (226, 184, 82)),       # SANDSTONE extras: black, gold pointer
    "whitegold": ((242, 240, 232), (186, 184, 176), (196, 148, 40)),  # SANDSTONE EQ FREQ: white, gold pointer (0.10.5)
    "darkred": ((150, 42, 40), (82, 18, 18), (245, 245, 240)),        # MOLTEN (0.12.0): dark red, white pointer
    # MOLTEN, the user's list (2026-11-04, 0.12.4); light red = (236, 112, 104) (my shade)
    "greyred": ((206, 206, 200), (138, 138, 134), (206, 36, 30)),     # light grey, red pointer (INPUT)
    "whitedarkred": ((242, 240, 232), (186, 184, 176), (150, 30, 30)),  # white, dark red pointer (COLOR, SUSTAIN, EXP RATIO, WET/DRY)
    "blacklightred": ((70, 72, 76), (28, 29, 32), (236, 112, 104)),   # black, light red pointer (LOW CUT, S/C HPF)
    "lightred": ((236, 112, 104), (178, 62, 56), (245, 245, 240)),    # light red, white pointer (FREQs, COMPRESSION)
    # MOCHA, the user's list (2026-11-04, 0.14.2)
    "blacklightbrown": ((70, 72, 76), (28, 29, 32), (200, 156, 114)),     # black, light brown pointer (LOW CUT, S/C HPF)
    "whitedarkbrown": ((242, 240, 232), (186, 184, 176), (100, 66, 40)),  # white, dark brown pointer (Qs, COMPRESSION)
}


def _cap(size, top, bot, pointer):
    ss = 4
    s = size * ss
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.ellipse([s * .07, s * .10, s * .95, s * .98], fill=(0, 0, 0, 110))                  # drop shadow
    d.ellipse([s * .04, s * .04, s * .96, s * .96], fill=(18, 18, 20, 255))               # skirt
    r0 = s * .40
    for i in range(int(2 * r0)):                                                         # face, lit from above
        t = i / (2 * r0)
        c = tuple(round(a + (b - a) * t) for a, b in zip(top, bot)) + (255,)
        y = s / 2 - r0 + i
        dx = math.sqrt(max(0.0, r0 * r0 - (y - s / 2) ** 2))
        d.line([(s / 2 - dx, y), (s / 2 + dx, y)], fill=c)
    d.ellipse([s / 2 - r0, s / 2 - r0, s / 2 + r0, s / 2 + r0], outline=(0, 0, 0, 120), width=ss)
    d.line([(s / 2, s * .13), (s / 2, s * .42)], fill=pointer + (255,), width=int(s * .055))   # pointer, up
    return im.resize((size, size), Image.LANCZOS)


def _grad(s, top, bot):
    g = Image.new("RGBA", (s, s))
    d = ImageDraw.Draw(g)
    for y in range(s):
        t = y / (s - 1)
        d.line([(0, y), (s, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    return g


def _shade(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c)


def _molten(size, top, bot):
    ss = 4
    s = size * ss
    c = s / 2
    L = lambda: Image.new("L", (s, s), 0)

    def skirt(d, g=0):          # the lower round skirt plus the arrow tongue
        r = s * .305 + g
        d.ellipse([c - r, c - r, c + r, c + r], fill=255)
        hw = s * .15 + g
        d.polygon([(c, s * .025 - g), (c + hw, s * .30), (c - hw, s * .30)], fill=255)

    def tail(d, g=0):           # the raised square tail bar, opposite the arrow
        hw = s * .175 + g
        d.rounded_rectangle([c - hw, c, c + hw, s * .955 + g], radius=s * .035, fill=255)

    def body(d, g=0):           # the fluted round body: 10 shallow flutes
        pts = []
        R = s * .275 + g
        for i in range(360):
            th = math.radians(i)
            fl = abs(math.cos(6 * th))
            r = R * (1 - .07 * (1 - fl) ** 4)
            pts.append((c + r * math.sin(th), c - r * math.cos(th)))
        d.polygon(pts, fill=255)

    def mask(*fns, g=0):
        m = L()
        d = ImageDraw.Draw(m)
        for f in fns:
            f(d, g)
        return m

    m_sk, m_tail, m_body = mask(skirt), mask(tail), mask(body)
    m_top = ImageChops.lighter(m_tail, m_body)
    m_all = ImageChops.lighter(m_sk, m_top)

    out = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    # soft shadow, centred so it turns with the cap
    sh = mask(skirt, tail, body, g=ss * 1.5).filter(ImageFilter.GaussianBlur(ss * 2.5)).point(lambda v: v * 150 // 255)
    out.paste((0, 0, 0, 255), (0, 0), sh)

    # skirt and arrow: the same plastic, a little darker (lower, less lit)
    out.paste(_grad(s, _shade(top, .78), _shade(bot, .78)), (0, 0), m_sk)
    # white V inlay along the arrow's edges, open towards the body
    v = L()
    vd = ImageDraw.Draw(v)
    w = int(s * .022)
    a, b1, b2 = (c, s * .075), (c + s * .105, s * .27), (c - s * .105, s * .27)
    vd.line([b2, a, b1], fill=255, width=w, joint="curve")
    out.paste((236, 236, 232, 255), (0, 0), v)

    # the raised top's shadow on the skirt
    tsh = ImageChops.multiply(mask(tail, body, g=ss).filter(ImageFilter.GaussianBlur(ss * 2)), m_sk).point(lambda x: x * 140 // 255)
    out.paste((0, 0, 0, 255), (0, 0), tsh)

    # the raised top (body + tail): lit from above
    out.paste(_grad(s, top, bot), (0, 0), m_top)
    # flute edges: darken the body's rim slightly
    rim = ImageChops.subtract(m_body, m_body.filter(ImageFilter.MinFilter(9))).filter(ImageFilter.GaussianBlur(ss))
    out.paste((0, 0, 0, 255), (0, 0), rim.point(lambda x: x * 90 // 255))
    # the round top: a soft ring and a centre dot, as on the photo
    ring = L()
    rd = ImageDraw.Draw(ring)
    r1, r2 = s * .145, s * .075
    rd.ellipse([c - r1, c - r1, c + r1, c + r1], outline=255, width=int(ss * 1.6))
    rd.ellipse([c - r2, c - r2, c + r2, c + r2], outline=255, width=int(ss * 1.3))
    ring = ring.filter(ImageFilter.GaussianBlur(ss * .6))
    out.paste((0, 0, 0, 255), (0, 0), ring.point(lambda x: x * 110 // 255))
    hl = L()
    hd = ImageDraw.Draw(hl)
    hd.arc([c - r1 - ss * 1.5, c - r1 - ss * 1.5, c + r1 + ss * 1.5, c + r1 + ss * 1.5], 200, 340, fill=255, width=int(ss * 1.2))
    out.paste((255, 255, 255, 255), (0, 0), hl.filter(ImageFilter.GaussianBlur(ss * .7)).point(lambda x: x * 70 // 255))
    # sheen on the upper body
    sheen = L()
    ImageDraw.Draw(sheen).ellipse([c - s * .17, c - s * .25, c + s * .17, c - s * .05], fill=255)
    sheen = ImageChops.multiply(sheen.filter(ImageFilter.GaussianBlur(ss * 5)), m_top).point(lambda x: x * 45 // 255)
    out.paste((255, 255, 255, 255), (0, 0), sheen)

    # outlines
    for m, al in ((m_all, 170), (m_top, 120)):
        e = ImageChops.subtract(m.filter(ImageFilter.MaxFilter(5)), m).point(lambda x, al=al: x * al // 255)
        out.paste((0, 0, 0, 255), (0, 0), e)
    return out.resize((size, size), Image.LANCZOS)


# MOLTEN (user, 2026-11-05, 0.14.3): chicken-heads after the user's photo (assets/MOLTEN KNOBS.webp): (top, bottom);
# the white V on the arrow is the pointer
MOLTEN_CAPS = {
    "chblack": ((62, 63, 66), (22, 22, 24)),
    "chred": ((236, 52, 44), (170, 18, 18)),
    "chgrey": ((96, 108, 106), (50, 58, 58)),
}


def _caps(d):
    for name, (top, bot, ptr) in CAPS.items():
        _cap(86, top, bot, ptr).save(os.path.join(d, "knob_%s.png" % name))
    for name, (top, bot) in MOLTEN_CAPS.items():
        _molten(86, top, bot).save(os.path.join(d, "knob_%s.png" % name))


# the transfer curves' looks (0.8.3): curve / meter colour and screen (bg, grid, diagonal) per preset
TC_COL = {"flannel": (127, 214, 255), "granite": (200, 156, 114), "hearts": (224, 53, 43), "suede": (176, 198, 216), "sandstone": (226, 184, 82), "hexx": (84, 124, 230), "molten": (204, 58, 52), "spades": (226, 228, 232), "mocha": (200, 156, 114)}
# 0.17.1 (user): every EQ screen and transfer-curve screen background black; grids, labels and logos unchanged
TC_SCREEN = {"flannel": ("#000000", "#21414f", "#4f7d90"), "granite": ("#000000", "#2a2a2a", "#5a5a5a"),
             "hearts": ("#000000", "#2b2e33", "#6a7078"), "suede": ("#000000", "#2a3a47", "#6a7f90"), "sandstone": ("#000000", "#3a3120", "#7c6a42"), "hexx": ("#000000", "#1e2c52", "#4a6094"), "molten": ("#000000", "#44191c", "#8c4448"), "spades": ("#000000", "#1e1e20", "#5a5a5e"), "mocha": ("#000000", "#3a2c20", "#8c7058")}


def _tc_sloped(w, h, k, k2, frames, line, fill):
    """one Gen2 transfer-curve frame (0.8.2): an anti-aliased 2 px line from level k at the column's left to level k2 at its
    right (the neighbour's), a faint fill under it; drawn 4x and scaled down"""
    ss = 4
    yk = lambda v: ((h - 2) - v / (frames - 1) * (h - 4)) * ss
    ya, yb = yk(k), yk(k2)
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(im).polygon([(0, ya), (w * ss, yb), (w * ss, h * ss), (0, h * ss)], fill=fill)
    ln = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    ImageDraw.Draw(ln).line([(0, ya), (w * ss, yb)], fill=line, width=2 * ss)   # exact segment, no edge extrapolation (user 2026-11-08: the line overshot the knee)
    im.alpha_composite(ln)
    return im.resize((w, h), Image.LANCZOS)


def write_tc(d, w, h, shp_frames, gr_frames, tiles, gw, bh, steps, sets):
    """The transfer-curve art, per look (0.8.0 the GRANITE's, 0.8.3 every preset's): for each (look, top, levels, jtiles):
    tc_col_<look>_t*.png (Gen1: frame k = output -60 + k dBFS, a faint fill and a 3 px edge), tc_join_<look>_t*.png (Gen2:
    frame = level x len(steps) + join, a smooth line to the neighbour), tc_screen_<look>.svg (grid every 20 dB, the 1:1
    diagonal; output up to `top`); per colour shape_bar_<c>.png (centre-zero, -20..+20 dB) and gr_bar20_<c>.png (0..-20 dB,
    top down)."""
    for look, top, frames, jtiles in sets:
        c = look.split("_")[0]
        line, fill = TC_COL[c] + (255,), TC_COL[c] + (90,)
        th = h // tiles
        tstrips = [Image.new("RGBA", (w, th * frames), (0, 0, 0, 0)) for _ in range(tiles)]
        for k in range(frames):
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            dr = ImageDraw.Draw(im)
            y = round((h - 2) - k / (frames - 1) * (h - 4))
            dr.rectangle([0, y, w - 1, h - 1], fill=fill)
            dr.rectangle([0, y - 1, w - 1, min(y + 3, h - 1)], fill=line)
            for t in range(tiles):
                tstrips[t].paste(im.crop((0, t * th, w, t * th + th)), (0, k * th))
        for t in range(tiles):
            tstrips[t].save(os.path.join(d, "tc_col_%s_t%d.png" % (look, t)))
        nj, jth = len(steps), h // jtiles
        jstrips = [Image.new("RGBA", (w, jth * frames * nj), (0, 0, 0, 0)) for _ in range(jtiles)]
        for k in range(frames):
            for j, st in enumerate(steps):
                im = _tc_sloped(w, h, k, k + st, frames, line, fill)
                for t in range(jtiles):
                    jstrips[t].paste(im.crop((0, t * jth, w, t * jth + jth)), (0, (k * nj + j) * jth))
        for t in range(jtiles):
            jstrips[t].save(os.path.join(d, "tc_join_%s_t%d.png" % (look, t)))
        bg, grid, diag = TC_SCREEN[c]
        ydb = lambda db: (top - db) / (60.0 + top) * h       # output dBFS -> y
        sv = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (gw, h, gw, h),
              '<rect x="0" y="0" width="%d" height="%d" fill="%s" stroke="#4a4a4a" stroke-width="2"/>' % (gw, h, bg)]
        for db in (-20, -40):
            sv.append('<line x1="%g" y1="2" x2="%g" y2="%d" stroke="%s" stroke-width="1"/>' % ((60 + db) / 60.0 * gw, (60 + db) / 60.0 * gw, h - 2, grid))
        for db in ((0,) if top else ()) + (-20, -40):
            sv.append('<line x1="2" y1="%g" x2="%d" y2="%g" stroke="%s" stroke-width="1"/>' % (ydb(db), gw - 2, ydb(db), grid))
        sv.append('<line x1="2" y1="%g" x2="%d" y2="%g" stroke="%s" stroke-width="1" stroke-dasharray="4 4"/>' % (ydb(-60) - 2, gw - 2, ydb(0) + 2, diag))
        sv.append("</svg>")
        open(os.path.join(d, "tc_screen_%s.svg" % look), "w").write("".join(sv))
    bw, n = 24, (shp_frames - 1) // 2
    for c, col in TC_COL.items():
        seg_h = (bh / 2) / n            # centre-zero SHAPE gain: frame k = k - 20 dB; 20 segments up, 20 down from the middle
        strip = Image.new("RGBA", (bw, bh * shp_frames), (0, 0, 0, 0))
        dr = ImageDraw.Draw(strip)
        for f in range(shp_frames):
            db = f - n
            for k in range(n):
                up_y = f * bh + bh / 2 - (k + 1) * seg_h + 1
                dn_y = f * bh + bh / 2 + k * seg_h + 1
                dr.rectangle([3, up_y, bw - 4, up_y + seg_h - 2], fill=col if db > k else OFF)
                dr.rectangle([3, dn_y, bw - 4, dn_y + seg_h - 2], fill=col if -db > k else OFF)
            dr.rectangle([0, f * bh + bh // 2 - 1, bw - 1, f * bh + bh // 2], fill=(236, 236, 240))
        strip.save(os.path.join(d, "shape_bar_%s.png" % c))
        m = gr_frames - 1               # gain reduction 0..-20 dB, top down: frame k = k * 0.5 dB (the VU's frames)
        seg_h = bh / 20.0
        strip = Image.new("RGBA", (bw, bh * gr_frames), (0, 0, 0, 0))
        dr = ImageDraw.Draw(strip)
        for f in range(gr_frames):
            for k in range(20):
                y = f * bh + k * seg_h + 1
                dr.rectangle([3, y, bw - 4, y + seg_h - 2], fill=col if f * 20.0 / m >= k + 0.5 else OFF)
        strip.save(os.path.join(d, "gr_bar20_%s.png" % c))


def _gold_logo(d, hue=43, name="logo_town_gold.png", sat=0.85, val=0.95):
    """SANDSTONE's #TOWN logo (0.10.0): the red one (logo_town_red.png) with its red turned gold, light and shade kept, the
    white lettering left white"""
    import colorsys
    im = Image.open(os.path.join(d, "logo_town_red.png")).convert("RGBA")
    px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if a and s > 0.25:
                nr, ng, nb = colorsys.hsv_to_rgb(hue / 360, min(1.0, s * sat), min(1.0, v * val))   # HEXX (0.11.0): hue 222, dark blue
                px[x, y] = (round(nr * 255), round(ng * 255), round(nb * 255), a)
    im.save(os.path.join(d, name))


CSS = {"title": "#f0f0f4", "border": "#8c8b93", "text": "#dcdce2"}   # skin.css's colours (user_theme.py's panel)


def write(d, led_frames, vu_frames, gr_frames, eq_size, bar_size, col, sp):
    _buttons(d)
    _caps(d)
    _eq_screen(d, eq_size)
    _eq_screen(d, eq_size, "eq_grid.svg", grid_only=True)   # over the logo, under the spectrum (FLANNEL)
    _eq_logo(d, eq_size)
    # MOLTEN (user, 2026-11-05, 0.14.4): the user's Chandler Limited logo (assets/Chandler-Ltd-Logo.png) in place of #TOWN,
    # same width and fade
    _eq_logo(d, eq_size, "logo_molten_eq_src.png", "eq_logo_molten.png")
    # MOCHA (user, 2026-11-05, 0.14.5): the user's Universal Audio logo (assets/universal audio logo.png), same fade,
    # 240 px tall (it is near-square: 480 px wide would overflow the 330 px screen)
    _eq_logo(d, eq_size, "logo_mocha_eq_src.png", "eq_logo_mocha.png", max_h=240)
    # FLANNEL + GRANITE (user, 2026-11-05, 0.14.6): the user's Solid State Logic logo (assets/SSLLogo.png), same width/fade
    _eq_logo(d, eq_size, "logo_flannel_eq_src.png", "eq_logo_flannel.png")
    # HEARTS (user, 2026-11-05, 0.14.7): the user's Weiss logo (assets/hearts logo.png), near-square so 240 px tall, same fade
    _eq_logo(d, eq_size, "logo_hearts_eq_src.png", "eq_logo_hearts.png", max_h=240)
    # SANDSTONE (user, 2026-11-05, 0.14.7): the user's Summit Audio logo (assets/Summit Audio Logo.png), 480 px wide, same fade
    _eq_logo(d, eq_size, "logo_sandstone_eq_src.png", "eq_logo_sandstone.png")
    # HEXX (user, 2026-11-05, 0.14.8): the user's HEXX logo (assets/HEXX_logo.png), near-square so 240 px tall, same fade
    _eq_logo(d, eq_size, "logo_hexx_eq_src.png", "eq_logo_hexx.png", max_h=240, alpha=HEXX_LOGO_ALPHA)   # 16.875% (0.19.2)
    # SUEDE (user, 2026-11-05, 0.14.8): the user's AMS Neve logo (assets/Neve logo.png), 480 px wide, same fade
    _eq_logo(d, eq_size, "logo_suede_eq_src.png", "eq_logo_suede.png")
    # SPADES (user, 2026-11-05, 0.14.9): the user's Avalon Design logo (assets/spades design.png), taller than wide so 240 px tall
    _eq_logo(d, eq_size, "logo_spades_eq_src.png", "eq_logo_spades.png", max_h=240)
    # TITANIUM + TITANIUM EQ (user, 2026-11-05, 0.16.1): the user's Empirical Labs logo (assets/EmpiricalLabsLogo.png), white on
    # black, so its brightness is its alpha; near-square, so 240 px tall, same fade
    _eq_logo(d, eq_size, "logo_titanium_eq_src.png", "eq_logo_titanium.png", max_h=240)
    _eq_screen(d, eq_size, "eq_screen_black.svg", bg="#000000", grid="#2a2a2a", label="#7a7a7a", zero="#4a4a4a", minor="#1c1c1c")   # the GRANITE's
    _eq_screen(d, eq_size, "eq_grid_black.svg", grid="#2a2a2a", label="#7a7a7a", zero="#4a4a4a", minor="#1c1c1c", grid_only=True)   # over the GRANITE's logo
    _eq_screen(d, eq_size, "eq_screen_hearts.svg", **HEARTS_SCREEN)                     # HEARTS's
    _eq_screen(d, eq_size, "eq_grid_hearts.svg", grid_only=True, **{k: v for k, v in HEARTS_SCREEN.items() if k != "bg"})
    _eq_screen(d, eq_size, "eq_screen_suede.svg", **SUEDE_SCREEN)                       # SUEDE's
    _eq_screen(d, eq_size, "eq_grid_suede.svg", grid_only=True, **{k: v for k, v in SUEDE_SCREEN.items() if k != "bg"})
    open(os.path.join(d, "header_suede.svg"), "w").write(open(os.path.join(d, "header_red.svg")).read().replace("#e0352b", "#8fa6ba")
                                                       .replace("HEARTS's EQ page (red rule; 0.7.4)", "SUEDE (blue-grey rule; 0.9.0)"))
    _eq_screen(d, eq_size, "eq_screen_sandstone.svg", **GOLD_SCREEN)                     # SANDSTONE's (0.10.0)
    _eq_screen(d, eq_size, "eq_grid_sandstone.svg", grid_only=True, **{k: v for k, v in GOLD_SCREEN.items() if k != "bg"})
    open(os.path.join(d, "header_gold.svg"), "w").write(open(os.path.join(d, "header_red.svg")).read().replace("#e0352b", "#d4a537")
                                                       .replace("HEARTS's EQ page (red rule; 0.7.4)", "SANDSTONE (gold rule; 0.10.0)"))
    _gold_logo(d)
    _eq_screen(d, eq_size, "eq_screen_hexx.svg", **HEXX_SCREEN)                         # HEXX's (0.11.0)
    _eq_screen(d, eq_size, "eq_grid_hexx.svg", grid_only=True, **{k: v for k, v in HEXX_SCREEN.items() if k != "bg"})
    open(os.path.join(d, "header_darkblue.svg"), "w").write(open(os.path.join(d, "header_red.svg")).read().replace("#e0352b", "#2a52be")
                                                           .replace("HEARTS's EQ page (red rule; 0.7.4)", "HEXX (dark blue rule; 0.11.0)"))
    _gold_logo(d, 222, "logo_town_darkblue.png", 1.0, 0.85)
    _eq_screen(d, eq_size, "eq_screen_molten.svg", **CH_SCREEN)                     # MOLTEN's (0.12.0)
    _eq_screen(d, eq_size, "eq_grid_molten.svg", grid_only=True, **{k: v for k, v in CH_SCREEN.items() if k != "bg"})
    open(os.path.join(d, "header_darkred.svg"), "w").write(open(os.path.join(d, "header_red.svg")).read().replace("#e0352b", "#a32020")
                                                          .replace("HEARTS's EQ page (red rule; 0.7.4)", "MOLTEN (dark red rule; 0.12.0)"))
    _gold_logo(d, 0, "logo_town_darkred.png", 1.0, 0.68)
    _eq_screen(d, eq_size, "eq_screen_spades.svg", **AV_SCREEN)                       # SPADES's (0.13.0)
    _eq_screen(d, eq_size, "eq_grid_spades.svg", grid_only=True, **{k: v for k, v in AV_SCREEN.items() if k != "bg"})
    open(os.path.join(d, "header_black.svg"), "w").write(open(os.path.join(d, "header_red.svg")).read().replace("#e0352b", "#0c0c0d")
                                                        .replace("HEARTS's EQ page (red rule; 0.7.4)", "SPADES (black rule; 0.13.1)"))
    # MOCHA (user, 2026-11-05, 0.14.12): the GRANITE's light brown rule, from the far left (x=10, the right end's 10 px margin)
    open(os.path.join(d, "header_mocha.svg"), "w").write(open(os.path.join(d, "header_lightbrown.svg")).read()
                                                         .replace('<rect x="128" y="55" width="1126"', '<rect x="10" y="55" width="1244"')
                                                         .replace("the GRANITE's EQ page (light brown rule; 0.7.10)", "MOCHA (light brown rule from the far left; 0.14.12)"))
    _gold_logo(d, 0, "logo_town_black.png", 0.0, 0.22)                               # SPADES: black (no colour, dark)
    _eq_screen(d, eq_size, "eq_screen_mocha.svg", **LA_SCREEN)                      # MOCHA's (0.14.0)
    _eq_screen(d, eq_size, "eq_grid_mocha.svg", grid_only=True, **{k: v for k, v in LA_SCREEN.items() if k != "bg"})
    _gold_logo(d, 29, "logo_town_lightbrown.png", 0.43, 0.80)                       # MOCHA: light brown (0.14.1)
    _bar(d, bar_size)
    _eq_col(d, col[0], eq_size[1], col[1])
    _eq_join(d, col[0], eq_size[1], col[1], col[2], col[3])
    EQ_WHITE = ((246, 246, 246, 255), (255, 255, 255, 32))   # HEARTS's curve: white (user, 2026-11-03), a faint white fill
    _eq_col(d, col[0], eq_size[1], col[1], "eq_col_white.png", *EQ_WHITE)
    _eq_join(d, col[0], eq_size[1], col[1], col[2], col[3], "eq_join_white", *EQ_WHITE)
    EQ_RED = ((226, 72, 60, 255), (226, 72, 60, 40))           # SUEDE's curve: red
    _eq_col(d, col[0], eq_size[1], col[1], "eq_col_red.png", *EQ_RED)
    _eq_join(d, col[0], eq_size[1], col[1], col[2], col[3], "eq_join_red", *EQ_RED)
    _sp_col(d, col[0], eq_size[1], sp[0])
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2])
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2])
    # the GRANITE's spectrum, brown (user, 2026-11-03), on its black screen
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_brown.png", BROWN_FILL, BROWN_EDGE)
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_brown", BROWN_FILL, BROWN_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_brown", BROWN_BAR, BROWN_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_hearts.png", HEARTS_FILL, HEARTS_EDGE)      # HEARTS's, in Weiss red
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_hearts", HEARTS_FILL, HEARTS_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_hearts", HEARTS_BAR, HEARTS_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_blue.png", BLUE_FILL, BLUE_EDGE)        # the FLANNEL's, blue (0.9.4)
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_blue", BLUE_FILL, BLUE_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_blue", BLUE_BAR, BLUE_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_suede.png", SUEDE_FILL, SUEDE_EDGE)        # SUEDE's, blue-grey
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_suede", SUEDE_FILL, SUEDE_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_suede", SUEDE_BAR, SUEDE_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_gold.png", GOLD_FILL, GOLD_EDGE)        # SANDSTONE's, gold
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_gold", GOLD_FILL, GOLD_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_gold", GOLD_BAR, GOLD_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_hexx.png", HEXX_FILL, HEXX_EDGE)          # HEXX's, dark blue
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_hexx", HEXX_FILL, HEXX_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_hexx", HEXX_BAR, HEXX_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_molten.png", CH_FILL, CH_EDGE)       # MOLTEN's, dark red
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_molten", CH_FILL, CH_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_molten", CH_BAR, CH_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_spades.png", AV_FILL, AV_EDGE)         # SPADES's, Avalon blue
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_spades", AV_FILL, AV_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_spades", AV_BAR, AV_TOP)
    _sp_col(d, col[0], eq_size[1], sp[0], "sp_col_mocha.png", LA_FILL, LA_EDGE)         # MOCHA's, white
    _sp_join(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "sp_join_mocha", LA_FILL, LA_EDGE)
    _sp_bars(d, col[0], eq_size[1], sp[0], sp[1], sp[2], "_mocha", LA_BAR, LA_TOP)
    _led_bar(d, led_frames)
    _led_pk(d, led_frames)
    _led_bar(d, led_frames, "led_bar_hearts.png", LED_HEARTS)
    _led_pk(d, led_frames, "led_pk_hearts.png", LED_HEARTS)
    _led_bar(d, led_frames, "led_bar_granite.png", LED_GRANITE)
    _led_pk(d, led_frames, "led_pk_granite.png", LED_GRANITE)
    _led_bar(d, led_frames, "led_bar_flannel.png", LED_FLANNEL)
    _led_pk(d, led_frames, "led_pk_flannel.png", LED_FLANNEL)
    _led_bar(d, led_frames, "led_bar_suede.png", LED_SUEDE)
    _led_pk(d, led_frames, "led_pk_suede.png", LED_SUEDE)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_suede.png", SUEDE_PK)
    _led_bar(d, led_frames, "led_bar_sandstone.png", LED_SANDSTONE)
    _led_pk(d, led_frames, "led_pk_sandstone.png", LED_SANDSTONE)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_gold.png", GOLD_PK)
    _led_bar(d, led_frames, "led_bar_hexx.png", LED_HEXX)
    _led_pk(d, led_frames, "led_pk_hexx.png", LED_HEXX)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_hexx.png", HEXX_PK)
    _led_bar(d, led_frames, "led_bar_molten.png", LED_MOLTEN)
    _led_pk(d, led_frames, "led_pk_molten.png", LED_MOLTEN)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_molten.png", CH_PK)
    _led_bar(d, led_frames, "led_bar_spades.png", LED_SPADES)
    _led_pk(d, led_frames, "led_pk_spades.png", LED_SPADES)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_spades.png", AV_PK)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_avgrey.png", (150, 152, 158, 235))   # SPADES's held peaks grey (user, 0.19.2)
    _led_bar(d, led_frames, "led_bar_mocha.png", LED_MOCHA)
    _led_pk(d, led_frames, "led_pk_mocha.png", LED_MOCHA)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_mocha.png", LA_PK)
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk.png", (236, 240, 244, 235))          # held spectrum peaks: near white
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_brown.png", (232, 186, 120, 235))    # the GRANITE's: tan
    _sp_pk(d, col[0], eq_size[1], sp[0], "sp_pk_hearts.png", HEARTS_PK)                 # HEARTS's: pale red
    _gr_bar(d, gr_frames)
    _vu(d, vu_frames)
    css = os.path.join(d, "skin.css")
    open(css, "w").write(
        "/* X-Console: grey console panel, white silkscreen and LED rings, blue section lights. */\n"
        ".frame-title { fill: %s; letter-spacing: 0.10em; font-weight: 600; }\n" % CSS["title"] +
        ".frame-border { stroke: %s; stroke-width: 1.2; }\n" % CSS["border"] +
        ".text { fill: %s; }\n" % CSS["text"] +
        ".look-led-on { fill: #f4f6f8; filter: drop-shadow(0 0 3px rgba(255,255,255,0.8)); }\n"
        ".look-led-off { fill: #2b2b30; }\n"
        ".look-lbody { fill: #2a2a2f; stroke: #111114; }\n")
