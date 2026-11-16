"""Theme Editor knob colours for the metal custom pages (user, 2026-11-11: "can the editor be updated to allow knob colors
to be edited?" -> "proceed").

Every X-Console plugin's pages are metal_pages.py pictures now, which never read the colours file's knob rows (those are
the old round caps). The knob choices for metal pages live in their own file, tools/metal-knobs.txt (written by the
Theme Editor):

    [flannel]                       # the plugin's tag (tools/plugins.sh)
    ALL / in_gain = red           # every page that has the knob
    PREAMP / nz_level = lblue     # one page (wins over ALL)
    EQ / eq_lf_gain = #6aa8e8/#ffffff   # any colour: #body/#pointer (#body alone: pointer picked for contrast)
    EQ / eq_lf_freq = hexx-silver-red:#6aa8e8   # a shaped cap (SHAPES) in any colour: same shape, that colour

A value is one of the script's own cap styles (STYLES) or a colour. Nothing set = the script's own choice, so an empty
file builds exactly what the scripts drew before.

What each script calls:
  save_list(mod, lay, seen)   after a full run (or --knobs): <tag>/knobs.txt for the editor (the page's knobs, the styles,
                              each style's colours) + <tag>/styles/<style>.png (small previews)
  apply(mod, art, lay)        in the build (--strips) and after a full run: draws a cap for every changed knob
                              (<PFX>knob_<key>__u<page>_<look>.png) and points that knob's .layout line at it; unchanged
                              knobs go back to the script's own <PFX>knob_<key>.png
"""
import glob, os, re
import fixed_light as FL
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(HERE, '..', 'metal-knobs.txt')
LIST = 'knobs.txt'
LIFT = 6.0   # see look()
FILE_PAGE = {'INFO': 'SETUP'}   # the editor's (and colours file's) name for the INFO page


def _tag(mod):
    return os.path.basename(os.path.dirname(os.path.abspath(mod.__file__)))


def _hex(s):
    s = s.strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', s):
        return None
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _h(c):
    return '#%02x%02x%02x' % tuple(int(v) for v in c[:3])


def read_values(tag, path=FILE):
    """{(PAGE, key): value} for one plugin; PAGE is the metal tab name (INFO, not SETUP) or ALL"""
    out, sect = {}, None
    if not os.path.exists(path):
        return out
    for n, raw in enumerate(open(path, encoding='utf-8-sig'), 1):
        ln = re.sub(r'\s+#\s.*$', '', raw.strip())
        if not ln or ln.startswith('#'):
            continue
        if ln.startswith('[') and ln.endswith(']'):
            sect = ln[1:-1].strip().lower()
            continue
        if sect != tag:
            continue
        if '=' not in ln or '/' not in ln.split('=', 1)[0]:
            print('  metal-knobs.txt line %d: not "PAGE / key = value", skipped' % n, flush=True)
            continue
        left, v = ln.split('=', 1)
        pg, key = left.split('/', 1)
        pg = ' '.join(pg.split()).upper()
        pg = {'SETUP': 'INFO'}.get(pg, pg)
        out[(pg, key.strip().lower())] = v.strip()
    return out


# Extra metal caps every plugin lists after its own (user 2026-11-12: "add the extra metal colours to the caps list").
# name, body colour (as it measures on the cap), pointer (None = dark or white for contrast), swirl (None = as a picked colour)
EXTRA = [
    ('chrome',    (214, 218, 226), (20, 20, 24), 64),
    ('titanium',  (150, 156, 170), None, None),
    ('gunmetal',  (84, 88, 98),    None, None),
    ('champagne', (222, 204, 170), None, None),
    ('brass',     (196, 164, 84),  (40, 30, 14), None),
    ('rosegold',  (214, 150, 132), None, None),
    ('orange',    (226, 116, 40),  None, None),
    ('yellow',    (232, 196, 44),  (30, 24, 8), None),
    ('burgundy',  (132, 26, 44),   None, None),
    ('purple',    (128, 74, 188),  None, None),
    ('cobalt',    (40, 82, 192),   None, None),
    ('ice',       (156, 204, 238), None, None),
    ('teal',      (30, 150, 152),  None, None),
    ('emerald',   (30, 150, 82),   None, None),
]


