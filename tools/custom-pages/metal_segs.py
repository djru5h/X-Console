"""Theme Editor LIT BUTTONS / LIT BUTTON TEXT for the metal custom pages (user, 2026-11-12: "make the editor handle lit
text like it used to": the rows did nothing once the presets got metal pages).

Each metal_pages.py writes its rows of option buttons (TAPE / TUBE / IRON, slopes, VIEW ...) as enum_h / enum_v lines with
its own pictures (img= <PFX>seg_<w>x<h>_off.png, img_on= ..._on.png) and a fixed seg_tx=ffffff, so the colours file's
LIT BUTTONS / LIT BUTTON TEXT rows never reached them. The build (--strips) now calls apply(mod, art, lay, colours):
on every enum line of every page,

    seg_tx=   LIT BUTTON TEXT   the text on the picked button (the MPC writes it; unpicked text stays as it is)
    img_on=   LIT BUTTONS       the picked button's picture, recoloured from the script's own: <..._on>_u<hex>.png

take the editor's value where it differs from the built-in one (tools/colours-info.txt, the build's own rule; a page
line wins over ALL), else the script's own, so an untouched colours file builds exactly what the scripts drew.

Recolouring keeps the drawn button's shading: each pixel's hue turns by (new - drawn), its saturation and brightness scale
by new / drawn (HSV), so the gradient, the ring, the glow under it and the sheen stay where they are, in the new colour.
The drawn colour is the mean of the middle of the script's lit pictures.

drawn_list(mod, lay) writes <lay>/segs.txt (DRAWN page item #hex) so the Theme Editor's untouched rows show the colour
the metal page draws.
"""
import glob, os, re

import metal_dropdown

KEYS = (('seg_tx', 'LIT BUTTON TEXT'), ('lit', 'LIT BUTTONS'))
FILE_PAGE = metal_dropdown.FILE_PAGE
ENUM = re.compile(r'^enum_[hv] .*$', re.M)


def builtins(section):
    out = {}
    names = {it for _, it in KEYS}
    if os.path.exists(metal_dropdown.INFO):
        for l in open(metal_dropdown.INFO, encoding='utf-8'):
            p = l.rstrip('\n').split('\t')
            if len(p) > 6 and p[0] == 'PLACE' and p[1] == section and p[3] in names:
                out[(p[2], p[3])] = p[6].strip().lower()
    return out


def _on_pics(mod, art):
    """the script's own lit pictures (not the recoloured copies)"""
    return sorted(f for f in glob.glob(os.path.join(art, mod.PFX + 'seg_*_on.png')))


def drawn_lit(mod, art):
    """the lit colour as drawn: the mean of the middle of every lit picture (hex), None without pictures"""
    import numpy as np
    from PIL import Image
    px = []
    for f in _on_pics(mod, art):
        a = np.asarray(Image.open(f).convert('RGBA'), np.float32)
        h, w = a.shape[:2]
        c = a[h // 4:3 * h // 4, w // 6:5 * w // 6]
        px.append(c[..., :3][c[..., 3] > 200])
    if not px:
        return None
    m = np.concatenate(px).mean(0)
    return '%02x%02x%02x' % tuple(int(round(v)) for v in m)


def own(mod, art):
    m = re.search(r"seg_tx=(\w{6})", open(mod.__file__, encoding='utf-8').read())
    lit = drawn_lit(mod, art)
    if not m or not lit:
        return None
    return {'seg_tx': m.group(1).lower(), 'lit': lit}


def drawn_list(mod, lay, mine):
    path = os.path.join(lay, 'segs.txt')
    out = ['# X-Console Theme Editor: the colours metal_pages.py draws its picked option buttons in. Written by the build (metal_segs.py).']
    for tab, _ in mod.PAGES:
        lp = os.path.join(lay, tab + '.layout')
        if os.path.exists(lp) and ENUM.search(open(lp, encoding='utf-8').read()):
            for key, it in KEYS:
                out.append('DRAWN\t%s\t%s\t#%s' % (FILE_PAGE.get(tab, tab), it, mine[key]))
    txt = '\n'.join(out) + '\n'
    if not os.path.exists(path) or open(path, encoding='utf-8').read() != txt:
        open(path, 'w', encoding='utf-8').write(txt)


def _rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def recolour(src, dst, drawn, new):
    """src lit picture -> dst in new (hex), the drawn hex's shading kept (HSV turn + scale)"""
    import numpy as np
    from PIL import Image
    im = Image.open(src).convert('RGBA')
    a = np.asarray(im, np.float32)
    rgb = a[..., :3] / 255.0
    hsv = np.asarray(Image.fromarray(np.uint8(np.round(rgb * 255))).convert('HSV'), np.float32) / 255.0
    dh, ds, dv = (np.asarray(Image.new('RGB', (1, 1), _rgb(drawn)).convert('HSV'), np.float32)[0, 0] / 255.0)
    nh, ns, nv = (np.asarray(Image.new('RGB', (1, 1), _rgb(new)).convert('HSV'), np.float32)[0, 0] / 255.0)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    h2 = (h + (nh - dh)) % 1.0
    s2 = np.clip(s * (ns / max(ds, 0.02)), 0, 1)
    v2 = np.clip(v * (nv / max(dv, 0.02)), 0, 1)
    out = Image.merge('HSV', [Image.fromarray(np.uint8(np.round(c * 255))) for c in (h2, s2, v2)]).convert('RGB')
    o = np.asarray(out, np.float32)
    o = np.concatenate([o, a[..., 3:4]], -1)
    Image.fromarray(np.uint8(np.clip(np.round(o), 0, 255))).save(dst)


def apply(mod, art, lay, colours):
    tag = os.path.basename(os.path.dirname(os.path.abspath(mod.__file__)))
    section = metal_dropdown.SECTION.get(tag)
    for f in glob.glob(os.path.join(art, mod.PFX + 'seg_*_on_u*.png')):
        os.remove(f)
    mine = own(mod, art)
    if mine is None:
        print('  lit button colours: no option buttons, as drawn', flush=True)
        return
    drawn_list(mod, lay, mine)
    vals = mod.read_colours(colours)
    built = builtins(section)
    if not built:
        print('  lit button colours: no built-in list (tools/colours-info.txt), as drawn', flush=True)
    done = []
    for tab, _ in mod.PAGES:
        lp = os.path.join(lay, tab + '.layout')
        if not os.path.exists(lp):
            continue
        cols, changed = metal_dropdown.wanted(vals, section, built, tab, mine, KEYS) if built else (mine, [])
        t = open(lp, encoding='utf-8').read()

        def fix(m):
            ln = re.sub(r'\bseg_tx=\w+', 'seg_tx=' + cols['seg_tx'], m.group(0))
            pm = re.search(r'\bimg_on=art/(\S+?)(?:_u[0-9a-f]{6})?\.png', ln)
            if pm:
                base = pm.group(1)
                if cols['lit'] != mine['lit']:
                    pic = '%s_u%s.png' % (base, cols['lit'])
                    if not os.path.exists(os.path.join(art, pic)):
                        recolour(os.path.join(art, base + '.png'), os.path.join(art, pic), mine['lit'], cols['lit'])
                else:
                    pic = base + '.png'
                ln = ln[:pm.start()] + 'img_on=art/' + pic + ln[pm.end():]
            return ln

        t2 = ENUM.sub(fix, t)
        if t2 != t:
            open(lp, 'w', encoding='utf-8').write(t2)
        if changed and ENUM.search(t):
            done.append('%s %s' % (tab, ', '.join(changed)))
    print('  lit button colours: %s' % ('; '.join(done) if done else 'as drawn'), flush=True)
