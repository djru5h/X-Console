#!/usr/bin/env python3
"""X-Console: write vst/params.json, vst/layout.conf and src/param_table.h from one list, so they can't drift apart.
    python3 vst/art/make_layout.py      (in the mpc-vst-html-art image, which has Pillow for the meter art)
A console-style channel strip, one page per section. Coordinates are Force Shadow pixels: the plugin area is 1280 x 628
from y = 86; pages use x 8..1272, y 92..708. Every page keeps the IN meter and INPUT knob on the left and the OUT meter
and VOLUME knob on the right, so level is always in reach. No maker's name or logo but our own."""
import json
import re
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_art  # noqa: E402

GEN2 = "gen2" in sys.argv[1:]       # the XL's skin: the spectrum's steps joined into one outline (tall filmstrips, Gen2 only)

TOP, BOTTOM = 152, 708              # pages 556 px tall under the banner (user, 2026-11-03: 60 px shorter; YES-SL 9000's frame)
BANNER_Y, BANNER_H = 86, 62         # the banner, edge to edge: top of the plugin area, full width, square corners (user, 2026-11-10; 88, 60 at x=8 w=1264 before)
LOGO_WH = (104, 48)                  # art/logo_town.png: the user's #TOWN logo, cropped, 48 px high
H = BOTTOM - TOP
MID_X0, MID_X1 = 136, 1144          # the page's own area, between the two meter columns
PARAMS, L, TABS = [], [], []
SPEC = {}                           # key -> (min, max, taper, unit), the engine's mapping of 0..1 (src/param_table.h)
SEEN = set()


def num(key, name, lo, hi, default, taper="lin", unit=""):
    """A continuous control. MPC sees 0..1 and the engine maps it (taper: lin, log, off-log = bottom is Off, sym = bipolar)."""
    if key in SEEN:
        return
    SEEN.add(key)
    SPEC[key] = (lo, hi, taper, unit)
    norm = to_norm(key, default)
    PARAMS.append({"key": key, "name": name, "min": 0, "max": 1, "default": round(norm, 6), "unit": "", "dynamic_display": True})


def to_norm(key, v):
    """0..1 position of value v. None = the end stop meaning Off or Auto (bottom), or Off (top, for top-off-log)."""
    import math
    lo, hi, taper, _ = SPEC[key]
    if v is None:
        return 1.0 if taper == "top-off-log" else 0.0
    if taper == "split":   # lo..0 on the left half, 0..hi on the right (2026-11-10: INPUT GAIN)
        return 0.5 * (1 - v / lo) if v < 0 else 0.5 + 0.5 * v / hi
    if "log" in taper:
        return math.log(v / lo) / math.log(hi / lo)
    return (v - lo) / (hi - lo)


def opt(key, name, options, default=0):
    if key in SEEN:
        return
    SEEN.add(key)
    PARAMS.append({"key": key, "name": name, "options": options, "default": default})


def meter_param(key, name, default):
    """Display only: the engine sets it, MPC redraws the meter's filmstrip."""
    if key in SEEN:
        return
    SEEN.add(key)
    PARAMS.append({"key": key, "name": name, "min": 0, "max": 1, "default": default, "unit": "", "poll": False})


# ---------------------------------------------------------------- widgets
TAB_SHOWN = {"DRIVE": "OUTPUT"}   # every preset: the DRIVE page is called OUTPUT (user, 2026-11-05, 0.19.0)


def tab(name, qlinks):
    CUR_PAGE[0] = name
    shown = TAB_SHOWN.get(name, name)
    L.append("[tab %s]" % shown)
    TABS.append((shown, qlinks))
    L.append('qlinks "%s" = %s' % (shown, qlinks))
    banner(name)
    sides()


# Page themes (user, 2026-11-03): under a preset, on the pages listed, these parts take the theme's look (the page's own
# preset key, PAGE_MODEL, picks it). Parts: logo (#TOWN picture), x ("X-" of X-CONSOLE), rule (the line under it), name
# (the preset name), meters (IN/OUT, art/led_bar<meters>.png), segs (lit segment buttons), on (section ON LEDs white),
# switch (the other switches' LEDs), curve (the EQ curve white).
THEMES = {
    2: {   # HEARTS: red (0.7.1-0.7.8)
        "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
                  for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
        "logo": "logo_town_red.png", "x": "e0352b", "rule": "header_red.svg", "name": "e0352b", "meters": "_hearts",
        "segs": "e0352b", "switch": "red", "order": ("e0352b", "_g"),
    },
    1: {   # GRANITE: brown, its EQ page (0.7.9); "X-" and the rule light brown, its meters on every page (0.7.10)
        "pages": dict({"EQ": {"logo", "x", "rule", "name", "meters", "segs", "on", "curve"}},
                      **{pg: {"meters", "logo", "x", "rule", "name", "segs", "on", "switch"}   # + the banner (0.7.11), buttons (0.8.0)
                         for pg in ("PREAMP", "SHAPE", "COMP", "DRIVE")}),
        "logo": "logo_town_brown.png", "x": "c89c72", "rule": "header_lightbrown.svg", "name": "c89c72", "meters": "_granite",
        "segs": "c89c72", "switch": "lightbrown", "order": ("c89c72", "_e"),
    },
}


