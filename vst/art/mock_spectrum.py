"""Picture of the EQ page's graph with a made-up spectrum and EQ curve, from the built page background and the art strips
(vst/art), to see the Gen2 (sloped) look before the device does.   python3 vst/art/mock_spectrum.py <skin Plugin Skins dir> <out.png>
Geometry follows make_layout.py: screen at x 180, y 136 (plugin area from y 86), 44 columns of 16 x 330."""
import glob
import math
import os
import sys

from PIL import Image

skin, out, brown = sys.argv[1], sys.argv[2], "brown" in sys.argv[3:]   # brown: the GRANITE look (black screen)
ART = os.path.dirname(os.path.abspath(__file__))
SX, SY, W, H, COLS = 180, 136 - 86, 16, 330, 44
SP_LV, SP_J, SP_T = 37, 3, 2
EQ_LV, EQ_J, EQ_T = 37, 8, 5
bg = Image.open(sorted(glob.glob(os.path.join(skin, "sh_bg_*.png")))[2]).convert("RGBA")   # page 3: EQ
if brown:   # the GRANITE screen: black with a dark grid (as eq_screen_black.svg)
    from PIL import ImageDraw
    dr = ImageDraw.Draw(bg)
    dr.rounded_rectangle([SX, SY, SX + COLS * W - 1, SY + H - 1], radius=6, fill=(0, 0, 0, 255))
    for f in (30, 50, 100, 200, 500, 1000, 2000, 5000, 10000):
        x = SX + COLS * W * math.log(f / 20) / math.log(1000)
        dr.line([x, SY + 4, x, SY + H - 4], fill=(42, 42, 42, 255))
    for g in (-12, -6, 0, 6, 12):
        y = SY + H / 2 - g * (H / 2 - 10) / 18
        dr.line([SX + 4, y, SX + COLS * W - 4, y], fill=(74, 74, 74, 255) if g == 0 else (28, 28, 28, 255))
TILES = {}


def frame_from_tiles(prefix, tiles, f):
    th = H // tiles
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for t in range(tiles):
        if (prefix, t) not in TILES:
            TILES[(prefix, t)] = Image.open(os.path.join(ART, "%s_t%d.png" % (prefix, t))).convert("RGBA")
        im.paste(TILES[(prefix, t)].crop((0, f * th, W, f * th + th)), (0, t * th))
    return im


# a music-like spectrum, smoothed like the engine (1-2-3-2-1 power mean), 2 dB levels
raw = []
for i in range(COLS):
    f = 20 * 1000 ** ((i + 0.5) / COLS)
    db = -30 - 6 * math.log2(max(f, 60) / 60) * 0.9 + 8 * math.exp(-math.log2(f / 70) ** 2) + 6 * math.exp(-math.log2(f / 4000) ** 2 * 2)
    db -= 25 / (1 + (14000 / f) ** 6) + 7 * math.sin(i * 1.7) ** 2
    raw.append(10 ** (db / 10))
sp = []
for i in range(COLS):
    s = ws = 0
    for j, wt in zip(range(-2, 3), (1, 2, 3, 2, 1)):
        if 0 <= i + j < COLS:
            s += wt * raw[i + j]; ws += wt
    sp.append(max(0, min(SP_LV - 1, round((10 * math.log10(s / ws) + 72) / 2))))
# an EQ curve: low cut 40 Hz, LF shelf +6, LMF -6 at 350 Hz, HMF +5 at 3 kHz, HF bell +8 at 12 kHz (1 dB levels)
eq = []
for i in range(COLS):
    f = 20 * 1000 ** ((i + 0.5) / COLS)
    db = -10 * math.log10(1 + (40 / f) ** 6) + 6 / (1 + (f / 120) ** 2) - 6 * math.exp(-math.log2(f / 350) ** 2 * 4)
    db += 5 * math.exp(-math.log2(f / 3000) ** 2 * 3) + 8 * math.exp(-math.log2(f / 12000) ** 2 * 8)
    eq.append(max(0, min(EQ_LV - 1, round(db) + 18)))
for i in range(COLS):
    j = max(-SP_J, min(SP_J, sp[i + 1] - sp[i])) if i + 1 < COLS else 0
    bg.alpha_composite(frame_from_tiles("sp_join_brown" if brown else "sp_join", SP_T, sp[i] * (2 * SP_J + 1) + j + SP_J), (SX + i * W, SY))
for i in range(COLS):
    j = max(-EQ_J, min(EQ_J, eq[i + 1] - eq[i])) if i + 1 < COLS else 0
    bg.alpha_composite(frame_from_tiles("eq_join", EQ_T, eq[i] * (2 * EQ_J + 1) + j + EQ_J), (SX + i * W, SY))
bg.crop((120, 0, 1160, 400)).save(out)
print("wrote", out)
