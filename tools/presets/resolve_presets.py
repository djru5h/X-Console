#!/usr/bin/env python3
"""X-Console presets for MPC's preset field (user 2026-11-13: "you draft them and include the gap-4 fix.. use x-console: hexx").

Reads tools/presets/<tag>.json, written in the knobs' own words:
  {"presets": [{"name": "Vocal", "values": {"cmp_ratio": "4:1", "eq_hmf_freq": "3 kHz", "eq_on": "On", ...}}]}
and writes the wrapper's presets.json (vst.json "presets"), where every continuous control is its 0..1 position.
- Each preset starts from the plugin's own starting state (the engine built with -DXC_ONLY_MODEL=<model>, read with
  xc_probe), so a control a preset doesn't name goes back to its default instead of keeping the last preset's value.
- Never in a preset: the section models / channel strip / section lists (the plugin's strip is fixed), the spectrum view
  and peak hold (screen preferences), and display-only params (past AUTOMATABLE_PARAMS).
- A value: an option's name; a number = a 0..1 position as is; a string = the knob text to aim for ("-6 dB", "1.5 kHz",
  "4:1", "30 ms", "Off"): the nearest of 2001 positions by the engine's own text (stepped knobs: their N steps only).
- The check report lists every named value as the engine shows it after the preset is set, and flags misses over 4%.
usage: resolve_presets.py --model N --params params.json --automatable 69 --src X/src --wrapper MV/wrapper \
                          --in tools/presets/hexx.json --out B/presets.json --report tools/presets/hexx-check.txt
"""
import argparse, json, math, os, re, subprocess, sys

SKIP = re.compile(r"(_model|_unit)$|^(strip_sel|sp_view|pk_hold|m_eqlook)$")
NUM = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*(kHz|Hz|ms|us|s|dB|%|x|:1)?")
SCALE = {"kHz": 1000.0, "s": 1000.0, "us": 0.001}   # Hz and ms are the base units


def number(text):
    m = NUM.search(text)
    if not m:
        return None
    return float(m.group(1)) * SCALE.get(m.group(2) or "", 1.0)


def main():
    a = argparse.ArgumentParser()
    for k in ("model", "params", "automatable", "src", "wrapper", "in", "out", "report"):
        a.add_argument("--" + k, required=True)
    o = a.parse_args()
    probe = "/tmp/xc_probe_%s" % o.model
    here = os.path.dirname(os.path.abspath(__file__))
    subprocess.run(["gcc", "-O1", "-DXC_ONLY_MODEL=%s" % o.model, "-I" + o.src, "-I" + o.wrapper, os.path.join(here, "xc_probe.c")]
                   + [os.path.join(o.src, f) for f in ("engine.c", "xconsole.c", "spectrum.c", "noise.c")]
                   + ["-lm", "-lpthread", "-o", probe], check=True)
    run = lambda *args: subprocess.run([probe] + list(args), check=True, capture_output=True, text=True).stdout

    pj = json.load(open(o.params))
    params = pj if isinstance(pj, list) else pj["params"]
    index = {p["key"]: i for i, p in enumerate(params)}
    auto = int(o.automatable)
    start = {}
    for kv in run("state").strip().split(";"):
        if "=" not in kv:
            continue
        k, v = kv.split("=", 1)
        if k in index and index[k] < auto and not SKIP.search(k):
            p = params[index[k]]
            start[k] = int(v) if p.get("options") else float(v)
    tables = {}

    def table(k):
        if k not in tables:
            n = params[index[k]].get("steps", 2001) - 1
            rows = [l.split(" ", 1) for l in run("table", k, str(n)).splitlines() if " " in l]
            tables[k] = [(float(v), t.strip()) for v, t in rows]
        return tables[k]

    def resolve(k, v, where):
        if k not in start:
            sys.exit("%s: %s is not a preset control of this plugin" % (where, k))
        p = params[index[k]]
        opts = [str(x) for x in p.get("options") or []]
        if opts:
            if isinstance(v, str) and v.lower() in [x.lower() for x in opts]:
                return [x.lower() for x in opts].index(v.lower())
            if isinstance(v, int) and 0 <= v < len(opts):
                return v
            sys.exit("%s: %s=%r is not one of %s" % (where, k, v, ", ".join(opts)))
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if not 0 <= v <= 1:
                sys.exit("%s: %s=%g is not a 0..1 position" % (where, k, v))
            return float(v)
        rows = table(k)
        for pos, t in rows:   # a word ("Off", "AUTO", "Limit")
            if t.lower() == str(v).lower():
                return pos
        want = number(str(v))
        if want is None:
            sys.exit("%s: %s=%r: no number in it and no knob text like it" % (where, k, v))
        best = min((abs((number(t) if number(t) is not None else math.inf) - want), pos) for pos, t in rows)
        return best[1]

    src = json.load(open(getattr(o, "in")))
    out, report = [], []
    for n, pr in enumerate(src["presets"]):
        where = "%s: preset %r" % (os.path.basename(getattr(o, "in")), pr.get("name", n))
        vals = dict(start)
        for k, v in pr.get("values", {}).items():
            vals[k] = resolve(k, v, where)
        ordered = {k: vals[k] for k in sorted(vals, key=lambda k: index[k])}   # the engine's order, like a project reload
        out.append({"name": pr["name"][:24], "values": ordered})
        shown = run("show", *["%s=%s" % (k, ("%d" % v) if isinstance(v, int) else ("%.6f" % v)) for k, v in ordered.items()])
        text = {l.split(" ", 1)[0].split("=")[0]: l.split(" ", 1)[1] for l in shown.splitlines() if " " in l}
        report.append("%d %s" % (n, pr["name"]))
        for k, v in pr.get("values", {}).items():
            p = params[index[k]]
            t = p["options"][ordered[k]] if p.get("options") else text.get(k, "?")
            flag = ""
            if isinstance(v, str) and not p.get("options") and number(v) is not None and number(t) is not None:
                w, g = number(v), number(t)
                if abs(g - w) > 0.04 * max(abs(w), 1e-9) and abs(g - w) > 0.05:
                    flag = "   <-- asked %s" % v
            report.append("   %-12s %-16s %s%s" % (k, p.get("name", ""), t, flag))
    json.dump({"presets": out}, open(o.out, "w"), indent=1)
    open(o.report, "w").write("\n".join(report) + "\n")
    misses = sum("<-- asked" in l for l in report)
    print("presets: %d (%s), %d controls each, %d off target (%s)" % (len(out), ", ".join(p["name"] for p in out),
          len(start), misses, o.report), file=sys.stderr)


if __name__ == "__main__":
    main()
