"""X-Console's user theme (0.21.0, user: "i want total control of all colors"): every colour of the skin from one text file,
vst/colours.txt (edited with X-Console Theme Editor.exe, or by hand), written back in a canonical form after each build.

    [PRESET]                       one block per preset, plus [ALL PRESETS] for the panel
    ALL / ITEM = value             every page of that preset that has ITEM
    PAGE / ITEM = value            one page (wins over ALL)

ITEM is a knob (its name on the page: HIGH CUT, LMF Q, NOISE LEVEL ...) or a theme item (BANNER LINE, METERS, SPECTRUM LINE,
ON LIGHTS ...). Values: #rrggbb; a knob: a cap name (the built-in caps), #body/#pointer, or #body for a chicken-head; METERS:
"dB #colour, dB #colour, ..." (a gradient on the -60..+6 dBFS meter). A value equal to the built-in one changes nothing, so an
untouched file builds exactly the built-in skin; a changed one gets its own art (u... names), drawn after make_art.write().
make_layout.py calls: knob(), theme(), tc_look(), tc_sets(), sp_arts(), pk_arts(), eq_art(), head(), finish(), run_jobs()."""
import os
import re
import sys

import __main__ as ml
import make_art as A

ART = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(ART, "..", "colours.txt")
INFO = os.path.join(ART, "..", "colours-info.txt")
PAGES = ["PREAMP", "SHAPE", "EQ", "COMP", "OUTPUT", "SETUP"]
GLOBAL, PANEL = "ALL PRESETS", "PANEL"

# ---------------------------------------------------------------- colour helpers
NAMED = {"white": "ffffff", "black": "000000", "red": "e23428", "pink": "f08cb4", "darkpink": "c45488", "orange": "f08824",
         "yellow": "f0d634", "gold": "d4a537", "green": "46c85a", "darkgreen": "366c44", "lightgreen": "9cd8a8",
         "blue": "2f9fd0", "darkblue": "2a52be", "lightblue": "96c8f0", "grey": "8c8b93", "darkgrey": "45444a",
         "lightgrey": "cecec8", "brown": "9c704c", "lightbrown": "c89c72", "darkbrown": "704e34", "tan": "e2cca6",
         "purple": "8a4fc8", "teal": "2aa198", "silver": "c4cad2", "darkred": "a32020"}


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def hx(c):
    return "#%02x%02x%02x" % tuple(c[:3])


def norm_colour(v):
    """'#AbC123', 'abc123', 'white' -> '#abc123'; None if it isn't a colour"""
    v = v.strip().lower().replace(" ", "")
    if v in NAMED:
        return "#" + NAMED[v]
    if re.fullmatch(r"#?[0-9a-f]{6}", v):
        return "#" + v.lstrip("#")
    if re.fullmatch(r"#?[0-9a-f]{3}", v):
        return "#" + "".join(ch * 2 for ch in v.lstrip("#"))
    return None


def shade(c, k):
    return tuple(max(0, min(255, round(v * k))) for v in c[:3])


def tag(*vals):
    """a file-name-safe id for a set of colours / numbers"""
    return "".join(re.sub(r"[^0-9a-z]", "", str(v).lower()) for v in vals)


# ---------------------------------------------------------------- the file
USER, LINES, ERRORS, SEEN, USED, KIND = {}, {}, [], {}, set(), {}
JOBS = []          # (key, fn) art to draw after make_art.write(); key dedupes
READ = [False]
STYLE = {}         # (PRESET, PAGE, NAME) -> "round" / "chicken": a knob's cap style


def _read():
    if READ[0]:
        return
    READ[0] = True
    if os.path.exists(FILE):
        _parse()
    _globals()


def _parse():
    names = {m.upper(): m for m in ml.MODELS}
    preset = None
    for n, raw in enumerate(open(FILE, encoding="utf-8-sig"), 1):
        ln = raw.strip()   # a line starting with # is a note
        if not ln or ln.startswith("#"):
            continue
        if ln.startswith("[") and ln.endswith("]"):
            preset = " ".join(ln[1:-1].split()).upper()
            if preset != GLOBAL and preset not in names:
                ERRORS.append("line %d: no preset called %s" % (n, preset))
                preset = "?"
            continue
        if preset == "?":
            continue
        if "=" not in ln or "/" not in ln.split("=", 1)[0]:
            ERRORS.append("line %d: expected PAGE / NAME = value, found: %s" % (n, ln))
            continue
        left, val = ln.split("=", 1)
        val = re.sub(r"\s+#\s.*$", "", val).strip()   # a note after the value: "= #ffffff   # my note"
        page, name = left.split("/", 1)
        page, name = " ".join(page.split()).upper(), " ".join(name.split()).upper()
        if preset is None:
            ERRORS.append("line %d: no [PRESET] line above it" % n)
        elif page not in PAGES + ["ALL"] + ([PANEL] if preset == GLOBAL else []):
            ERRORS.append("line %d: no page called %s (pages: ALL, %s)" % (n, page, ", ".join(PAGES)))
        else:
            USER[(preset, page, name)] = val
            LINES[(preset, page, name)] = n


def lookup(preset, page, name):
    """the file's value for this place: the page's own line, else the preset's ALL line"""
    _read()
    for k in ((preset, page, name), (preset, "ALL", name)):
        if k in USER:
            USED.add(k)
            return USER[k], k
    return None, None


def _bad(k, msg):
    ERRORS.append("line %d: %s" % (LINES[k], msg))


def colour_item(preset, page, name, builtin, kind="colour"):
    """record a colour place; the file's colour if it differs from the built-in one, else None"""
    builtin = norm_colour(builtin)
    SEEN.setdefault((preset, page, name), builtin)
    KIND[name] = kind
    v, k = lookup(preset, page, name)
    if v is None:
        return None
    c = norm_colour(v)
    if c is None:
        _bad(k, "%s / %s: %s isn't a colour (use #rrggbb)" % (page, name, v))
        return None
    return None if c == builtin else c


def page_name():
    p = ml.CUR_PAGE[0]
    return ml.TAB_SHOWN.get(p, p)


def P(m):
    return ml.MODELS[m].upper()


# ---------------------------------------------------------------- knobs
def _cap_colours(cap):
    if cap in A.CAPS:
        top, bot, ptr = A.CAPS[cap]
        return "round", top, bot, ptr
    if cap in A.MOLTEN_CAPS:
        top, bot = A.MOLTEN_CAPS[cap]
        return "chicken", top, bot, (236, 236, 232)
    if cap.startswith("uch"):
        top = rgb(cap[3:9])
        return "chicken", top, shade(top, .55), (236, 236, 232)
    if cap.startswith("u"):
        top, ptr = rgb(cap[1:7]), rgb(cap[7:13])
        return "round", top, shade(top, .6), ptr
    raise KeyError(cap)


