#!/usr/bin/env bash
# X-Console: rebuild with the knob colours in "X-Console colours.txt", and install on the XL. Run by Rebuild X-Console.bat
# (WSL, root).   colours-rebuild.sh build    copy the colours in, build both MPCs, test, package, name the previews
#                colours-rebuild.sh install  put the last build on the XL (restarts MPC)
#                colours-rebuild.sh layout   colours + Gen2 layout only (for the single-preset plugins: tools/plugins.sh)
# The full (all-presets) Gen2 build has its own uid XCAL since 2026-11-08 ("X-Console: All Presets"): installing it no
# longer replaces X-Console: FLANNEL (XCN1).
set -uo pipefail
X=/root/mpc-dev/mpc-xconsole
MV=/root/mpc-dev/mpc-vst-plugins
P="/mnt/g/claude/mpc/plugins/Gen 2/X-Console"
F="$P/X-Console colours.txt"
SK="Ru5h Music - VST - X-Console"
LAST="$P/gen2/last-colour-build.txt"
cd "$X" || exit 1
# one build or install at a time: two at once share the build folders and spoil each other (2026-11-06)
exec 9>/tmp/xc-colours.lock
flock -n 9 || { echo "Another X-Console build or install is already running (another editor window, or Rebuild X-Console.bat). Wait for it to finish, then try again."; exit 1; }
ts() { date +%H:%M:%S; }

if [ "${1:-}" = "install" ]; then
  [ -f "$LAST" ] || { echo "No build yet: run the rebuild first."; exit 1; }
  read -r V SHA < "$LAST"
  Z="X-Console-$V-mpc-aarch64.zip"
  [ -f "$P/gen2/$Z" ] || { echo "$Z is missing from the gen2 folder."; exit 1; }
  echo "Copying $Z to the XL..."
  scp -q -o ConnectTimeout=10 "$P/gen2/$Z" "$P/tools/xc-install.sh" mpcxl:/tmp/ || { echo "Couldn't reach the XL (is it on and on the network?)."; exit 1; }
  ssh -o ConnectTimeout=10 mpcxl "sh /tmp/xc-install.sh '/tmp/$Z' $SHA"
  exit $?
fi

BASE=$(cat vst/BASE_VERSION)
if [ -f "$F" ]; then cp "$F" vst/colours.txt; else rm -f vst/colours.txt; fi
# the Q-Link speeds (Theme Editor, 2026-11-08): tools/qlink-speed.txt -> vst/qlink-speed.txt (make_layout.py reads it)
if [ -f "$P/tools/qlink-speed.txt" ]; then cp "$P/tools/qlink-speed.txt" vst/qlink-speed.txt; else rm -f vst/qlink-speed.txt; fi   # make_layout.py ignores 
# the user's pictures (EQ PICTURE / CURVE PICTURE, 2026-11-08): the X-Console folder's "pictures" -> vst/art/user_pics
rm -rf vst/art/user_pics; mkdir -p vst/art/user_pics
[ -d "$P/pictures" ] && cp -r "$P/pictures/." vst/art/user_pics/
colour_errors() {   # the build's log $1 -> the colours file's mistakes, else its last lines
  if grep -q "X-Console colours file:" "$1"; then
    echo; echo "The colours file has mistakes, nothing was built:"
    awk '/X-Console colours file:/{on=1; next} on && /^  /{print; next} on{exit}' "$1" | head -40
  else
    echo "The build failed. Last lines of the log ($1 in WSL):"; tail -20 "$1"
  fi
}

# layout: only the Gen2 skin layout with the colours (vst/layout-gen2.conf, about a minute), for the single-preset plugins
# (tools/plugins.sh, the Theme Editor's builds since 2026-11-08); no full X-Console is compiled or packaged
if [ "${1:-}" = "layout" ]; then
  N=$(python3 - <<'EOF'
import json
p = "vst/vst.json"; c = json.load(open(p)); c["version"] += 1
json.dump(c, open(p, "w"), indent=2); print(c["version"])
EOF
)
  V="$BASE-c$N"
  echo "$(ts) == colours and layout ($V)"
  if ! docker run --rm -v /root/mpc-dev:/r -v "$MV":/mv:ro -w /r/mpc-xconsole mpc-vst-html-art python3 vst/art/make_layout.py gen2 > /tmp/xc-colours-layout.log 2>&1; then
    colour_errors /tmp/xc-colours-layout.log; exit 1
  fi
  grep -h "colours file" /tmp/xc-colours-layout.log | head -1
  [ -f "$F" ] && cp "$F" "$P/tools/colours-backup.txt"
  cp vst/colours.txt "$F"
  cp vst/colours-info.txt "$P/tools/colours-info.txt"
  cp vst/qlink-info.txt "$P/tools/qlink-info.txt" 2>/dev/null || true
  echo "$V" > "$P/gen2/last-layout.txt"
  exit 0
