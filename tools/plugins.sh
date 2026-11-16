#!/usr/bin/env bash
# X-Console's single-preset plugins (one per channel strip, 2026-11-08), for X-Console Theme Editor.exe (WSL, root):
#   plugins.sh build TAG...     colours + layout once (colours-rebuild.sh layout), then each plugin (single-preset-build.sh)
#   plugins.sh install TAG...   put each plugin's last build on the XL (each install restarts MPC)
#   plugins.sh list             the table below
# TAGs: flannel granite suede hearts sandstone hexx molten spades mocha titanium, or "all".
# Lines the editor reads: "BUILT <tag> <version>", "INSTALLED <tag> <version>", "FAILED <tag>".
set -uo pipefail
P="/mnt/g/claude/mpc/plugins/Gen 2/X-Console"
T="$P/tools"
# tag | preset | folder name | uid | .so | MPC list name | banner name (empty = the preset's)
TABLE='flannel|FLANNEL|X-Console_Flannel|XCN1|r5hxconsole.so|X-Console: Flannel|
granite|GRANITE|X-Console_Granite|XC4E|r5hxcgranite.so|X-Console: Granite|
suede|SUEDE|X-Console_Suede|XCNV|r5hxcsuede.so|X-Console: Suede|
hearts|HEARTS|X-Console_Hearts|XCWS|r5hxchearts.so|X-Console: Hearts|HEARTS
sandstone|SANDSTONE|X-Console_Sandstone|XCSM|r5hxcsandstone.so|X-Console: Sandstone|
hexx|HEXX|X-Console_Hexx|XCAP|r5hxchexx.so|X-Console: Hexx|
molten|MOLTEN|X-Console_Molten|XCCH|r5hxcmolten.so|X-Console: Molten|
spades|SPADES|X-Console_Spades|XCAV|r5hxcspades.so|X-Console: Spades|
mocha|MOCHA|X-Console_Mocha|XC61|r5hxcmocha.so|X-Console: Mocha|
titanium|TITANIUM|X-Console_Titanium|XCTP|r5hxctitanium.so|X-Console: Titanium|'
ts() { date +%H:%M:%S; }
row() { echo "$TABLE" | grep "^$1|"; }
# the name on a plugin's banners and SETUP: tools/banner-names.txt (tag<TAB>NAME, written by the Theme Editor,
# 2026-11-08), else the table's last column, else (empty) the preset's own
NAMES="$T/banner-names.txt"
banner() { local n=""; [ -f "$NAMES" ] && n=$(tr -d '\r' < "$NAMES" | awk -F'\t' -v t="$1" '$1 == t { print $2 }' | tail -n 1); echo "${n:-$2}"; }
# the name in the middle of the SETUP page: banner-names.txt's 3rd column (tag<TAB>BANNER<TAB>SETUP), empty = the banner name
setupname() { [ -f "$NAMES" ] && tr -d '\r' < "$NAMES" | awk -F'\t' -v t="$1" '$1 == t { print $3 }' | tail -n 1; }
# the extra text under the name on the INFO page: tools/info-text.txt (tag<TAB>text, newlines written as \n), empty = none
INFOS="$T/info-text.txt"
infotext() { [ -f "$INFOS" ] && tr -d '\r' < "$INFOS" | awk -F'\t' -v t="$1" '$1 == t { print $2 }' | tail -n 1; }
# sections up to the banner (no gap under it): tools/tight-top.txt, one tag per line (written by the Theme Editor, 2026-11-10)
TIGHTS="$T/tight-top.txt"
tight() { [ -f "$TIGHTS" ] && tr -d '\r' < "$TIGHTS" | sed 's/#.*//' | awk -v t="$1" '$1 == t { f = 1 } END { exit !f }' && echo 1 || echo 0; }

CMD="${1:-}"; shift || true
[ "$CMD" = "list" ] && { echo "$TABLE"; exit 0; }
[ "${1:-}" = "all" ] && set -- $(echo "$TABLE" | cut -d'|' -f1)
[ $# -gt 0 ] || { echo "Which plugins? (tags: $(echo "$TABLE" | cut -d'|' -f1 | tr '\n' ' '))"; exit 1; }
for t in "$@"; do row "$t" > /dev/null || { echo "Unknown plugin: $t"; exit 1; }; done
exec 8>/tmp/xc-plugins.lock
flock -n 8 || { echo "Another X-Console build or install is already running (another editor window?). Wait for it to finish, then try again."; exit 1; }

if [ "$CMD" = "build" ]; then
  # WSL drops the arm64 emulation when it restarts; the plugin compile needs it
  if [ ! -e /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
    echo "The build needs the ARM emulator in WSL, and it's off (WSL restarted). In PowerShell run:"
    echo "  wsl -u root -e docker run --privileged --rm tonistiigi/binfmt --install arm,arm64"
    echo "then press Build again. Nothing was built."
    exit 1
  fi
  S0=$(date +%s)
  bash "$T/colours-rebuild.sh" layout || exit 1
  read -r V < "$P/gen2/last-layout.txt"
  n=0; fail=0
  for t in "$@"; do
    n=$((n + 1))
    IFS='|' read -r tag preset name uid so disp shown <<< "$(row "$t")"
    shown=$(banner "$tag" "$shown")
    sname=$(setupname "$tag")
    itext=$(infotext "$tag")
    echo "$(ts) ==== $disp ($n of $#)${shown:+, banner name $shown}${sname:+, SETUP name $sname}${itext:+, INFO text}"
    # an empty 6th / 7th argument = that name's default (the preset's / the banner name); XC_INFO = the INFO-page text (\n per line)
    if XC_VERSION="$V" XC_INFO="$itext" XC_TIGHT="$(tight "$tag")" bash "$T/single-preset-build.sh" "$preset" "$name" "$uid" "$so" "$disp" "$shown" "$sname" 2>&1 | sed 's/^/  /'; then   # pipefail: the build's own status
      echo "BUILT $tag $V"
    else
      echo "FAILED $tag"; fail=1
    fi
  done
  echo "$(ts) done in $(( ($(date +%s) - S0) / 60 )) min"
  exit $fail
fi

if [ "$CMD" = "install" ]; then
  fail=0
  for t in "$@"; do
    IFS='|' read -r tag preset name uid so disp shown <<< "$(row "$t")"
    L="$P/gen2/last-$tag.txt"
    [ -f "$L" ] || { echo "$disp: not built yet."; echo "FAILED $tag"; fail=1; continue; }
    read -r V SHA Z < "$L"
    [ -f "$P/gen2/$Z" ] || { echo "$disp: $Z is missing from the gen2 folder."; echo "FAILED $tag"; fail=1; continue; }
    echo "$(ts) == $disp $V: copying to the XL"
    if ! scp -q -o ConnectTimeout=10 "$P/gen2/$Z" "$T/xc-install-pkg.sh" mpcxl:/tmp/; then
      echo "Couldn't reach the XL (is it on and on the network?)."; echo "FAILED $tag"; exit 1
    fi
    echo "$(ts) installing (MPC restarts)"
    if ssh -o ConnectTimeout=10 mpcxl "sh /tmp/xc-install-pkg.sh '/tmp/$Z' $SHA; r=\$?; rm -f '/tmp/$Z'; exit \$r" 2>&1 | sed 's/^/  /'; then
      echo "INSTALLED $tag $V"
      echo "$(date '+%Y-%m-%d %H:%M') installed $disp $V sha256 $SHA" >> "$T/colour-builds.log"
    else
      echo "FAILED $tag"; fail=1
    fi
  done
  exit $fail
fi
echo "plugins.sh build|install|list TAG..."; exit 1