def knob_ink(m):
    """the knob names' and values' colours for preset m on this page: (ink, ink_dim) if the file changes them, else None"""
    _read()
    p, pg = P(m), page_name()
    n0, v0 = "#" + GLOBAL_VALUE["theme_ink"], "#" + GLOBAL_VALUE["theme_ink_dim"]
    n, v = colour_item(p, pg, "KNOB NAMES", n0), colour_item(p, pg, "KNOB VALUES", v0)
    if not (n or v):
        return None
    return ((n or n0)[1:], (v or v0)[1:])


def knob(m, key, label, builtin):
    """knob(): the cap for preset m's knob, from the file if it changes it"""
    name = ml.knob_name(m, key, label)
    k0 = (P(m), page_name(), name)
    SEEN.setdefault(k0, builtin)
    KIND[name] = "knob"
    style = _cap_colours(builtin)[0]
    STYLE[k0] = style
    v, k = lookup(*k0)
    if v is None:
        return builtin
    v = v.strip().lower().replace(" ", "")
    if v in A.CAPS or v in A.MOLTEN_CAPS:
        return v
    parts = v.split("/")
    cols = [norm_colour(p) for p in parts]
    if not 1 <= len(parts) <= 2 or None in cols:
        _bad(k, "%s / %s: %s isn't a knob colour (a cap name, #body/#pointer, or #body)" % (k[1], k[2], v))
        return builtin
    _, top, _, ptr = _cap_colours(builtin)
    top = rgb(cols[0])
    ptr = rgb(cols[1]) if len(cols) == 2 else ptr
    if style == "chicken":
        cap = "uch" + tag(hx(top))
        bot = shade(top, .55)
        JOBS.append((cap, lambda d, top=top, bot=bot, cap=cap: A._molten(86, top, bot).save(os.path.join(d, "knob_%s.png" % cap))))
    else:
        cap = "u" + tag(hx(top), hx(ptr))
        bot = shade(top, .6)
        JOBS.append((cap, lambda d, top=top, bot=bot, ptr=ptr, cap=cap: A._cap(86, top, bot, ptr).save(os.path.join(d, "knob_%s.png" % cap))))
    return cap


# ---------------------------------------------------------------- theme parts (banner, meters, lights, buttons, lists, curve)
def _svg_colours(name):
    s = open(os.path.join(ART, name)).read()
    rule = re.search(r'stop-color="(#[0-9a-fA-F]{6})"', s).group(1).lower()
    bg, border = re.search(r'<rect x="0.5" y="0.5"[^>]*fill="(#[0-9a-fA-F]{6})" stroke="(#[0-9a-fA-F]{6})"', s).groups()
    return rule, bg.lower(), border.lower()


def _header(rule, bg, border, base="header.svg"):
    name = "header_u%s.svg" % tag(rule, bg, border)
    s = open(os.path.join(ART, base)).read()
    r0, b0, e0 = _svg_colours(base)
    s = s.replace(r0, rule).replace(r0.upper(), rule).replace('fill="%s" stroke="%s"' % (b0, e0), 'fill="%s" stroke="%s"' % (bg, border))
    open(os.path.join(ART, name), "w").write(s)
    return name


METERS = {"": None, "_hearts": "LED_HEARTS", "_granite": "LED_GRANITE", "_flannel": "LED_FLANNEL", "_suede": "LED_SUEDE", "_sandstone": "LED_SANDSTONE",
          "_hexx": "LED_HEXX", "_molten": "LED_MOLTEN", "_spades": "LED_SPADES", "_mocha": "LED_MOCHA"}


def _meter_text(suf):
    if METERS.get(suf):
        stops = getattr(A, METERS[suf])
    else:   # the plain look, three zones: as stops that change within a segment
        stops = [(-9.6, A.BLUE), (-9.5, A.LED_WHITE), (-0.1, A.LED_WHITE), (0.0, A.ORANGE)]
    return ", ".join("%g %s" % (db, hx(c)) for db, c in stops)


def _meter_parse(v):
    raw = []
    for part in v.split(","):
        bits = part.split()
        if len(bits) != 2:
            return None
        try:
            db = float(bits[0])
        except ValueError:
            return None
        cs, fade = bits[1], True
        if cs.endswith("!"):   # "#rrggbb!" = a solid band to the next stop (no fade), a hard edge there
            cs, fade = cs[:-1], False
        c = norm_colour(cs)
        if c is None:
            return None
        raw.append((db, rgb(c), fade))
    if not raw or any(b[0] < a[0] for a, b in zip(raw, raw[1:])):   # two stops at one level: a hard change there
        return None
    # a no-fade stop holds its colour to the next level, so that level's stop makes a hard edge (same expansion as the
    # Theme Editor's Model.Expand, so preview == plugin)
    stops = []
    for i, (db, col, fade) in enumerate(raw):
        stops.append((db, col))
        if not fade and i + 1 < len(raw):
            stops.append((raw[i + 1][0], col))
    return stops


def _btn(name, led):
    A._btn_svg(ART, name, led)
    return name


