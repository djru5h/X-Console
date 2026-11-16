#!/usr/bin/env bash
# Build and run X-Console's desktop harness in Docker (gcc:12): sanitizers first, then an optimised build with demos and a bench.
#   harness/run.sh [out_dir]    demos go to out_dir, relative to the repo root (default harness/out)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-harness/out}"
U="$(id -u):$(id -g)"
mkdir -p "$ROOT/harness/build" "$ROOT/$OUT"
docker run --rm -u "$U" -v "$ROOT":/w -w /w gcc:12 bash -euc "
  set -o pipefail
  gcc -std=gnu11 -O1 -g -Wall -Wextra -Wno-unused-parameter -fsanitize=address,undefined -fno-sanitize-recover=undefined \
      -Isrc harness/harness.c src/xconsole.c src/noise.c -lm -o harness/build/harness_san
  echo '--- sanitizers'
  harness/build/harness_san | tail -n 1
  gcc -std=gnu11 -O2 -Wall -Wextra -Wno-unused-parameter -Isrc harness/harness.c src/xconsole.c src/noise.c -lm -o harness/build/harness
  echo '--- optimised'
  harness/build/harness '$OUT'
  gcc -std=gnu11 -O2 -Isrc harness/bench.c src/xconsole.c src/noise.c -lm -o harness/build/bench
  echo '--- bench (this PC)'
  harness/build/bench 5
"
