"""Theme Editor drop-down colours for the metal custom pages (user, 2026-11-11: the PREAMP WAVEFORM drop-down's text and
arrow stayed light blue on Flannel with DROP-DOWN TEXT set to white).

Each metal_pages.py writes its drop-downs (PREAMP WAVEFORM, OUTPUT ORDER) as live "popup" lines with its own fixed
accent= / field_ink= / list_ink=, so the colours file's DROP-DOWN rows never reached them. The build (--strips) now
calls apply(mod, art, lay, colours): on every popup line of every page,

    accent=     DROP-DOWN            the field's border, the picked list row
    field_ink=  DROP-DOWN TEXT       the field's text and arrow
    list_ink=   DROP-DOWN LIST TEXT  the unpicked rows of the open list

take the editor's value where it differs from the built-in one (tools/colours-info.txt, the build's own rule; a page
line wins over ALL), else the script's own value, so an untouched colours file builds exactly what the scripts drew.
The arrow is painted into the page background by field(): when DROP-DOWN TEXT changes, the arrow is drawn again in that
colour (FIELD_ARROW / FIELD_GLOW, as drawn vs new, difference added) on a copy <bg>__dd.png the .layout points at.

drawn_list(mod, lay) writes <lay>/dropdown.txt (DRAWN page item #hex: the script's own colours) so the Theme Editor's
untouched DROP-DOWN rows show the colour the metal page draws.
"""
import glob, inspect, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
INFO = os.path.join(HERE, '..', 'colours-info.txt')
FILE_PAGE = {'INFO': 'SETUP'}
SECTION = {'granite': 'GRANITE', 'mocha': 'MOCHA', 'flannel': 'FLANNEL', 'hexx': 'HEXX', 'spades': 'SPADES',
           'molten': 'MOLTEN', 'hearts': 'HEARTS', 'suede': 'SUEDE', 'sandstone': 'SANDSTONE', 'titanium': 'TITANIUM'}
KEYS = (('accent', 'DROP-DOWN'), ('field_ink', 'DROP-DOWN TEXT'), ('list_ink', 'DROP-DOWN LIST TEXT'))


def _hex(s):
    s = (s or '').strip().lstrip('#')
    return s.lower() if re.fullmatch(r'[0-9a-fA-F]{6}', s) else None


def builtins(section):
    out = {}
    names = {it for _, it in KEYS}
    if os.path.exists(INFO):
        for l in open(INFO, encoding='utf-8'):
            p = l.rstrip('\n').split('\t')
            if len(p) > 6 and p[0] == 'PLACE' and p[1] == section and p[3] in names:
                out[(p[2], p[3])] = p[6].strip().lower()
    return out


def own(mod):
    """{accent: hex, field_ink: hex, list_ink: hex}: the colours the script writes on its popup lines"""
    m = re.search(r"'popup [^']*accent=(\w{6}) [^']*field_ink=(\w{6}) [^']*list_ink=(\w{6})", inspect.getsource(mod))
    return dict(zip([k for k, _ in KEYS], (g.lower() for g in m.groups()))) if m else None


def wanted(vals, section, built, tab, mine, keys=KEYS):
    pg = FILE_PAGE.get(tab, tab)
    out, changed = dict(mine), []
    for key, it in keys:
        v = vals.get((section, pg, it), vals.get((section, 'ALL', it)))
        # 2026-11-13 (user: the drop-down text/arrow colour "will not save"): any value that differs from what the page
        # draws, no longer "differs from the old flat skin's built-in" (white on Hexx = that built-in, so it was skipped).
        # The Theme Editor's built-in for these rows is now the drawn colour; the colours file was moved over once.
        if v is None or (pg, it) not in built:
            continue
        c = _hex(v)
        if c is None:
            print('  colours: %s / %s = %s is not #rrggbb, as drawn' % (pg, it, v), flush=True)
            continue
        if c == mine[key]:
            continue
        out[key] = c
        changed.append('%s #%s' % (it, c))
    return out, changed


def drawn_list(mod, lay, mine):
    path = os.path.join(lay, 'dropdown.txt')
    out = ['# X-Console Theme Editor: the colours metal_pages.py draws its drop-downs in. Written by the build (metal_dropdown.py).']
    for tab, _ in mod.PAGES:
        lp = os.path.join(lay, tab + '.layout')
        if os.path.exists(lp) and re.search(r'^popup ', open(lp).read(), re.M):
            for key, it in KEYS:
                out.append('DRAWN\t%s\t%s\t#%s' % (FILE_PAGE.get(tab, tab), it, mine[key]))
    txt = '\n'.join(out) + '\n'
    if not os.path.exists(path) or open(path, encoding='utf-8').read() != txt:
        open(path, 'w', encoding='utf-8').write(txt)


