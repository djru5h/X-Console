"""Theme Editor banner text colours for the metal custom pages (user, 2026-11-11: "can editing the color of the text in
the banner be added back to the editor? I would like to be able to choose the color of the "X-", CONSOLE, and the text on
the right side of the banner").

Every plugin's pages are metal_pages.py pictures with the banner drawn into the page background, so the colours file's
BANNER X- / BANNER TITLE / BANNER NAME / BANNER OUTLINE rows never reached them. The build (--strips) now calls
apply(mod, art, lay): for each page whose value differs from the built-in one (tools/colours-info.txt, the build's own
rule) it draws the banner's text twice on a scratch canvas, once as the script draws it and once in the editor's colours,
and adds the difference to a copy of the page background (<PFX>bg_<tab>__ub.png); that page's .layout points at the copy.
Unchanged pages go back to <PFX>bg_<tab>.png, so an untouched colours file builds exactly what the scripts drew.

A colour becomes the script's kind of gradient: top a little lighter than the colour, bottom darker. OUTLINE is the stroke
round X- and the name (only where the script strokes them; CONSOLE keeps its dark edge).

Logo banners (a script with LOGO_ACCENT, xc_logo.py; user 2026-11-11 "i want to be able to change the accent color in the
logo"): BANNER LINE is the logo's accent (swoosh, red faces of the X, the line); the name follows it unless BANNER NAME
is set too. CONSOLE is the picture, so BANNER TITLE does nothing there. New logo (2026-11-15, user: Suede X- "will not
change"): BANNER X- colours the logo's red (swoosh, X faces) on its own; unset or the drawn red = it follows BANNER LINE. The difference is only added where the
page still shows the banner as drawn (panels drawn over the logo's lower edge keep their own pixels).
"""
import inspect, glob, os, re
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
INFO = os.path.join(HERE, '..', 'colours-info.txt')
FILE_PAGE = {'INFO': 'SETUP'}
SECTION = {'granite': 'GRANITE', 'mocha': 'MOCHA', 'flannel': 'FLANNEL', 'hexx': 'HEXX', 'spades': 'SPADES',
           'molten': 'MOLTEN', 'hearts': 'HEARTS', 'suede': 'SUEDE', 'sandstone': 'SANDSTONE', 'titanium': 'TITANIUM'}
ITEMS = ('BANNER X-', 'BANNER TITLE', 'BANNER NAME', 'BANNER OUTLINE')
LOGO_ITEMS = ITEMS + ('BANNER LINE',)
ROWS = 80          # page rows the banner text (and its shadow) can touch; the banner is 62 high


def _hex(s):
    s = (s or '').strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', s):
        return None
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def builtins(section):
    out = {}
    if os.path.exists(INFO):
        for l in open(INFO, encoding='utf-8'):
            p = l.rstrip('\n').split('\t')
            if len(p) > 6 and p[0] == 'PLACE' and p[1] == section and p[3] in LOGO_ITEMS:
                out[(p[2], p[3])] = p[6].lower()
    return out


def is_logo(mod):
    return hasattr(mod, 'LOGO_ACCENT')


def wanted(vals, section, built, tab, items=ITEMS, always={}):
    """{item: (r,g,b)} the editor changed on this page; always = {item: drawn rgb} rows taken whenever they differ from
    what the page draws, not from the old skin's built-in (the logo's BANNER LINE)"""
    pg = FILE_PAGE.get(tab, tab)
    out = {}
    for it in items:
        v = vals.get((section, pg, it), vals.get((section, 'ALL', it)))
        if it in always:   # the logo accent: whatever the file says (2026-11-12: #2f9fd0 = the old built-in was skipped)
            if v is None or _hex(v) == always[it]:
                continue
        elif v is None or (pg, it) not in built or v.strip().lower() == built[(pg, it)]:
            continue
        c = _hex(v)
        if c is None:
            print('  banner colours: %s / %s = %s is not #rrggbb, as drawn' % (pg, it, v), flush=True)
            continue
        out[it] = c
    return out


def grad(c):
    c = np.asarray(c, np.float32)
    return tuple(c + (255 - c) * 0.3), tuple(c * 0.6)


def textures(mod):
    """the script's texture globals (TEX1, SUEDE, WOOD, VEINS ...: every name a function declares global, but the
    page-size / meter / conf ones); a --strips run never loads them"""
    names = set()
    for m in re.finditer(r'^\s+global ([\w, ]+)$', inspect.getsource(mod), re.M):
        names.update(n.strip() for n in m.group(1).split(','))
    return sorted(names - {'CONF', 'METER_STOPS', 'UNLIT', 'W', 'H'})


def drawn_list(mod, lay):
    """<lay>/banner.txt for the Theme Editor: the colours each page's banner text is drawn in (the middle of each
    gradient, the stroke round X- / the name), so its swatches show the metal banner, not the old flat skin's colours.
    Rewritten when missing or older than metal_pages.py."""
    path = os.path.join(lay, 'banner.txt')
    if os.path.exists(path) and os.path.getmtime(path) >= os.path.getmtime(mod.__file__):
        return
    orig = mod.grad_text
    out = ['# X-Console Theme Editor: the colours metal_pages.py draws the banner text in. Written by the build (metal_banner.py).']
    for tab, fn in mod.PAGES:
        call = banner_call(mod, fn)
        if call is None:
            continue
        name = call[0][0] if call[0] else None
        got = {}

        def g(cv, x, y, t, px, c0, c1, *a, **k):
            it = 'BANNER X-' if t == 'X-' else 'BANNER TITLE' if t == 'CONSOLE' else 'BANNER NAME' if t == name else None
            if it and it not in got:
                got[it] = tuple((np.asarray(c0, np.float32) + np.asarray(c1, np.float32)) / 2)
                if it in ('BANNER X-', 'BANNER NAME') and 'stroke_col' in k and 'BANNER OUTLINE' not in got:
                    got['BANNER OUTLINE'] = tuple(k['stroke_col'])
            return None

        mod.grad_text = g
        try:
            cv = mod.Cv()
            mod.banner(cv, *call[0], **call[1])
        finally:
            mod.grad_text = orig
        if is_logo(mod):
            got.pop('BANNER NAME', None)   # the name follows BANNER LINE, so the editor shows the file's own value
        for it in LOGO_ITEMS:
            if it in got:
                out.append('DRAWN\t%s\t%s\t#%02x%02x%02x' % ((FILE_PAGE.get(tab, tab), it) + tuple(int(round(v)) for v in got[it][:3])))
    open(path, 'w', encoding='utf-8').write('\n'.join(out) + '\n')


