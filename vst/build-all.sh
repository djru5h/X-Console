#!/usr/bin/env bash
# Build X-Console for both MPCs, each with its own skin:
#   Gen1 (armv7, MPC One): vst/vst.json + layout.conf            -> vst/build/
#   Gen2 (aarch64, MPC XL): vst/gen2/vst.json + layout-gen2.conf -> vst/gen2/build/  (the spectrum's steps joined: tall
#                           filmstrips that only Gen2 draws; the engine's aarch64 build encodes the joins to match)
# vst/gen2/vst.json is written from vst/vst.json each time, so they stay in step. Same params.json for both.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
MV="${MV:-$ROOT/../mpc-vst-plugins}"
P="$(cd "$ROOT/.." && pwd)"
docker run --rm -v "$P":/r -v "$MV":/mv:ro -w /r/$(basename "$ROOT") mpc-vst-html-art python3 vst/art/make_layout.py gen2
docker run --rm -v "$P":/r -v "$MV":/mv:ro -w /r/$(basename "$ROOT") mpc-vst-html-art python3 vst/art/make_layout.py
mkdir -p "$HERE/gen2"
python3 - "$HERE" <<'EOF'
import json, os, sys
vst = sys.argv[1]
cfg = json.load(open(os.path.join(vst, "vst.json")))
cfg.update(params="../params.json", layout="../layout-gen2.conf", targets=["aarch64"], uid="XCAL", display_name="X-Console: All Presets")   # own uid (2026-11-08): XCN1 is X-Console: FLANNEL
cfg["build"]["root"] = "../.."
json.dump(cfg, open(os.path.join(vst, "gen2", "vst.json"), "w"), indent=2)
EOF
"$MV/tools/build_port.sh" "$HERE/vst.json" armv7
"$MV/tools/build_port.sh" "$HERE/gen2/vst.json" aarch64
