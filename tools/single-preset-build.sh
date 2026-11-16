#!/usr/bin/env bash
# X-Console: a single-preset Gen2 (MPC XL) plugin (user, 2026-11-08: "split the presets up into individual plugins").
# Run after colours-rebuild.sh build (it filters that build's vst/layout-gen2.conf, with the user's colours):
#   single-preset-build.sh                                   FLANNEL as "X-Console" (uid XCN1: replaces the full X-Console)
#   single-preset-build.sh "GRANITE" "X-Console GRANITE" XC4E r5hxcgranite.so
#   single-preset-build.sh "FLANNEL" "X-Console_FLANNEL" XCN1 r5hxconsole.so "X-Console: FLANNEL"   (5th: plugin-list name)
#   single-preset-build.sh "HEARTS" "X-Console_Hearts" XCWS r5hxchearts.so "X-Console: Hearts" "HEARTS"   (6th: banner/SETUP name)
#       7th (optional): the name in the middle of the SETUP page, if not the banner name
#       env XC_INFO (optional): extra INFO-page text under the name, lines joined by a literal \n (up to 6 lines)
#       -> gen2/<name>-<last build>-mpc-aarch64.zip  (a plugin of its own: own name, uid, .so, skin folder)
# The engine keeps every preset (built with -DXC_ONLY_MODEL=<model>: it starts on that strip); the skin keeps only that
# preset's pages (both EQ views, on the VIEW switch), SETUP shows the preset's name instead of the drop-downs.
set -euo pipefail
PRESET="${1:-FLANNEL}"
NAME="${2:-X-Console}"
UID_="${3:-XCN1}"
SO="${4:-r5hxconsole.so}"
DISP="${5:-$NAME}"   # the name MPC's plugin list shows (may hold a ":"; NAME is the folder's: exFAT refuses ":")
SHOWN="${6:-$PRESET}"   # the name on the banners and SETUP (user, 2026-11-08: HEARTS shows as HEARTS); default the preset's
SETUPNAME="${7:-$SHOWN}"   # the name in the middle of the SETUP page (user, 2026-11-08: "the setup page is independent"); default the banner name
X=/root/mpc-dev/mpc-xconsole
MV=/root/mpc-dev/mpc-vst-plugins
P="/mnt/g/claude/mpc/plugins/Gen 2/X-Console"
TAG=$(echo "$PRESET" | tr 'A-Z' 'a-z' | sed 's/^ssl //; s/[^a-z0-9]//g')
B="vst/gen2-$TAG"
SK="Ru5h Music - VST - $NAME"
cd "$X"
exec 9>/tmp/xc-colours.lock
flock -n 9 || { echo "Another X-Console build or install is running; try again when it's done."; exit 1; }
read -r BV _ < "$P/gen2/last-colour-build.txt"
[ -n "${XC_VERSION:-}" ] && BV="$XC_VERSION"   # tools/plugins.sh: the version of its colours + layout step
V="$BV"; [ "$NAME" = "X-Console" ] && V="$BV-$TAG"
ts() { date +%H:%M:%S; }