# Shaped caps (user 2026-11-14: "add all the knobs submitted today to the x-console editor"): the realistic-caps shapes
# (realistic-caps-mock/real_caps.py cap_frame, from assets/hexx and pointer knobs.png, hexx knobs*.png, mad knobs.png), each in
# the colours of the pictures. name -> (shape, colour); the colour is the part that changes (insert / top / skirt / body).
SHAPES = [
    ('pointer',            'pointer',    (226, 214, 184)),
    ('hexcap',            'hexcap',    (40, 40, 42)),
]
# pointer skirt colours (user 2026-11-15: "there is only one knob for pointer. please give it as many colors as the other knobs");
# 'pointer' (cream) keeps its name, 15 more = 16 like the tops
for _c, _rgb in [('black', (24, 24, 26)), ('white', (238, 238, 236)), ('grey', (110, 112, 116)), ('silver', (200, 202, 206)),
                 ('red', (214, 46, 40)), ('blue', (28, 62, 168)), ('green', (22, 120, 64)), ('yellow', (236, 196, 30)),
                 ('orange', (232, 110, 30)), ('purple', (110, 60, 170)), ('pink', (222, 80, 150)), ('teal', (20, 140, 140)),
                 ('sky', (90, 170, 230)), ('burgundy', (128, 24, 40)), ('gold', (212, 168, 60))]:
    SHAPES.append(('pointer-' + _c, 'pointer', _rgb))
for _c, _rgb in [('blue', (28, 62, 168)), ('green', (22, 120, 64)), ('grey', (70, 70, 72)), ('red', (214, 46, 40)),
                 ('yellow', (236, 196, 30)), ('white', (238, 238, 236)),
                 # more insert colours (user 2026-11-14: "add more colours for the hexx knobs")
                 ('orange', (232, 110, 30)), ('purple', (110, 60, 170)), ('pink', (222, 80, 150)), ('teal', (20, 140, 140)),
                 ('sky', (90, 170, 230)), ('black', (24, 24, 26)), ('cream', (226, 214, 184)), ('burgundy', (128, 24, 40))]:
    SHAPES.append(('hexx-silver-' + _c, 'tabcap', _rgb))
    SHAPES.append(('hexx-black-' + _c, 'tabcapblk', _rgb))
for _c, _rgb in [('blue', (28, 62, 168)), ('green', (22, 120, 64)), ('silver', (200, 202, 206)), ('red', (214, 46, 40)),
                 ('yellow', (236, 180, 30)),
                 # more top colours (user 2026-11-15: "generate more colors of the blacktop, greytop, and spuntop knobs")
                 ('orange', (232, 110, 30)), ('purple', (110, 60, 170)), ('pink', (222, 80, 150)), ('teal', (20, 140, 140)),
                 ('sky', (90, 170, 230)), ('white', (238, 238, 236)), ('cream', (226, 214, 184)), ('burgundy', (128, 24, 40)),
                 ('gold', (212, 168, 60)), ('lime', (140, 200, 40)), ('grey', (110, 112, 116))]:
    SHAPES.append(('blacktop-' + _c, 'colourtop', _rgb))
for _c, _rgb in [('orange', (232, 110, 40)), ('red', (214, 46, 40)), ('yellow', (236, 196, 30)), ('blue', (40, 110, 200)),
                 ('pink', (214, 60, 150)), ('green', (40, 160, 80)),
                 ('purple', (110, 60, 170)), ('teal', (20, 140, 140)), ('sky', (90, 170, 230)), ('white', (238, 238, 236)),
                 ('black', (24, 24, 26)), ('cream', (226, 214, 184)), ('burgundy', (128, 24, 40)), ('silver', (200, 202, 206)),
                 ('gold', (212, 168, 60)), ('lime', (140, 200, 40))]:
    SHAPES.append(('greytop-' + _c, 'greytop', _rgb))
for _c, _rgb in [('black', (30, 30, 32)), ('red', (200, 30, 28)), ('blue', (30, 80, 150)), ('white', (230, 228, 222)),
                 ('green', (22, 120, 64)), ('yellow', (236, 196, 30)), ('orange', (232, 110, 30)), ('purple', (110, 60, 170)),
                 ('pink', (222, 80, 150)), ('teal', (20, 140, 140)), ('sky', (90, 170, 230)), ('grey', (110, 112, 116)),
                 ('cream', (226, 214, 184)), ('burgundy', (128, 24, 40)), ('gold', (212, 168, 60)), ('lime', (140, 200, 40))]:
    SHAPES.append(('spuntop-' + _c, 'spuntop', _rgb))
