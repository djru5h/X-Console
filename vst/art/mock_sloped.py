"""Side-by-side mock: the spectrum as it is now (steps joined by vertical lines) and drawn as sloped segments from each
column's level to its right neighbour's (the same frame data: level + the neighbour's difference), at 2 dB and 1 dB levels.
python3 vst/art/mock_sloped.py out.png"""
import math
import sys

from PIL import Image, ImageDraw

W, H, COLS, SS = 16, 330, 44, 4
FILL, EDGE = (70, 190, 104, 70), (160, 244, 170, 255)
BG, GRID = (13, 26, 34, 255), (33, 65, 79, 255)


def levels(step_db):
    raw = []
    for i in range(COLS):
        f = 20 * 1000 ** ((i + 0.5) / COLS)
        db = -30 - 6 * math.log2(max(f, 60) / 60) * 0.9 + 8 * math.exp(-math.log2(f / 70) ** 2) + 6 * math.exp(-math.log2(f / 4000) ** 2 * 2)
        db -= 25 / (1 + (14000 / f) ** 6) + 7 * math.sin(i * 1.7) ** 2
        raw.append(10 ** (db / 10))
    out = []
    for i in range(COLS):
        s = ws = 0
        for j, wt in zip(range(-2, 3), (1, 2, 3, 2, 1)):
            if 0 <= i + j < COLS:
                s += wt * raw[i + j]; ws += wt
        out.append(round((10 * math.log10(s / ws) + 72) / step_db))
    return out


def panel(title, step_db, join, sloped):
    n = int(72 / step_db)
    lv = [max(0, min(n, v)) for v in levels(step_db)]
    im = Image.new("RGBA", (COLS * W * SS, (H + 30) * SS), (60, 59, 64, 255))
    d = ImageDraw.Draw(im)
    top = 30 * SS
    d.rectangle([0, top, COLS * W * SS, top + H * SS], fill=BG)
    for db in range(0, 73, 12):
        y = top + (3 + db / 72 * (H - 6)) * SS
        d.line([0, y, COLS * W * SS, y], fill=GRID, width=SS)
    y_of = lambda k: top + ((H - 3) - k / n * (H - 6)) * SS
    for i in range(COLS):
        x0, x1 = i * W * SS, (i + 1) * W * SS
        k = lv[i]
        k2 = max(0, min(n, k + max(-join, min(join, lv[i + 1] - k)))) if i + 1 < COLS else k
        ya, yb = y_of(k), y_of(k2)
        if sloped:
            d.polygon([(x0, ya), (x1, yb), (x1, top + H * SS), (x0, top + H * SS)], fill=FILL)
            d.line([(x0, ya), (x1, yb)], fill=EDGE, width=3 * SS)
        else:
            d.rectangle([x0, ya, x1, top + H * SS], fill=FILL)
            d.line([(x0, ya), (x1, ya)], fill=EDGE, width=3 * SS)
            if k2 != k:
                d.line([(x1 - SS, ya), (x1 - SS, yb)], fill=EDGE, width=2 * SS)
    d.text((8 * SS, 6 * SS), title, fill=(236, 236, 240, 255), font_size=16 * SS) if hasattr(d, "text") else None
    return im.resize((COLS * W, H + 30), Image.LANCZOS)


a = panel("NOW (0.4.1): steps, 2 dB", 2, 3, False)
b = panel("SLOPED, 2 dB levels (same data, same updates)", 2, 3, True)
c = panel("SLOPED, 1 dB levels", 1, 6, True)
out = Image.new("RGBA", (a.size[0], a.size[1] * 3 + 20), (60, 59, 64, 255))
for i, p in enumerate((a, b, c)):
    out.paste(p, (0, i * (a.size[1] + 10)))
out.save(sys.argv[1])
print("wrote", sys.argv[1])
