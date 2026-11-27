"""R3: summary of judge verdicts in eval_internal/judge/runs (read-only)."""
import json, collections, glob, os, sys
ROOT = "eval_internal/judge/runs"
pat = sys.argv[1] if len(sys.argv) > 1 else "b3_v6_*"
for d in sorted(glob.glob(f"{ROOT}/{pat}")):
    for sub in ("", "rubric_v2"):
        dd = os.path.join(d, sub)
        outs = sorted(glob.glob(f"{dd}/judge_out_*.json"))
        if not outs:
            continue
        v = [x for f in outs for x in json.load(open(f))]
        ins = [x for f in sorted(glob.glob(f"{d}/judge_input_*.json")) for x in json.load(open(f))]
        c = collections.Counter(x["correctness"] for x in v)
        se = collections.Counter(x.get("serious_error") for x in v)
        b = collections.Counter(x.get("behavior") for x in v if "behavior" in x)
        print(f"{d.split('/')[-1]}/{sub or 'v3'}: n={len(v)}/{len(ins)} {dict(c)} serious={dict(se)} behavior={dict(b)}")
