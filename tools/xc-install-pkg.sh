#!/bin/sh
# Install one X-Console package on the XL: xc-install-pkg.sh /tmp/<zip> <sha256>   (any single-preset plugin's zip)
Z="$1"; SHA="$2"
if dmesg | grep -i nvme | grep -qiE 'error|reset|timeout|disabl'; then echo "NVMe errors on the XL, stopping (nothing changed)."; exit 1; fi
if pidof weston >/dev/null 2>&1; then echo "cratesurf browse mode is on, stopping (nothing changed)."; exit 1; fi
[ "$(sha256sum "$Z" | cut -d' ' -f1)" = "$SHA" ] || { echo "The package arrived damaged, stopping (nothing changed)."; exit 1; }
W=/tmp/xc-pkg-install; rm -rf "$W"; mkdir -p "$W"
unzip -q -o "$Z" -d "$W" || { echo "unzip failed"; exit 1; }
I=$(find "$W" -name install.sh | head -n 1); [ -n "$I" ] || { echo "no installer in the package"; exit 1; }
cd "$(dirname "$I")" && sh install.sh -y -t /nvme/Synths || { echo "the installer failed"; exit 1; }
cd /; i=0
while ! pidof MPC >/dev/null 2>&1 && [ "$i" -lt 60 ]; do sleep 1; i=$((i + 1)); done
sleep 6
pidof MPC >/dev/null 2>&1 && echo "MPC is running again." || echo "MPC hasn't started yet: check the XL."