THEMES[3] = {   # SUEDE: blue-grey with red (user, 2026-11-03, 0.9.0): red logo, X- and lit buttons, blue-grey rule and name
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": "logo_town_red.png", "x": "d23c32", "rule": "header_suede.svg", "name": "a8bccc", "meters": "_suede",
    "segs": "d23c32", "switch": "red", "on_img": "btn_on_red.svg", "curve": "_red", "order": ("d23c32", "_n"),
}
THEMES[0] = {   # FLANNEL: "X-" blue on every page (user, 2026-11-04: light blue in 0.9.1, blue in 0.9.2), the banner rule's blue
    "pages": {pg: {"x", "name", "meters", "on"} | ({"curve"} if pg == "EQ" else set()) for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    # "on": the section ON buttons light white (user, 2026-11-04, 0.9.6); the other switches stay blue
    "x": "2f9fd0", "name": "2f9fd0",
    "meters": "_flannel",   # IN/OUT blue -> white from -18 -> red from 0 on every page (user, 2026-11-04, 0.9.4)
    "curve": "_white",    # the EQ curve white (user, 2026-11-04, 0.9.4)   # and the preset name in the banner's right corner blue (user, 2026-11-04, 0.9.3)
}
THEMES[1]["pages"]["DRIVE"] = THEMES[1]["pages"]["DRIVE"] | {"order"}   # its own light brown ORDER list (0.8.0)
THEMES[4] = {   # SANDSTONE: gold on every page (user, 2026-11-04, 0.10.0): gold logo, X-, rule, name, buttons, ON lights, ORDER list
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": "logo_town_gold.png", "x": "d4a537", "rule": "header_gold.svg", "name": "e8c66a", "meters": "_sandstone",
    "segs": "d4a537", "segs_tx": "000000", "switch": "gold", "curve": "_white", "order": ("d4a537", "_s"),   # segs_tx: lit text black (user, 2026-11-04, 0.10.4)
      # ON buttons white (user, 2026-11-04, 0.10.1); other switches gold
}
THEMES[5] = {   # HEXX: dark blue on every page (user, 2026-11-04, 0.11.0): logo, X-, rule, name, meters, buttons, ORDER list
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": "logo_town_darkblue.png", "x": "2a52be", "rule": "header_darkblue.svg", "name": "4a72d4", "meters": "_hexx",
    "segs": "2a52be", "switch": "darkblue", "curve": "_white", "order": ("2a52be", "_a"),
    "order_ink": "ffffff", "order_list_ink": "ffffff",   # ORDER text, arrow and list items white (user, 2026-11-05, 0.19.0)   # was light blue (user, 2026-11-04, 0.11.2; white field 0.11.1)
    # banner name: the 0.12.3 default (28 px, white stroke) for every preset; was "name_stroke" + "name_size": 2.8:  "HEXX" 28 px (user, 2026-11-04, 0.11.3; 22 px before)                           # "HEXX" in the banner: 1 px white stroke (user, 2026-11-04, 0.11.2)
    # ON buttons white (user, 2026-11-04, 0.11.2; dark blue btn_on_darkblue.svg in 0.11.0-0.11.1); other switches dark blue
}
THEMES[6] = {   # MOLTEN: dark red on every page (user, 2026-11-04, 0.12.0): logo, X-, rule, name, meters, buttons, ON lights, ORDER list
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": "logo_town_darkred.png", "x": "a32020", "rule": "header_darkred.svg", "name": "c8423a", "meters": "_molten",
    "segs": "a32020", "switch": "darkred", "curve": "_white", "order": ("a32020", "_c"),   # ON buttons white (user, 2026-11-04, 0.12.4; dark red btn_on_darkred.svg in 0.12.0-0.12.3)
    "order_ink": "ffffff",   # ORDER text and arrow white (user, 2026-11-04, 0.12.4)
}
THEMES[7] = {   # SPADES: black on every page (user, 2026-11-04, 0.13.1: "give it a black theme"; silver in 0.13.0): logo, X-, rule,
    # name, lit segments (white text), knobs, EQ screen; ON lights and switches white (a black light wouldn't read as on); meters
    # grey -> white -> red, spectrum white (my choices)
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": "logo_town_black.png", "x": "0c0c0d", "rule": "header_black.svg", "name": "0c0c0d", "meters": "_spades",
    "segs": "000000", "segs_tx": "ffffff", "switch": "white", "curve": "_white", "order": ("000000", "_v"),   # ON buttons white
    "order_ink": "ffffff", "order_list_ink": "ffffff",
}
THEMES[8] = {   # MOCHA: light brown on every page (user, 2026-11-04, 0.14.1: "Give this preset a light brown theme"; dark grey
    # in 0.14.0): the GRANITE's light brown c89c72 for logo, X-, rule, name, lit segments (black text), switches, ORDER (black ink),
    # knobs; ON lights white; meters light brown -> white -> red; a dark brown EQ screen, light brown spectrum (my choices)
    "pages": {pg: {"logo", "x", "rule", "name", "meters", "segs", "on", "switch", "curve", "order"}
              for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},
    "logo": None,   # no #TOWN logo in the banner (user, 2026-11-05, 0.14.11; logo_town_lightbrown.png before)
    "x": "c89c72", "rule": "header_mocha.svg", "name": "c89c72", "meters": "_mocha",   # rule from the far left (0.14.12; header_lightbrown.svg before)
    "title_x": 18,   # X-CONSOLE at the far left, where the logo was (user, 2026-11-05, 0.14.12; 138 before)
    "segs": "c89c72", "segs_tx": "000000", "switch": "lightbrown", "curve": "_white", "order": ("c89c72", "_l"),   # ON buttons white
    "order_ink": "ffffff",   # ORDER text and arrow white (user, 2026-11-04, 0.14.2; black in 0.14.1)
}
for _m in (9, 10, 11):   # Empirical Labs (0.16.0): SPADES's black theme (user: black, white knobs)
    THEMES[_m] = dict(THEMES[7])
# the SETUP page (no preset of its own): "X-" blue and the FLANNEL's IN/OUT meters (user, 2026-11-04, 0.9.5)
SETUP_LOOK = {"x": "2f9fd0", "meters": "_flannel"}
ACTIVE = [None]   # a set of presets while a page draws a layout for those presets only (the GRANITE's SHAPE / COMP), else None


def theme(m, page, part):
    """preset m's theme for `part` on this page, with the user's colours file over it (user_theme.py), else None"""
    return UT.theme(m, page, part)


def _theme_base(m, page, part):
    """the theme of preset m when it changes `part` on this page, else None"""
    t = THEMES.get(m)
    return t if t and part in t["pages"].get(page, ()) else None


def per_model(page, part):
    """[(model, condition)]: one per preset when some preset's theme changes `part` on this page, else one plain line"""
    key = PAGE_MODEL[page]   # only the presets in this page's list (0.15.0)
    if ACTIVE[0] is not None:   # a layout for some presets only: one line each
        return [(m, " when=%s:%d" % (key, mopt(m, key))) for m in LISTS[key] if m in ACTIVE[0]]
    if not any([theme(m, page, part) for m in LISTS[key]]):   # every preset asked (records each one's colours)
        return [(None, "")]
    return [(m, " when=%s:%d" % (key, mopt(m, key))) for m in LISTS[key]]


def only(models, fn, *a, **k):
    """call a widget function for the given presets only (a per-preset layout): fn's lines get when= for each of them"""
    ACTIVE[0] = set(models)
    try:
        n0 = len(L)
        fn(*a, **k)
        lines = L[n0:]   # lines fn wrote without a when= (text, meters, art, a button's name): one copy per preset
        del L[n0:]
        for ln in lines:
            if " when=" in ln:
                L.append(ln)
            else:
                pk = PAGE_MODEL[CUR_PAGE[0]]
                L.extend(ln + " when=%s:%d" % (pk, mopt(m, pk)) for m in LISTS[pk] if m in models)
    finally:
        ACTIVE[0] = None


def art_line(line):
    L.append(line)


# the banner's text, every preset (user, 2026-11-04, 0.12.3, "apply this to the banners of all future presets"):
TITLE_SIZE = 3.8            # X-CONSOLE 38 px (user, 2026-11-05, 0.14.14; 35 px since 0.12.3, 30 px before)
NAME_SIZE = 3.2             # the preset name / SETUP on the right 32 px (user, 2026-11-05, 0.14.14; 28 px since 0.12.3, 22 px before; HEXX 28 px since 0.11.3, MOLTEN 25 px in 0.12.1)
BANNER_STROKE = "ffffff:1"  # 1 px white stroke on "X-" and on the preset name


def banner(page):
    """across the top of every page: the panel and the logo slot (art/header.svg; the user's logo goes in the slot), the
    name, and on the right the name of the preset the page follows (alone, 0.6.1) (COMP and DRIVE: the compressor's; SETUP: none, it has all four)"""
    cy = BANNER_Y + BANNER_H // 2
    for m, cond in per_model(page, "rule"):
        t = theme(m, page, "rule")
        L.append('art file="art/%s" x=0 y=%d w=1280 h=%d' % (t["rule"] if t else "header.svg", BANNER_Y, BANNER_H) + cond)
    # no #TOWN logo in any banner (user, 2026-11-05, 0.14.13; MOCHA first in 0.14.11): X-CONSOLE from the far left
    nx = 18   # 16 + LOGO_WH[0] + 18 = 138 with the logo
    name = 'text cx=%d cy=%d label="%s" size=%s weight=700 spacing=4 align=left color=%s'
    # every banner, every preset, future ones too (user, 2026-11-04, 0.12.3): X-CONSOLE 35 px, "X-" with a 1 px white stroke
    # (so "X-" is always its own text); a theme may still override with title_size / x_stroke
    for m, cond in per_model(page, "x"):   # a coloured "X-": "X-" is 28.3 px in Titillium Bold 30 px, + 2 x 4 spacing
        t = theme(m, page, "x") or (SETUP_LOOK if page == "SETUP" else None) or {}
        ts = t.get("title_size", TITLE_SIZE)   # 3.5: "X-" 33.0 px wide, + 2 x 4 spacing, so CONSOLE at +41
        tx = t.get("title_x", nx)   # a theme may start the title further left (MOCHA, 0.14.12)
        L.append(name % (tx, cy, "X-", ts, t.get("x", "ececf0")) + cond + " stroke=%s" % t.get("x_stroke", BANNER_STROKE))
        L.append(name % (tx + round(28.3 * ts / 3 + 8), cy, "CONSOLE", ts, t.get("title_col", "ececf0")) + cond)
    if page == "SETUP":   # "SETUP" on the right, blue (the SETUP X-'s), 28 px, white stroke (user, 2026-11-04, 0.12.4)
        for m, cond in per_model(page, "name"):   # per preset once the colours file changes it (0.21.0)
            t = theme(m, page, "name") or {}
            L.append('text cx=1256 cy=%d label="SETUP" size=%s weight=700 spacing=2 align=right color=%s stroke=%s'
                     % (cy, NAME_SIZE, t.get("name", SETUP_LOOK["x"]), t.get("name_stroke", BANNER_STROKE)) + cond)
        return
    key = PAGE_MODEL[page]
    for m in LISTS[key]:
        t = theme(m, page, "name")
        col = t["name"] if t else "96c8f0"
        L.append('text cx=1256 cy=%d label="%s" size=%s weight=700 spacing=2 align=right color=%s when=%s:%d stroke=%s'
                 % (cy, MODELS[m].upper(), (t or {}).get("name_size", NAME_SIZE), col, key, mopt(m, key), (t or {}).get("name_stroke", BANNER_STROKE)))


def tc_graph(gx, gy, prefix, label, m, top=0):
    """a transfer-curve graph in preset m's colours, its top-left at (gx, gy): the screen (grid, the 1:1 diagonal), the
    curve's columns and the axis numbers (input along the bottom, output up the left, dBFS; output up to `top`) (user,
    2026-11-03: after Softube's XL 9000 K strip)"""
    gw = TC_COLS * TC_W
    look = UT.tc_look(m, CUR_PAGE[0], top) + ("_x" if top else "")
    lv = tc_levels(top)
    art_line('art file="art/tc_screen_%s.svg" x=%d y=%d w=%d h=%d' % (look, gx, gy, gw, TC_H))
    lg = TC_LOGO_M.get(m) or TC_LOGO.get(TC_LOOK[m])
    if lg and not os.path.exists(os.path.join(HERE, lg)):
        lg = None   # public repo: no logo picture
    lg = UT.picture(m, UT.page_name(), "CURVE PICTURE", lg, (gw, TC_H))   # the user's picture, if the colours file sets one
    if lg:   # a maker's logo over the screen, under the curve (5% fade, so the grid shows through)
        art_line('art file="art/%s" x=%d y=%d w=%d h=%d' % (lg, gx, gy, gw, TC_H))
    tiles, art, nf = (tc_jtiles(lv), "tc_join_" + look, lv * len(TC_STEPS)) if GEN2 else (TC_TILES, "tc_col_" + look, lv)
    th = TC_H // tiles   # Gen2: sloped joins, one smooth line (0.8.2); Gen1: the stepped columns
    for i in range(TC_COLS):
        for t in range(tiles):
            meter(gx + TC_W * i + TC_W // 2, gy + t * th + th // 2, TC_W, th, "%s_%02d" % (prefix, i), "art/%s_t%d.png" % (art, t), nf)
            L[-1] += " maxstrip=56000" if GEN2 else ""
    for db in ((top,) if top else ()) + (0, -20, -40, -60):
        text(gx - 5, gy + 3 + (top - db) / (60.0 + top) * (TC_H - 6), ("+%d" % db) if db > 0 else str(db), 1.0, " align=right weight=600 opacity=0.8")
    for db in (0, -20, -40, -60):
        text(gx + (60 + db) / 60.0 * gw, gy + TC_H + 12, str(db), 1.0, " weight=600 opacity=0.8")
    text(gx + gw // 2, gy + TC_H + 30, label, 1.1, " opacity=0.7")


def frame(x, y, w, h, title):
    L.append('frame x=%d y=%d w=%d h=%d title="%s"' % (x, y, w, h, title))


def text(cx, cy, label, size=1.4, extra=""):
    L.append('text cx=%d cy=%d size=%s align=center label="%s"%s' % (cx, cy, size, label, extra))


# Knob caps follow the preset of the knob's section (user, 2026-11-03): brown unless listed below (key: model number).
# KNOB_PAGE_COLOURS overrides a knob on one page only (INPUT and OUTPUT sit on every page). INPUT and OUTPUT follow the PREAMP preset, PAN and WIDTH the COMP preset (they sit on its DRIVE page).
KNOB_COLOURS = {
    0: {"pre_color": "darkpink", "lc_freq": "black", "hc_freq": "grey",   # FLANNEL PREAMP (user, 2026-11-03)
        "sh_punch": "brown", "sh_sustain": "greybrown",                    # FLANNEL SHAPE (user, 2026-11-03)
        "gate_thr": "darkgreen", "gate_range": "darkgreen", "gate_ratio": "greygreen", "gate_hold": "lightgreen", "gate_rel": "lightgreen",
        "eq_lf_gain": "black", "eq_lf_freq": "darkgrey", "eq_lmf_gain": "darkblue", "eq_lmf_freq": "blue", "eq_lmf_q": "greyblue",   # FLANNEL EQ
        "eq_hmf_gain": "darkgreen", "eq_hmf_freq": "green", "eq_hmf_q": "greygreen", "eq_hf_gain": "darkpink", "eq_hf_freq": "pink",
        "cmp_thr": "darkblue", "cmp_ratio": "lightbluegrey", "cmp_att": "lightbluegrey", "cmp_rel": "lightbluegrey",   # FLANNEL COMP (user, 2026-11-03)
        "cmp_knee": "greyblue", "cmp_makeup": "greyblue", "cmp_sc_hpf": "black", "cmp_mix": "tanblack",
        "drv_amt": "brown", "drv_char": "pink", "out_pan": "lightblue", "out_width": "darkblue"},   # FLANNEL DRIVE = the GRANITE DRIVE (user, 2026-11-03)
    1: {"in_gain": "white", "out_vol": "red", "pre_color": "pink", "lc_freq": "black", "hc_freq": "grey",
        "sh_punch": "brown", "sh_sustain": "greybrown",
        "gate_thr": "darkgreen", "gate_range": "darkgreen", "gate_ratio": "greygreen", "gate_hold": "green", "gate_rel": "green",
        "eq_lf_gain": "darkbrown", "eq_lf_freq": "brown", "eq_lmf_gain": "darkblue", "eq_lmf_freq": "blue", "eq_lmf_q": "greyblue",
        "eq_hmf_gain": "darkgreen", "eq_hmf_freq": "green", "eq_hmf_q": "greygreen", "eq_hf_gain": "darkpink", "eq_hf_freq": "pink",
        "cmp_att": "greypink", "cmp_ratio": "greypink", "cmp_knee": "brown", "cmp_rel": "greypink", "cmp_thr": "pink",
        "cmp_makeup": "brown", "cmp_mix": "tanbrown", "cmp_sc_hpf": "black",
        "drv_amt": "brown", "drv_char": "pink", "out_pan": "lightblue", "out_width": "darkblue"},
}
KNOB_PAGE_COLOURS = {
    (2, "EQ"): {"in_gain": "red", "out_vol": "red"},       # HEARTS's EQ page: INPUT and OUTPUT red (user, 2026-11-03)
    (2, "PREAMP"): {"in_gain": "red", "out_vol": "red"},   # and its PREAMP page
    (2, "SHAPE"): {"in_gain": "red", "out_vol": "red"},    # and SHAPE, COMP, DRIVE (0.7.6)
    (2, "COMP"): {"in_gain": "red", "out_vol": "red"},
    (2, "DRIVE"): {"in_gain": "red", "out_vol": "red"},
    (0, "SHAPE"): {"in_gain": "red", "out_vol": "white"},
    (0, "EQ"): {"in_gain": "red", "out_vol": "white"},
    (0, "COMP"): {"in_gain": "red", "out_vol": "white"},
    (0, "DRIVE"): {"in_gain": "red", "out_vol": "white"},   # GRANITE DRIVE colours, but INPUT/OUTPUT swapped (user, 2026-11-03)
    (0, "PREAMP"): {"in_gain": "red", "out_vol": "white"},
    **{(m, "SETUP"): {"in_gain": "red", "out_vol": "red"} for m in range(12)},
    **{(4, pg): {"in_gain": "brown", "out_vol": "brown"} for pg in ("PREAMP", "SHAPE", "EQ", "COMP", "DRIVE")},   # SANDSTONE INPUT/OUTPUT brown, white pointer (user, 2026-11-04, 0.10.3; light brown in 0.10.1-0.10.2)   # SANDSTONE: OUTPUT light brown, white pointer (user, 2026-11-04, 0.10.1)   # SETUP: INPUT and OUTPUT red whatever the preset (user, 2026-11-04, 0.9.5)   # FLANNEL: "on the PREAMP page" only; red cap = white pointer, white cap = red pointer
}


def knob_colour(m, key):
    return KNOB_PAGE_COLOURS.get((m, CUR_PAGE[0]), {}).get(key) or KNOB_COLOURS.get(m, {}).get(key, KNOB_DEFAULT.get(m, "brown"))


PAGE_MODEL = {"PREAMP": "in_model", "SHAPE": "sh_model", "EQ": "eq_model", "COMP": "cmp_model", "DRIVE": "cmp_model", "SETUP": "in_model"}
CUR_PAGE = [None]


def knob_model(key):
    """the preset parameter whose choice colours this knob. INPUT and OUTPUT follow the preset of the page they're on
    (user, 2026-11-03: "on the SHAPE page of the GRANITE preset, make the input gain knob white, Output knob is red")."""
    if key in ("in_gain", "out_vol"):
        return PAGE_MODEL.get(CUR_PAGE[0], "in_model")
    if key.startswith(("pre_", "lc_", "hc_", "flt_", "nz_")):   # nz_: the noise generator, on the PREAMP page (0.19.0)
        return "in_model"
    if key.startswith(("sh_", "gate_")):
        return "sh_model"
    if key.startswith("eq_"):
        return "eq_model"
    return "cmp_model"   # cmp_, drv_, out_pan, out_width


KNOB_LABELS = {(4, "eq_lmf_q"): "BW", (4, "eq_hmf_q"): "BW", (5, "eq_lmf_q"): "PROP Q", (5, "eq_hmf_q"): "PROP Q",
               (6, "cmp_ratio"): "MODE", (9, "cmp_thr"): "THRESHOLD", (11, "cmp_thr"): "THRESHOLD"}   # Mike-E: THRESHOLD (Softube's)   # MOLTEN: the Zener's COMP 1 / COMP 2 / LIMIT   # HEXX: the Q scales its proportional Q   # SANDSTONE: the EQF-100 says BANDWIDTH (0.10.0)
# ---- the user's colours (0.20.0 knobs; 0.21.0 every colour, user: "total control of all colors"): vst/colours.txt, read
# and checked by user_theme.py (see its docstring), rewritten in canonical form after each build
import user_theme as UT  # noqa: E402


def knob_name(m, key, label):
    """the knob's name in the colour file: its label under that preset; the EQ's GAIN / FREQ / Q get their band"""
    lab = KNOB_LABELS.get((m, key), label)
    p = key.split("_")
    if len(p) == 3 and p[0] == "eq" and p[1] in ("lf", "lmf", "hmf", "hf"):
        lab = "%s %s" % (p[1].upper(), lab)
    elif p[0] == "nz":   # the noise section's LEVEL
        lab = "NOISE " + lab
    return " ".join(lab.split()).upper()


def user_colour(m, key, label, col):
    return UT.knob(m, key, label, col)


def finish_colours():
    """after every page: the colours file checked and rewritten; the preview names for tools/colours-rebuild.sh"""
    UT.finish()
    # for tools/colours-rebuild.sh: which preset each preview picture shows (studio.py's page_<i>_mode<param>-<option>)
    pidx = {p["key"]: i for i, p in enumerate(PARAMS)}
    pages = []
    for name, _ql in TABS:
        page = {v: k for k, v in TAB_SHOWN.items()}.get(name, name)
        key = PAGE_MODEL[page] if page != "SETUP" else None
        pages.append({"name": name, "param": pidx[key] if key else None,
                      "presets": [MODELS[m].upper() for m in LISTS[key]] if key else []})
    json.dump(pages, open(os.path.join(HERE, "..", "preview-names.json"), "w"), indent=1)


KNOB_SIZES = (30, 40, 50)   # every knob is one of three sizes: each size x colour is a big filmstrip (0.5.3: 27 strips, 32 MB)


def knob(cx, cy, key, label, r=34, bw=130, vcase=None):
    r = min(KNOB_SIZES, key=lambda k: abs(k - r))
    base = 'knob cx=%d cy=%d r=%d key=%s bw=%d img=art/knob_%%s.png base=art/knob_scale.png label="%s"' % (cx, cy, r, key, bw, label)
    if vcase:   # 0.19.1: vcase=none, the value as the engine writes it ("dB"; MPC capitalises knob values otherwise)
        base += " vcase=" + vcase
    kk = knob_model(key)   # the preset parameter that colours it; only the presets in its list (0.15.0)
    models = [m for m in range(len(MODELS)) if in_list(m, kk) and (ACTIVE[0] is None or m in ACTIVE[0])]
    cols = [user_colour(m, key, label, knob_colour(m, key)) for m in models]   # the user's colour file first (0.20.0)
    inks = [UT.knob_ink(m) for m in models]   # the knob's name / value colours, if the colours file sets them (0.21.0)
    if ACTIVE[0] is None and len(set(cols)) == 1 and not any(inks):
        L.append(base % cols[0])
        return
    for m, col, ink in zip(models, cols, inks):   # one cap per preset; MPC shows the one the section's preset picks
        ln = base % col + (" ink=%s ink_dim=%s" % ink if ink else "") + " when=%s:%d" % (kk, mopt(m, kk))
        if (m, key) in KNOB_LABELS:     # a preset's own name for the knob (SANDSTONE: BW, the EQF-100's BANDWIDTH)
            ln = ln.replace('label="%s"' % label, 'label="%s"' % KNOB_LABELS[(m, key)])
        L.append(ln)


def onbtn(cx, cy, key, label, kind=None):
    """A round push button with a blue LED, its name baked in under it (the hardware's section ON buttons). kind="on" (a
    section ON: white under a theme with "on") or "switch" (another switch: the theme's "switch" colour)."""
    line = 'toggle cx=%d cy=%d key=%s ns=0 bw=84 img=art/btn_off.svg img_on=art/%%s w=56 h=56 label="%s"' % (cx, cy, key, label)
    page = CUR_PAGE[0]
    for m, cond in (per_model(page, kind) if kind else [(None, "")]):
        t = theme(m, page, kind) if kind else None
        img = "btn_on.svg" if not t else t.get("on_img", "btn_on_white.svg") if kind == "on" else "btn_on_%s.svg" % t["switch"]
        L.append(line % img + cond)
    text(cx, cy + 44, label)


def gseg(cx, cy, w, key, label, options, sh=40):
    """seg() whose lit segment takes the page theme's colour (segs) (user, 2026-11-03)"""
    page = CUR_PAGE[0]
    for m, cond in per_model(page, "segs"):
        seg(cx, cy, w, key, label, options, sh)
        t = theme(m, page, "segs")
        L[-1] += (" seg_on=%s" % t["segs"] if t else "") + (" seg_tx=%s" % t["segs_tx"] if t and "segs_tx" in t else "") + cond


def seg(cx, cy, w, key, label, options, sh=40):
    names = options.split(",")
    L.append('enum_h cx=%d cy=%d sw=%d sh=%d key=%s label="%s" options="%s"' % (cx, cy, w // len(names), sh, key, label, options))


def popup(cx, cy, w, key, label, options):
    L.append('popup cx=%d cy=%d w=%d h=48 key=%s label="%s" options="%s"' % (cx, cy, w, key, label, options))


def meter(cx, cy, w, h, key, strip, frames):
    L.append('meter cx=%d cy=%d w=%d h=%d key=%s strip=%s frames=%d' % (cx, cy, w, h, key, strip, frames))


# ---------------------------------------------------------------- the parameters (engine mapping lives here)
# PREAMP, SHAPE, EQ and COMP each have a preset: the model whose circuit that section follows, picked on the
# SETUP page. COMP's preset also sets DRIVE (user, 2026-11-02: DRIVE has no preset of its own). The first (and so far only) model is the FLANNEL, from SSL's published 9000-series figures (Super 9000
# User Guide, pp. 8-22; refdocs in ~/mpc-dev/refdocs). Controls the model doesn't have (marked "extra") keep working on
# top of it. Ranges below are the FLANNEL's; a later model brings its own table (src/param_table.h carries model 0's).
# Thresholds: console dB shown as dBFS with 0 dBu = -20 dBFS (bx_console's calibration).
MODELS = ["FLANNEL", "GRANITE", "HEARTS", "SUEDE", "SANDSTONE", "HEXX", "MOLTEN", "SPADES", "MOCHA",
          "TITANIUM", "TITANIUM EQ", "TITANIUM DRIVE"]   # 9-11: Empirical Labs (0.16.0)   # HEARTS: Weiss's, was HEARTS (0.7.0)   # model numbers: the order they were added (MODEL_SPECS, KNOB_COLOURS, m_eqlook use these)
# The SETUP drop-downs list the presets alphabetically (user, 2026-11-03: "always display in alphabetical order"), so a
# preset parameter's value is the model's place in that list; the engine maps it back (MODEL_BY_OPT in param_table.h).
MODEL_ORDER = sorted(range(len(MODELS)), key=lambda m: MODELS[m].lower())   # list place -> model number
# Which SETUP lists a preset is in (user, 2026-11-05, 0.15.0: "only if i can have them show up in their respective
# component list"): a channel strip is in all four; a single unit (a preamp, a shape unit such as a gate, an EQ, a
# compressor) only in its own section's list (a unit with two sections, e.g. a preamp with an EQ: both). A model not
# named in MODEL_SECTIONS is a channel strip. The COMPRESSOR list's preset also sets DRIVE.
PRESET_KEYS = ("in_model", "sh_model", "eq_model", "cmp_model")   # PREAMP, SHAPE, EQ, COMPRESSOR (+ DRIVE)
MODEL_SECTIONS = {   # model number -> the preset keys of the lists it's in (user, 2026-11-05, 0.16.0)
    10: ("sh_model", "eq_model"),   # TITANIUM EQ: the Lil FrEQ's DS section (SHAPE) and its EQ
    11: ("cmp_model",),             # TITANIUM DRIVE: the Mike-E's CompSat (COMPRESSOR, and so DRIVE)
}
DS_MODELS = {9, 10}   # SHAPE is the Lil FrEQ's de-esser / HF limiter under these (its own SHAPE layout)
for _m, _ks in MODEL_SECTIONS.items():
    assert _ks and set(_ks) <= set(PRESET_KEYS), (_m, _ks)


def in_list(m, key):
    """is model m in that preset parameter's drop-down?"""
    return key in MODEL_SECTIONS.get(m, PRESET_KEYS)


LISTS = {k: [m for m in MODEL_ORDER if in_list(m, k)] for k in PRESET_KEYS}   # each drop-down: place -> model number
LIST_OPTS = {k: [MODELS[m] for m in LISTS[k]] for k in PRESET_KEYS}
assert all(0 in LISTS[k] for k in PRESET_KEYS), "the FLANNEL (every list's default) must stay a channel strip"


# 0.17.0 (user, 2026-11-05): a CHANNEL STRIP drop-down with the channel strips only; each section's drop-down lists STRIP
# (= that section follows the channel strip) then its single units. They set the preset parameters above, which stay
# the model each section runs (every when=<key>:N picture follows those), so they're no longer on the SETUP page.
STRIPS = [m for m in MODEL_ORDER if m not in MODEL_SECTIONS]                      # CHANNEL STRIP: place -> model number
UNITS = {k: [m for m in LISTS[k] if m in MODEL_SECTIONS] for k in PRESET_KEYS}    # a section's units (after STRIP)
UNIT_KEYS = {"in_model": "in_unit", "sh_model": "sh_unit", "eq_model": "eq_unit", "cmp_model": "cmp_unit"}
UNIT_OPTS = {k: ["STRIP"] + [MODELS[m] for m in UNITS[k]] for k in PRESET_KEYS}
assert 0 in STRIPS


def mopt(m, key):
    """model m's place in that preset parameter's drop-down (the parameter's value, what a skin when=key:N tests)"""
    return LISTS[key].index(m)


# Each later model's ranges and defaults where they differ from the FLANNEL's (the num()/opt() lines below). key: (min, max,
# taper, default) for a continuous control, or the default index for an option. Physical units as below.
# GRANITE (user, 2026-11-03): the SL 4000 E channel with the 242 "Black Knob" EQ, from the Waves SSL E-Channel manual
# (~/mpc-dev/refdocs/waves-ssl4000.txt) and the bx_console SSL 4000 E manual (bx4000e.txt). Not in either: the LF/HF bell
# Q (Waves: "calculated based on frequency"), the auto attack times, the console's colour (DRIVE) -> choices in the engine.
MODEL_SPECS = {
    1: {
        "in_gain": (-64, 12, "split", 0),  # INPUT GAIN -64..+12 dB, 0 at the centre (user 2026-11-10)                 # input trim +-18 dB
        "lc_freq": (16, 350, "off-log", None),          # HPF 16-350 Hz, 18 dB/oct (the slope default is already 18)
        "hc_freq": (3000, 22000, "top-off-log", None),  # LPF 3-22 kHz, 12 dB/oct
        "gate_mode": 1,                                 # the expander is the default mode, GATE the switch
        "eq_lf_gain": (-18, 18, "sym", 0),              # +-18 bell, +-16.5 shelf (the engine scales the shelf)
        "eq_hf_gain": (-18, 18, "sym", 0),
        "eq_lmf_gain": (-18, 18, "sym", 0),             # +-15 at Q 0.1 up to +-18 at Q 3.5 (the engine scales by Q)
        "eq_hmf_gain": (-18, 18, "sym", 0),
        "eq_lmf_q": (0.1, 3.5, "log", 1.0),             # Q 0.1-3.5
        "eq_hmf_q": (0.1, 3.5, "log", 1.0),
        "cmp_thr": (-40, -10, "lin", -10),              # threshold +10..-20 dBu (0 dBu = -20 dBFS, as the FLANNEL)
        "drv_char": (0, 100, "lin", 65),                # choice: the E's colour leans to the odd (3rd) side
    },
    # HEARTS (user, 2026-11-03): Weiss's digital Gambit units as a strip, after Softube's Gambit Series channel strip.
    # Figures: Weiss EQ1-MK2 and DS1-MK3 operating manuals (~/mpc-dev/refdocs/hearts/). No preamp, transient shaper or
    # saturation in Weiss gear: PREAMP is a clean input (the colour extras stay, off), SHAPE's expander takes the DS1's
    # scales, DRIVE is the DS1's safety limiter (DRIVE = pre-limiter gain, CHARACTER = limiter type, as the Gambit strip's
    # Character control). Choices are marked in the engine.
    2: {
        "in_gain": (-64, 12, "split", 0),  # INPUT GAIN -64..+12 dB, 0 at the centre (user 2026-11-10)               # choice: EQ1's overall gain tops out at +10 dB; 0 dB at the centre
        "lc_freq": (14, 1000, "off-log", None),         # EQ1 frequencies from 13.8 Hz; bottom = Off
        "lc_slope": 1,                                  # Gambit strip: 12 dB/oct low cut
        "hc_freq": (1000, 21000, "top-off-log", None),  # EQ1 up to 21.1 kHz; top = Off
        "hc_slope": 0,                                  # Gambit strip: 6 dB/oct high cut
        "gate_thr": (-60, 0, "lin", -40),               # DS1 threshold 0..-60 dB
        "gate_ratio": (1.05, 5, "log", 2),              # DS1 expansion down to 1:5
        "gate_hold": (1, 8000, "off-log", None),        # DS1 release delay, 20 us..8 s (bottom = Off)
        "gate_rel": (10, 8000, "log", 250),             # DS1 release up to 8 s
        "gate_mode": 1,                                 # an expander, not a gate
        "eq_lf_gain": (-39, 18, "split", 0),            # EQ1 boost -39..+18 dB, 0 at the knob's centre
        "eq_lmf_gain": (-39, 18, "split", 0),
        "eq_hmf_gain": (-39, 18, "split", 0),
        "eq_hf_gain": (-39, 18, "split", 0),
        "eq_lf_freq": (14, 21000, "log", 100),          # EQ1: every band covers 13.8 Hz..21.1 kHz
        "eq_lmf_freq": (14, 21000, "log", 500),
        "eq_hmf_freq": (14, 21000, "log", 2000),
        "eq_hf_freq": (14, 21000, "log", 8000),
        "eq_lmf_q": (0.2, 650, "log", 1.0),             # EQ1 Q 0.20..650
        "eq_hmf_q": (0.2, 650, "log", 1.0),
        "cmp_thr": (-60, 0, "lin", -20),                # DS1 threshold 0..-60 dB, no auto make-up
        "cmp_ratio": (0.2, 20, "lim-log", 2.5),         # DS1 1:5 (upward expansion) .. 1:1 .. 20:1, top = 1000:1 (Limit)
        "cmp_att": (0.02, 1000, "log", 1.0),            # DS1 attack from 20 us; no AUTO
        "cmp_rel": (10, 8000, "log", 250),              # DS1 release slow, up to 8 s (release fast is the engine's)
        "cmp_knee": (0, 1, "lin", 0),                   # DS1 soft-knee 0.0..1.0 (1.0: from 0 dBFS down to twice the threshold)
        "cmp_makeup": (0, 30, "lin", 0),                # DS1 gain make-up (manual)
        "cmp_det": 1,                                   # peak sensing
        "drv_amt": (0, 18, "lin", 0),                   # DS1 pre-limiter gain, dB. choice: up to +18
        "drv_char": (0, 100, "lin", 0),                 # limiter type: ORIGINAL, TYPE 1, TYPE 2 (thirds of the knob)
    },
    # SUEDE (user, 2026-11-03, 0.9.0): a 1073-style preamp and EQ with a 2254-style compressor, after Softube's British
    # Class A for Console 1. The hardware's switches are stepped, so these are too ("steps": the knob's travel in equal
    # zones, one a position; OFF / AUTO / LIMIT positions as named). Figures: 1073 HPF 50/80/160/300 Hz, LF 35/60/110/220 Hz,
    # mids 360 Hz-7.2 kHz (split over two overlapping mid bands, as Console 1's version), HF 12 kHz; 2254 ratio 1.5-6:1,
    # threshold -20..+10 dBu in 2 dB steps, attack 5 ms, recovery 400/800/1500 ms/AUTO (AMS Neve 2254/R); Softube's added
    # attack 10-30 ms and recovery 100/200 ms, the gate's DEPTH, OFF at the EQ bands' ends. Gains stay continuous.
    # Choices: gain +-16 LF/HF, +-18 mids (clone figures; no original spec found), the LPF positions, the gate's steps,
    # Hi Q = Q 2.0 (NORMAL 0.8), the input trim's 5 dB steps.
    3: {
        "in_gain": (-64, 12, "split", 0),  # INPUT GAIN -64..+12 dB, 0 at the centre (user 2026-11-10)     # choice: the 1073 line amp's 5 dB steps
        "pre_type": 2,                                                     # IRON: its transformers (PREAMP ON adds them)
        "lc_freq": ("steps", ["OFF", 50, 80, 160, 300], "OFF"),           # 1073 HPF, 18 dB/oct (the slope default)
        "hc_freq": ("steps", [6000, 8000, 10000, 12000, 18000, "OFF"], "OFF"),   # choice: Neve-style LPF positions, 12 dB/oct
        "gate_thr": ("steps", list(range(-60, -8, 2)), -40),              # choice: 2 dB steps, as the 2254's thresholds
        "gate_range": ("steps", list(range(0, 42, 2)), 0),                # DEPTH, 0 = inactive
        "gate_rel": ("steps", [50, 100, 200, 400, 800, 1500], 200),       # RECOVERY. choice: the positions
        "eq_lf_gain": (-16, 16, "sym", 0),
        "eq_hf_gain": (-16, 16, "sym", 0),
        "eq_lmf_gain": (-18, 18, "sym", 0),
        "eq_hmf_gain": (-18, 18, "sym", 0),
        "eq_lf_freq": ("steps", ["OFF", 35, 60, 110, 220], 110),
        "eq_lmf_freq": ("steps", ["OFF", 360, 700, 1600, 3200], 700),
        "eq_hmf_freq": ("steps", ["OFF", 1600, 3200, 4800, 7200], 3200),
        "eq_hf_freq": ("steps", [10000, 12000, 16000, "OFF"], 12000),     # 12 kHz is the 1073's; 10 and 16 added (choice)
        "eq_lmf_q": ("steps", [0.8, 2.0], 0.8),                           # NORMAL / HI Q
        "eq_hmf_q": ("steps", [0.8, 2.0], 0.8),
        "cmp_thr": ("steps", list(range(-40, -8, 2)), -20),               # -20..+10 dBu in 2 dB steps (0 dBu = -20 dBFS)
        "cmp_ratio": ("steps", [1.5, 2, 3, 4, 6, "LIMIT"], 3),            # 2254 ratios; the top = its limiter
        "cmp_att": ("steps", [5, 10, 20, 30], 5),                         # 5 ms the 2254's, the rest Softube's; FAST ATT 2 ms
        "cmp_rel": ("steps", [100, 200, 400, 800, 1500, "AUTO"], 400),
        "cmp_makeup": ("steps", list(range(0, 21)), 0),                   # GAIN, 1 dB steps (no auto make-up)
        "drv_char": (0, 100, "lin", 25),                                  # choice: class A leans to the 2nd harmonic
    },
    # SANDSTONE (user, 2026-11-04, 0.10.0): Summit Audio's EQF-100 Full Range Equalizer and TLA-100A Tube Leveling Amplifier,
    # after Softube's Summit Audio Grand Channel. Figures from the EQF-100 manual (~/mpc-dev/refdocs/sandstone/eqf100.pdf):
    # four bands of seven switched frequencies (band 1 33-390 Hz, 2 250 Hz-1.2 kHz, 3 1-5.6 kHz, 4 3.3-15 kHz), bandwidth
    # 0 (narrow) .. 10 (wide), LF/HF shelf or peak, high filter 8.2/12/18 kHz, low filter 22/47/82 Hz. TLA-100A: attack and
    # release FAST / MEDIUM / SLOW, release program dependent, soft knee, manual GAIN. The gate is the Grand Channel's BCA
    # gate (THRESHOLD / RECOVERY / DEPTH, as SUEDE's). Choices: gain +-15 dB (not in the manual), filter slopes 12 dB/oct,
    # BW 10..0 = Q 0.5..5, the attack/release times (0.5/5/30 ms, 50/300/1500 ms: a user's measured 180 us-100 ms and
    # 32 ms-1.5 s), the threshold range, default ratio 3:1.
    4: {
        "pre_type": 1,                                                    # TUBE: Summit's tube stages (PREAMP ON adds them)
        "lc_freq": ("steps", ["OFF", 22, 47, 82], "OFF"),                 # EQF-100 low filter
        "lc_slope": 1,                                                    # choice: 12 dB/oct
        "hc_freq": ("steps", [8200, 12000, 18000, "OFF"], "OFF"),         # EQF-100 high filter, 12 dB/oct (the slope default)
        "gate_thr": ("steps", list(range(-60, -8, 2)), -40),              # the Grand Channel's BCA gate (= SUEDE's)
        "gate_range": ("steps", list(range(0, 42, 2)), 0),                # DEPTH, 0 = inactive
        "gate_rel": ("steps", [50, 100, 200, 400, 800, 1500], 200),       # RECOVERY
        "eq_lf_gain": (-15, 15, "sym", 0),
        "eq_lmf_gain": (-15, 15, "sym", 0),
        "eq_hmf_gain": (-15, 15, "sym", 0),
        "eq_hf_gain": (-15, 15, "sym", 0),
        "eq_lf_freq": ("steps", [33, 56, 100, 180, 220, 270, 390], 180),
        "eq_lmf_freq": ("steps", [250, 330, 470, 560, 680, 820, 1200], 560),
        "eq_hmf_freq": ("steps", [1000, 1500, 1800, 2200, 2700, 3900, 5600], 2200),
        "eq_hf_freq": ("steps", [3300, 4700, 6800, 8200, 10000, 12500, 15000], 8200),
        "eq_lmf_q": (0.5, 5, "log", 0.5),                                 # shown as BANDWIDTH 10 (wide) .. 0 (narrow)
        "eq_hmf_q": (0.5, 5, "log", 0.5),
        "eq_lf_type": 1,                                                  # BELL (the Grand Channel's default)
        "eq_hf_type": 1,
        "cmp_thr": (-50, -10, "lin", -30),                                # the TLA's reduction, as a threshold
        "cmp_ratio": (1, 20, "lim-log", 3),
        "cmp_att": ("steps", [0.5, 5, 30], 30),                           # FAST / MEDIUM / SLOW (the Grand Channel starts on SLOW)
        "cmp_rel": ("steps", [50, 300, 1500], 300),                       # FAST / MEDIUM / SLOW, program dependent
        "cmp_makeup": (0, 24, "lin", 0),                                  # GAIN (no auto make-up)
    },
    # HEXX (user, 2026-11-04, 0.11.0): an HEXX console strip, after Softube's American Class A for Console 1 (the user's
    # screenshot: LF 100 Hz, LMF 240 Hz, HMF 5 kHz, HF 10 kHz, both ends BELL; ratio 1.5:1, attack 25 ms, release 1.3 s,
    # threshold +3 dBu; gate release 1.33 s). EQ: the 550B's four bands of seven switched frequencies, gain +-12 dB,
    # proportional Q (wider at small gains, narrower as the gain goes up; the engine). Compressor: 2500/527 ranges
    # (attack 0.03-30 ms, release 0.05-3 s, threshold -20..+10 dBu), manual output gain. Choices: gains continuous (the
    # 550B steps 2 dB), the Q knob a scale on the proportional Q (1.00 = HEXX's), AUTO knee 4 dB (the 2500's MED).
    5: {
        "pre_type": 2,                                                    # IRON: HEXX's output transformers (PREAMP ON adds them)
        "gate_rel": (100, 4000, "log", 1330),                             # the screenshot's 1.33 s
        "eq_lf_gain": (-12, 12, "sym", 0),
        "eq_lmf_gain": (-12, 12, "sym", 0),
        "eq_hmf_gain": (-12, 12, "sym", 0),
        "eq_hf_gain": (-12, 12, "sym", 0),
        "eq_lf_freq": ("steps", [30, 40, 50, 100, 200, 300, 400], 100),
        "eq_lmf_freq": ("steps", [75, 150, 180, 240, 500, 700, 1000], 240),
        "eq_hmf_freq": ("steps", [800, 1500, 3000, 5000, 8000, 10000, 12500], 5000),
        "eq_hf_freq": ("steps", [2500, 5000, 7000, 10000, 12500, 15000, 20000], 10000),
        "eq_lmf_q": (0.5, 2, "log", 1.0),                                 # PROP Q scale, 1.00 = HEXX's own
        "eq_hmf_q": (0.5, 2, "log", 1.0),
        "eq_lf_type": 1,                                                  # BELL (the screenshot's)
        "eq_hf_type": 1,
        "cmp_thr": (-40, -10, "lin", -17),                                # -20..+10 dBu (0 dBu = -20 dBFS); +3 dBu default
        "cmp_ratio": (1, 20, "lim-log", 1.5),
        "cmp_att": (0.03, 30, "log", 25),                                 # the 2500's 0.03-30 ms, no AUTO
        "cmp_rel": (50, 3000, "log", 1300),
        "cmp_makeup": (0, 20, "lin", 0),                                  # output gain (no auto make-up)
        "drv_char": (0, 100, "lin", 60),                                  # choice: discrete op-amps lean to the 3rd harmonic
    },
    # MOLTEN (user, 2026-11-04, 0.12.0): Chandler Limited's Curve Bender (EMI TG12345 MkIV-style EQ) and Zener Limiter
    # (EMI TG12413-style), after Softube's Chandler Limited Zener-Bender for Console 1 (the user's screenshot: LF 91 Hz,
    # LMF 1.2 kHz, HMF 3.6 kHz, HF 10 kHz, both ends BELL, filters Out, COMP 1, gate release 1.33 s). Figures: Softube's
    # Curve Bender manual (Bass 35-300 Hz, Presence 2 = LOW MID 0.3-3.6 kHz, Presence 1 = HIGH MID 0.8-8.1 kHz, Treble
    # 3.6-20 kHz, +-15 dB that narrows the bands, HPF 20-320 Hz and LPF 2-20 kHz at 6 dB/oct) and Zener Limiter manual
    # (COMP 1 2:1 slow, COMP 2 its curve with faster times, LIMIT fast; ATTACK 11 positions, RELEASE 21, OUTPUT +-10 dB
    # in 1 dB steps, side-chain filter 30-300 Hz). The times per position are a third-party manual's ranges (the
    # engine). Choices: gains continuous, LIMIT 8:1, AUTO knee 6 dB, attack default position 2 (the original EMI time;
    # the screenshot's 11 would be 570 ms in COMP 1), the LPF's 30 kHz position left out (above Nyquist at 44.1 kHz).
    6: {
        "pre_type": 2,                                                    # IRON: its transformers (PREAMP ON adds them)
        "lc_freq": ("steps", ["OFF", 20, 30, 40, 50, 60, 80, 100, 160, 200, 320], "OFF"),
        "lc_slope": 0,                                                    # 6 dB/oct
        "hc_freq": ("steps", [2000, 3000, 5000, 8100, 10000, 12000, 14000, 18000, 20000, "OFF"], "OFF"),
        "hc_slope": 0,                                                    # 6 dB/oct
        "gate_rel": (100, 4000, "log", 1330),                             # the screenshot's 1.33 s
        "eq_lf_gain": (-15, 15, "sym", 0),
        "eq_lmf_gain": (-15, 15, "sym", 0),
        "eq_hmf_gain": (-15, 15, "sym", 0),
        "eq_hf_gain": (-15, 15, "sym", 0),
        "eq_lf_freq": ("steps", [35, 50, 70, 91, 150, 200, 300], 91),                       # Bass
        "eq_lmf_freq": ("steps", [300, 400, 500, 800, 1200, 1800, 2800, 3600], 1200),       # Presence 2
        "eq_hmf_freq": ("steps", [800, 1200, 1800, 2800, 3600, 4200, 6500, 8100], 3600),    # Presence 1
        "eq_hf_freq": ("steps", [3600, 4200, 6500, 8100, 10000, 12000, 16000, 20000], 10000),   # Treble
        "eq_lmf_q": (0.5, 2, "log", 1.0),                                 # a scale on its gain-dependent width, 1.00 = its own
        "eq_hmf_q": (0.5, 2, "log", 1.0),
        "eq_lf_type": 1,                                                  # BELL (the screenshot's)
        "eq_hf_type": 1,
        "cmp_thr": (-40, -10, "lin", -20),
        "cmp_ratio": ("steps", [1, 2, 3], 1),                             # MODE: COMP 1, COMP 2, LIMIT
        "cmp_att": ("steps", list(range(1, 12)), 2),                      # ATTACK positions 1-11
        "cmp_rel": ("steps", list(range(1, 22)), 11),                     # RELEASE positions 1-21 (the screenshot's 11)
        "cmp_makeup": ("steps", list(range(-10, 11)), 0),                 # OUTPUT +-10 dB, 1 dB steps (no auto make-up)
        "cmp_sc_hpf": ("steps", ["OFF", 30, 50, 90, 150, 300], "OFF"),    # the Zener's side-chain filter
        "drv_char": (0, 100, "lin", 50),                                  # Softube: neutral at 12 o'clock
    },
    # SPADES (user, 2026-11-04, 0.13.0): the Avalon VT-737sp (Class A tube preamp, opto compressor, 4-band EQ), after UA's
    # Avalon VT-737 Tube Channel Strip (the user's link). Figures: Avalon's VT-737sp page (avalondesign.com/vt-737-sp):
    # HPF 30-140 Hz, 6 dB/oct; bass shelf 15/30/60/150 Hz +-24 dB; low mid 30-450 Hz and x10 300 Hz-4.5 kHz +-16 dB; high
    # mid 200 Hz-2.8 kHz and x10 2-28 kHz +-16 dB; hi/lo Q; treble shelf 10/15/20/32 kHz +-20 dB; opto compressor threshold
    # -30..+20 dB, ratio 1:1-20:1, attack 2-200 ms, release 100 ms-5 s. Choices: each mid's two ranges as one sweep (high mid
    # to 20 kHz), the treble's 32 kHz left out (above Nyquist), LO Q 0.7 / HI Q 2.0 (no figures), the threshold as -50..0
    # dBFS (0 dBu = -20 dBFS), manual make-up 0-20 dB, release program dependent (opto), AUTO knee 10 dB, DRIVE leaning 2nd.
    7: {
        "pre_type": 1,                                                    # TUBE: the 737's Class A tube stages (PREAMP ON adds them)
        "lc_freq": (30, 140, "off-log", None),                            # HPF 30-140 Hz, bottom = Off
        "lc_slope": 0,                                                    # 6 dB/oct
        "eq_lf_gain": (-24, 24, "sym", 0),
        "eq_lmf_gain": (-16, 16, "sym", 0),
        "eq_hmf_gain": (-16, 16, "sym", 0),
        "eq_hf_gain": (-20, 20, "sym", 0),
        "eq_lf_freq": ("steps", [15, 30, 60, 150], 60),                   # bass shelf
        "eq_lmf_freq": (30, 4500, "log", 300),                            # low mid, both ranges (x1 and x10)
        "eq_hmf_freq": (200, 20000, "log", 2000),                         # high mid, both ranges (x1 and x10), to 20 kHz
        "eq_hf_freq": ("steps", [10000, 15000, 20000], 15000),            # treble shelf (32 kHz left out)
        "eq_lmf_q": ("steps", [0.7, 2.0], 0.7),                           # LO Q / HI Q
        "eq_hmf_q": ("steps", [0.7, 2.0], 0.7),
        "cmp_thr": (-50, 0, "lin", -20),                                  # -30..+20 dB (0 dBu = -20 dBFS)
        "cmp_ratio": (1, 20, "log", 3),
        "cmp_att": (2, 200, "log", 10),                                   # 2-200 ms, no AUTO
        "cmp_rel": (100, 5000, "log", 500),                               # 100 ms-5 s, program dependent (opto)
        "cmp_makeup": (0, 20, "lin", 0),                                  # GAIN (no auto make-up)
        "drv_char": (0, 100, "lin", 30),                                  # choice: tubes lean to the 2nd harmonic
    },
    # MOCHA (user, 2026-11-04, 0.14.0): UA's LA-6176 Signature Channel Strip (the user's link): a 610-B tube preamp with
    # high and low shelving EQ into a 1176LN (or LA-2A; this preset takes the 1176, the 6176 hardware's). UA's pages
    # answered 429/403; figures from UA's 6176 manual (the user's PDF): preamp GAIN in 5 dB steps, 0 at the centre (-10..+10
    # read from its text); high shelf 4.5/7/10 kHz, low shelf 70/100/200 Hz, both -9, -6, -4.5, -3, -1.5, 0, +1.5, +3, +4.5,
    # +6, +9 dB; attack 20-800 us, release 50 ms-1.1 s; ratios 1, 4, 8, 12, 20, ALL. Choices: ALL as the list's Limit, the
    # 1176's INPUT as a threshold -40..-10 dBFS, OUTPUT 0-24 dB manual, AUTO knee 2 dB, mids left at the defaults (the 6176
    # has shelves only), DRIVE leaning 2nd (tubes).
    8: {
        "in_gain": (-64, 12, "split", 0),  # INPUT GAIN -64..+12 dB, 0 at the centre (user 2026-11-10)                     # INPUT GAIN +-64 dB (user 2026-11-10; +-24 earlier that day; was the 610 GAIN +-10, 5 dB steps before that)
        "pre_type": 1,                                                    # TUBE: the 610's tube stages (PREAMP ON adds them)
        "eq_lf_gain": ("steps", [-9, -6, -4.5, -3, -1.5, 0, 1.5, 3, 4.5, 6, 9], 0),   # the 6176's stepped boost/cut
        "eq_hf_gain": ("steps", [-9, -6, -4.5, -3, -1.5, 0, 1.5, 3, 4.5, 6, 9], 0),
        "eq_lf_freq": ("steps", [70, 100, 200], 100),                     # 610 low shelf (UA's manual)
        "eq_hf_freq": ("steps", [4500, 7000, 10000], 10000),              # 610 high shelf
        "cmp_thr": (-40, -10, "lin", -20),                                # the 1176's INPUT, as a threshold
        "cmp_ratio": ("steps", [1, 4, 8, 12, 20, "LIMIT"], 4),            # 6176 RATIO: 1 (colour, no reduction) .. 20, ALL
        "cmp_att": (0.02, 0.8, "log", 0.8),                               # 20-800 us
        "cmp_rel": (50, 1100, "log", 400),                                # 50 ms-1.1 s
        "cmp_makeup": (0, 24, "lin", 0),                                  # OUTPUT (no auto make-up)
        "drv_char": (0, 100, "lin", 30),                                  # choice: tubes lean to the 2nd harmonic
    },
}
# Empirical Labs (user, 2026-11-05, 0.16.0), after Softube's Empirical Labs Trak Pak for Console 1 (Console 1 User's Guide
# ch. 11, its panel shot) and the hardware manuals (~/mpc-dev/refdocs/empirical/: Lil FrEQ EL-Q Rev 14.3; Mike-E EL-9 read
# online). Softube publishes no ranges. TITANIUM: INPUT = the Lil FrEQ's 3rd-order high pass and a low pass made from it, both
# with a bump (the engine), no preamp colour; SHAPE = the Lil FrEQ's DS section (THRESHOLD = gate_thr, FREQUENCY = gate_hold,
# HF LIMITER = gate_fast; attack < 1 ms, release 0.04 s fixed); EQ = the Lil FrEQ: LF/HF SHELF its fixed 120 Hz / 4 kHz 6 dB/oct
# shelves (+-10 dB), BELL its LF/HF parametric bands, CUT a non-stepped cut, mids +-14 dB; COMP = the Mike-E: ratios 1:1
# (saturation only), 2:1 (20 dB knee), 4:1, 8:1, NUKE; attack 0.9-100 ms, release 50 ms-1 s (panel .05-.5 s, spec .15-1 s);
# DRIVE = its Warm/Toasty saturation (DRIVE 0-10). Choices: the ranges of THRESHOLD (-40..0), FREQUENCY (2-12 kHz), the mids
# (LMF 40 Hz-2.5 kHz, HMF 400 Hz-10 kHz), Q 0.5-10 (BW about 2 to 0.15 oct), threshold -50..0 dBFS, manual GAIN, DRIVE on at 3.0.
for _m in (9, 10):   # TITANIUM and TITANIUM EQ: SHAPE and EQ
    MODEL_SPECS[_m] = {
        "gate_thr": (-40, 0, "lin", -20),                                 # DS THRESHOLD
        "gate_hold": (2000, 12000, "log", 6000),                          # DS FREQUENCY ("start ... at 6KHz")
        "gate_fast": 0,                                                   # HF LIMITER off: the de-esser
        "eq_lf_gain": (-14, 14, "sym", 0),                                # PEQ +-14; the shelf +-10 (the engine scales it)
        "eq_lmf_gain": (-14, 14, "sym", 0),
        "eq_hmf_gain": (-14, 14, "sym", 0),
        "eq_hf_gain": (-14, 14, "sym", 0),
        "eq_lf_freq": (30, 600, "log", 120),                              # BELL / CUT; SHELF is fixed at 120 Hz
        "eq_lmf_freq": (40, 2500, "log", 700),                            # the panel shot's 705 Hz
        "eq_hmf_freq": (400, 10000, "log", 3400),                         # its 3.38 kHz
        "eq_hf_freq": (2000, 20500, "log", 4000),                         # BELL / CUT up to 20.5 kHz; SHELF fixed at 4 kHz
        "eq_lmf_q": (0.5, 10, "log", 0.7),                                # the panel shot's 0.7
        "eq_hmf_q": (0.5, 10, "log", 0.7),
    }
MODEL_SPECS[9].update({   # TITANIUM's INPUT: the Lil FrEQ's high pass and the new low pass, 18 dB/oct, non-stepped
    "lc_freq": (20, 500, "off-log", None), "lc_slope": 2,
    "hc_freq": (2000, 20000, "top-off-log", None), "hc_slope": 2,
})
for _m in (9, 11):   # TITANIUM and TITANIUM DRIVE: COMPRESSOR and DRIVE
    MODEL_SPECS.setdefault(_m, {}).update({
        "cmp_thr": (-50, 0, "lin", -20),
        "cmp_ratio": ("steps", [1, 2, 4, 8, "LIMIT"], 4),                  # 1:1, 2:1, 4:1, 8:1, NUKE
        "cmp_att": (0.9, 100, "log", 8),                                  # continuous (Trak Pak), the panel's .9-100 ms
        "cmp_rel": (50, 1000, "log", 100),
        "cmp_makeup": (0, 24, "lin", 0),                                  # GAIN (no auto make-up)
        "drv_amt": (0, 100, "lin", 30),                                   # DRIVE 0-10, on at 3.0 (the unit's own colour)
        "drv_char": (0, 100, "lin", 35),                                  # choice: the triode stage leans to the 2nd harmonic
        "drv_on": 1,
    })
HEARTS_RED = "e0352b"   # HEARTS's red: the red #TOWN logo's (user, 2026-11-03); THEMES[2] uses it
KNOB_DEFAULT = {2: "black", 3: "bluegrey", 4: "gold", 5: "darkblue", 6: "darkred", 7: "black", 8: "lightbrown",
                9: "whiteblack", 10: "whiteblack", 11: "whiteblack"}   # Empirical Labs: white caps, black pointers (user, 0.16.0)
# MOCHA: light brown caps, white pointers (user, 0.14.1: light brown theme; dark grey 0.14.0); the extras and Qs dark brown (my choice)
KNOB_COLOURS[8] = {k: "darkbrown" for k in ("pre_color", "sh_punch", "sh_sustain", "gate_ratio", "gate_hold", "eq_lmf_q", "eq_hmf_q",
                                        "cmp_knee", "cmp_mix", "cmp_sc_hpf", "out_pan", "out_width")}
KNOB_COLOURS[8].update({   # the user's list (2026-11-04, 0.14.2); not listed (FREQs, PUNCH, EXP RATIO, KNEE, ...) stay as 0.14.1
    "in_gain": "tanblack", "out_vol": "lightred",                                # INPUT tan / black; OUTPUT light red / white
    "pre_color": "darkpink", "lc_freq": "blacklightbrown",                       # COLOR dark pink / white; LOW CUT black / light brown
    "sh_sustain": "lightbrown", "gate_hold": "lightbrown",                       # SUSTAIN, HOLD light brown / white
    **{k: "darkbrown" for k in ("eq_lf_gain", "eq_lmf_gain", "eq_hmf_gain", "eq_hf_gain")},   # EQ gains dark brown / white
    "eq_lmf_q": "whitedarkbrown", "eq_hmf_q": "whitedarkbrown",                  # Qs white / dark brown
    "cmp_sc_hpf": "blacklightbrown", "cmp_mix": "darkgrey",                      # S/C HPF black / light brown; WET/DRY grey / white
    "cmp_thr": "whitedarkbrown",                                                 # COMPRESSION white / dark brown
    "drv_amt": "brown", "drv_char": "pink",                                      # DRIVE brown / white; CHARACTER pink / white
    "out_pan": "lightblue", "out_width": "darkblue",                             # PAN light blue / white; WIDTH dark blue / white
})
# SPADES: black caps with white pointers (user, 2026-11-04, 0.13.1: black theme; silver 0.13.0); the extras and Qs dark grey (my choice)
KNOB_COLOURS[7] = {k: "darkgrey" for k in ("pre_color", "sh_punch", "sh_sustain", "gate_ratio", "gate_hold", "eq_lmf_q", "eq_hmf_q",
                                          "cmp_knee", "cmp_mix", "cmp_sc_hpf", "out_pan", "out_width")}
KNOB_COLOURS[7].update({   # the user's list (2026-11-05, 0.19.2); SETUP keeps red INPUT/OUTPUT, as every preset
    "in_gain": "grey", "out_vol": "red",                                         # INPUT grey / black; OUTPUT red / white
    "nz_level": "darkpink", "hc_freq": "whiteblack",                             # noise LEVEL dark pink / white; HIGH CUT white / black
    "cmp_thr": "whiteblack",                                                     # COMPRESSION white / black
    "drv_amt": "whiteblack", "drv_char": "pink",                                 # DRIVE white / black; CHARACTER pink / white
    "out_pan": "lightblueblack", "out_width": "darkblue",                        # PAN light blue / black; WIDTH dark blue / white
})
# MOLTEN (0.12.0): dark red caps; EQ frequencies black; the extras and Qs grey (my choice, the user revises)
KNOB_COLOURS[6] = {   # the user's list (2026-11-04, 0.12.4); the rest stay dark red (the default)
    "in_gain": "greyred", "out_vol": "darkred",                                  # INPUT light grey / red; OUTPUT dark red / white
    "pre_color": "whitedarkred", "lc_freq": "blacklightred",                     # COLOR white / dark red; LOW CUT black / light red
    "sh_punch": "darkred", "sh_sustain": "whitedarkred",                         # PUNCH dark red / white; SUSTAIN white / dark red
    "gate_ratio": "whitedarkred", "gate_hold": "darkred",                        # EXP RATIO white / dark red; HOLD dark red / white
    **{k: "lightred" for k in ("eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq")},   # FREQs light red / white
    "eq_lmf_q": "black", "eq_hmf_q": "black",                                    # Qs black / white
    "cmp_thr": "lightred", "cmp_knee": "darkred",                                # COMPRESSION light red / white; KNEE dark red / white
    "cmp_sc_hpf": "blacklightred", "cmp_mix": "whitedarkred",                    # S/C HPF black / light red; WET/DRY white / dark red
    "drv_amt": "darkbrown", "out_pan": "lightblueblack", "out_width": "darkblue",   # DRIVE dark brown / white; PAN light blue / black; WIDTH dark blue / white
}
# MOLTEN chicken-heads (user, 2026-11-05, 0.14.3: "use the following knobs on ALL Pages" + photo, black / red / dark grey;
# "map to the photo's 3"): the 0.12.4 list's reds -> red, black -> black, white, grey and the other colours -> dark grey
CH_MAP = {"darkred": "chred", "lightred": "chred", "blacklightred": "chblack", "black": "chblack",
          "greyred": "chgrey", "whitedarkred": "chgrey", "darkbrown": "chgrey", "lightblueblack": "chgrey", "darkblue": "chgrey"}
KNOB_COLOURS[6] = {k: CH_MAP[v] for k, v in KNOB_COLOURS[6].items()}
KNOB_DEFAULT[6] = "chred"                                            # the unlisted ones were dark red
KNOB_PAGE_COLOURS[(6, "SETUP")] = {"in_gain": "chred", "out_vol": "chred"}   # SETUP's red INPUT/OUTPUT, as chicken-heads
# HEXX (0.11.0): dark blue caps; EQ frequencies grey; the extras and Qs grey with a blue pointer
KNOB_COLOURS[5] = {k: "greyblue" for k in ("pre_color", "sh_punch", "sh_sustain", "gate_ratio", "gate_hold", "eq_lmf_q", "eq_hmf_q",
                                           "cmp_knee", "cmp_mix", "cmp_sc_hpf", "out_pan", "out_width")}
KNOB_COLOURS[5].update({k: "lightblue" for k in ("eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq")})   # user, 2026-11-04, 0.11.1
KNOB_COLOURS[5].update({k: "lightblueblack" for k in ("eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq")})   # user, 2026-11-04, 0.11.2: black pointers
KNOB_COLOURS[5].update({   # user, 2026-11-04, 0.11.2 (SETUP keeps red INPUT/OUTPUT, as for every preset)
    "in_gain": "lightblueblack", "out_vol": "red", "lc_freq": "blacklightblue", "sh_punch": "darkblue", "gate_hold": "darkblue",
    "cmp_thr": KNOB_COLOURS[5]["pre_color"], "cmp_sc_hpf": "blacklightblue", "cmp_knee": "darkblue",
    "cmp_makeup": KNOB_COLOURS[5]["eq_lmf_q"], "cmp_mix": "lightblueblack", "drv_amt": "brown", "drv_char": "pink",
    "out_pan": "lightblue", "out_width": "darkblue"})   # COMPRESSION = PREAMP COLOR's cap, MAKE-UP = LMF Q's (greyblue)
# SANDSTONE (0.10.0): gold caps with a black pointer; the extras and Qs black with a gold pointer
KNOB_COLOURS[4] = {k: "blackgold" for k in ("pre_color", "sh_punch", "sh_sustain", "gate_ratio", "gate_hold", "eq_lmf_q", "eq_hmf_q",
                                            "cmp_knee", "cmp_mix", "cmp_sc_hpf", "out_pan", "out_width")}
KNOB_COLOURS[4].update({k: "whitegold" for k in ("eq_lf_freq", "eq_lmf_freq", "eq_hmf_freq", "eq_hf_freq")})   # user, 2026-11-04, 0.10.5
KNOB_COLOURS[4].update({"pre_color": "pink", "lc_freq": "blackgold", "sh_sustain": "gold", "gate_hold": "gold",   # user, 2026-11-04, 0.10.6
                        "cmp_mix": "tanblack", "cmp_thr": "darkbrown", "cmp_knee": "gold", "drv_amt": "brown",
                        "drv_char": "pink", "out_pan": "lightblue", "out_width": "darkblue"})
KNOB_COLOURS[3] = {"in_gain": "red", "out_vol": "bluegrey",   # SUEDE: red gains and thresholds, blue-grey frequencies and times, grey Qs and extras
                   "pre_color": "red", "lc_freq": "bluegrey", "hc_freq": "bluegrey",
                   "sh_punch": "grey", "sh_sustain": "grey", "gate_thr": "red", "gate_range": "red", "gate_ratio": "grey", "gate_hold": "grey",
                   "eq_lf_gain": "red", "eq_lmf_gain": "red", "eq_hmf_gain": "red", "eq_hf_gain": "red", "eq_lmf_q": "grey", "eq_hmf_q": "grey",
                   "cmp_thr": "red", "cmp_makeup": "red", "cmp_knee": "grey", "cmp_mix": "grey", "cmp_sc_hpf": "grey",
                   "drv_amt": "red"}
KNOB_COLOURS[2] = {k: "white" for k in ("eq_lf_gain", "eq_lf_freq", "eq_lmf_gain", "eq_lmf_freq", "eq_lmf_q",
                                        "eq_hmf_gain", "eq_hmf_freq", "eq_hmf_q", "eq_hf_gain", "eq_hf_freq",
                                        "pre_color", "lc_freq", "hc_freq",   # + PREAMP's COLOR, LOW CUT, HIGH CUT
                                        "sh_punch", "sh_sustain", "gate_thr", "gate_range", "gate_ratio", "gate_hold", "gate_rel",
                                        "cmp_att", "cmp_ratio", "cmp_knee", "cmp_rel", "cmp_thr", "cmp_makeup", "cmp_mix", "cmp_sc_hpf",
                                        "drv_amt", "drv_char", "out_pan", "out_width")}   # + SHAPE, COMP, DRIVE (0.7.6): every HEARTS knob
# HEARTS's EQ knobs: white with a red pointer (the white cap's own) (user, 2026-11-03)   # a knob's cap where KNOB_COLOURS doesn't list it: the SSLs brown, Weiss's black (its hardware's)

# PREAMP: SuperAnalogue line trim and polarity, the filters; TAPE/TUBE/IRON is extra
opt("in_model", "Preamp Preset", LIST_OPTS["in_model"], mopt(0, "in_model"))
num("in_gain", "Input Gain", -64, 12, 0, "split", "dB")  # -64..+12 dB, all plugins (user 2026-11-10)                    # FLANNEL line trim +-20
opt("phase", "Phase Invert", ["Off", "On"])
opt("pre_on", "Preamp On/Off", ["Off", "On"])                                 # extra
opt("pre_type", "Preamp Type", ["TAPE", "TUBE", "IRON"])                  # extra
num("pre_color", "Preamp Color", 0, 100, 30, "lin", "%")                  # extra
num("lc_freq", "Low Cut Freq", 20, 500, None, "off-log", "Hz")                 # FLANNEL HPF 20-500 Hz, bottom = Off
opt("lc_slope", "Low Cut Slope", ["6", "12", "18", "24"], 2)              # FLANNEL: 18 dB/oct (others extra)
num("hc_freq", "High Cut Freq", 3000, 16000, None, "top-off-log", "Hz")        # FLANNEL LPF 3-16 kHz, top = Off
opt("hc_slope", "High Cut Slope", ["6", "12", "18", "24"], 1)             # FLANNEL: 12 dB/oct (others extra)
opt("flt_on", "Filters On/Off", ["Off", "On"], 1)
opt("flt_sc", "Filters To S/C", ["Off", "On"])                            # FLANNEL DYN S/C
# SHAPE: 9000-series gate/expander; PUNCH, SUSTAIN and the expander ratio are extra
opt("sh_model", "Shape Preset", LIST_OPTS["sh_model"], mopt(0, "sh_model"))
num("sh_punch", "Transient Punch", -100, 100, 0, "sym", "%")                        # extra
num("sh_sustain", "Transient Sustain", -100, 100, 0, "sym", "%")                    # extra
num("gate_thr", "Gate Threshold", -50, -10, -40, "lin", "dB")             # FLANNEL -30..+10 console dB
num("gate_range", "Gate Range", 0, 40, 0, "lin", "dB")                    # FLANNEL 0-40 dB, 0 = section inactive
num("gate_hold", "Gate Hold Time", 1, 4000, None, "off-log", "ms")             # FLANNEL 0-4 s
num("gate_rel", "Gate Release", 100, 4000, 300, "log", "ms")              # FLANNEL 0.1-4 s
opt("gate_mode", "Gate/Exp Mode", ["GATE", "EXP"])                            # FLANNEL: gate, or 2:1 expander
opt("gate_fast", "Gate Fast Attack", ["Off", "On"])                       # FLANNEL: 1.5 ms / 40 dB, fast 100 us / 40 dB
num("gate_ratio", "Expander Ratio", 1.2, 10, 2, "log", ":1")              # extra: FLANNEL is fixed 2:1
opt("sh_on", "Shape On/Off", ["Off", "On"])
# EQ: the 9000-series four bands, G (292) or E (242) curves
opt("eq_model", "Equalizer Preset", LIST_OPTS["eq_model"], mopt(0, "eq_model"))
EQ_BANDS = [("lf", "LF", 30, 450, 100, 19), ("lmf", "LMF", 200, 2500, 600, 20),
            ("hmf", "HMF", 600, 7000, 2000, 20), ("hf", "HF", 1500, 16000, 8000, 18.5)]
for b, name, flo, fhi, fdef, g in EQ_BANDS:
    # names 12+ characters: MPC's Q-Link displays add the track name to short ones (0.14.10, user)
    num("eq_%s_gain" % b, "%s Band Gain" % name, -g, g, 0, "sym", "dB")
    num("eq_%s_freq" % b, "%s Band Freq" % name, flo, fhi, fdef, "log", "Hz")
    if b in ("lmf", "hmf"):
        num("eq_%s_q" % b, "%s Q (Width)" % name, 0.5, 2.5, 1.0, "log", "")
opt("eq_style", "EQ Curve Style", ["G", "E"])                                   # G: variable-Q mids, overshoot shelves; E: constant Q
opt("eq_lf_type", "LF Band Type", ["SHELF", "BELL", "CUT"])                    # FLANNEL: bell (Q 2.5) in E only; CUT and G bells extra
opt("eq_hf_type", "HF Band Type", ["SHELF", "BELL", "CUT"])
opt("eq_on", "Equalizer On/Off", ["Off", "On"])
# COMP: 9000-series compressor/limiter (soft-knee RMS, or PK hard-knee peak; auto make-up). Attack/knee knobs are
# extra with AUTO (the model's own) at the bottom; make-up, wet/dry and S/C HPF are extra.
opt("cmp_model", "Compressor Preset", LIST_OPTS["cmp_model"], mopt(0, "cmp_model"))
num("cmp_thr", "Compression Level", -46, -16, -16, "lin", "dB")                 # FLANNEL +4..-26 console dB, auto make-up
num("cmp_ratio", "Compressor Ratio", 1, 20, 4, "lim-log", ":1")                      # FLANNEL 1:1 (off) .. limit at the top
num("cmp_rel", "Comp Release Time", 100, 4000, 300, "log", "ms")                    # FLANNEL 0.1-4 s
opt("cmp_fast", "Comp Fast Attack", ["Off", "On"])                        # FLANNEL: 3-30 ms program dependent, fast 3 ms
opt("cmp_det", "Comp Detector", ["RMS", "PEAK"])                               # FLANNEL PK: peak sensing, hard knee
num("cmp_att", "Comp Attack Time", 0.1, 100, None, "auto-log", "ms")                # extra, bottom = AUTO
num("cmp_knee", "Compressor Knee", 0, 24, None, "auto-lin", "dB")                    # extra, bottom = AUTO
num("cmp_makeup", "Comp Make-Up Gain", 0, 24, 0, "lin", "dB")                       # extra, on top of the auto make-up
num("cmp_mix", "Comp Wet/Dry Mix", 0, 100, 100, "lin", "%")                        # extra
num("cmp_sc_hpf", "S/C High Pass", 20, 500, None, "off-log", "Hz")        # extra
opt("cmp_on", "Compressor On", ["Off", "On"])
# DRIVE follows COMP's preset. The FLANNEL has no drive circuit (VHD came with the XL 9000 K), so under it DRIVE is
# extra: VHD-style, CHARACTER blending 2nd (valve) and 3rd (transistor) harmonics
num("drv_amt", "Drive Amount", 0, 100, 0, "lin", "%")
num("drv_char", "Drive Character", 0, 100, 50, "lin", "%")
opt("drv_on", "Drive On/Off", ["Off", "On"])
opt("drv_pos", "Drive Position", ["POST", "PRE"])                         # extra
# Output
num("out_pan", "Output Panning", -100, 100, 0, "sym", "")
num("out_width", "Stereo Width", 0, 200, 100, "lin", "%")
num("out_vol", "Output Volume", -60, 12, 0, "lin", "dB")                         # bottom = Off
ORDERS = ["SHP>EQ>CMP", "SHP>CMP>EQ", "EQ>SHP>CMP", "EQ>CMP>SHP", "CMP>SHP>EQ", "CMP>EQ>SHP"]
opt("order", "Section Order", ORDERS, 1)
PARAMS[-1]["qlink_ticks"] = 6   # 6 Q-Link events (or wheel clicks) per option; user, 2026-11-04 (4 in 0.10.7 too fast), 0.10.8
for _p in PARAMS:   # TITANIUM EQ's DS section: the engine names these (De-Ess Threshold, De-Ess Frequency, HF Limiter On/Off)
    if _p["key"] in ("gate_thr", "gate_hold", "gate_fast"):
        _p["dynamic_name"] = True
for _p in PARAMS:   # the SETUP preset lists: 6 Q-Link events per preset like ORDER (0.10.9)
    if _p["key"] in ("in_model", "sh_model", "eq_model", "cmp_model"):
        _p["qlink_ticks"] = 6
                                        # FLANNEL: dynamics before the EQ
opt("bypass", "Console Bypass", ["Off", "On"])
opt("sp_view", "Spectrum View", ["LINE", "BARS"])                         # display only: the spectrum as a line or as bars (user, 2026-11-03)
PK_HOLD_OPTS = ["Off", "1 s", "3 s", "6 s", "Infinite"]   # engine.c PK_HOLD_S matches; the skin button reads OFF,1s,3s,6s,∞
opt("pk_hold", "Peak Hold", PK_HOLD_OPTS)
opt("strip_sel", "Channel Strip", [MODELS[m] for m in STRIPS], STRIPS.index(0))   # 0.17.0: names 12+ characters (Q-Link displays)
for _k, _nm in (("in_model", "Preamp Section"), ("sh_model", "Shape Section"), ("eq_model", "Equalizer Section"), ("cmp_model", "Compressor Section")):
    opt(UNIT_KEYS[_k], _nm, UNIT_OPTS[_k], 0)
for _p in PARAMS:   # Q-Links: 6 events per entry, as the preset lists before (0.10.9)
    if _p["key"] == "strip_sel" or _p["key"].endswith("_unit"):
        _p["qlink_ticks"] = 6
# 0.18.0 (user, 2026-11-05): the NOISE page, P-Valley PNG's generator (src/noise.c). Its own ranges: the 0..100 knob
# positions noise.c maps (low cut Off/20 Hz-5 kHz, high cut 200 Hz-20 kHz/Off, release 5 ms-2 s, density 0.5-200 /s).
# Names 10+ characters (Q-Link displays). NOISE is Off by default, so a project saved before 0.18.0 sounds the same.
NZ_COLORS = ["Pink", "White", "Brown", "Blue", "Violet", "Grey", "Crackle"]   # noise.h's order
opt("nz_on", "Noise On/Off", ["Off", "On"], 0)
opt("nz_color", "Noise Color Type", NZ_COLORS, 0)
PARAMS[-1]["qlink_ticks"] = 6   # an option list on a Q-Link: 6 events per entry (user, 0.10.8)
num("nz_level", "Noise Level", -60, 0, -24, "lin", "dB")
# 0.19.0 (user): the NOISE page's DRY, LOW CUT, HIGH CUT, WIDTH, FOLLOW, RELEASE and DENSITY are gone (noise.c's defaults)
# Meters (engine-driven)
for k, n in (("m_in_l", "In L"), ("m_in_r", "In R"), ("m_out_l", "Out L"), ("m_out_r", "Out R")):
    meter_param(k, n, 0.0)
for k, n in (("m_pk_in_l", "Peak In L"), ("m_pk_in_r", "Peak In R"), ("m_pk_out_l", "Peak Out L"), ("m_pk_out_r", "Peak Out R")):
    meter_param(k, n, 0.0)                         # PEAK HOLD: the held peak, one lit segment over the LED bar (0 = none)
meter_param("m_gr", "Gain Reduction", 0.0)
meter_param("m_gate", "Gate Reduction", 0.0)
meter_param("m_shape", "Shape Gain", 0.5)          # the SHAPE section's gain change, -20..+20 dB (0.5 = 0) (GRANITE's meter, 0.8.0)
TC_COLS, TC_FRAMES, TC_W, TC_H = 60, 241, 5, 300    # transfer curves: 60 columns of 5 px; output -60..0 dBFS in 0.25 dB frames (user 2026-11-08: 1 dB frames stair-stepped the compressor's fractional slope, e.g. 4:1 = 0.25 dB/dB)
TC_TILES, TC_BAR = 2, 296                          # each column in 2 tiles of 150 px (Gen1's 12,288 px strips); the bars 296 px (41 frames)
TC_STEPS = [-160, -64, -32, -16, -8, -4, -3, -2, -1, 0, 1, 2, 3, 4, 8, 16, 32, 64, 160]   # Gen2 joins, in 0.25 dB LEVEL units to the right neighbour (fine near 0 for compressor slopes, 2026-11-08)
TC_LOOK = {0: "flannel", 1: "granite", 2: "hearts", 3: "suede", 4: "sandstone", 5: "hexx", 6: "molten", 7: "spades", 8: "mocha",
           9: "spades", 10: "spades", 11: "spades"}    # each preset's curve / meter colours (0.8.3)
# MOCHA (user, 2026-11-05, 0.18.1): the Universal Audio logo behind the SHAPE and COMP transfer curves
TC_LOGO = {"mocha": "tc_logo_mocha.png", "hexx": "tc_logo_hexx.png"}   # HEXX: its logo too (user, 2026-11-05, 0.19.0)
TC_LOGO_M = {7: "tc_logo_spades.png"}   # by preset: SPADES's Avalon Design logo (user, 0.19.2; Empirical Labs share its look)
TC_TOP_G = 12                                      # HEARTS's compressor graph: output up to +12 dBFS (its upward expansion)


def tc_levels(top):
    return TC_FRAMES + int(round(top * (TC_FRAMES - 1) / 60))   # frames from -60 to +top dBFS (top is dBFS; 0.25 dB frames, 2026-11-08)


def tc_jtiles(levels):
    """Gen2 tiles a column needs for `levels` x len(TC_STEPS) frames under ~56,000 px strips"""
    for jt in (5, 6, 10, 12, 15, 20, 25, 30, 50, 60):
        if levels * len(TC_STEPS) * (TC_H // jt) <= 56000:
            return jt
SHP_FRAMES = 41                                    # the SHAPE gain meter: -20..+20 dB in 1 dB frames
for i in range(TC_COLS):
    meter_param("gtc_%02d" % i, "Gate Curve %d" % (i + 1), 0.0)
for i in range(TC_COLS):
    meter_param("ctc_%02d" % i, "Comp Curve %d" % (i + 1), 0.0)
LOOKS = ["FLANNEL LINE", "FLANNEL BARS", "GRANITE LINE", "GRANITE BARS", "HEARTS LINE", "HEARTS BARS", "SUEDE LINE", "SUEDE BARS", "SANDSTONE LINE", "SANDSTONE BARS", "HEXX LINE", "HEXX BARS", "MOLTEN LINE", "MOLTEN BARS", "SPADES LINE", "SPADES BARS", "MOCHA LINE", "MOCHA BARS",
         "TITANIUM LINE", "TITANIUM BARS", "TITANIUM EQ LINE", "TITANIUM EQ BARS", "TITANIUM DRIVE LINE", "TITANIUM DRIVE BARS"]
opt("m_eqlook", "EQ Look", LOOKS)                  # kept by the engine (EQ preset x VIEW): a skin line takes one condition only
EQC_COLS, EQC_FRAMES, EQC_W = 44, 37, 16          # the live curve: 44 columns of 16 px, -18..+18 dB in 1 dB frames
for i in range(EQC_COLS):
    meter_param("eqc_%02d" % i, "EQ Curve %d" % (i + 1), 0.5)
SPC_FRAMES = 37                                    # spectrum levels: -72..0 dBFS in 2 dB steps, at the curve's 44 frequencies
SPC_JOIN = 3                                       # Gen2: each column also joins to its right neighbour, up to 3 levels away
SPC_JOINED = SPC_FRAMES * (2 * SPC_JOIN + 1)       # Gen2 frames: level x 7 + join + 3
for i in range(EQC_COLS):
    meter_param("spc_%02d" % i, "Spectrum %d" % (i + 1), 0.0)
for i in range(EQC_COLS):                          # PEAK HOLD: each column's held peak, a dash at its level (0 = none)
    meter_param("spk_%02d" % i, "Spectrum Peak %d" % (i + 1), 0.0)

LED_FRAMES, VU_FRAMES, GR_FRAMES = 31, 41, 25
Y0, HB = TOP + 42, H                # frames run the full height; content sits 42 px down from the top
EQ_GRAPH_H = 384                    # the EQ page's graph frame (the screen inside is EQ_SCREEN high)
EQ_SCREEN = (EQC_COLS * EQC_W, 330)  # 37 frames x 330 = 12,210 px: the tallest Gen1's 12,288 px strips allow
SP_TILES = 2                        # Gen2's joined spectrum (259 frames) is cut into 2 tiles of 165 px a column: 42,735 px strips
EQC_JOIN, EQC_TILES = 8, 5          # Gen2's sloped EQ curve: each column also carries its right neighbour (up to 8 dB away):
EQC_JOINED = EQC_FRAMES * (2 * EQC_JOIN + 1)   # 37 x 17 = 629 frames, in 5 tiles of 66 px a column (41,514 px strips)


METER_MARKS = (6, 0, -6, -12, -18, -24, -30, -36, -48, -60)


def sides():
    """IN meter + INPUT on the left, OUT meter + OUTPUT on the right, on every page."""
    for x0, title, kl, kr, key, label in ((8, "IN", "m_in_l", "m_in_r", "in_gain", "INPUT"),
                                          (1148, "OUT", "m_out_l", "m_out_r", "out_vol", "OUTPUT")):
        frame(x0, TOP, 124, H, title)
        # HEARTS's EQ page: white, then pink, red from 0 dBFS (user, 2026-11-03); everywhere else blue, white, orange
        for m, cond in per_model(CUR_PAGE[0], "meters"):
            t = theme(m, CUR_PAGE[0], "meters")
            suf = t["meters"] if t else SETUP_LOOK["meters"] if CUR_PAGE[0] == "SETUP" else ""
            for xx, k in ((x0 + 48, kl), (x0 + 76, kr)):
                meter(xx, TOP + 220, 14, 330, k, "art/led_bar%s.png" % suf, LED_FRAMES)
                L[-1] += cond
                meter(xx, TOP + 220, 14, 330, k.replace("m_", "m_pk_"), "art/led_pk%s.png" % suf, LED_FRAMES)   # held peaks over the bars
                L[-1] += cond
        knob(x0 + 62, TOP + 455, key, label, r=40, bw=120)
        bottom = TOP + 220 + 165
        for db in METER_MARKS:   # numbers left of the pair of bars, IN and OUT alike (OUT's were on the right until
            y = bottom - (db + 60) * 5   # the user's "move the numbers ... to the left side of the OUT meters", 2026-11-08)
            text(x0 + 37, y, ("+%d" % db) if db > 0 else str(db), 1.1, " align=right weight=600 opacity=0.85")


def ql(*keys):
    """A page's Q-Links, left to right on the XL's row: INPUT always first, OUTPUT always last (user, 2026-11-02)."""
    return ",".join(("in_gain",) + keys + ("out_vol",))


# ---------------------------------------------------------------- pages
def gpopup(cx, cy, w, key, label, options):
    """a drop-down in the page theme's ORDER colours (accent, own list, field/list ink); presets without one share a plain list"""
    page, plain = CUR_PAGE[0], 0
    for m, cond in per_model(page, "order"):
        popup(cx, cy, w, key, label, options)
        t = theme(m, page, "order")
        if t:
            L[-1] += " accent=%s opens=%s" % t["order"]
            L[-1] += (" field_ink=%s" % t["order_ink"] if t.get("order_ink") else "") + (" list_ink=%s" % t["order_list_ink"] if t.get("order_list_ink") else "")
        else:
            L[-1] += " list=none" if plain else ""
            plain += 1
        L[-1] += cond


tab("PREAMP", ql("pre_type", "pre_color", "phase", "pre_on", "lc_freq", "lc_slope", "hc_freq", "hc_slope", "flt_sc", "flt_on",
                 "nz_level", "nz_color", "nz_on"))
frame(MID_X0, TOP, 400, H, "TAPE / PREAMP")
gseg(336, Y0 + 90, 330, "pre_type", "TYPE", "TAPE,TUBE,IRON")
knob(336, Y0 + 210, "pre_color", "COLOR", r=52, bw=180)
onbtn(236, Y0 + 385, "phase", "PHASE INV", kind="switch")
onbtn(436, Y0 + 385, "pre_on", "ON", kind="on")
frame(MID_X0 + 404, TOP, 380, H, "FILTER")          # 0.19.0: 380 wide (was the rest of the page), NOISE beside it
knob(630, Y0 + 105, "lc_freq", "LOW CUT", r=50, bw=170)
gseg(630, Y0 + 260, 168, "lc_slope", "SLOPE", "6,12,18,24")
knob(830, Y0 + 105, "hc_freq", "HIGH CUT", r=50, bw=170)
gseg(830, Y0 + 260, 168, "hc_slope", "SLOPE", "6,12,18,24")
text(730, Y0 + 306, "dB / OCT", 1.3)
onbtn(640, Y0 + 385, "flt_sc", "TO S/C", kind="switch")
onbtn(820, Y0 + 385, "flt_on", "ON", kind="on")
# 0.19.0 (user, 2026-11-05): "a simpler Noise Generator with a level knob, an ON switch/toggle, and selectable waveforms in
# dropdown menu. This is a gain staging tool so put it on the PREAMP PAGE". The noise joins after INPUT, before the preamp.
NZ_X = MID_X0 + 788 + (MID_X1 - MID_X0 - 788) // 2
frame(MID_X0 + 788, TOP, MID_X1 - MID_X0 - 788, H, "NOISE")
gpopup(NZ_X, Y0 + 90, 190, "nz_color", "WAVEFORM", ",".join(c.upper() for c in NZ_COLORS))
knob(NZ_X, Y0 + 250, "nz_level", "LEVEL", r=50, bw=170, vcase="none")   # "-24.0 dB", not "DB" (user, 0.19.1)
onbtn(NZ_X, Y0 + 385, "nz_on", "ON", kind="on")

tab("SHAPE", ql("sh_punch", "sh_sustain", "gate_thr", "gate_range", "gate_hold", "gate_rel", "gate_ratio", "gate_mode", "gate_fast", "sh_on"))
GATE_M = [m for m in LISTS["sh_model"] if m not in DS_MODELS]   # the transient shaper and gate
DS_M = [m for m in LISTS["sh_model"] if m in DS_MODELS]         # the Lil FrEQ's DS section (0.16.0)
only(GATE_M, frame, MID_X0, TOP, 380, H, "TRANSIENT")
only(GATE_M, knob, 326, Y0 + 105, "sh_punch", "PUNCH", r=50, bw=170)
only(GATE_M, knob, 326, Y0 + 290, "sh_sustain", "SUSTAIN", r=50, bw=170)
only(GATE_M, frame, MID_X0 + 384, TOP, MID_X1 - MID_X0 - 384, H, "GATE / EXPANDER")
only(DS_M, frame, MID_X0, TOP, 380, H, "DE-ESSER")
only(DS_M, knob, 326, Y0 + 105, "gate_thr", "THRESHOLD", r=50, bw=170)
only(DS_M, knob, 326, Y0 + 290, "gate_hold", "FREQUENCY", r=50, bw=170)
only(DS_M, frame, MID_X0 + 384, TOP, MID_X1 - MID_X0 - 384, H, "HF LIMITER")
only(DS_M, onbtn, 1036, Y0 + 195, "gate_fast", "HF LIMITER", kind="switch")
# every preset (0.8.3; the GRANITE's from 0.8.0): a transfer curve and the SHAPE gain meter (-20..+20 dB) on the left of
# the frame, the knobs smaller on the right; the curve and the meter in the preset's colour
for m in LISTS["sh_model"]:
    only([m], tc_graph, 552, Y0 + 20, "gtc", "INPUT  dBFS", m)
    only([m], meter, 880, Y0 + 170, 24, TC_BAR, "m_shape", "art/shape_bar_%s.png" % UT.tc_look(m, "SHAPE"), SHP_FRAMES)
text(880, Y0 + 336, "GAIN", 1.2)
for db, yy in ((20, 0), (0, 150), (-20, 300)):
    text(898, Y0 + 20 + yy + 3, ("+%d" % db) if db > 0 else str(db), 1.0, " align=left weight=600 opacity=0.8")
only(GATE_M, knob, 985, Y0 + 60, "gate_thr", "THRESHOLD", r=30, bw=100)
only(GATE_M, knob, 1088, Y0 + 60, "gate_range", "RANGE", r=30, bw=100)
only(GATE_M, knob, 985, Y0 + 195, "gate_ratio", "EXP RATIO", r=30, bw=100)
only(GATE_M, knob, 1088, Y0 + 195, "gate_hold", "HOLD", r=30, bw=100)
only(GATE_M, knob, 985, Y0 + 330, "gate_rel", "RELEASE", r=30, bw=100)
only(GATE_M, gseg, 640, Y0 + 418, 150, "gate_mode", "MODE", "GATE,EXP", sh=40)   # under the graph
only(GATE_M, onbtn, 790, Y0 + 408, "gate_fast", "FAST ATT", kind="switch")
onbtn(880, Y0 + 408, "sh_on", "ON", kind="on")

tab("EQ", ql("eq_lf_gain", "eq_lf_freq", "eq_lf_type", "eq_lmf_gain", "eq_lmf_freq", "eq_lmf_q", "eq_hmf_gain", "eq_hmf_freq", "eq_hmf_q",
             "eq_hf_gain", "eq_hf_freq", "eq_hf_type", "eq_style", "eq_on"))
frame(MID_X0, TOP, MID_X1 - MID_X0, EQ_GRAPH_H, "EQUALIZER")
SY = TOP + 44                                      # the screen's top
SX = MID_X0 + 44                                   # its left edge: the spectrum's dB scale sits to the left of it
L.append('art file="art/%s" x=%d y=%d w=%d h=%d' % (UT.eq_art(0, "eq_screen.svg"), SX, SY, EQ_SCREEN[0], EQ_SCREEN[1]))
def eq_layer(m, a):
    """one layer of preset m's EQ screen (screen, logo, grid): the logo is the user's picture or nothing if the file says so"""
    f = UT.eq_art(m, a)
    if a.startswith("eq_logo"):
        f = UT.picture(m, "EQ", "EQ PICTURE", f, EQ_SCREEN)
        if f and not os.path.exists(os.path.join(HERE, f)):
            f = None   # public repo: no logo picture
    if f:
        L.append('art file="art/%s" x=%d y=%d w=%d h=%d when=eq_model:%d' % (f, SX, SY, EQ_SCREEN[0], EQ_SCREEN[1], mopt(m, "eq_model")))


for a in ("eq_logo_flannel.png", "eq_grid.svg"):   # 0.14.6: Solid State Logic logo (user)   # FLANNEL: the #TOWN logo over the screen, the grid over the logo (user, 2026-11-03)
    eq_layer(0, a)
L.append('art file="art/%s" x=%d y=%d w=%d h=%d when=eq_model:%d' % (UT.eq_art(1, "eq_screen_black.svg"), SX, SY, EQ_SCREEN[0], EQ_SCREEN[1], mopt(1, "eq_model")))   # the GRANITE's: black
for a in ("eq_logo_flannel.png", "eq_grid_black.svg"):   # 0.14.6: Solid State Logic logo (user)   # GRANITE: the same #TOWN logo, placed as the FLANNEL's, its own grid over it (user, 2026-11-03)
    eq_layer(1, a)
for a in ("eq_screen_hearts.svg", "eq_logo_hearts.png", "eq_grid_hearts.svg"):   # 0.14.7: Weiss logo (user)   # HEARTS: its own screen, the logo, its grid
    eq_layer(2, a)
for a in ("eq_screen_suede.svg", "eq_logo_suede.png", "eq_grid_suede.svg"):   # 0.14.8: AMS Neve logo (user)     # SUEDE: blue-grey screen, the logo, its grid
    eq_layer(3, a)
for a in ("eq_screen_sandstone.svg", "eq_logo_sandstone.png", "eq_grid_sandstone.svg"):   # 0.14.7: Summit Audio logo (user)   # SANDSTONE: a warm black screen, gold grid
    eq_layer(4, a)
for a in ("eq_screen_hexx.svg", "eq_logo_hexx.png", "eq_grid_hexx.svg"):   # 0.14.8: HEXX logo (user)         # HEXX: a navy screen, dark blue grid
    eq_layer(5, a)
for a in ("eq_screen_molten.svg", "eq_logo_molten.png", "eq_grid_molten.svg"):   # 0.14.4: Chandler Limited logo (user)   # MOLTEN: a dark wine screen, dark red grid
    eq_layer(6, a)
for a in ("eq_screen_spades.svg", "eq_logo_spades.png", "eq_grid_spades.svg"):   # 0.14.9: Avalon Design logo (user)   # SPADES: a black screen, dark grey grid (0.13.1)
    eq_layer(7, a)
for a in ("eq_screen_mocha.svg", "eq_logo_mocha.png", "eq_grid_mocha.svg"):   # 0.14.5: Universal Audio logo (user)   # MOCHA: a dark brown screen, brown grid (0.14.1)
    eq_layer(8, a)
for _m in (9, 10):   # TITANIUM, TITANIUM EQ: SPADES's black screen, the Empirical Labs logo (user, 0.16.1), the grid
    for a in ("eq_screen_spades.svg", "eq_logo_titanium.png", "eq_grid_spades.svg"):
        eq_layer(_m, a)
for db in (0, -12, -24, -36, -48, -60, -72):       # the spectrum's scale (dBFS), as YES-SL 9000's
    text(SX - 6, SY + 3 + (-db) / 72.0 * (EQ_SCREEN[1] - 6), str(db), 1.0, " align=right weight=600 opacity=0.8")
for i in range(EQC_COLS):   # the output's spectrum first, so the curve draws over it
    cx = SX + EQC_W * i + EQC_W // 2
    # two looks on the same values, VIEW picks one: LINE (Gen2 sloped, Gen1 steps) or BARS (separate bars, the 0.2.0 look);
    # the bars' strips have the same frames as the line's, so the engine needn't know which one shows
    # the GRANITE's in brown (user, 2026-11-03): four looks, m_eqlook = EQ preset x 2 + VIEW
    if GEN2:
        th = EQ_SCREEN[1] // SP_TILES
        for look, art in enumerate(UT.sp_arts(True)):   # 9-11: SPADES's white
            for t in range(SP_TILES):
                L.append('meter cx=%d cy=%d w=%d h=%d key=spc_%02d strip=art/%s_t%d.png frames=%d maxstrip=56000 when=m_eqlook:%d'
                         % (cx, SY + t * th + th // 2, EQC_W, th, i, art, t, SPC_JOINED, look))
    else:
        for look, art in enumerate(UT.sp_arts(False)):
            meter(cx, SY + EQ_SCREEN[1] // 2, EQC_W, EQ_SCREEN[1], "spc_%02d" % i, "art/%s.png" % art, SPC_FRAMES)
            L[-1] += " when=m_eqlook:%d" % look
for i in range(EQC_COLS):   # PEAK HOLD: a dash at each column's held peak, over both views (the GRANITE's in tan)
    cx = SX + EQC_W * i + EQC_W // 2
    for m, art in UT.pk_arts():
        if not in_list(m, "eq_model"):
            continue
        meter(cx, SY + EQ_SCREEN[1] // 2, EQC_W, EQ_SCREEN[1], "spk_%02d" % i, "art/%s.png" % art, SPC_FRAMES)
        L[-1] += " when=eq_model:%d" % mopt(m, "eq_model")
for i in range(EQC_COLS):   # the live curve (EQ + filters) over the screen, one filmstrip column per frequency
    cx = SX + EQC_W * i + EQC_W // 2
    for m, cond in per_model("EQ", "curve"):   # white under a theme with "curve" (HEARTS, GRANITE), else light blue
        t = theme(m, "EQ", "curve")
        suf = t.get("curve", "_white") if t else ""
        if GEN2:   # sloped: drawn from its level to its right neighbour's, so the columns join into one line
            th = EQ_SCREEN[1] // EQC_TILES
            for t in range(EQC_TILES):
                L.append('meter cx=%d cy=%d w=%d h=%d key=eqc_%02d strip=art/eq_join%s_t%d.png frames=%d maxstrip=56000%s'
                         % (cx, SY + t * th + th // 2, EQC_W, th, i, suf, t, EQC_JOINED, cond))
        else:
            meter(cx, SY + EQ_SCREEN[1] // 2, EQC_W, EQ_SCREEN[1], "eqc_%02d" % i, "art/eq_col%s.png" % suf, EQC_FRAMES)
            L[-1] += cond
gseg(1019, TOP + 104, 220, "sp_view", "VIEW", "FFT,BARS", sh=40)            # the spectrum's look, top right of the graph
gseg(1019, TOP + 214, 220, "pk_hold", "PEAK HOLD", "OFF,1s,3s,6s,∞", sh=40)   # held peaks: IN/OUT meters and the spectrum
seg(952, SY + EQ_SCREEN[1] - 22, 120, "eq_style", "STYLE", "G,E", sh=40)    # level with the bottom of the spectrum (user, 2026-11-03)
L[-1] += " when=eq_model:%d" % mopt(0, "eq_model")                         # only the FLANNEL has G/E; the GRANITE's 242 EQ is E only
text(952, SY + EQ_SCREEN[1] - 22, "GRANITE", 1.3, " weight=700 when=eq_model:%d" % mopt(1, "eq_model"))
text(952, SY + EQ_SCREEN[1] - 22, "HEARTS", 1.3, " weight=700 when=eq_model:%d" % mopt(2, "eq_model"))   # constant Q, no G/E
text(952, SY + EQ_SCREEN[1] - 22, "CLASS A", 1.3, " weight=700 when=eq_model:%d" % mopt(3, "eq_model"))   # SUEDE: no G/E
text(952, SY + EQ_SCREEN[1] - 22, "SANDSTONE", 1.3, " weight=700 when=eq_model:%d" % mopt(4, "eq_model"))   # SANDSTONE: no G/E
text(952, SY + EQ_SCREEN[1] - 22, "HEXX", 1.3, " weight=700 when=eq_model:%d" % mopt(5, "eq_model"))      # HEXX: no G/E
text(952, SY + EQ_SCREEN[1] - 22, "MOLTEN", 1.3, " weight=700 when=eq_model:%d" % mopt(6, "eq_model"))   # MOLTEN: the Curve Bender's EMI model
text(952, SY + EQ_SCREEN[1] - 22, "SPADES", 1.3, " weight=700 when=eq_model:%d" % mopt(7, "eq_model"))  # SPADES
text(952, SY + EQ_SCREEN[1] - 22, "MOCHA", 1.3, " weight=700 when=eq_model:%d" % mopt(8, "eq_model"))   # MOCHA
for _m in (9, 10):
    text(952, SY + EQ_SCREEN[1] - 22, "TITANIUM EQ", 1.3, " weight=700 when=eq_model:%d" % mopt(_m, "eq_model"))
onbtn(1086, SY + EQ_SCREEN[1] - 50, "eq_on", "ON", kind="on")
cw = (MID_X1 - MID_X0) // 4
BT = TOP + EQ_GRAPH_H + 4                          # the band frames' top
for i, (b, name, *_r) in enumerate(EQ_BANDS):
    x = MID_X0 + i * cw
    frame(x, BT, cw - (0 if i == 3 else 4), BOTTOM - BT, name)   # one row a band, so the graph above gets the height
    cx = x + cw // 2 - 2
    knob(cx - 80, BT + 72, "eq_%s_gain" % b, "GAIN", r=30, bw=80)
    knob(cx, BT + 72, "eq_%s_freq" % b, "FREQ", r=30, bw=80)
    if b in ("lmf", "hmf"):
        knob(cx + 80, BT + 72, "eq_%s_q" % b, "Q", r=30, bw=80)
    else:
        for m, cond in per_model("EQ", "segs"):   # lit in the theme's colour
            t = theme(m, "EQ", "segs")
            L.append('enum_v cx=%d cy=%d sw=76 sh=30 key=eq_%s_type label="TYPE" options="SHELF,BELL,CUT"%s%s%s'
                     % (cx + 82, BT + 98, b, " seg_on=%s" % t["segs"] if t else "",
                        " seg_tx=%s" % t["segs_tx"] if t and "segs_tx" in t else "", cond))

tab("COMP", ql("cmp_att", "cmp_ratio", "cmp_knee", "cmp_rel", "cmp_thr", "cmp_makeup", "cmp_mix", "cmp_sc_hpf", "cmp_fast", "cmp_det", "cmp_on"))
frame(MID_X0, TOP, 600, H, "COMPRESSOR")
knob(276, Y0 + 86, "cmp_att", "ATTACK", r=40, bw=150)
knob(436, Y0 + 86, "cmp_ratio", "RATIO", r=40, bw=150)
knob(596, Y0 + 86, "cmp_knee", "KNEE", r=34, bw=140)
knob(276, Y0 + 246, "cmp_rel", "RELEASE", r=40, bw=150)
knob(436, Y0 + 246, "cmp_thr", "COMPRESSION", r=48, bw=170)
knob(596, Y0 + 246, "cmp_makeup", "MAKE-UP", r=34, bw=140)
knob(276, Y0 + 396, "cmp_mix", "WET/DRY", r=34, bw=140)
knob(436, Y0 + 396, "cmp_sc_hpf", "S/C HPF", r=34, bw=140)
onbtn(596, Y0 + 386, "cmp_fast", "FAST ATT", kind="switch")
frame(MID_X0 + 604, TOP, MID_X1 - MID_X0 - 604, H, "GAIN REDUCTION")
# every preset (0.8.3; the GRANITE's from 0.8.0): transfer curve + gain reduction 0..-20 dB, top down, in the preset's
# colour; HEARTS's graph goes up to +12 dBFS so its upward expansion shows (user, 2026-11-03)
for m in LISTS["cmp_model"]:
    only([m], tc_graph, 774, Y0 + 20, "ctc", "INPUT  dBFS", m, TC_TOP_G if m == 2 else 0)
    only([m], meter, 1092, Y0 + 170, 24, TC_BAR, "m_gr", "art/gr_bar20_%s.png" % UT.tc_look(m, "COMP", TC_TOP_G if m == 2 else 0), VU_FRAMES)
text(1092, Y0 + 336, "GR", 1.2)
for db, yy in ((0, 0), (-10, 150), (-20, 300)):
    text(1108, Y0 + 20 + yy + 3, str(db), 1.0, " align=left weight=600 opacity=0.8")
gseg(880, Y0 + 418, 200, "cmp_det", "DETECT", "RMS,PEAK", sh=40)   # under the graph
onbtn(1060, Y0 + 408, "cmp_on", "ON", kind="on")

tab("DRIVE", ql("drv_amt", "drv_char", "drv_pos", "drv_on", "out_pan", "out_width", "order", "bypass"))
frame(MID_X0, TOP, 400, H, "DRIVE")
knob(336, Y0 + 100, "drv_amt", "DRIVE", r=52, bw=180)
knob(336, Y0 + 270, "drv_char", "CHARACTER", r=42, bw=170)
for m, lo, hi in ((0, "2ND", "3RD"), (1, "2ND", "3RD"), (2, "ORIG", "TYPE 2"), (3, "2ND", "3RD"), (4, "2ND", "3RD"), (5, "2ND", "3RD"), (6, "2ND", "3RD"), (7, "2ND", "3RD"), (8, "2ND", "3RD"), (9, "2ND", "3RD"), (11, "2ND", "3RD")):   # HEARTS: CHARACTER picks the limiter type
    if not in_list(m, "cmp_model"):
        continue
    text(276, Y0 + 270, lo, 1.2, " when=cmp_model:%d" % mopt(m, "cmp_model"))
    text(396, Y0 + 270, hi, 1.2, " when=cmp_model:%d" % mopt(m, "cmp_model"))
gseg(236, Y0 + 415, 160, "drv_pos", "POSITION", "POST,PRE", sh=40)
onbtn(436, Y0 + 405, "drv_on", "ON", kind="on")
frame(MID_X0 + 404, TOP, 300, H, "OUTPUT")
knob(MID_X0 + 554, Y0 + 100, "out_pan", "PAN", r=44, bw=170)
knob(MID_X0 + 554, Y0 + 275, "out_width", "WIDTH", r=44, bw=170)
frame(MID_X0 + 708, TOP, MID_X1 - MID_X0 - 708, H, "ROUTING")
# HEARTS's ORDER red, its open list too (user, 2026-11-03): HEARTS's field opens its own list (opens=_g: its own hidden
# flag order__open_g); the SSLs' fields share the blue one (built once, list=none on the second)
plain_n = 0   # a theme's ORDER: its own field and list (accent, opens=); the others share the blue list (0.8.0: per THEMES)
for m in LISTS["cmp_model"]:
    popup(MID_X0 + 858, Y0 + 100, 260, "order", "ORDER", ",".join(ORDERS))
    t = theme(m, "DRIVE", "order")
    if t:
        L[-1] += " accent=%s opens=%s" % t["order"]
        if t.get("order_ink"):
            L[-1] += " field_ink=%s" % t["order_ink"]   # the field's text and arrow (HEXX: white, user 2026-11-04, 0.11.1)
        if t.get("order_list_ink"):
            L[-1] += " list_ink=%s" % t["order_list_ink"]   # the list's unpicked options (HEXX: light blue, 0.11.2)
    else:
        L[-1] += " list=none" if plain_n else ""
        plain_n += 1
    L[-1] += " when=cmp_model:%d" % mopt(m, "cmp_model")
text(MID_X0 + 858, Y0 + 170, "SHAPE  /  EQ  /  COMP", 1.2)
onbtn(MID_X0 + 858, Y0 + 420, "bypass", "BYPASS", kind="switch")   # clears the open ORDER list

tab("SETUP", ql("strip_sel", "in_unit", "sh_unit", "eq_unit", "cmp_unit"))   # the five lists on Q-Links, as on the page (0.17.0; 0.10.9)
frame(MID_X0, TOP, MID_X1 - MID_X0, H, "PRESETS")
# 0.17.0 (user, 2026-11-05): CHANNEL STRIP on top, centred over the two columns; under it PREAMP / SHAPE, EQ / COMPRESSOR
SET_CX = (MID_X0 + MID_X1) // 2
text(SET_CX, TOP + 62, "CHANNEL STRIP", 1.9, " weight=700 spacing=2")
popup(SET_CX, TOP + 112, 440, "strip_sel", "", ",".join(MODELS[m] for m in STRIPS))
text(SET_CX, TOP + 158, "SETS ALL FOUR SECTIONS", 1.2, " opacity=0.75")
for i, (key, label) in enumerate((("in_model", "PREAMP"), ("sh_model", "SHAPE"), ("eq_model", "EQ"), ("cmp_model", "COMPRESSOR"))):
    cx = MID_X0 + (MID_X1 - MID_X0) // 4 * (1 + 2 * (i % 2))
    y = TOP + 222 + (i // 2) * 150
    text(cx, y, label, 1.9, " weight=700 spacing=2")
    popup(cx, y + 50, 400, UNIT_KEYS[key], "", ",".join(UNIT_OPTS[key]))   # STRIP + the section's single units
text(MID_X0 + (MID_X1 - MID_X0) // 4 * 3, TOP + 222 + 150 + 96, "ALSO SETS DRIVE", 1.2, " opacity=0.75")
text(SET_CX, TOP + 515, "STRIP: the section follows the channel strip. A pick sets that section's controls to its defaults.", 1.3, " opacity=0.75")

# ---------------------------------------------------------------- write
head = ["theme_bg=3c3b40", "theme_panel=45444a", "theme_box=2a292e", "theme_line=8c8b93", "theme_ink=ececf0",
        "theme_ink_dim=c4c3ca", "theme_ink_faint=8f8e96", "theme_accent=2f9fd0", "theme_accent_hi=f4f6f8",
        "theme_lcd=121318", "theme_seg_active=2f9fd0", "theme_seg_active_tx=ffffff", "theme_seg_inactive=2c2b30",
        "art_css=art/skin.css",
        # 0.21.1 (user, 2026-11-07: "takes a long time to open"): 64-frame knob strips (half the decoded RAM) and a compact
        # TUI.json (23 MB -> 7 MB); shared shadow_skin options, other plugins unchanged
        "skin_knob_frames=64", "skin_json=compact",
        "qlinks_track = %s" % TABS[0][1]]
# page backgrounds, per preset and page (user, 2026-11-10): colour, photo, see-through panel fill; #pagebg comments that only
# the single-preset builds use (tools/single-preset-build.sh)
def _shows(m, k, v):
    if k == "strip_sel":
        return m in STRIPS and STRIPS.index(m) == v
    if k in LISTS:
        return m in LISTS[k] and LISTS[k].index(m) == v
    if k == "m_eqlook":
        return v // 2 == m
    return True


# Sections edge to edge (user, 2026-11-10: "close the gap on the left and right sides ... nudge the input section to the
# left edge of the screen and the output section to the right edge ... make sure the gaps between the different sections are
# the same size"). The pages are laid out as before (IN x=8, middle 136..1144, OUT x=1148, 4 px gaps); this pass then puts IN
# at x=0 and OUT at 1156, widens each row of middle sections to 128..1152 (the extra 16 px shared out by width, the old 4 px
# gaps kept), and moves everything inside a section by that section's centre shift (sizes unchanged, so strips stay whole).
EDGE_W = 1280


def edge_to_edge(lines):
    fr = re.compile(r'^frame x=(-?\d+) y=(-?\d+) w=(\d+) h=(\d+)')
    out, i = [], 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and not lines[j].startswith("[tab "):
            j += 1
        block = lines[i:j]
        old = sorted({tuple(map(int, m.groups())) for m in (fr.match(l) for l in block) if m})
        new = {}
        for f in old:
            x, y, w, h = f
            if x == 8 and w == 124:
                new[f] = (0, y, w, h)
            elif x == 1148 and w == 124:
                new[f] = (EDGE_W - w, y, w, h)
        rows = {}
        for f in old:
            if f not in new:
                rows.setdefault((f[1], f[3]), set()).add((f[0], f[2]))
        for (y, h), segs in rows.items():
            segs = sorted(segs)
            if segs[0][0] != MID_X0 or sum(segs[-1]) != MID_X1 or any(a[0] + a[1] > b[0] for a, b in zip(segs, segs[1:])):
                raise SystemExit("edge_to_edge: a row of sections that isn't one partition of %d..%d: %s" % (MID_X0, MID_X1, segs))
            extra, total = 16, sum(w for _, w in segs)
            adds = [round(extra * w / total) for _, w in segs[:-1]]
            adds.append(extra - sum(adds))
            nx = MID_X0 - 8
            for k, ((x, w), a) in enumerate(zip(segs, adds)):
                new[(x, y, w, h)] = (nx, y, w + a, h)
                if k + 1 < len(segs):
                    nx += w + a + (segs[k + 1][0] - (x + w))   # the old gap (4 px)
        def shift(px, py):
            hits = [f for f in old if f[0] <= px <= f[0] + f[2] and f[1] <= py <= f[1] + f[3]]
            if not hits:
                return 0
            f = min(hits, key=lambda f: f[2] * f[3])
            n = new[f]
            return round(((2 * n[0] + n[2]) - (2 * f[0] + f[2])) / 2.0)
        for l in block:
            m = fr.match(l)
            if m:
                n = new[tuple(map(int, m.groups()))]
                out.append(fr.sub("frame x=%d y=%d w=%d h=%d" % n, l, count=1))
                continue
            c = re.search(r' cx=(-?[\d.]+) cy=(-?[\d.]+)', l)
            if c:
                cx, cy = float(c.group(1)), float(c.group(2))
                if TOP <= cy <= BOTTOM:
                    d = shift(cx, cy)
                    if d:
                        v = cx + d
                        l = l[:c.start(1)] + ("%d" % v if v == int(v) else "%g" % v) + l[c.end(1):]
                out.append(l)
                continue
            a = re.search(r' x=(-?\d+) y=(-?\d+) w=(\d+) h=(\d+)', l)
            if a and not l.startswith("#"):
                x, y, w, h = map(int, a.groups())
                if TOP <= y + h / 2.0 <= BOTTOM:
                    d = shift(x + w / 2.0, y + h / 2.0)
                    if d:
                        l = l[:a.start(1)] + str(x + d) + l[a.end(1):]
            out.append(l)
        i = j
    return out


L[:] = edge_to_edge(L)
L[:] = UT.sections_and_labels(L, STRIPS, _shows)   # per-preset sections, text colours, labels (2026-11-10)
L[:] = UT.page_backgrounds(L, STRIPS, _shows)
lines = UT.head(head) + L
# Parameter 0 is INPUT: MPC (JUCE) briefly sets parameter 0 to 0 and back when it loads a plugin, and a preset parameter
# there would reset its section; a trim that dips for an instant is harmless. Meters and curve columns go last, outside
# AUTOMATABLE_PARAMS (MPC answers every automate of an automatable parameter with a name lookup).
DISPLAY_ONLY = ("m_", "eqc_", "spc_", "spk_", "gtc_", "ctc_")   # m_eqlook too: the engine keeps it
PARAMS.sort(key=lambda p: 0 if p["key"] == "in_gain" else 2 if p["key"].startswith(DISPLAY_ONLY) else 1)
AUTOMATABLE = sum(1 for p in PARAMS if not p["key"].startswith(DISPLAY_ONLY))
cfg_path = os.path.join(HERE, "..", "vst.json")   # the wrapper's AUTOMATABLE_PARAMS: the controls, not the meters after them
cfg = json.load(open(cfg_path))
cfg.setdefault("defines", {})["AUTOMATABLE_PARAMS"] = AUTOMATABLE
open(cfg_path, "w").write(json.dumps(cfg, indent=2) + "\n")
open(os.path.join(HERE, "..", "layout-gen2.conf" if GEN2 else "layout.conf"), "w").write("\n".join(lines) + "\n")
# Q-Link speed (user, 2026-11-08: PREAMP's TYPE and SLOPEs "move very fast and erratically" on the Q-Links, and "can the
# adjustment of the speed of these controls be added to the editor?"). qlink_ticks = Q-Link events (or wheel clicks) per
# option, compiled into the plugin (gen_vst); 0 = MPC's own (one event can jump options). Built in: 6 like ORDER (0.10.8).
for _p in PARAMS:
    if _p["key"] in ("pre_type", "lc_slope", "hc_slope"):
        _p["qlink_ticks"] = 6
        _p["nudge_pct"] = 100   # XL Q-Link moves >1 option/event on a short list -> cap each move to one step (vst2_wrap option branch, user 2026-11-08)
# the user's speeds: vst/qlink-speed.txt ("key = N", from tools/qlink-speed.txt, written by the Theme Editor) over the built-in
_QBUILTIN = {_p["key"]: int(_p.get("qlink_ticks", 0)) for _p in PARAMS}
_qfile = os.path.join(HERE, "..", "qlink-speed.txt")
if os.path.exists(_qfile):
    _byk = {_p["key"]: _p for _p in PARAMS}
    for _ln in open(_qfile, encoding="utf-8"):
        _ln = _ln.split("#")[0].strip()
        if "=" not in _ln:
            continue
        _k, _v = [x.strip() for x in _ln.split("=", 1)]
        if _k in _byk and "options" in _byk[_k] and _v.isdigit() and int(_v) <= 30:
            if int(_v):
                _byk[_k]["qlink_ticks"] = int(_v)
            else:
                _byk[_k].pop("qlink_ticks", None)
        else:
            print("qlink-speed.txt: ignored %r" % _ln)
# for the editor: every option control on a page's Q-Links (key, name, pages, option count, built-in, in force)
_qpages = {}
for _shown, _ql in TABS:
    for _k in [x.strip() for x in _ql.split(",") if x.strip()]:
        _qpages.setdefault(_k, [])
        if _shown not in _qpages[_k]:
            _qpages[_k].append(_shown)
with open(os.path.join(HERE, "..", "qlink-info.txt"), "w", encoding="utf-8") as _f:
    _f.write("# X-Console: option controls on Q-Links, written by make_layout.py for the Theme Editor. key, name, pages, options, built-in events per option, in force\n")
    for _p in PARAMS:
        if "options" in _p and _p["key"] in _qpages:
            _f.write("	".join([_p["key"], _p["name"], ",".join(_qpages[_p["key"]]), str(len(_p["options"])),
                                 str(_QBUILTIN[_p["key"]]), str(int(_p.get("qlink_ticks", 0)))]) + "\n")
json.dump({"name": "X-Console", "params": PARAMS}, open(os.path.join(HERE, "..", "params.json"), "w"), indent=1)
os.makedirs(os.path.join(HERE, "..", "..", "src"), exist_ok=True)
ON_BUTTONS = ("pre_on", "flt_on", "sh_on", "eq_on", "cmp_on")   # a preset change leaves these alone (drv_on follows COMP's preset)


def section(k):
    """Which section preset a control belongs to: 1 PREAMP, 2 SHAPE, 3 EQ, 4 COMP (and DRIVE), 0 none.
    Picking a preset resets that section's controls (not the preset key itself, not the ON buttons) to the preset's defaults."""
    if k in ON_BUTTONS or k.endswith(("_model", "_unit")) or k == "strip_sel":
        return 0
    if k == "phase" or k.startswith(("pre_", "lc_", "hc_", "flt_")):
        return 1
    if k.startswith(("sh_", "gate_")):
        return 2
    if k.startswith("eq_"):
        return 3
    if k.startswith(("cmp_", "drv_")):
        return 4
    return 0


def norm_of(lo, hi, taper, v):
    import math
    if v is None:
        return 1.0 if taper == "top-off-log" else 0.0
    if taper == "split":   # lo..0 on the left half, 0..hi on the right
        return 0.5 * (1 - v / lo) if v < 0 else 0.5 + 0.5 * v / hi
    if "log" in taper:
        return math.log(v / lo) / math.log(hi / lo)
    return (v - lo) / (hi - lo)


TAPER = {"lin": 0, "sym": 0, "log": 1, "off-log": 2, "top-off-log": 3, "lim-log": 4, "auto-log": 5, "auto-lin": 6, "split": 7, "steps": 8}
STEP_WORDS = {"OFF": "-1000000.0f", "AUTO": "-2000000.0f", "LIMIT": "1000000.0f"}   # xconsole.c ST_OFF, ST_AUTO, ST_LIMIT
with open(os.path.join(HERE, "..", "..", "src", "param_table.h"), "w") as f:
    f.write("/* Generated by vst/art/make_layout.py: don't edit.\n"
            " * N(key, default 0..1, min, max, taper: 0 lin, 1 log, 2 log Off at 0, 3 log Off at 1, 4 log Limit at 1, 5 log Auto at 0, 6 lin Auto at 0)  O(key, default index, option count)  M(key) meter.\n"
            " * The last field of N and O is the section preset the control belongs to (0 none, 1 PREAMP, 2 SHAPE, 3 EQ, 4 COMP + DRIVE). */\n")
    for p in PARAMS:
        k = p["key"]
        if k in SPEC:
            lo, hi, taper, _ = SPEC[k]
            f.write("N(%s, %sf, %sf, %sf, %d, %d)\n" % (k, repr(float(p["default"])), repr(float(lo)), repr(float(hi)), TAPER[taper], section(k)))
        elif "options" in p:
            f.write("O(%s, %d, %d, %d)\n" % (k, p["default"], len(p["options"]), section(k)))
        else:
            f.write("M(%s)\n" % k)
    f.write("#define SPC_FRAMES %d\n#define SPC_JOIN %d\n#define EQC_JOIN %d\n" % (SPC_FRAMES, SPC_JOIN, EQC_JOIN))
    f.write("#define MODEL_COUNT %d\n" % len(MODELS))
    for k, nm in zip(PRESET_KEYS, ("IN", "SH", "EQ", "CMP")):   # each drop-down its own list (0.15.0)
        f.write("#define MODEL_BY_OPT_%s %s   /* %s's value (its place in that alphabetical list) -> model number */\n"
                % (nm, ", ".join(str(m) for m in LISTS[k]), k))
    f.write("#define STRIP_BY_OPT %s   /* strip_sel's value -> model number (0.17.0) */\n" % ", ".join(str(m) for m in STRIPS))
    for k, nm in zip(PRESET_KEYS, ("IN", "SH", "EQ", "CMP")):
        f.write("#define UNIT_BY_OPT_%s %s   /* %s's value -> model number, -1 = STRIP */\n"
                % (nm, ", ".join(str(m) for m in [-1] + UNITS[k]), UNIT_KEYS[k]))
    f.write("/* the later models' differences: MR(model, key, default 0..1, min, max, taper)  MO(model, key, default index)  MS(model, key, default 0..1, count, positions) */\n")
    keys = [p["key"] for p in PARAMS]
    for m, over in sorted(MODEL_SPECS.items()):
        for k, v in over.items():
            assert k in keys, k
            if isinstance(v, tuple) and v[0] == "steps":   # MS(model, key, default 0..1, count, values...)
                _, vals, d = v
                f.write("MS(%d, %s, %sf, %d, %s)\n" % (m, k, repr(round((vals.index(d) + 0.5) / len(vals), 6)), len(vals),
                                                      ", ".join(STEP_WORDS[s] if isinstance(s, str) else repr(float(s)) + "f" for s in vals)))
            elif isinstance(v, tuple):
                lo, hi, taper, d = v
                f.write("MR(%d, %s, %sf, %sf, %sf, %d)\n" % (m, k, repr(float(round(norm_of(lo, hi, taper, d), 6))), repr(float(lo)), repr(float(hi)), TAPER[taper]))
            else:
                f.write("MO(%d, %s, %d)\n" % (m, k, v))
    f.write("#define TC_COLS %d\n#define TC_FRAMES %d\n#define SHP_FRAMES %d\n" % (TC_COLS, TC_FRAMES, SHP_FRAMES))
    f.write("#define TC_NJ %d\n#define TC_STEPS_LIST %s\n" % (len(TC_STEPS), ", ".join(str(v) for v in TC_STEPS)))
    f.write("#define TC_TOP_G %d\n" % TC_TOP_G)
    f.write("#define EQC_COLS %d\n#define EQC_FRAMES %d\n#define LED_FRAMES %d\n#define VU_FRAMES %d\n#define GR_FRAMES %d\n"
            % (EQC_COLS, EQC_FRAMES, LED_FRAMES, VU_FRAMES, GR_FRAMES))
finish_colours()   # 0.20.0: the colour file checked (or written) once every page is drawn
TC_SETS = [(TC_LOOK[m], 0) for m in sorted(TC_LOOK)] + [(TC_LOOK[2] + "_x", TC_TOP_G)] + UT.tc_sets(TC_TOP_G)   # (look, top dBFS)
make_art.write_tc(HERE, TC_W, TC_H, SHP_FRAMES, VU_FRAMES, TC_TILES, TC_COLS * TC_W, TC_BAR, TC_STEPS,
                  [(look, top, tc_levels(top), tc_jtiles(tc_levels(top))) for look, top in TC_SETS])
make_art._eq_logo(HERE, (TC_COLS * TC_W, TC_H), "logo_hexx_eq_src.png", "tc_logo_hexx.png", max_h=200, alpha=make_art.HEXX_LOGO_ALPHA)   # 0.19.0
make_art._eq_logo(HERE, (TC_COLS * TC_W, TC_H), "logo_mocha_eq_src.png", "tc_logo_mocha.png", max_h=200)   # 0.18.1: ~270 x 200, centred, 5%
make_art._eq_logo(HERE, (TC_COLS * TC_W, TC_H), "logo_spades_eq_src.png", "tc_logo_spades.png", max_h=200)   # 0.19.2: SPADES, 5%
make_art.write(HERE, LED_FRAMES, VU_FRAMES, GR_FRAMES, EQ_SCREEN, (MID_X1 - MID_X0, 80), (EQC_W, EQC_FRAMES, EQC_JOIN, EQC_TILES), (SPC_FRAMES, SPC_JOIN, SP_TILES))
UT.run_jobs(HERE)   # 0.21.0: the colours file's own pictures (knobs, meters, spectrum, curves, screens)
print("params:", len(PARAMS), "tabs:", len(TABS), "lines:", len(lines), "(gen2)" if GEN2 else "(gen1)")
