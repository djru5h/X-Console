#!/usr/bin/env bash
# X-Console through the real wrapper, under sanitizers. Needs vst/build/params.h: run after a build.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MV="${MV:-$HOME/mpc-dev/mpc-vst-plugins}"
U="$(id -u):$(id -g)"
docker run --rm -u "$U" -v "$ROOT":/w -v "$MV":/mv:ro -w /w gcc:12 bash -euc '
  D=$(sed -n "s/.*\"\\([A-Z_]*\\)\": \\([0-9]*\\).*/-D\\1=\\2/p" vst/vst.json | tr "\n" " ")
  gcc -std=gnu11 -g -O1 -fsanitize=address,undefined -fno-sanitize-recover=undefined -DPLUG_EFFECT=1 $D -Isrc -Ivst/build -I/mv/wrapper \
      harness/wraptest.c /mv/wrapper/vst2_wrap.c src/engine.c src/xconsole.c src/spectrum.c src/noise.c -lm -lpthread -ldl -o harness/build/wraptest
  harness/build/wraptest
  echo "--- the Gen2 (XL) spectrum frames"
  gcc -std=gnu11 -g -O1 -fsanitize=address,undefined -fno-sanitize-recover=undefined -DPLUG_EFFECT=1 -DXC_GEN2=1 $D -Isrc -Ivst/build -I/mv/wrapper \
      harness/wraptest.c /mv/wrapper/vst2_wrap.c src/engine.c src/xconsole.c src/spectrum.c src/noise.c -lm -lpthread -ldl -o harness/build/wraptest2
  harness/build/wraptest2
'