# Neve caps (user 2026-11-15: "add these knobs to the collection", assets/suede knobs.png): photo cuts in real_caps.py.
# suede-ear = the blue/red ear knob on a grey skirt (colour = the ear body); suede-knurl = knurled silver ring + fluted cap;
# suede-fluted = fluted cap on a grey skirt (colour = the cap; grey = the photo as is).
_SUEDE_COLS = [('green', (22, 120, 64)), ('yellow', (236, 196, 30)), ('white', (238, 238, 236)), ('orange', (232, 110, 30)),
              ('purple', (110, 60, 170)), ('pink', (222, 80, 150)), ('teal', (20, 140, 140)), ('sky', (90, 170, 230)),
              ('black', (24, 24, 26)), ('cream', (226, 214, 184)), ('burgundy', (128, 24, 40))]
for _c, _rgb in [('blue', (32, 62, 140)), ('red', (156, 26, 32)), ('grey', (110, 112, 116))] + _SUEDE_COLS:
    SHAPES.append(('suede-ear-' + _c, 'suedeear', _rgb))
for _shape, _own in [('knurl', (128, 133, 145)), ('fluted', (123, 128, 138))]:
    for _c, _rgb in [('grey', _own), ('blue', (32, 62, 140)), ('red', (156, 26, 32))] + _SUEDE_COLS:
        SHAPES.append(('suede-%s-%s' % (_shape, _c), 'suede' + _shape, _rgb))
SHAPE = {n: (sh, c) for n, sh, c in SHAPES}
TOPPED = {'pointer'}   # shapes with a second (top) colour: "cap:#skirt/#top" (user 2026-11-15)
_rc = None


def _real_caps():
    global _rc
    if _rc is None:
        import sys
        p = os.path.join(HERE, 'realistic-caps-mock')
        if p not in sys.path:
            sys.path.insert(0, p)
        import real_caps
        _rc = real_caps
    return _rc


def _ptr_for(body):
    lum = 0.299 * body[0] + 0.587 * body[1] + 0.114 * body[2]
    return (18, 18, 22) if lum > 150 else (246, 246, 248)


def _metal(body, ptr, swirl=None):
    """(base, tint, pointer) for cap(): a colour as brushed metal"""
    lum = max(0.299 * body[0] + 0.587 * body[1] + 0.114 * body[2], 12.0)
    # brushed-metal brightness and swirl, as the script's own styles; +LIFT because the cap's darker rim pulls its
    # measured colour about 6 below the base (user 2026-11-12: a picked colour should look as bright as the built-in caps)
    base = (lum + LIFT, swirl if swirl else min(60.0, max(26.0, 0.25 * lum + 18)))
    return base, tuple(c / lum for c in body), ptr


def _extras(mod):
    """registers EXTRA in the script's CUSTOM and STYLES once (a name the script already has keeps the script's own)"""
    if getattr(mod, '_xc_extras', False) or not hasattr(mod, 'STYLES'):
        return
    mod._xc_extras = True
    for name, body, ptr, swirl in EXTRA:
        if name in mod.STYLES:
            continue
        if chicken(mod):
            mod.CUSTOM[name] = (body, tuple(int(c * 0.42) for c in body))   # chicken-head top / bottom
        else:
            mod.CUSTOM[name] = _metal(body, ptr or _ptr_for(body), swirl)
        mod.STYLES.append(name)
    for name, _, _ in SHAPES:
        if name not in mod.STYLES:
            mod.STYLES.append(name)


def styles_of(mod):
    _extras(mod)
    return list(getattr(mod, 'STYLES', []))


def chicken(mod):
    return hasattr(mod, 'knob_pic')


def look(mod, v):
    """a value -> a style name the script's cap() knows (registering a colour as a custom one), or None if it's no good"""
    s = v.strip()
    if s.lower() in styles_of(mod):
        return s.lower()
    if ':' in s:   # a shaped cap in any colour (user 2026-11-15): "hexx-silver-red:#6aa8e8" keeps the shape, recolours it
        # "pointer-red:#6aa8e8/#c0c0c0" = skirt / top; either may be left empty ("pointer-red:/#c0c0c0" = own skirt, silver top)
        base, rest = s.split(':', 1)
        base = base.strip().lower()
        if base not in SHAPE:
            return None
        shape, own = SHAPE[base][0], SHAPE[base][1]
        parts = [x.strip() for x in rest.split('/')]
        if len(parts) > 2 or (len(parts) == 2 and shape not in TOPPED):
            return None
        col = _hex(parts[0]) if parts[0] else own
        top = (_hex(parts[1]) if parts[1] else None) if len(parts) == 2 else None
        if col is None or (len(parts) == 2 and parts[1] and top is None):
            return None
        name = '%s_u%02x%02x%02x' % ((base,) + tuple(col))
        if top is not None:
            name += 't%02x%02x%02x' % top
            col = (tuple(col), top)
        SHAPE[name] = (shape, col)
        return name
    parts = s.split('/')
    body = _hex(parts[0])
    if body is None or len(parts) > 2:
        return None
    if chicken(mod):
        name = 'u%02x%02x%02x' % body
        mod.CUSTOM[name] = (body, tuple(int(c * 0.42) for c in body))   # chicken-head top / bottom
        return name
    if len(parts) == 2:
        ptr = _hex(parts[1])
        if ptr is None:
            return None
    else:
        ptr = _ptr_for(body)
    name = 'u%02x%02x%02x%02x%02x%02x' % (body + ptr)
    mod.CUSTOM[name] = _metal(body, ptr)
    return name