def theme(m, page, part):
    """make_layout's theme(): the built-in theme, with the file's colours over it (a dict the call sites read as before)"""
    base = ml._theme_base(m, page, part)
    if m is None:   # a plain line for every preset (no preset's theme changes this part here)
        return base
    _read()
    G = GLOBAL_VALUE
    pg = ml.TAB_SHOWN.get(page, page)
    p = P(m)
    over = {}
    setup = page == "SETUP"
    if part == "rule":
        hf = base["rule"] if base else "header.svg"
        r, b, e = _svg_colours(hf)
        cr, cb, ce = (colour_item(p, pg, "BANNER LINE", r), colour_item(p, pg, "BANNER BACKGROUND", b),
                      colour_item(p, pg, "BANNER BORDER", e))
        if cr or cb or ce:
            over["rule"] = _header(cr or r, cb or b, ce or e, hf)
    elif part == "x":
        d = base or (ml.SETUP_LOOK if setup else {})
        for item, key, dflt in (("BANNER X-", "x", "ececf0"), ("BANNER TITLE", "title_col", "ececf0")):
            c = colour_item(p, pg, item, "#" + d.get(key, dflt))
            if c:
                over[key] = c[1:]
        c = colour_item(p, pg, "BANNER OUTLINE", "#" + d.get("x_stroke", ml.BANNER_STROKE).split(":")[0])
        if c:
            over["x_stroke"] = c[1:] + ":1"
    elif part == "name":
        d = base or {}
        c = colour_item(p, pg, "BANNER NAME", "#" + d.get("name", ml.SETUP_LOOK["x"] if setup else "96c8f0"))
        if c:
            over["name"] = c[1:]
        c = colour_item(p, pg, "BANNER OUTLINE", "#" + d.get("name_stroke", ml.BANNER_STROKE).split(":")[0])
        if c:
            over["name_stroke"] = c[1:] + ":1"
    elif part == "meters":
        suf = base["meters"] if base else ml.SETUP_LOOK["meters"] if setup else ""
        b = _meter_text(suf)
        SEEN.setdefault((p, pg, "METERS"), b)
        KIND["METERS"] = "meters"
        v, k = lookup(p, pg, "METERS")
        if v is not None and " ".join(v.split()) != b:
            stops = _meter_parse(v)
            if stops is None:
                _bad(k, "METERS: %s isn't a gradient (dB #colour, dB #colour, ..., levels rising or equal)" % v)
            else:
                s = "_u" + tag(*["%g%s" % (db, hx(c)) for db, c in stops]).replace("-", "m")[:60]
                over["meters"] = s
                JOBS.append((s, lambda d, s=s, stops=stops: (A._led_bar(d, ml.LED_FRAMES, "led_bar%s.png" % s, stops),
                                                             A._led_pk(d, ml.LED_FRAMES, "led_pk%s.png" % s, stops))))
    elif part == "on":
        img = base.get("on_img", "btn_on_white.svg") if base else "btn_on.svg"
        c = colour_item(p, pg, "ON LIGHTS", A.BTN_LEDS[img])
        if c:
            over["on_img"] = _btn("btn_on_u%s.svg" % tag(c), c)
    elif part == "switch":
        img = "btn_on_%s.svg" % base["switch"] if base else "btn_on.svg"
        c = colour_item(p, pg, "SWITCH LIGHTS", A.BTN_LEDS[img])
        if c:
            _btn("btn_on_u%s.svg" % tag(c), c)
            over["switch"] = "u" + tag(c)
    elif part == "segs":
        d = base or {}
        s0, t0 = d.get("segs", G["theme_seg_active"]), d.get("segs_tx", G["theme_seg_active_tx"])
        c = colour_item(p, pg, "LIT BUTTONS", "#" + s0)
        t = colour_item(p, pg, "LIT BUTTON TEXT", "#" + t0)
        if c or t:
            over["segs"] = (c or "#" + s0)[1:]
            over["segs_tx"] = (t or "#" + t0)[1:]
    elif part == "order":
        d = base or {}
        acc = d["order"][0] if base else G["theme_accent"]
        fi = d.get("order_ink") or acc
        li = d.get("order_list_ink") or G["theme_ink"]
        c = [colour_item(p, pg, "DROP-DOWN", "#" + acc), colour_item(p, pg, "DROP-DOWN TEXT", "#" + fi),
             colour_item(p, pg, "DROP-DOWN LIST TEXT", "#" + li)]
        if any(c):
            a2, f2, l2 = [(x or "#" + y)[1:] for x, y in zip(c, (acc, fi, li))]
            over.update(order=(a2, "_u" + tag(a2, f2, l2)[:18]), order_ink=f2, order_list_ink=l2)
    elif part == "curve":
        suf = base.get("curve", "_white") if base else ""
        line, fill = EQ_CURVES[suf]
        c = colour_item(p, pg, "EQ CURVE", hx(line))
        f = colour_item(p, pg, "EQ CURVE FILL", hx(fill))
        if c or f:
            ln, fl = rgb(c or hx(line)), rgb(f or hx(fill))
            s = "_u" + tag(hx(ln), hx(fl))
            over["curve"] = s
            JOBS.append((s, lambda d, s=s, ln=ln, fl=fl: _eq_curve(d, s, ln, fl)))
    if not over:
        return base
    dflt = {"x": ml.SETUP_LOOK if setup else {}, "meters": {"meters": ml.SETUP_LOOK["meters"] if setup else ""}}.get(part, {})
    out = dict(base or dflt)
    out.update(over)
    return out


EQ_CURVES = {"": ((127, 214, 255), (63, 182, 232)), "_white": ((246, 246, 246), (255, 255, 255)), "_red": ((226, 72, 60), (226, 72, 60))}


def _eq_curve(d, s, ln, fl):
    A._eq_col(d, ml.EQC_W, ml.EQ_SCREEN[1], ml.EQC_FRAMES, "eq_col%s.png" % s, ln + (255,), fl + (40,))
    A._eq_join(d, ml.EQC_W, ml.EQ_SCREEN[1], ml.EQC_FRAMES, ml.EQC_JOIN, ml.EQC_TILES, "eq_join%s" % s, ln + (255,), fl + (40,))


# ---------------------------------------------------------------- EQ screen, spectrum, peaks
SP_NAMES = ["blue", "brown", "hearts", "suede", "gold", "hexx", "molten", "spades", "mocha", "spades", "spades", "spades"]
SP_COLS = {"blue": "BLUE", "brown": "BROWN", "hearts": "HEARTS", "suede": "SUEDE", "gold": "GOLD", "hexx": "HEXX", "molten": "CH",
           "spades": "AV", "mocha": "LA"}


def _sp(m):
    """preset m's spectrum: (fill, edge, bar, top) as built in, and its art names' part"""
    nm = SP_NAMES[m]
    pre = SP_COLS[nm]
    f, e, b, t = (getattr(A, "%s_%s" % (pre, x)) for x in ("FILL", "EDGE", "BAR", "TOP"))
    if not in_eq(m):
        return nm
    fc = colour_item(P(m), "EQ", "SPECTRUM FILL", hx(f))
    ec = colour_item(P(m), "EQ", "SPECTRUM LINE", hx(e))
    if not (fc or ec):
        return nm
    f2, e2 = rgb(fc or hx(f)), rgb(ec or hx(e))
    fill, edge, bar, top = f2 + (f[3],), e2 + (255,), f2 + (b[3],), e2 + (255,)
    s = "u" + tag(hx(fill), fill[3], hx(edge), bar[3])
    JOBS.append(("sp" + s, lambda d, s=s, fill=fill, edge=edge, bar=bar, top=top: _spectrum(d, s, fill, edge, bar, top)))
    return s


def _spectrum(d, s, fill, edge, bar, top):
    w, h, (lv, jn, tl) = ml.EQC_W, ml.EQ_SCREEN[1], (ml.SPC_FRAMES, ml.SPC_JOIN, ml.SP_TILES)
    if ml.GEN2:
        A._sp_join(d, w, h, lv, jn, tl, "sp_join_" + s, fill, edge)
    else:
        A._sp_col(d, w, h, lv, "sp_col_%s.png" % s, fill, edge)
    A._sp_bars(d, w, h, lv, jn, tl, "_" + s, bar, top)


def in_eq(m):
    return ml.in_list(m, "eq_model")


def sp_arts(gen2):
    """the spectrum's 24 looks (preset x 2 + VIEW), as make_layout listed them"""
    out = []
    for m in range(len(SP_NAMES)):
        s = _sp(m)
        out += ["sp_join_" + s, "sp_bars_" + s] if gen2 else ["sp_col_" + s, "sp_bar1_" + s]
    return out