def banner_call(mod, fn):
    """the (args, kwargs) a page function passes to banner(), read from its source"""
    m = re.search(r'\bbanner\(cv,\s*(.*?)\)\s*;', inspect.getsource(fn))
    if not m:
        return None
    ns = dict(vars(mod))
    ns['_cap'] = lambda *a, **k: (a, k)
    return eval('_cap(%s)' % m.group(1), ns)


def render(mod, call, want):
    """the banner area of a scratch page (S scale) with the banner as drawn, or in the editor's colours"""
    orig = mod.grad_text
    name = call[0][0] if call[0] else None

    def g(cv, x, y, t, px, c0, c1, *a, **k):
        it = 'BANNER X-' if t == 'X-' else 'BANNER TITLE' if t == 'CONSOLE' else 'BANNER NAME' if t == name else None
        if it and it in want:
            c0, c1 = grad(want[it])
        if it in ('BANNER X-', 'BANNER NAME') and 'BANNER OUTLINE' in want and 'stroke_col' in k:
            k['stroke_col'] = want['BANNER OUTLINE']
        return orig(cv, x, y, t, px, c0, c1, *a, **k)

    cv = mod.Cv()
    cv.a[:] = 40
    mod.grad_text = g
    acc = getattr(mod, 'LOGO_ACCENT', None)
    if is_logo(mod):
        import xc_logo
        mod.LOGO_ACCENT = want.get('BANNER LINE')
        xc_logo.X_ACCENT = want.get('BANNER X-')   # the logo's X / swoosh (2026-11-15); None = follows BANNER LINE
    try:
        mod.banner(cv, *call[0], **call[1])
    finally:
        mod.grad_text = orig
        if is_logo(mod):
            mod.LOGO_ACCENT = acc
            xc_logo.X_ACCENT = None
    return cv.a[:ROWS * mod.S]


def _down(mod, a):
    return np.asarray(Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).resize((mod.W, ROWS), Image.LANCZOS), np.float32)


def apply(mod, art, lay, colours):
    tag = os.path.basename(os.path.dirname(os.path.abspath(mod.__file__)))
    section = SECTION.get(tag)
    vals = mod.read_colours(colours)
    built = builtins(section)
    if not built:
        print('  banner colours: no built-in list (tools/colours-info.txt), banners as drawn', flush=True)
    for f in glob.glob(os.path.join(art, mod.PFX + 'bg_*__ub.png')):
        os.remove(f)
    saved = {k: getattr(mod, k, None) for k in textures(mod)}
    blank = np.zeros((mod.H * mod.S, mod.W * mod.S), np.float32)   # the banner's own texture cancels out of the difference
    for k, v in saved.items():
        if v is None:
            setattr(mod, k, blank)
    done = []
    try:
        drawn_list(mod, lay)
        for tab, fn in mod.PAGES:
            lp = os.path.join(lay, tab + '.layout')
            if not os.path.exists(lp):
                continue
            bg = mod.PFX + 'bg_%s.png' % tab.lower()
            img = bg
            if is_logo(mod):
                import xc_logo
                want = wanted(vals, section, built, tab, LOGO_ITEMS, {'BANNER LINE': tuple(xc_logo.DRAWN_ACCENT), 'BANNER X-': tuple(xc_logo.DRAWN_ACCENT)}) if built else {}
            else:
                want = wanted(vals, section, built, tab) if built else {}
            call = banner_call(mod, fn) if want else None
            if want and call is None:
                print('  banner colours: %s has no banner() call, as drawn' % tab, flush=True)
            elif want:
                base = _down(mod, render(mod, call, {}))
                d = _down(mod, render(mod, call, want)) - base
                pic = np.asarray(Image.open(os.path.join(art, bg)).convert('RGB'), np.float32)
                if is_logo(mod):   # only where the page still shows the logo as drawn (not under the panels)
                    d *= np.clip(1 - np.abs(pic[:ROWS] - base).max(axis=2, keepdims=True) / 48.0, 0, 1)
                pic[:ROWS] += d
                img = mod.PFX + 'bg_%s__ub.png' % tab.lower()
                Image.fromarray(np.clip(np.round(pic), 0, 255).astype(np.uint8)).save(os.path.join(art, img))
                done.append('%s %s' % (tab, ', '.join('%s #%02x%02x%02x' % ((it[7:],) + want[it]) for it in LOGO_ITEMS if it in want)))
            t = open(lp).read()
            t2 = re.sub(r'art file="art/%sbg_%s(__ub)?(__dd)?\.png"' % (re.escape(mod.PFX), tab.lower()), 'art file="art/%s"' % img, t, count=1)
            if t2 != t:
                open(lp, 'w').write(t2)
    finally:
        for k, v in saved.items():
            setattr(mod, k, v)
    print('  banner colours: %s' % ('; '.join(done) if done else 'as drawn'), flush=True)