FIXED_LIGHT = os.environ.get('XC_FIXED_LIGHT', '1') != '0'   # 0 = the old way (one picture the skin turns, light and all)


def _shaped(t):
    shape, col, R, box, n = t
    return (_real_caps(), shape, col, R, box, n)


def picture(mod, r, rw, style):
    """the knob's turning picture, exactly as the script's control_pictures() cuts it"""
    S = mod.S
    if style in SHAPE:   # a shaped cap: the realistic-caps drawing, pointer up, same box as the script's own
        shape, col = SHAPE[style]
        box = 2 * rw + 8
        return _real_caps().cap_frame(shape, col, 0.0, R=float(r), box=float(box), n=int(box * S))
    if chicken(mod):
        box = (2 * rw + 8) * S
        kp = mod.knob_pic(r, style)
        im = Image.new('RGBA', (box, box), (0, 0, 0, 0))
        im.alpha_composite(kp, ((box - kp.size[0]) // 2, (box - kp.size[1]) // 2))
        return im
    box = 2 * rw + 8
    return mod.extract(lambda cv: mod.cap(cv, 640, 314, r, style, 0.5), 640 - box / 2, 314 - box / 2, box, box)


def colours(mod, style):
    """(body, pointer) of a style, measured off its picture (pointer None for chicken-heads)"""
    r = 30
    im = np.asarray(picture(mod, r, r, style)).astype(np.float32)
    n = im.shape[0]
    c = n / 2
    yy, xx = np.mgrid[0:n, 0:n]
    k = n / (2 * r + 8)                       # picture px per screen px
    rr = np.hypot(xx - c, yy - c) / k
    near_ptr = (np.abs(xx - c) / k < 4) & (yy < c)
    disc = (im[..., 3] > 240) & (rr < (0.55 if chicken(mod) else 0.7) * r) & ~near_ptr
    if style in SHAPE and SHAPE[style][0] in TOPPED:   # pointer: body = the skirt (the editor's skirt swatch), pointer spot = the top
        disc = (im[..., 3] > 240) & (rr > 0.64 * r) & (rr < 0.86 * r) & ~near_ptr
    body = np.median(im[disc][:, :3], axis=0) if disc.any() else (128, 128, 128)
    if chicken(mod):
        return _h(body), None
    p = im[int(c - 0.55 * 0.8 * r * k), int(c)]
    return _h(body), _h(p)


def save_list(mod, lay, seen):
    """seen: {tab: [knob dicts]} from this run; tabs not drawn now keep their old lines"""
    path = os.path.join(lay, LIST)
    old = []
    if os.path.exists(path):
        old = [l.rstrip('\n').split('\t') for l in open(path, encoding='utf-8') if l.startswith('KNOB\t')]
    order = [t for t, _ in mod.PAGES]
    rows = []
    for tab in order:
        if tab in seen:
            labs = [' '.join(str(c.get('lab', c['key'])).split()) for c in seen[tab]]
            for c, lab in zip(seen[tab], labs):
                rw = int(round(c['by'] - c['cy'] - 15))
                bits = c['key'].split('_')
                if labs.count(lab) > 1 and len(bits) >= 3:   # EQ bands: GAIN x4 -> LF GAIN, LMF GAIN ...
                    lab = bits[1].upper() + ' ' + lab
                rows.append(['KNOB', tab, c['key'], lab, c['style'], str(c['r']), str(rw)])
        else:
            rows.extend(r for r in old if r[1] == tab)
    sdir = os.path.join(lay, 'styles')
    os.makedirs(sdir, exist_ok=True)
    lines = ['# Knobs on this plugin\'s metal pages, for the X-Console Theme Editor (written by metal_pages.py). Tab separated.',
             '# KIND chicken|metal; STYLE name body pointer preview [shape]; KNOB page key label style r value-radius',
             'KIND\t' + ('chicken' if chicken(mod) else 'metal')]
    for st in styles_of(mod):
        b, p = colours(mod, st)
        picture(mod, 30, 30, st).resize((34, 34), Image.LANCZOS).save(os.path.join(sdir, st + '.png'))
        lines.append('\t'.join(['STYLE', st, b, p or '', 'styles/%s.png' % st] + (['shape'] if st in SHAPE else [])))
    lines += ['\t'.join(r) for r in rows]
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')
    print('  knobs.txt: %d knobs, %d styles' % (len(rows), len(styles_of(mod))), flush=True)


def apply(mod, art, lay):
    tag = _tag(mod)
    path = os.path.join(lay, LIST)
    if not os.path.exists(path):
        print('  knob colours: no knobs.txt yet (run metal_pages.py --knobs), knobs as drawn', flush=True)
        return
    knobs = [l.rstrip('\n').split('\t') for l in open(path, encoding='utf-8') if l.startswith('KNOB\t')]
    vals = read_values(tag)
    for f in glob.glob(os.path.join(art, mod.PFX + 'knob_*__u*.png')):
        os.remove(f)
    want, changed, bad = {}, [], []
    shaped = {}   # img -> (shape, colour, R, box, n): a realistic-caps shape, drawn at each angle for its strip
    for _, tab, key, lab, style, r, rw in knobs:
        v = vals.get((tab, key), vals.get(('ALL', key)))
        img = mod.PFX + 'knob_%s.png' % key
        if v is not None:
            st = look(mod, v)
            if st is None:
                bad.append('%s / %s = %s' % (FILE_PAGE.get(tab, tab), key, v))
            elif st != style:
                img = mod.PFX + 'knob_%s__u%s_%s_%s.png' % (key, r, rw, st)   # one picture per size and look (INPUT on 6 pages: 1)
                if not os.path.exists(os.path.join(art, img)):
                    picture(mod, int(r), int(rw), st).save(os.path.join(art, img))
                if st in SHAPE:
                    box = 2 * int(rw) + 8
                    shaped[img] = (SHAPE[st][0], SHAPE[st][1], float(r), float(box), int(box * mod.S))
                changed.append('%s %s %s' % (tab, key, v))
        want[(tab, key)] = img
    strips = 0
    for tab, _ in mod.PAGES:
        lp = os.path.join(lay, tab + '.layout')
        if not os.path.exists(lp):
            continue
        out = []
        for ln in open(lp).read().splitlines():
            m = re.match(r'knob .*\bkey=(\S+)', ln)
            if m:   # a strip from an earlier build: back to its picture first
                ln = re.sub(r'\bstrip=art/(\S+)%s\.png frames=\d+' % FL.SUFFIX, r'img=art/\1.png', ln)
            if m and (tab, m.group(1)) in want:
                ln = re.sub(r'\bimg=art/\S+', 'img=art/' + want[(tab, m.group(1))], ln)
            if m and FIXED_LIGHT and not chicken(mod):   # the light stays put while the cap turns (2026-11-15)
                im = re.search(r'\bimg=art/(\S+)', ln)
                if im and os.path.exists(os.path.join(art, im.group(1))):
                    sh = _shaped(shaped[im.group(1)]) if im.group(1) in shaped else None
                    sp = FL.make_strip(os.path.join(art, im.group(1)), shaped=sh)
                    ln = ln.replace(im.group(0), 'strip=art/%s frames=%d' % (os.path.basename(sp), FL.FRAMES))
                    strips += 1
            out.append(ln)
        open(lp, 'w').write('\n'.join(out) + '\n')
    for b in bad:
        print('  metal-knobs.txt [%s] %s: not a cap style (%s) or #body/#pointer; knob as drawn' % (tag, b, ', '.join(styles_of(mod))), flush=True)
    print('  knob colours: %s' % ('; '.join(changed) if changed else 'as drawn'), flush=True)
    if strips:
        print('  fixed light: %d knobs as %d-frame strips' % (strips, FL.FRAMES), flush=True)


def knobs_only(mod, conf, lay):
    """--knobs: draw the pages in memory only to list their knobs (nothing else is written)"""
    mod.CONF = conf
    mod.load_textures()
    seen = {}
    for tab, fn in mod.PAGES:
        mod.CTRL.clear(); mod.EXTRA.clear()
        cv = mod.Cv()
        fn(cv)
        seen[tab] = [dict(c) for c in mod.CTRL if c['kind'] == 'knob']
    save_list(mod, lay, seen)