PEAKS = {0: ("sp_pk", (236, 240, 244)), 1: ("sp_pk_brown", (232, 186, 120)), 2: ("sp_pk_hearts", None), 3: ("sp_pk_suede", None),
         4: ("sp_pk_gold", None), 5: ("sp_pk_hexx", None), 6: ("sp_pk_molten", None), 7: ("sp_pk_avgrey", (150, 152, 158)),
         8: ("sp_pk_mocha", None), 9: ("sp_pk_spades", None), 10: ("sp_pk_spades", None)}
PK_VARS = {"sp_pk_hearts": "HEARTS_PK", "sp_pk_suede": "SUEDE_PK", "sp_pk_gold": "GOLD_PK", "sp_pk_hexx": "HEXX_PK",
           "sp_pk_molten": "CH_PK", "sp_pk_mocha": "LA_PK", "sp_pk_spades": "AV_PK"}


def pk_arts():
    out = []
    for m, (art, col) in PEAKS.items():
        col = col or getattr(A, PK_VARS[art])[:3]
        if in_eq(m):
            c = colour_item(P(m), "EQ", "SPECTRUM PEAKS", hx(col))
            if c:
                art = "sp_pk_u" + tag(c)
                JOBS.append((art, lambda d, art=art, c=c: A._sp_pk(d, ml.EQC_W, ml.EQ_SCREEN[1], ml.SPC_FRAMES, art + ".png", rgb(c) + (235,))))
        out.append((m, art))
    return out


SCREENS = {"": dict(bg="#000000", grid="#21414f", label="#4f7d90", zero="#3a6a7e", minor="#1b3542"),
           "_black": dict(bg="#000000", grid="#2a2a2a", label="#7a7a7a", zero="#4a4a4a", minor="#1c1c1c")}
SCREEN_VARS = {"_hearts": "HEARTS_SCREEN", "_suede": "SUEDE_SCREEN", "_sandstone": "GOLD_SCREEN", "_hexx": "HEXX_SCREEN",
               "_molten": "CH_SCREEN", "_spades": "AV_SCREEN", "_mocha": "LA_SCREEN"}
SCREEN_ITEMS = (("bg", "EQ SCREEN"), ("grid", "EQ GRID"), ("minor", "EQ GRID LEVELS"), ("zero", "EQ ZERO LINE"), ("label", "EQ SCREEN TEXT"))


def eq_art(m, a):
    """an EQ screen picture for preset m: its screen and grid in the file's colours (a logo passes through)"""
    mt = re.fullmatch(r"eq_(screen|grid)(_[a-z0-9]+)?\.svg", a)
    if not mt or not in_eq(m):
        return a
    suf = mt.group(2) or ""
    b = SCREENS.get(suf) or getattr(A, SCREEN_VARS[suf])
    new = {}
    for key, item in SCREEN_ITEMS:
        c = colour_item(P(m), "EQ", item, b[key].lower())
        if c:
            new[key] = c
    if not new:
        return a
    cols = dict(b, **new)
    s = "u" + tag(*(cols[k] for k, _ in SCREEN_ITEMS))
    JOBS.append(("eqs" + s, lambda d, s=s, cols=cols: (
        A._eq_screen(d, ml.EQ_SCREEN, "eq_screen_%s.svg" % s, **cols),
        A._eq_screen(d, ml.EQ_SCREEN, "eq_grid_%s.svg" % s, grid_only=True, **{k: v for k, v in cols.items() if k != "bg"}))))
    return "eq_%s_%s.svg" % (mt.group(1), s)


# ---------------------------------------------------------------- transfer curves
TC_CUSTOM = {}   # look -> top dBFS


def tc_look(m, page, top=0):
    """the transfer-curve look for preset m on SHAPE / COMP: the built-in one, or the file's colours"""
    b = ml.TC_LOOK[m]
    pg = ml.TAB_SHOWN.get(page, page)
    col, (bg, grid, diag) = A.TC_COL[b], A.TC_SCREEN[b]
    new = [colour_item(P(m), pg, "TRANSFER CURVE", hx(col)), colour_item(P(m), pg, "CURVE SCREEN", bg.lower()),
           colour_item(P(m), pg, "CURVE GRID", grid.lower()), colour_item(P(m), pg, "CURVE DIAGONAL", diag.lower())]
    if not any(new):
        return b
    c, bg2, g2, d2 = [(n or o) for n, o in zip(new, (hx(col), bg.lower(), grid.lower(), diag.lower()))]
    look = "u" + tag(c, bg2, g2, d2)
    A.TC_COL[look], A.TC_SCREEN[look] = rgb(c), (bg2, g2, d2)
    TC_CUSTOM[look] = max(TC_CUSTOM.get(look, 0), top)
    return look


def tc_sets(top_g):
    out = []
    for look, top in TC_CUSTOM.items():
        out.append((look, 0))
        if top:
            out.append((look + "_x", top))
    return out


# ---------------------------------------------------------------- pictures (user, 2026-11-08: "insert pictures (to fit) into
# the background of the eq spectrum and transfer curves"). Places: EQ / EQ PICTURE, SHAPE + COMP / CURVE PICTURE.
# Values: built-in (the maker's logo, or nothing), none, or "file | fit | NN%": a file in the X-Console folder's "pictures"
# (tools/colours-rebuild.sh copies it to vst/art/user_pics), fitted to the screen: fill (cover, cropped), fit (whole,
# centred) or stretch; NN% its opacity. EQ: it takes the logo's place, under the grid; curves: over the screen, under the curve.
PICS = os.path.join(ART, "user_pics")
FITS = ("fill", "fit", "stretch")


def _pic_parse(v):
    s = " ".join(v.split())
    low = s.lower()
    if low.replace(" ", "") in ("built-in", "builtin", "logo"):
        return ("built-in",)
    if low in ("none", "off"):
        return ("none",)
    parts = [p.strip() for p in s.split("|")]
    if not parts[0]:
        raise ValueError("no picture file named (use: file | fill | 50%)")
    fit = parts[1].lower() if len(parts) > 1 and parts[1] else "fill"
    if fit not in FITS:
        raise ValueError("%s isn't a fit (fill, fit or stretch)" % parts[1])
    op = parts[2].rstrip("%").strip() if len(parts) > 2 and parts[2] else "50"
    try:
        n = int(round(float(op)))
    except ValueError:
        raise ValueError("%s isn't an opacity (1%% to 100%%)" % parts[2])
    if not 1 <= n <= 100:
        raise ValueError("opacity %d%% is outside 1%% to 100%%" % n)
    return ("file", parts[0], fit, n)


def _pic_text(p):
    return p[0] if p[0] != "file" else "%s | %s | %d%%" % p[1:]