echo "$(ts) == layout: $PRESET only ($NAME)"
MODEL=$(P="$P" PRESET="$PRESET" SHOWN="$SHOWN" SETUPNAME="$SETUPNAME" INFOTEXT="${XC_INFO:-}" B="$B" python3 - <<'EOF'
import json, os, re, sys
preset, B, shown, setupname = os.environ["PRESET"], os.environ["B"], os.environ["SHOWN"], os.environ["SETUPNAME"]
# the INFO-page text under the name (tools/plugins.sh, from tools/info-text.txt): lines joined by a literal backslash-n
_il = [l.strip() for l in os.environ.get("INFOTEXT", "").split("\\n")]
while _il and not _il[0]: _il.pop(0)
while _il and not _il[-1]: _il.pop()
INFO_MAX = 14   # lines (user 2026-11-13: "14 rows sounds better than 6"; was 6)
infolines = _il[:INFO_MAX]   # rich text (2026-11-11): blank lines inside are spacers
RICH_TAG = re.compile(r"\[\*\]|\[/?(b|i|u|c|s|o|h)(=[^\]]*)?\]")   # h = highlight (2026-11-14)
def info_width(l):
    """a line's drawn width in px, estimated (the page font: about 0.5 em a character, bold 0.55; [s=] sizes)"""
    w, size, bold, bullet = 0.0, [1.4], [False], False
    for part in re.split(r"(\[\*\]|\[/?[a-z](?:=[^\]]*)?\])", l):
        m = re.match(r"\[s=([0-9]+(?:\.[0-9]+)?)\]$", part)
        if m: size.append(float(m.group(1)))
        elif part == "[/s]" and len(size) > 1: size.pop()
        elif part == "[b]": bold.append(True)
        elif part == "[/b]" and len(bold) > 1: bold.pop()
        elif part == "[*]": bullet = True   # sized like the line's first words (drawn that way, 2026-11-13)
        elif not re.match(r"\[/?[a-z]", part) and part:
            if bullet: w += 0.85 * size[-1] * 10; bullet = False
            w += len(part) * size[-1] * 10 * (0.55 if bold[-1] else 0.5)
    if bullet: w += 0.85 * 14
    return w
INFO_BOTTOM, INFO_SQUEEZE = 684, 0.75   # lowest line centre on the INFO panel (screen y); gaps may shrink to 75% to fit
def info_text(icy, step, bottom=INFO_BOTTOM):
    """the INFO text's layout lines (Theme Editor rich text, 2026-11-11: [b] [i] [u] [c=rrggbb] [s=size], drawn by
    html_art.rich_svg): from cy=icy; a line's height follows its biggest [s=] size (1.4 = step); a line with its own
    colours draws them at full strength, its plain words at the usual 0.8.
    Alignment ("[left]" / "[right]" at a line's start, 2026-11-11): the text sits in a box as wide as its widest line
    (estimated), centred under the name; left lines start at its left edge, right lines end at its right edge, the rest
    are centred. Bullets ("[*]" after that): a run of centred bullet lines shares one left edge, the run centred by its
    widest line, so the bullets stand in a column"""
    parsed = []
    for l in infolines:
        m = re.match(r"\[(left|right|center)\]", l)
        parsed.append((m.group(1) if m else "center", l[m.end():] if m else l))
    # pictures ("[img=file:WxH]" alone on a line, 2026-11-11): a file in the X-Console folder's pictures, drawn W x H px
    pics = {}
    for n, (_, l) in enumerate(parsed):
        pm = re.match(r"\[img=([^:\]]+):(\d+)x(\d+)\]$", l.strip())
        if pm:
            pics[n] = (pm.group(1).strip(), max(4, min(1000, int(pm.group(2)))), max(4, min(400, int(pm.group(3)))))
    widths = [pics[n][1] if n in pics else info_width(l) for n, (_, l) in enumerate(parsed) if n in pics or RICH_TAG.sub("", l).strip()]
    half = (max(widths) if widths else 0) / 2
    x_left, x_right = max(160, round(640 - half)), min(1120, round(640 + half))
    # Fit (2026-11-13, up to 14 lines): each line takes its own height (text: step x size / 1.4; picture: its height + 10);
    # the gap between two lines is half of each. If the last line would sit below `bottom`, the text gaps shrink evenly
    # (not under INFO_SQUEEZE; pictures keep their size), so short texts look exactly as before. Lines still past it are left off.
    ext = []
    for n, (_, l) in enumerate(parsed):
        sizes = [float(v) for v in re.findall(r"\[s=([0-9]+(?:\.[0-9]+)?)\]", l)]
        ext.append((pics[n][2] + 10, False) if n in pics else (step * max([1.4] + sizes) / 1.4, True))
    gaps = [(ext[k], ext[k + 1]) for k in range(len(ext) - 1)]
    fixed = sum(a[0] * (not a[1]) + b[0] * (not b[1]) for a, b in gaps) / 2
    flex = sum(a[0] * a[1] + b[0] * b[1] for a, b in gaps) / 2
    fit = 1.0 if fixed + flex <= bottom - icy or flex == 0 else max(INFO_SQUEEZE, (bottom - icy - fixed) / flex)
    if fit < 1:
        print("INFO text: line gaps squeezed to %d%% to fit the page" % round(fit * 100), file=sys.stderr)
    res, y, prev = [], icy, None
    left = {}   # line index -> the left edge of its centred bullet run
    i = 0
    while i < len(parsed):
        if parsed[i][0] == "center" and parsed[i][1].startswith("[*]"):
            j = i
            while j < len(parsed) and parsed[j][0] == "center" and parsed[j][1].startswith("[*]"):
                j += 1
            x0 = round(640 - max(info_width(parsed[k][1]) for k in range(i, j)) / 2)
            for k in range(i, j):
                left[k] = max(160, x0)
            i = j
        else:
            i += 1
    for n, (al, l) in enumerate(parsed):
        e = ext[n][0] * (fit if ext[n][1] else 1)
        if prev is not None:
            y += (prev + e) / 2
        prev = e
        if round(y) > bottom + 2:
            print("INFO text: line %d and after don't fit on the page; left off" % (n + 1), file=sys.stderr)
            break
        if n in pics:
            name, pw, ph = pics[n]
            src = os.path.join(os.environ["P"], "pictures", name)
            if not os.path.isfile(src):
                print("INFO text: picture %s is not in the pictures folder; left out" % name, file=sys.stderr)
                continue
            import hashlib, shutil as _sh
            art = "ipic_%s%s" % (hashlib.md5(open(src, "rb").read()).hexdigest()[:12], os.path.splitext(name)[1].lower())
            _sh.copy(src, os.path.join("vst", "art", art))
            px = x_left if al == "left" else x_right - pw if al == "right" else 640 - pw // 2
            res.append('art file="art/%s" x=%d y=%d w=%d h=%d' % (art, px, round(y) - ph // 2, pw, ph))
            continue
        if not RICH_TAG.sub("", l).strip():
            continue
        lab, op = l.replace('"', ''), "opacity=0.8"
        if lab.startswith("[*]"):   # the bullet, then a space (as bright as the line's plain words)
            # the bullet takes the formatting of the line's first words: colour, size, bold, italic (user 2026-11-13:
            # "bullets should follow the properties of the line"; underline left off). No colour there = the plain
            # words' brightness (the empty tag pair makes the renderer read the tags)
            rest, props = lab[3:].lstrip(), {}
            for t in re.finditer(r"\[(/?)([bicsuoh])(?:=([^\]]*))?\]|[^\[]+|\[", rest):   # highlight, like underline, stays off the bullet
                if t.group(2) is None:
                    if t.group(0).strip(): break   # the first words: the tags open here are theirs
                    continue
                if t.group(1): props.pop(t.group(2), None)
                elif t.group(2) in "bics": props[t.group(2)] = t.group(3)
            opn = "".join("[%s%s]" % (k, "=" + props[k] if props[k] else "") for k in "scbi" if k in props)
            cls = "".join("[/%s]" % k for k in "ibcs" if k in props)
            lab = opn + "[*]" + cls + " " + rest + ("" if "c" in props or "[c=" in rest else "[o=1][/o]")
        if "[c=" in lab:
            lab = "[o=0.8]" + re.sub(r"\[c=([0-9a-fA-F]{6})\]", r"[c=\1][o=1]", lab).replace("[/c]", "[/o][/c]") + "[/o]"
            op = "opacity=1"
        if al == "left":
            x, align = x_left, "left"
        elif al == "right":
            x, align = x_right, "right"
        elif n in left:
            x, align = left[n], "left"
        else:
            x, align = 640, "center"
        res.append('text cx=%d cy=%d size=1.4 align=%s label="%s" %s' % (x, round(y), align, lab, op))
    return res
_pj = json.load(open("vst/params.json")); L = {p["key"]: p for p in (_pj if isinstance(_pj, list) else _pj["params"])}
place = {k: L[k]["options"].index(preset) for k in ("in_model", "sh_model", "eq_model", "cmp_model", "strip_sel")}
short = re.sub(r"^SSL ", "", preset)
look = L["m_eqlook"]["options"].index(short + " LINE")   # model number x 2 (+1 = BARS)
model = look // 2
src, dst = "vst/layout-gen2.conf", "vst/layout-gen2-%s.conf" % B.split("gen2-")[1]   # beside the others: art/ paths are relative to it
os.makedirs(B, exist_ok=True)
out, tab, skip, dropnext = [], None, False, False
for ln in open(src).read().splitlines():
    if ln.startswith("[tab "):
        tab, skip = ln[5:-1], False
    # "#dropnext": the next line is the all-presets build's shared copy of a line each preset has its own copy of
    # (sections, text colours, labels: user_theme.sections_and_labels, 2026-11-10)
    if ln == "#dropnext":
        dropnext = True
        continue
    if dropnext:
        dropnext = False
        continue
    # this preset's own lines: its page picture (colour, photo, see-through panel fill: user, 2026-11-10) and its copies of
    # the lines above; the others' are dropped. Since 2026-11-10 they go through the tests below like any other line.
    pb = re.match(r"#pagebg\[([^\]]+)\] (.*)$", ln)
    if pb:
        if pb.group(1).upper() != preset.upper():
            continue
        ln = pb.group(2)
    conds = re.findall(r"when=([a-z_]+):(\d+)", ln)
    if any((k in place and int(v) != place[k]) or (k == "m_eqlook" and int(v) not in (look, look + 1)) for k, v in conds):
        continue
    # only this preset is left: its pieces need no preset test (they show whatever the preset parameters say)
    ln = re.sub(r" when=(in_model|sh_model|eq_model|cmp_model|strip_sel):\d+", "", ln)
    # the spectrum's LINE/BARS pictures follow the VIEW switch itself, not the engine-kept m_eqlook (on the XL the fill
    # never showed with m_eqlook, 2026-11-08), sp_view is a plain parameter MPC always knows
    ln = re.sub(r" when=m_eqlook:(\d+)\b", lambda m: " when=sp_view:%d" % (int(m.group(1)) - look), ln)
    if tab == "SETUP":
        if ln.startswith('qlinks "SETUP"'):
            ln = 'qlinks "SETUP" = in_gain,out_vol'
        elif 'label="CHANNEL STRIP"' in ln:   # the drop-downs and their names -> the preset's name
            skip = True
            out.append('text cx=640 cy=330 size=3.2 align=center label="%s" weight=700 spacing=2 color=2f9fd0' % setupname.upper())
            out.append('text cx=640 cy=400 size=1.4 align=center label="CHANNEL STRIP" opacity=0.75')
            out.extend(info_text(470, 40))   # the user's INFO text, centred under the name
            continue
        if skip and ln.startswith(("text ", "popup ")):
            continue
    if shown != preset and ln.startswith("text ") and 'label="%s"' % preset.upper() in ln:   # banner names
        ln = ln.replace('label="%s"' % preset.upper(), 'label="%s"' % shown.upper())
    out.append(ln)
# a page's Q-Links only on controls this preset shows there (GRANITE: no EQ STYLE switch, so no Q-Link turning it unseen)
tabs, cur = {}, None
for ln in out:
    if ln.startswith("[tab "):
        cur = ln[5:-1]
    elif cur:
        tabs.setdefault(cur, set()).update(re.findall(r"\bkey=([a-z0-9_]+)", ln))
cur = None
for i, ln in enumerate(out):
    if ln.startswith("[tab "):
        cur = ln[5:-1]
    m = re.match(r'(qlinks "([^"]+)" = )(.*)$', ln)
    if m and cur:
        keep = [k.strip() for k in m.group(3).split(",") if k.strip() in tabs.get(cur, ())]
        out[i] = m.group(1) + ",".join(keep)
# the SETUP page is called INFO on the MPC (user, 2026-11-08: "On ALL X-Console plugins, rename the SETUP page to INFO"):
# its tab, its Q-Link page title and the word on its banner. Display only: the colours file and the layout code keep "SETUP"
for i, ln in enumerate(out):
    if ln == "[tab SETUP]":
        out[i] = "[tab INFO]"
    elif ln.startswith('qlinks "SETUP" ='):
        out[i] = 'qlinks "INFO" =' + ln[len('qlinks "SETUP" ='):]
    elif ln.startswith("text cx=1256 ") and ' label="SETUP" ' in ln:
        out[i] = ln.replace(' label="SETUP" ', ' label="INFO" ')
# Hexx: sections up against the banner (user, 2026-11-10: "close the gap between the bottom of the banner and the top of all
# sections"). Every section whose top is the page top (152, banner bottom 148) gets its top edge at 148 (4 px taller); its
# title and title rule move up with the edge, the controls stay put. A user frame picture gets a taller copy (ufr_*_t4.svg).
# Per plugin: XC_TIGHT=1 from tools/plugins.sh (tools/tight-top.txt, the Theme Editor's "SECTIONS UP TO THE BANNER")
if os.environ.get("XC_TIGHT") == "1":
    TOP0, NEWTOP = 152, 148
    d = TOP0 - NEWTOP
    fx = set()
    for i, ln in enumerate(out):
        if ln.startswith("[tab "):
            fx = set()
            continue
        m = re.match(r'art file="art/(ufr_[0-9a-f]+)\.svg" x=(-?\d+) y=%d w=(\d+) h=(\d+)(.*)$' % TOP0, ln)
        if m:
            name, x, w, h = m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))
            new = "%s_t%d" % (name, d)
            svg = open("vst/art/%s.svg" % name).read()
            svg = svg.replace('height="%d" viewBox="0 0 %d %d"' % (h, w, h), 'height="%d" viewBox="0 0 %d %d"' % (h + d, w, h + d), 1)
            svg = svg.replace('width="%d" height="%d"' % (w - 1, h - 1), 'width="%d" height="%d"' % (w - 1, h + d - 1), 1)
            open("vst/art/%s.svg" % new, "w").write(svg)
            out[i] = 'art file="art/%s.svg" x=%d y=%d w=%d h=%d%s' % (new, x, NEWTOP, w, h + d, m.group(5))
            fx.add(x)
            continue
        m = re.match(r'frame x=(-?\d+) y=%d w=(\d+) h=(\d+)' % TOP0, ln)
        if m:   # a built-in frame (the engine draws its title from the top edge)
            out[i] = ln.replace(m.group(0), "frame x=%s y=%d w=%s h=%d" % (m.group(1), NEWTOP, m.group(2), int(m.group(3)) + d), 1)
            continue
        t = re.match(r'text cx=(-?\d+) cy=%d ' % (TOP0 + 20), ln)
        if t and int(t.group(1)) - 18 in fx:   # a user frame's title (x+18, y+20)
            out[i] = ln.replace(" cy=%d " % (TOP0 + 20), " cy=%d " % (NEWTOP + 20), 1)
# Custom pages (user, 2026-11-10: a generated picture as a page's skin, Avalon PREAMP first): tools/custom-pages/<tag>/<TAB>.layout
# replaces everything on that page but its qlinks lines; its pictures (tools/custom-pages/<tag>/art/*) are copied into vst/art.
# Made by tools/custom-pages/<tag>/make_page.py from the picture.
import glob, shutil, sys, subprocess
cdir = os.path.join(os.environ["P"], "tools", "custom-pages", B.split("gen2-")[1])
# Pages made by metal_pages.py (Avalon, 2026-11-10): their IN/OUT LED strips are redrawn here in the Theme Editor's
# METERS / UNLIT METER SEGMENTS colours (from the colours file this build uses) and the .layout files pointed at them.
if os.path.exists(os.path.join(cdir, "metal_pages.py")):
    cfile = "vst/colours.txt" if os.path.exists("vst/colours.txt") else os.path.join(os.environ["P"], "X-Console colours.txt")
    r = subprocess.run(["/root/venv-skin/bin/python", "metal_pages.py", "--strips", "art", os.path.abspath(cfile), "."],
                       cwd=cdir, capture_output=True, text=True)
    sys.stderr.write(r.stdout)
    if r.returncode:
        sys.stderr.write(r.stderr)
        raise SystemExit("custom pages: meter strips failed")
custom = {os.path.basename(f)[:-len(".layout")]: [l for l in open(f).read().splitlines() if l.strip()]
          for f in glob.glob(os.path.join(cdir, "*.layout"))}
if custom:
    for f in glob.glob(os.path.join(cdir, "art", "*")):
        shutil.copy(f, "vst/art/")
    # Live lines (user, 2026-11-10: "add back the ability to edit the EQ spectrum and transfer curve colors"): a custom page's
    # spectrum (spc_), peaks (spk_), EQ curve (eqc_), transfer curves (gtc_/ctc_) and screen pictures (EQ / CURVE PICTURE:
    # upic_, the maker's eq_logo_/tc_logo_) come from THIS build's own lines for that page, so the Theme Editor's SPECTRUM
    # LINE / FILL / PEAKS, EQ CURVE (FILL), TRANSFER CURVE and pictures reach it; the copies in the .layout only mark where
    # they go. The gain / GR bar keeps the custom picture's strip unless TRANSFER CURVE is changed (the build then names
    # its strip shape_bar_u... / gr_bar20_u...).
    LIVE_KEY = re.compile(r"^meter .* key=(spc_|spk_|eqc_|gtc_|ctc_)")
    LIVE_ART = re.compile(r'^art file="art/(upic_|eq_logo|tc_logo)')
    GAIN = re.compile(r"^meter .* key=(m_shape|m_gr) .*strip=(\S+)")
    def is_live(l):
        return bool(LIVE_KEY.match(l) or LIVE_ART.match(l))
    def merged(tab, own):
        live = [l for l in own if is_live(l)]
        gains = {m.group(1): m.group(2) for m in (GAIN.match(l) for l in own) if m}
        res, put = [], False
        # INFO TEXT on a custom INFO page (user, 2026-11-11): the Theme Editor's lines, centred under the page's name. The page
        # script says where with "#infotext cy=<first line> step=<gap>" (screen y); without it they start at cy=470, step 40.
        icy, istep = 470, 40
        for l in custom[tab]:
            m = re.match(r"#infotext cy=(\d+) step=(\d+)", l)
            if m:
                icy, istep = int(m.group(1)), int(m.group(2))
        for l in custom[tab]:
            if l.startswith("#"):
                continue
            if is_live(l):
                if not put:
                    res.extend(live); put = True
                continue
            g = GAIN.match(l)
            if g and re.search(r"(shape_bar|gr_bar20)_u", gains.get(g.group(1), "")):
                l = l.replace("strip=" + g.group(2), "strip=" + gains[g.group(1)])
            res.append(l)
        if not put and live:   # no marker line: right after the page picture
            res[1:1] = live
        if tab == "INFO":
            res.extend(info_text(icy, istep))
        return res, len(live)
    new, cur, own, nlive = [], None, [], {}
    def flush():
        if cur in custom:
            lines, nlive[cur] = merged(cur, own)
            new.extend(lines)   # the custom page's lines go after its qlinks lines
    for ln in out:
        if ln.startswith("[tab "):
            flush()
            cur, own = ln[5:-1], []
            new.append(ln)
            continue
        if cur in custom and not ln.startswith("qlinks "):
            own.append(ln)
            continue
        new.append(ln)
    flush()
    out = new
    print("custom pages: %s (live spectrum/curve lines: %s)" % (", ".join(sorted(custom)),
          ", ".join("%s %d" % (t, n) for t, n in sorted(nlive.items()) if n) or "none"), file=sys.stderr)
open(dst, "w").write("\n".join(out) + "\n")
c = json.load(open("vst/gen2/vst.json"))
c["version"] = json.load(open("vst/vst.json"))["version"]   # the latest colours/layout step's number (gen2/vst.json: the last full build's)
c["layout"] = "../layout-gen2-%s.conf" % B.split("gen2-")[1]
c["params"] = "../params.json"
# Stepped knobs move in steps (user 2026-11-12: "is there a way to make knobs move in increments if the available values are
# in increments?" -> "yes, try it on hexx first"): this plugin's T_STEPS knobs (param_table.h MS(model, key, def, N, ...))
# get the wrapper's "steps": N (settled on k/(N-1), which lands in the engine's zone k) + qlink_ticks 6 like the option lists.
STEPPED_TAGS = {"flannel", "granite", "suede", "hearts", "sandstone", "hexx", "molten", "spades", "mocha", "titanium"}   # all (user 2026-11-12, Hexx checked: "it works now, do the rest of the plugins")
_tag = B.split("gen2-")[1]
if _tag in STEPPED_TAGS:
    _ms = re.findall(r"^MS\((\d+),\s*(\w+),\s*[-\d.ef]+,\s*(\d+),", open("src/param_table.h").read(), re.M)
    _steps = {k: int(n) for m, k, n in _ms if int(m) == model}
    _pj2 = json.loads(json.dumps(_pj))
    for _p in (_pj2 if isinstance(_pj2, list) else _pj2["params"]):
        if _p["key"] in _steps and not _p.get("options"):
            _p["steps"] = _steps[_p["key"]]
            _p.setdefault("qlink_ticks", 6)
    json.dump(_pj2, open(B + "/params-steps.json", "w"), indent=1)
    c["params"] = "params-steps.json"
    print("stepped knobs: " + ", ".join("%s %d" % kv for kv in sorted(_steps.items())), file=sys.stderr)
# Presets in MPC's preset field (user 2026-11-13: "you draft them and include the gap-4 fix.. use x-console: hexx"):
# tools/presets/<tag>.json (knob text) -> B/presets.json (0..1 positions, from this plugin's starting state) via
# tools/presets/resolve_presets.py; vst.json "presets" makes the wrapper report them as VST programs. The wrapper saves the
# picked one after the engine's state in the chunk (vst2_wrap.c effGetChunk), so a reload shows it again.
PRESET_TAGS = {"flannel", "granite", "suede", "hearts", "sandstone", "hexx", "molten", "spades", "mocha", "titanium"}   # all (user 2026-11-14: "whatever you did to hexx ... do for the other plugins")
c.pop("presets", None)
if _tag in PRESET_TAGS:
    import subprocess
    _pin = os.path.join(os.environ["P"], "tools/presets/%s.json" % _tag)
    subprocess.run(["python3", os.path.join(os.environ["P"], "tools/presets/resolve_presets.py"), "--model", str(model),
                    "--params", os.path.normpath(os.path.join(B, c["params"])),
                    "--automatable", str(c.get("defines", {}).get("AUTOMATABLE_PARAMS", 69)),
                    "--src", "src", "--wrapper", "/root/mpc-dev/mpc-vst-plugins/wrapper", "--in", _pin,
                    "--out", B + "/presets.json", "--report", os.path.join(os.environ["P"], "tools/presets/%s-check.txt" % _tag)],
                   check=True, stdout=sys.stderr)
    c["presets"] = "presets.json"
c["build"]["cflags"] = [f for f in c["build"]["cflags"] if not f.startswith("-DXC_ONLY_MODEL")] + ["-DXC_ONLY_MODEL=%d" % model]
json.dump(c, open(B + "/vst.json", "w"), indent=2)
print(model)
EOF
)
python3 - "$B/vst.json" "$NAME" "$UID_" "$SO" "$DISP" <<'EOF'
import json, sys
p, name, uid, so, disp = sys.argv[1:]
c = json.load(open(p)); c.update(name=name, uid=uid, so=so); c.pop("display_name", None)
if disp != name: c["display_name"] = disp
json.dump(c, open(p, "w"), indent=2)
EOF
echo "model $MODEL, $(wc -l < "vst/layout-gen2-$TAG.conf") layout lines (from $(wc -l < vst/layout-gen2.conf))"
echo "$(ts) == building (about 3 minutes)"
"$MV/tools/build_port.sh" "$B/vst.json" aarch64 > /tmp/xc-single-build.log 2>&1 || { echo "build failed:"; tail -20 /tmp/xc-single-build.log; exit 1; }
echo "$(ts) == checking"
bash "$MV/tools/test_port.sh" "$B/vst.json" aarch64 > /tmp/xc-single-tp.log 2>&1 || { echo "test failed:"; tail -15 /tmp/xc-single-tp.log; exit 1; }
echo ok
echo "$(ts) == page pictures"
PG="$P/pages-$TAG-only"
rm -rf "$PG" "$B/build/preview"; mkdir -p "$PG" "$B/build/preview"
docker run --rm -v /root/mpc-dev:/r -w /r/mpc-vst-plugins mpc-vst-html-art python3 tools/studio.py preview "/r/mpc-xconsole/$B/build/skin/$SK/Plugin Skins" -o "/r/mpc-xconsole/$B/build/preview/page_%d.png" --meter-level 1 --meters '^m_(pk_)?(in|out)_' > /dev/null 2>&1 || true
cp "$B"/build/preview/page_[0-9].png "$PG/" 2>/dev/null || true
echo "$(ts) == packaging"
rm -rf /tmp/xc-dist9
ABOUT="Console-style channel strip, $PRESET: preamp, filters, transient shaper and gate, EQ with live curve and spectrum, compressor, drive, width and pan, and a gain-staging noise generator. One preset of X-Console."
python3 "$MV/tools/release.py" --so "$B/build/aarch64/$SO" --skin "$B/build/skin/$SK" --entry "$B/build/pluginlist-entry.xml" --version "$V" --about "$ABOUT" -o /tmp/xc-dist9 > /dev/null
Z=$(cd /tmp/xc-dist9 && ls *-mpc-aarch64.zip | head -n 1)
cp "/tmp/xc-dist9/$Z" "$P/gen2/"
rm -rf /tmp/xc-dist9
SHA=$(sha256sum "$P/gen2/$Z" | cut -d' ' -f1)
echo "$(date '+%Y-%m-%d %H:%M') single-preset build $NAME $V gen2 sha256 $SHA" >> "$P/tools/colour-builds.log"
echo "$V $SHA $Z" > "$P/gen2/last-$TAG.txt"   # tools/plugins.sh install reads it
echo "$(ts) Built $NAME $V: gen2/$Z  sha256 $SHA"
