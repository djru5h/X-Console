#!/usr/bin/env python3
"""X-Console's NOISE page (0.18.0): the SPECTRUM pictures, one per colour (art/nz_spec_<colour>.svg), drawn as
P-Valley PNG's (each colour's level against frequency from src/noise.c's filters; crackle a strip of clicks), in
X-Console's colours (blue on a black screen) instead of PNG's pink. No packages needed."""
import cmath
import math
import os
import random

W, H = 448, 244
L, R, T, B = 40, 10, 12, 28
DB = 30
SR = 44100
ACCENT, INK, DIM, GRID, BG = "#2f9fd0", "#ececf0", "#8f8e96", "#1e2a30", "#000000"
OUT = os.path.dirname(os.path.abspath(__file__))


def fx(f):
    return L + (W - L - R) * math.log(f / 20) / math.log(1000)


def fy(db):
    return T + (H - T - B) * (DB - db) / (2 * DB)


def biquad(kind, f0, q, gain_db):
    w = 2 * math.pi * f0 / SR
    cw, sw, A = math.cos(w), math.sin(w), 10 ** (gain_db / 40)
    al = sw / (2 * q)
    sq = 2 * math.sqrt(A) * al
    if kind == "peak":
        b, a = (1 + al * A, -2 * cw, 1 - al * A), (1 + al / A, -2 * cw, 1 - al / A)
    elif kind == "lowshelf":
        b = (A * ((A + 1) - (A - 1) * cw + sq), 2 * A * ((A - 1) - (A + 1) * cw), A * ((A + 1) - (A - 1) * cw - sq))
        a = ((A + 1) + (A - 1) * cw + sq, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sq)
    else:
        b = (A * ((A + 1) + (A - 1) * cw + sq), -2 * A * ((A - 1) + (A + 1) * cw), A * ((A + 1) + (A - 1) * cw - sq))
        a = ((A + 1) - (A - 1) * cw + sq, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sq)
    return b, a


def resp_db(filters, f):
    z = cmath.exp(-1j * 2 * math.pi * f / SR)
    h = 1
    for b, a in filters:
        h *= (b[0] + b[1] * z + b[2] * z * z) / (a[0] + a[1] * z + a[2] * z * z)
    return 20 * math.log10(abs(h))


GREY = [biquad("lowshelf", 180, 0.5, 18), biquad("peak", 3500, 1.0, -6), biquad("highshelf", 9000, 0.7, 7)]
BROWN_A = math.exp(-2 * math.pi * 20 / SR)


def level(colour, f):
    diff = 20 * math.log10(2 * math.sin(math.pi * f / SR))
    pink = -10 * math.log10(f / 1000)
    if colour == "white":
        return 0
    if colour == "pink":
        return pink
    if colour == "brown":
        return -20 * math.log10(abs(1 - BROWN_A * cmath.exp(-1j * 2 * math.pi * f / SR)))
    if colour == "blue":
        return pink + diff
    if colour == "violet":
        return diff
    return resp_db(GREY, f)


def svg(parts, caption):
    parts = parts + ['<text x="%d" y="%d" fill="%s" font-size="14" font-weight="600" text-anchor="end">%s</text>'
                     % (W - R - 6, T + 18, INK, caption)]
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" '
            'font-family="Titillium Web, Roboto, sans-serif">%s</svg>\n' % (W, H, W, H, "".join(parts)))


def frame(body, caption, axes=True):
    g = ['<rect x="0" y="0" width="%d" height="%d" rx="6" fill="%s" stroke="#000" stroke-width="2"/>' % (W, H, BG)]
    if axes:
        for db in range(-DB + 10, DB, 10):
            g.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1"/>' % (L, fy(db), W - R, fy(db), GRID))
            g.append('<text x="%d" y="%.1f" fill="%s" font-size="12" text-anchor="end" dominant-baseline="middle">%s</text>'
                     % (L - 5, fy(db), DIM, "%+d" % db if db else "0"))
        for f, t in ((50, "50"), (100, "100"), (200, "200"), (500, "500"), (1000, "1k"), (2000, "2k"), (5000, "5k"), (10000, "10k")):
            g.append('<line x1="%.1f" y1="%d" x2="%.1f" y2="%d" stroke="%s" stroke-width="1"/>' % (fx(f), T, fx(f), H - B, GRID))
            g.append('<text x="%.1f" y="%d" fill="%s" font-size="12" text-anchor="middle">%s</text>' % (fx(f), H - 9, DIM, t))
        g.append('<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (L, fy(0), W - R, fy(0), DIM))
    return svg(g + body, caption)


def curve(colour):
    ref = level(colour, 1000)
    pts = []
    for i in range(241):
        f = 20 * 1000 ** (i / 240)
        pts.append((fx(f), fy(max(-DB, min(DB, level(colour, f) - ref)))))
    line = " ".join("%.1f,%.1f" % p for p in pts)
    area = "%.1f,%.1f %s %.1f,%.1f" % (pts[0][0], fy(-DB), line, pts[-1][0], fy(-DB))
    return ['<polygon points="%s" fill="%s" fill-opacity="0.22"/>' % (area, ACCENT),
            '<polyline points="%s" fill="none" stroke="%s" stroke-width="3" stroke-linejoin="round"/>' % (line, ACCENT)]


def clicks():
    rnd = random.Random(7)
    mid = (T + H - B) / 2
    g = ['<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="%s" stroke-width="1.5"/>' % (L, mid, W - R, mid, DIM)]
    x = L + 6
    while x < W - R - 6:
        a = rnd.random() ** 4 * (H - T - B) / 2 * 0.95
        g.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" stroke-width="2.5" stroke-linecap="round"/>'
                 % (x, mid - a, x, mid + a * rnd.uniform(0.4, 1), ACCENT))
        x += rnd.expovariate(1 / 12)
    return frame(g, "RANDOM CLICKS AND POPS", axes=False)


CAPTIONS = {"white": "FLAT: EVEN ENERGY PER HZ", "pink": "-3 dB / OCTAVE", "brown": "-6 dB / OCTAVE",
            "blue": "+3 dB / OCTAVE", "violet": "+6 dB / OCTAVE", "grey": "SHAPED TO SOUND EVEN"}
COLOURS = ("pink", "white", "brown", "blue", "violet", "grey", "crackle")   # noise.h's order


def write(d=OUT):
    for c in COLOURS[:-1]:
        open(os.path.join(d, "nz_spec_%s.svg" % c), "w").write(frame(curve(c), CAPTIONS[c]))
    open(os.path.join(d, "nz_spec_crackle.svg"), "w").write(clicks())
    return ["art/nz_spec_%s.svg" % c for c in COLOURS]


if __name__ == "__main__":
    print(write())