def _arrow_diff(mod, cx, cy, w, h, col):
    """(x0, y0, diff) for one field: the arrow in col minus the arrow as drawn, page pixels"""
    import numpy as np
    from PIL import Image
    m = 16
    x0, x1 = int(cx - w / 2 - m), int(cx + w / 2 + m)
    y0, y1 = int(cy - h / 2 - m), int(cy + h / 2 + m)
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(mod.W, x1), min(mod.H, y1)
    S = mod.S
    out = []
    for arrow in (None, col):
        mod.FIELD_ARROW = arrow
        mod.FIELD_GLOW = tuple(c * 0.55 for c in arrow) if arrow else None
        cv = mod.Cv()
        cv.a[:] = 40
        mod.field(cv, cx, cy, w, h)
        a = np.clip(cv.a[y0 * S:y1 * S, x0 * S:x1 * S], 0, 255).astype(np.uint8)
        out.append(np.asarray(Image.fromarray(a).resize((x1 - x0, y1 - y0), Image.LANCZOS), np.float32))
    mod.FIELD_ARROW = mod.FIELD_GLOW = None
    return x0, y0, out[1] - out[0]


def repaint(mod, art, lay, tab, t, arrow):
    """point the page's background line at <bg>__dd.png with every drop-down arrow in arrow (or back to <bg>.png)"""
    import numpy as np
    from PIL import Image
    pat = r'art file="art/(%sbg_%s(?:__ub)?)(?:__dd)?\.png"' % (re.escape(mod.PFX), tab.lower())
    m = re.search(pat, t)
    if not m:
        return t
    base, img = m.group(1), m.group(1) + '.png'
    if arrow:
        import metal_banner
        saved = {k: getattr(mod, k, None) for k in metal_banner.textures(mod)}
        blank = np.zeros((mod.H * mod.S, mod.W * mod.S), np.float32)
        for k, v in saved.items():
            if v is None:
                setattr(mod, k, blank)
        try:
            pic = np.asarray(Image.open(os.path.join(art, base + '.png')).convert('RGB'), np.float32)
            for p in re.finditer(r'^popup cx=(-?\d+) cy=(-?\d+) w=(\d+) h=(\d+)', t, re.M):
                cx, cy, w, h = (int(v) for v in p.groups())
                x0, y0, d = _arrow_diff(mod, cx, cy - mod.TOP, w, h, arrow)
                pic[y0:y0 + d.shape[0], x0:x0 + d.shape[1]] += d
        finally:
            for k, v in saved.items():
                setattr(mod, k, v)
        img = base + '__dd.png'
        Image.fromarray(np.clip(np.round(pic), 0, 255).astype(np.uint8)).save(os.path.join(art, img))
    return re.sub(pat, 'art file="art/%s"' % img, t, count=1)


def apply(mod, art, lay, colours):
    tag = os.path.basename(os.path.dirname(os.path.abspath(mod.__file__)))
    section = SECTION.get(tag)
    mine = own(mod)
    if mine is None:
        print('  drop-down colours: no popup line in metal_pages.py, as drawn', flush=True)
        return
    drawn_list(mod, lay, mine)
    vals = mod.read_colours(colours)
    built = builtins(section)
    if not built:
        print('  drop-down colours: no built-in list (tools/colours-info.txt), as drawn', flush=True)
    for f in glob.glob(os.path.join(art, mod.PFX + 'bg_*__dd.png')):
        os.remove(f)
    done = []
    for tab, _ in mod.PAGES:
        lp = os.path.join(lay, tab + '.layout')
        if not os.path.exists(lp):
            continue
        cols, changed = wanted(vals, section, built, tab, mine) if built else (mine, [])
        t = open(lp).read()

        def fix(m):
            ln = m.group(0)
            for key, _ in KEYS:
                ln = re.sub(r'\b%s=\w+' % key, '%s=%s' % (key, cols[key]), ln)
            return ln

        t2 = re.sub(r'^popup .*$', fix, t, flags=re.M)
        has = re.search(r'^popup ', t, re.M)
        ink = cols['field_ink'] if has and cols['field_ink'] != mine['field_ink'] else None
        t2 = repaint(mod, art, lay, tab, t2, tuple(int(ink[i:i + 2], 16) for i in (0, 2, 4)) if ink else None)
        if t2 != t:
            open(lp, 'w').write(t2)
        if changed and has:
            done.append('%s %s' % (tab, ', '.join(changed)))
    print('  drop-down colours: %s' % ('; '.join(done) if done else 'as drawn'), flush=True)
