#!/bin/sh
# Install an X-Console package on the XL: xc-install.sh /tmp/X-Console-<version>-mpc-aarch64.zip <sha256>
Z="$1"
SHA="$2"
W=/tmp/xc-colours-install
D="/nvme/Synths/Ru5h - VST - X-Console"
S=/data/Settings/MPC/MPC.settings

if dmesg | grep -i nvme | grep -qiE 'error|reset|timeout|disabl'; then
  echo "NVMe errors on the XL, stopping (nothing changed)."; exit 1
fi
if pidof weston >/dev/null 2>&1; then echo "cratesurf browse mode is on, stopping (nothing changed)."; exit 1; fi
[ -d /nvme/Synths ] || { echo "/nvme/Synths missing, stopping."; exit 1; }
[ "$(sha256sum "$Z" | cut -d' ' -f1)" = "$SHA" ] || { echo "The package arrived damaged, stopping (nothing changed)."; exit 1; }
echo "Installed before: $(grep '"version"' "$D/mpc-plugin.json" | tr -d ' ",' | cut -d: -f2)"

rm -rf "$W"; mkdir -p "$W"
unzip -q -o "$Z" -d "$W" || { echo "unzip failed"; exit 1; }
I=$(find "$W" -name install.sh | head -n 1)
[ -n "$I" ] || { echo "no installer in the package"; exit 1; }
cd "$(dirname "$I")" || exit 1
sh install.sh -y -t /nvme/Synths || { echo "the installer failed"; exit 1; }
cd /

i=0
while ! pidof MPC >/dev/null 2>&1 && [ "$i" -lt 60 ]; do sleep 1; i=$((i + 1)); done
sleep 8
echo "Installed now: $(grep '"version"' "$D/mpc-plugin.json" | tr -d ' ",' | cut -d: -f2)"
echo "X-Console (All Presets) entries in MPC's settings: $(grep -c 'uid="5843414c"' "$S") (should be 1)"
if pidof MPC >/dev/null 2>&1; then echo "MPC is running again."; else echo "MPC hasn't started yet: check the XL."; fi
rm -rf "$W" "$Z"
