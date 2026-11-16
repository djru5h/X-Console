#!/bin/bash
# Rerun all 6 metal pages for every X-Console strip into tools/custom-pages/<tag> + [Ru5h Skins]/<Name> Skins/metal.
# Usage (WSL as root): bash rerun-metal-all.sh [tag...]
XC="/mnt/g/claude/mpc/plugins/Gen 2/X-Console"
PY=/root/venv-skin/bin/python
export XC_COLOURS="$XC/X-Console colours.txt"
declare -A SKIN=([flannel]=Flannel [granite]=Granite [suede]=Suede [hearts]=Hearts [sandstone]=Sandstone
                 [hexx]=Hexx [molten]=Molten [spades]=Avalon [mocha]=Mocha [titanium]=Titanium)
TAGS="${*:-flannel granite suede hearts sandstone hexx molten spades mocha titanium}"
for t in $TAGS; do
  cd "$XC/tools/custom-pages/$t" || exit 1
  conf=$(ls plugin-layout-*.conf | head -1)
  echo "=== $t ($conf) ==="
  "$PY" metal_pages.py "$XC/[Ru5h Skins]/${SKIN[$t]} Skins/metal" art . "$conf" || { echo "FAILED $t"; exit 1; }
done
echo ALL DONE