fi
N=$(python3 - <<'EOF'
import json
p = "vst/vst.json"; c = json.load(open(p)); c["version"] += 1
json.dump(c, open(p, "w"), indent=2); print(c["version"])
EOF
)
V="$BASE-c$N"
echo "$(ts) == building X-Console $V for both MPCs (about 5 minutes; nothing prints until it's done)"
if ! bash vst/build-all.sh > /tmp/xc-colours-build.log 2>&1; then
  colour_errors /tmp/xc-colours-build.log; exit 1
fi
grep -h "colours file" /tmp/xc-colours-build.log | head -1
# the build rewrites the file in its full form (every colour, your values kept): back to Windows, the old one kept as a backup
[ -f "$F" ] && cp "$F" "$P/tools/colours-backup.txt"
cp vst/colours.txt "$F"
cp vst/colours-info.txt "$P/tools/colours-info.txt"
cp vst/qlink-info.txt "$P/tools/qlink-info.txt" 2>/dev/null || true
echo "$(ts) == checking both builds (about a minute)"
for a in "vst/vst.json armv7" "vst/gen2/vst.json aarch64"; do
  bash "$MV/tools/test_port.sh" $a > /tmp/xc-colours-tp.log 2>&1 || { echo "test failed ($a):"; tail -15 /tmp/xc-colours-tp.log; exit 1; }
done
echo "ok"
echo "$(ts) == drawing the page pictures (about 2 minutes)"
rm -rf vst/gen2/build/preview; mkdir -p vst/gen2/build/preview
docker run --rm -v /root/mpc-dev:/r -w /r/mpc-vst-plugins mpc-vst-html-art python3 tools/studio.py preview "/r/mpc-xconsole/vst/gen2/build/skin/$SK/Plugin Skins" -o /r/mpc-xconsole/vst/gen2/build/preview/page_%d.png --meter-level 1 --meters '^m_(pk_)?(in|out)_' > /dev/null 2>&1
rm -rf "$P/pages-colours"; mkdir -p "$P/pages-colours"
python3 - "$P/pages-colours" <<'EOF'
import json, os, shutil, sys
src, dst = "vst/gen2/build/preview", sys.argv[1]
for i, pg in enumerate(json.load(open("vst/preview-names.json"))):
    if pg["param"] is None:
        files = {"page_%d.png" % i: pg["name"]}
    else:
        files = {"page_%d.png" % i: "%s %s" % (pg["presets"][0], pg["name"])}
        files.update({"page_%d_mode%d-%d.png" % (i, pg["param"], n): "%s %s" % (p, pg["name"]) for n, p in enumerate(pg["presets"]) if n})
    for f, name in files.items():
        if os.path.exists(os.path.join(src, f)):
            shutil.copy(os.path.join(src, f), os.path.join(dst, name.replace("/", "-") + ".png"))
print(len(os.listdir(dst)), "pictures")
EOF
echo "$(ts) == packaging (under a minute)"
rm -rf /tmp/xc-dist
ABOUT="Console-style channel strip: preamp, filters, transient shaper and gate, 4-band EQ with live curve and spectrum, compressor, drive, width and pan, and a gain-staging noise generator on the PREAMP page. Channel strip presets on a SETUP page, with single units per section. Knob colours from the user's colours file. Early test build."
python3 "$MV/tools/release.py" --so vst/gen2/build/aarch64/r5hxconsole.so --skin "vst/gen2/build/skin/$SK" --entry vst/gen2/build/pluginlist-entry.xml --version "$V" --about "$ABOUT" -o /tmp/xc-dist/g2 > /dev/null || { echo "packaging failed"; exit 1; }
python3 "$MV/tools/release.py" --so vst/build/r5hxconsole.so --skin "vst/build/skin/$SK" --entry vst/build/pluginlist-entry.xml --version "$V" --about "$ABOUT" -o /tmp/xc-dist/g1 > /dev/null || { echo "packaging failed"; exit 1; }
cp /tmp/xc-dist/g2/X-Console-$V-mpc-aarch64.zip "$P/gen2/" && cp /tmp/xc-dist/g1/X-Console-$V-mpc-armv7.zip "$P/gen1/" || exit 1
rm -rf /tmp/xc-dist
SHA=$(sha256sum "$P/gen2/X-Console-$V-mpc-aarch64.zip" | cut -d' ' -f1)
echo "$V $SHA" > "$LAST"
echo "$(date '+%Y-%m-%d %H:%M') colours build $V gen2 sha256 $SHA" >> "$P/tools/colour-builds.log"
echo "$(ts) Built X-Console $V (gen2 and gen1 folders)."