def _pic_draw(src, dst, size, fit, n):
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(src)).convert("RGBA")
    if fit == "fill":
        im = ImageOps.fit(im, size, Image.LANCZOS)
    elif fit == "stretch":
        im = im.resize(size, Image.LANCZOS)
    else:
        k = min(size[0] / im.width, size[1] / im.height)
        im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        out.alpha_composite(im, ((size[0] - im.width) // 2, (size[1] - im.height) // 2))
        im = out
    if n < 100:
        im.putalpha(im.getchannel("A").point(lambda v: round(v * n / 100.0)))
    im.save(dst)


def picture(m, page, name, builtin, size):
    """the art behind preset m's EQ screen / transfer curve: `builtin` (a logo, or None), None, or the user's picture"""
    k = (P(m), page, name)
    SEEN.setdefault(k, "built-in")
    KIND[name] = "picture"
    v, kk = lookup(*k)
    if v is None:
        return builtin
    try:
        p = _pic_parse(v)
    except ValueError as e:
        _bad(kk, "%s / %s: %s" % (page, name, e))
        return builtin
    if p[0] == "built-in":
        return builtin
    if p[0] == "none":
        return None
    src = os.path.join(PICS, p[1])
    if not os.path.isfile(src):
        _bad(kk, "%s / %s: no picture called %s in the pictures folder" % (page, name, p[1]))
        return builtin
    import hashlib
    h = hashlib.md5(open(src, "rb").read()).hexdigest()[:10]
    s = "upic_%s.png" % tag(h, p[2], p[3], size[0], size[1])
    JOBS.append((s, lambda d, src=src, s=s, fit=p[2], n=p[3]: _pic_draw(src, os.path.join(d, s), tuple(size), fit, n)))
    return s


# ---------------------------------------------------------------- the panel: one set for every preset
GLOBALS = {   # item -> (where, built-in); checked in a test build, each changes something on the pages
    "BACKGROUND": ("theme_bg", "3c3b40"), "FRAME BORDERS": ("css_border", "8c8b93"), "FRAME TITLES": ("css_title", "f0f0f4"),
    "LINES": ("theme_line", "8c8b93"), "TEXT": ("theme_ink", "ececf0"), "DIM TEXT": ("theme_ink_dim", "c4c3ca"),
    "ACCENT": ("theme_accent", "2f9fd0"), "ACCENT LIGHT": ("theme_accent_hi", "f4f6f8"), "SCREENS": ("theme_lcd", "121318"),
    "LIT BUTTONS": ("theme_seg_active", "2f9fd0"), "LIT BUTTON TEXT": ("theme_seg_active_tx", "ffffff"),
    "UNLIT BUTTONS": ("theme_seg_inactive", "2c2b30"),
    "UNLIT METER SEGMENTS": ("off", "26282e"), "UNLIT BUTTON LIGHTS": ("btn_off", "20343e"),
}   # PANELS / BOXES / FAINT TEXT / css .text: no effect on this skin (0.21.0 test), so not offered
GLOBAL_VALUE = {"css_text": "dcdce2"}


def _globals():
    for item, (where, b) in GLOBALS.items():
        c = colour_item(GLOBAL, PANEL, item, "#" + b)
        GLOBAL_VALUE[where] = (c or "#" + b)[1:]


def head(lines):
    """the layout's theme_* lines, in the file's panel colours"""
    _read()
    out = []
    for ln in lines:
        k, _, v = ln.partition("=")
        out.append("%s=%s" % (k, GLOBAL_VALUE[k]) if k in GLOBAL_VALUE else ln)
    have = {ln.partition("=")[0] for ln in lines}
    out[0:0] = ["%s=%s" % (k, v) for k, v in GLOBAL_VALUE.items() if k.startswith("theme_") and k not in have]
    return out


def apply_art_globals():
    A.OFF = rgb(GLOBAL_VALUE["off"])
    A.BTN_LEDS["btn_off.svg"] = "#" + GLOBAL_VALUE["btn_off"]
    A.CSS.update(title="#" + GLOBAL_VALUE["css_title"], text="#" + GLOBAL_VALUE["css_text"], border="#" + GLOBAL_VALUE["css_border"])


# ---------------------------------------------------------------- after every page
def finish():
    _read()
    for k in sorted(set(USER) - USED, key=lambda k: LINES[k]):
        if k[1] == "ALL" and any(s[0] == k[0] and s[2] == k[2] for s in SEEN):
            continue   # an ALL line whose pages were all named on their own
        where = "ALL pages of %s" % k[0] if k[1] == "ALL" else "%s's %s page" % (k[0], k[1])
        _bad(k, "%s has nothing called %s" % (where, k[2]))
    if ERRORS:
        sys.exit("X-Console colours file:\n  " + "\n  ".join(dict.fromkeys(ERRORS)))   # each once
    apply_art_globals()
    _write_file()
    _write_info()
    n = len({j[0] for j in JOBS})
    print("colours file: %d places, %d set by the file, %d new colour pictures" % (len(SEEN), sum(1 for k in SEEN if _eff(k) != SEEN[k]), n))


def run_jobs(d):
    done = set()
    for key, fn in JOBS:
        if key not in done:
            done.add(key)
            fn(d)


def _eff(k):
    """the value in force at place k: its page's line, else its preset's ALL line, else built in"""
    v = USER.get(k)
    if v is None:
        v = USER.get((k[0], "ALL", k[2]))
    if v is None:
        return SEEN[k]
    if KIND.get(k[2]) == "colour":
        return norm_colour(v) or SEEN[k]
    if KIND.get(k[2]) == "picture":
        try:
            return _pic_text(_pic_parse(v))
        except ValueError:
            return v.strip()
    if KIND.get(k[2]) == "label":
        return _label_text(v) or SEEN[k]
    if KIND.get(k[2]) == "number":
        try:
            return str(int(round(float(v.strip().lower().replace("px", "")))))
        except ValueError:
            return v.strip()
    if KIND.get(k[2]) == "choice":
        return " ".join(v.split()).upper()
    return " ".join(v.split()) if KIND.get(k[2]) == "meters" else v.strip().lower().replace(" ", "")


def _write_file():
    """the canonical file: every place, the file's value or the built-in one; ALL where every page agrees"""
    out = ["# X-Console colours. Edit with X-Console Theme Editor.exe, or here: change a value, save, run Rebuild X-Console.bat.",
           "# [PRESET] blocks; ALL / NAME = every page of the preset; PAGE / NAME = one page (wins over ALL).",
           "# Colours are #rrggbb. Knobs: a cap name, #body/#pointer, or #body (chicken-heads). METERS: dB #colour, ... (rising dB); #colour! = a solid band to the next (no fade).",
           "# The build rewrites this file in this form; your values are kept."]
    presets = [GLOBAL] + [ml.MODELS[m].upper() for m in ml.MODEL_ORDER]
    for pr in presets:
        keys = [k for k in SEEN if k[0] == pr]
        if not keys:
            continue
        out += ["", "[%s]" % pr]
        names = []
        for k in keys:
            if k[2] not in names:
                names.append(k[2])
        theme_first = sorted(names, key=lambda n: (KIND.get(n) == "knob", ))
        all_lines, page_lines = [], {pg: [] for pg in PAGES + [PANEL]}
        for n in theme_first:
            ks = [k for k in keys if k[2] == n]
            vals = {_eff(k) for k in ks}
            if len(ks) > 1 and len(vals) == 1:
                all_lines.append((n, vals.pop()))
            else:
                for k in ks:
                    page_lines[k[1]].append((n, _eff(k)))
        rows = [("ALL", n, v) for n, v in all_lines] + [(pg, n, v) for pg in PAGES + [PANEL] for n, v in page_lines[pg]]
        w = max(len("%s / %s" % (pg, n)) for pg, n, _ in rows)
        last = None
        for pg, n, v in rows:
            if last and pg != last:
                out.append("")
            out.append("%-*s = %s" % (w, "%s / %s" % (pg, n), v))
            last = pg
    open(FILE, "w", encoding="utf-8", newline="\r\n").write("\n".join(out) + "\n")


def _write_info():
    """for the Theme Editor: every place (preset, page, name, kind, style) and the caps' colours"""
    out = ["# X-Console Theme Editor's map of the skin, written by the build. Tab separated."]
    for name, (top, bot, ptr) in sorted(A.CAPS.items()):
        out.append("CAP\t%s\tround\t%s\t%s" % (name, hx(top), hx(ptr)))
    for name, (top, bot) in sorted(A.MOLTEN_CAPS.items()):
        out.append("CAP\t%s\tchicken\t%s\t#ecece8" % (name, hx(top)))
    for k, b in SEEN.items():
        out.append("PLACE\t%s\t%s\t%s\t%s\t%s\t%s" % (k[0], k[1], k[2], KIND.get(k[2], "colour"), STYLE.get(k, ""), b))
    open(INFO, "w", encoding="utf-8", newline="\r\n").write("\n".join(out) + "\n")


# ---------------------------------------------------------------- page backgrounds (user, 2026-11-10)
# "option 3, see-through panels, per plugin per page ... add the ability to change the background color of what is behind
# the transparent panels". The panels are only outlines (no fill), so the page's own colour is what shows in and between
# them. Per preset and page: PAGE BACKGROUND (colour), PAGE PICTURE (a photo over it: file | fill/fit/stretch | NN%),
# PANEL FILL + PANEL FILL OPACITY (a see-through tint inside each panel, 0% = none, as before). Drawn as ONE picture per
# preset and page, first on the page (under the banner, frames, labels, screens and controls). The layout carries it as a
# "#pagebg[PRESET] art ..." comment: the all-presets build skips it, tools/single-preset-build.sh uncomments its preset's.
PAGE_ITEMS = ("PAGE BACKGROUND", "PAGE PICTURE", "PANEL FILL", "PANEL FILL OPACITY")
PAGE_BOX = (0, 86, 1280, 628)   # the plugin area in layout coordinates (shadow_skin W, H, Y_OFF)


def _percent(page, name, builtin, m):
    k = (P(m), page, name)
    SEEN.setdefault(k, "%d%%" % builtin)
    KIND[name] = "percent"
    v, kk = lookup(*k)
    if v is None:
        return builtin
    try:
        n = int(round(float(v.strip().rstrip("%").strip())))
    except ValueError:
        _bad(kk, "%s / %s: %s isn't a percentage (0%% to 100%%)" % (page, name, v))
        return builtin
    if not 0 <= n <= 100:
        _bad(kk, "%s / %s: %d%% is outside 0%% to 100%%" % (page, name, n))
        return builtin
    return n


def _page_pic(m, page):
    k = (P(m), page, "PAGE PICTURE")
    SEEN.setdefault(k, "none")
    KIND["PAGE PICTURE"] = "picture"
    v, kk = lookup(*k)
    if v is None:
        return None
    try:
        p = _pic_parse(v)
    except ValueError as e:
        _bad(kk, "%s / PAGE PICTURE: %s" % (page, e))
        return None
    if p[0] != "file":
        return None
    src = os.path.join(PICS, p[1])
    if not os.path.isfile(src):
        _bad(kk, "%s / PAGE PICTURE: no picture called %s in the pictures folder" % (page, p[1]))
        return None
    return src, p[2], p[3]


def _page_draw(dst, bg, pic, fill, fill_op, frames):
    from PIL import Image, ImageDraw
    x0, y0, w, h = PAGE_BOX
    im = Image.new("RGBA", (w, h), rgb(bg) + (255,))
    if pic:
        tmp = dst + ".pic.png"
        _pic_draw(pic[0], tmp, (w, h), pic[1], pic[2])
        im.alpha_composite(Image.open(tmp).convert("RGBA"))
        os.remove(tmp)
    if fill_op:
        lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        for fx, fy, fw, fh in frames:
            d.rectangle((fx - x0, fy - y0, fx - x0 + fw - 1, fy - y0 + fh - 1), fill=rgb(fill) + (round(255 * fill_op / 100.0),))
        im.alpha_composite(lay)
    im.convert("RGB").save(dst)


def page_backgrounds(lines, models, shows):
    """lines with each preset's own page picture after its tab's qlinks line (as #pagebg[PRESET] comments).
    shows(m, when_key, value) -> whether a when= test passes for preset m (a frame on that preset's page)."""
    _read()
    import hashlib
    frames, tab = {}, None
    for ln in lines:
        if ln.startswith("[tab "):
            tab = ln[5:-1]
            frames[tab] = []
        elif tab and ln.startswith("frame "):
            d = dict(re.findall(r"\b([a-z]+)=(\d+)", ln))
            conds = re.findall(r"when=([a-z_]+):(\d+)", ln)
            frames[tab].append(((int(d["x"]), int(d["y"]), int(d["w"]), int(d["h"])), conds))
    bg0 = "#" + GLOBAL_VALUE["theme_bg"]
    extra = {}
    for tab, fr in frames.items():
        if tab not in PAGES:
            continue
        for m in models:
            bg = colour_item(P(m), tab, "PAGE BACKGROUND", bg0) or norm_colour(bg0)
            pic = _page_pic(m, tab)
            fill = colour_item(P(m), tab, "PANEL FILL", "#000000") or "#000000"
            op = _percent(tab, "PANEL FILL OPACITY", 0, m)
            if bg == norm_colour(bg0) and not pic and not op:
                continue   # as built in: nothing drawn, the page is as before
            rects = [r for r, conds in fr if all(shows(m, k, int(v)) for k, v in conds)]
            ph = hashlib.md5(open(pic[0], "rb").read()).hexdigest()[:10] if pic else "-"
            s = "upage_%s.png" % hashlib.md5(repr((bg, ph, pic[1:] if pic else None, fill, op, rects)).encode()).hexdigest()[:12]
            JOBS.append((s, lambda d, s=s, bg=bg, pic=pic, fill=fill, op=op, rects=rects: _page_draw(os.path.join(d, s), bg, pic, fill, op, rects)))
            extra.setdefault(tab, []).append('#pagebg[%s] art file="art/%s" x=%d y=%d w=%d h=%d' % ((P(m), s) + PAGE_BOX))
    out, tab = [], None
    for ln in lines:
        out.append(ln)
        if ln.startswith("[tab "):
            tab = ln[5:-1]
        elif tab and ln.startswith('qlinks "%s"' % tab):
            out += extra.pop(tab, [])
    for tab, ls in extra.items():   # a tab without its own qlinks line: right after [tab]
        i = out.index("[tab %s]" % tab) + 1
        out[i:i] = ls
    return out


# ---------------------------------------------------------------- sections, text colours and labels (user, 2026-11-10)
# "can the colors of the lines that create the 'panels' be changed in the editor? can the color and properties of the text
# that labels each section be changed ...? can the text under the knobs and buttons be changed ...?" -> "i want all 4 but i
# also need to be able to control the color of the text for each plugin". Per preset and page:
#   SECTION BORDERS / SECTION LINES / SECTION TITLES (colours; built-in = the panel's FRAME BORDERS, LINES, FRAME TITLES),
#   SECTION TITLE SIZE (px), SECTION TITLE WEIGHT (REGULAR/SEMIBOLD/BOLD), SECTION TITLE SPACING (px),
#   BUTTON NAMES (the words under the round buttons), TEXT (the other printed words: TYPE, SLOPE, dB / OCT, meter numbers),
#   and "LABEL: SECTION > NAME" places renaming a section title, knob, button, switch group or drop-down.
# The shared skin tool draws every frame and plain label in ONE colour per skin, so a preset that changes them gets its own
# copies of those lines: "#dropnext" + the shared line (the all-presets build keeps it; tools/single-preset-build.sh drops
# it) + one "#pagebg[PRESET] ..." copy per preset (single-preset-build.sh keeps its own preset's). A changed frame becomes an
# SVG (border + rule) and a text line (its title), drawn as the stock frame was: border 1.2 px, rule at y+36.5 from x+18 to
# x+w-18, title at (x+18, y+20), 20 px, weight 600, 2 px letter spacing.
SECTION_ITEMS = ("SECTION BORDERS", "SECTION LINES", "SECTION TITLES", "SECTION TITLE SIZE", "SECTION TITLE WEIGHT",
                 "SECTION TITLE SPACING", "BUTTON NAMES", "TEXT")
WEIGHTS = {"REGULAR": 400, "SEMIBOLD": 600, "BOLD": 700}
TEXT_PAGES = ("PREAMP", "SHAPE", "EQ", "COMP", "OUTPUT")   # SETUP/INFO: tools/single-preset-build.sh rewrites its text


def _label_text(v):
    return " ".join(v.replace('"', "").split())


def _number(m, page, name, builtin, lo, hi):
    k = (P(m), page, name)
    SEEN.setdefault(k, str(builtin))
    KIND[name] = "number"
    STYLE[k] = "%d-%d" % (lo, hi)
    v, kk = lookup(*k)
    if v is None:
        return builtin
    try:
        n = int(round(float(v.strip().lower().replace("px", ""))))
    except ValueError:
        _bad(kk, "%s / %s: %s isn't a number" % (page, name, v))
        return builtin
    if not lo <= n <= hi:
        _bad(kk, "%s / %s: %d is outside %d to %d" % (page, name, n, lo, hi))
        return builtin
    return n


def _choice(m, page, name, builtin, options):
    k = (P(m), page, name)
    SEEN.setdefault(k, builtin)
    KIND[name] = "choice"
    STYLE[k] = ",".join(options)
    v, kk = lookup(*k)
    if v is None:
        return builtin
    c = " ".join(v.split()).upper()
    if c not in options:
        _bad(kk, "%s / %s: %s isn't one of %s" % (page, name, v, ", ".join(options)))
        return builtin
    return c


def _label(m, page, name, builtin):
    k = (P(m), page, name)
    SEEN.setdefault(k, builtin)
    KIND[name] = "label"
    v, kk = lookup(*k)
    if v is None:
        return builtin
    return _label_text(v) or builtin


def _frame_svg(dst, w, h, border, line):
    open(dst, "w").write(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">\n'
        '  <rect x="0.5" y="0.5" width="%d" height="%d" fill="none" stroke="%s" stroke-width="1.2"/>\n'
        '  <line x1="18" y1="36.5" x2="%d" y2="36.5" stroke="%s" stroke-width="1"/>\n</svg>\n'
        % (w, h, w, h, w - 1, h - 1, border, w - 18, line))


def _num(ln, a):
    m = re.search(r"\b%s=(-?[\d.]+)" % a, ln)
    return float(m.group(1)) if m else None


def _set_label(ln, lab):
    return re.sub(r'\blabel="[^"]*"', 'label="%s"' % lab, ln, count=1)


def sections_and_labels(lines, models, shows):
    """lines with each preset's own frames, text colours and labels where it changes them (see above)"""
    _read()
    import hashlib
    b_border, b_line, b_title, ink = ("#" + GLOBAL_VALUE[k] for k in ("css_border", "theme_line", "css_title", "theme_ink"))
    top, bottom = ml.TOP, ml.BOTTOM
    out, i = [], 0
    while i < len(lines):
        j = i + 1
        while j < len(lines) and not lines[j].startswith("[tab "):
            j += 1
        block = lines[i:j]
        page = block[0][5:-1] if block[0].startswith("[tab ") else None
        i = j
        if page not in PAGES:
            out += block
            continue
        conds = [re.findall(r"when=([a-z_]+):(\d+)", ln) for ln in block]
        when = [" ".join(re.findall(r"when=\S+", ln)) for ln in block]
        frames = []
        for n, ln in enumerate(block):
            if ln.startswith("frame "):
                t = re.search(r'title="([^"]*)"', ln)
                frames.append((n, tuple(int(_num(ln, a)) for a in ("x", "y", "w", "h")), t.group(1) if t else ""))
        toggles = {}
        for ln in block:
            if ln.startswith("toggle "):
                k = re.search(r"\bkey=(\S+)", ln)
                toggles[(_num(ln, "cx"), _num(ln, "cy"))] = k.group(1) if k else ""
        texted = page in TEXT_PAGES
        var = {}   # line number -> {preset: [lines]}
        for m in models:
            P_ = P(m)
            vis = lambda n: all(shows(m, k, int(v)) for k, v in conds[n])
            border = colour_item(P_, page, "SECTION BORDERS", b_border)
            line = colour_item(P_, page, "SECTION LINES", b_line)
            title_c = colour_item(P_, page, "SECTION TITLES", b_title)
            size = _number(m, page, "SECTION TITLE SIZE", 20, 8, 40)
            weight = _choice(m, page, "SECTION TITLE WEIGHT", "SEMIBOLD", tuple(WEIGHTS))
            spacing = _number(m, page, "SECTION TITLE SPACING", 2, 0, 20)
            btn_c = colour_item(P_, page, "BUTTON NAMES", ink) if texted else None
            text_c = colour_item(P_, page, "TEXT", ink) if texted else None
            fm = [f for f in frames if vis(f[0])]

            def section(cx, cy):
                hit = [f for f in fm if f[1][0] <= cx <= f[1][0] + f[1][2] and f[1][1] <= cy <= f[1][1] + f[1][3]]
                return min(hit, key=lambda f: f[1][2] * f[1][3]) if hit else None
            # the labels: section titles, then each section's controls top to bottom, left to right
            new_label, seen_t = {}, set()
            for n, xywh, title in fm:
                if title and title not in seen_t:
                    seen_t.add(title)
                    new_label[("title", title)] = _label(m, page, "LABEL: %s" % title, title)
            ctl = {}     # (section title, label) -> [(cy, cx, ident)]
            where = {}   # line number -> (ident, label)
            if texted:
                for n, ln in enumerate(block):
                    kind = ln.split(" ", 1)[0]
                    if kind not in ("knob", "enum_h", "enum_v", "popup", "text") or not vis(n):
                        continue
                    cx, cy = _num(ln, "cx"), _num(ln, "cy")
                    if cx is None or cy is None or not top <= cy <= bottom:
                        continue
                    lab = re.search(r'\blabel="([^"]*)"', ln)
                    if not lab or not lab.group(1):
                        continue
                    if kind == "text":
                        if (cx, cy - 44) not in toggles:
                            continue
                        ident = "btn:" + toggles[(cx, cy - 44)]
                    else:
                        k = re.search(r"\bkey=(\S+)", ln)
                        ident = k.group(1) if k else "%g,%g" % (cx, cy)
                    sec = section(cx, cy)
                    if not sec:
                        continue
                    where[n] = (ident, lab.group(1))
                    lst = ctl.setdefault((sec[2], lab.group(1)), [])
                    if ident not in [c[2] for c in lst]:
                        lst.append((cy, cx, ident))
                names = {}
                for (st, lab), lst in ctl.items():
                    lst.sort()
                    for k_, (cy, cx, ident) in enumerate(lst):
                        names[(ident, lab)] = "LABEL: %s > %s%s" % (st, lab, " %d" % (k_ + 1) if len(lst) > 1 else "")
                order = sorted(ctl.items(), key=lambda kv: (min(c[0] for c in kv[1]), min(c[1] for c in kv[1])))
                done_t = set()
                for fn, xywh, title in fm:   # register in reading order: section by section
                    if title in done_t:
                        continue
                    done_t.add(title)
                    for (st, lab), lst in order:
                        if st != title:
                            continue
                        for cy, cx, ident in lst:
                            if (ident, lab) not in new_label:
                                new_label[(ident, lab)] = _label(m, page, names[(ident, lab)], lab)
            custom = bool(border or line or title_c or size != 20 or weight != "SEMIBOLD" or spacing != 2)
            for n, ln in enumerate(block):
                cond = (" " + when[n]) if when[n] else ""
                if ln.startswith("frame "):
                    f = next(f for f in frames if f[0] == n)
                    t = new_label.get(("title", f[2]), f[2]) if f[2] else ""
                    if not custom and t == f[2]:
                        var.setdefault(n, {})[P_] = [ln]
                        continue
                    x, y, w, h = f[1]
                    bc, lc = border or b_border, line or b_line
                    sname = "ufr_%s.svg" % hashlib.md5(repr((w, h, bc, lc)).encode()).hexdigest()[:12]
                    JOBS.append((sname, lambda d, s=sname, w=w, h=h, bc=bc, lc=lc: _frame_svg(os.path.join(d, s), w, h, bc, lc)))
                    vl = ['art file="art/%s" x=%d y=%d w=%d h=%d%s' % (sname, x, y, w, h, cond)]
                    if t:
                        vl.append('text cx=%d cy=%d size=%g weight=%d spacing=%g align=left label="%s" color=%s%s'
                                  % (x + 18, y + 20, size / 10.0, WEIGHTS[weight], spacing, t, (title_c or b_title)[1:], cond))
                    var.setdefault(n, {})[P_] = vl
                    continue
                if not texted:
                    continue
                kind = ln.split(" ", 1)[0]
                v = None
                if n in where:
                    ident, lab = where[n]
                    nl = new_label.get((ident, lab), lab)
                    if kind == "text":   # a button's name
                        if nl != lab or btn_c:
                            v = [_set_label(ln, nl) + (" color=%s" % btn_c[1:] if btn_c else "")]
                    elif kind == "enum_h" and (nl != lab or text_c):   # its group label as a text line, as baked
                        v = [_set_label(ln, ""), 'text cx=%d cy=%d size=1 label="%s" color=%s%s'
                             % (_num(ln, "cx"), _num(ln, "cy") - 33 // 2 - 22, nl, (text_c or ink)[1:], cond)]
                    elif kind == "enum_v" and (nl != lab or text_c):   # baked above the column in ACCENT LIGHT
                        nopt = len(re.search(r'\boptions="([^"]*)"', ln).group(1).split(","))
                        v = [_set_label(ln, ""), 'text cx=%d cy=%d size=1 label="%s" color=%s%s'
                             % (_num(ln, "cx"), _num(ln, "cy") - (nopt * 32) // 2 - 24, nl,
                                (text_c or "#" + GLOBAL_VALUE["theme_accent_hi"])[1:], cond)]
                    elif kind == "popup" and (nl != lab or text_c):   # baked over the box's left edge in DIM TEXT
                        pw, ph = _num(ln, "w"), _num(ln, "h")
                        v = [_set_label(ln, ""), 'text cx=%d cy=%d size=1.5 weight=600 spacing=1.2 align=left label="%s" color=%s%s'
                             % (_num(ln, "cx") - pw // 2, _num(ln, "cy") - ph // 2 - 15, nl,
                                (text_c or "#" + GLOBAL_VALUE["theme_ink_dim"])[1:], cond)]
                    elif nl != lab:
                        v = [_set_label(ln, nl)]
                elif kind == "text" and text_c and " color=" not in ln:
                    cy = _num(ln, "cy")
                    if cy is not None and top <= cy <= bottom:
                        v = [ln + " color=%s" % text_c[1:]]
                if v:
                    var.setdefault(n, {})[P_] = v
        for n, ln in enumerate(block):
            vs = var.get(n)
            if not vs or all(x == [ln] for x in vs.values()):
                out.append(ln)
                continue
            out += ["#dropnext", ln]
            for m in models:
                for x in vs.get(P(m), [ln]):
                    out.append("#pagebg[%s] %s" % (P(m), x))
    return out
