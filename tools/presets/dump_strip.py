import json, re, subprocess, os, sys
X = "/root/mpc-dev/mpc-xconsole"; MV = "/root/mpc-dev/mpc-vst-plugins/wrapper"
P = "/mnt/g/claude/mpc/plugins/Gen 2/X-Console"
os.chdir(X)
pj = json.load(open("vst/params.json")); params = pj if isinstance(pj, list) else pj["params"]
L = {p["key"]: p for p in params}; idx = {p["key"]: i for i, p in enumerate(params)}
auto = json.load(open("vst/gen2/vst.json")).get("defines", {}).get("AUTOMATABLE_PARAMS", 69)
SKIP = re.compile(r"(_model|_unit)$|^(strip_sel|sp_view|pk_hold|m_eqlook)$")
ms = re.findall(r"^MS\((\d+),\s*(\w+),\s*[-\d.ef]+,\s*(\d+),", open("src/param_table.h").read(), re.M)
tags = {"flannel":"FLANNEL","granite":"GRANITE","suede":"SUEDE","hearts":"HEARTS","sandstone":"SANDSTONE","molten":"MOLTEN","spades":"SPADES","mocha":"MOCHA","titanium":"TITANIUM"}
only = sys.argv[1:] or list(tags)
for tag in only:
    preset = tags[tag]; short = re.sub(r"^SSL ", "", preset)
    model = L["m_eqlook"]["options"].index(short + " LINE") // 2
    steps = {k: int(n) for m, k, n in ms if int(m) == model}
    probe = "/tmp/xcp_%d" % model
    subprocess.run(["gcc","-O1","-DXC_ONLY_MODEL=%d"%model,"-I"+X+"/src","-I"+MV,P+"/tools/presets/xc_probe.c"]+[X+"/src/"+f for f in ("engine.c","xconsole.c","spectrum.c","noise.c")]+["-lm","-lpthread","-o",probe],check=True)
    run = lambda *a: subprocess.run([probe]+list(a),check=True,capture_output=True,text=True).stdout
    st = dict(kv.split("=",1) for kv in run("state").strip().split(";") if "=" in kv)
    print("##### %s  model %d" % (tag, model))
    for k, v in st.items():
        if k not in idx or idx[k] >= auto or SKIP.search(k): continue
        p = L[k]
        if p.get("options"):
            print("%-13s %-20s OPT [%s] def=%s" % (k, p.get("name",""), " | ".join(map(str,p["options"])), p["options"][int(v)]))
            continue
        n = steps.get(k)
        rows = run("table", k, str((n-1) if n else 8)).splitlines()
        txt = [r.split(" ",1)[1] for r in rows]
        dflt = run("show", "%s=%s" % (k, v)).split(" ",1)[1].strip()
        print("%-13s %-20s %s [%s] def=%s" % (k, p.get("name",""), ("STEP%d"%n) if n else "RANGE", " | ".join(txt), dflt))
