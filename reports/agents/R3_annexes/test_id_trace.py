"""R3: test ids = full dataset ids minus dev ids (test.jsonl is never opened); then look for those
ids in judge inputs, replay caches / prompt exports and generation reports produced on or after
the sealing dates. Prints only ids and file names."""
import json, glob, collections
def ids(path):
    return [json.loads(l)["id"] for l in open(path, encoding="utf-8") if l.strip()]
abp_all = set(ids("eval/datasets/abp171.jsonl")); abp_dev = set(ids("eval/splits/abp171/dev.jsonl"))
mr_all = set(ids("eval_internal/datasets/multirfe_synth.jsonl")); mr_dev = set(ids("eval_internal/splits/multirfe_synth/dev.jsonl"))
abpe_dev = set(ids("eval/splits/abpe171/dev.jsonl"))
abp_test = abp_all - abp_dev; mr_test = mr_all - mr_dev
print("abp171 test ids", len(abp_test), "| abpe171 dev == abp171 dev:", abpe_dev == abp_dev, "| multirfe test ids", len(mr_test))
def qid(cid):  # judge case ids look like "<config>::<id>"
    return cid.split("::")[-1]
found = collections.Counter()
for f in glob.glob("eval_internal/judge/runs/**/judge_input_*.json", recursive=True):
    try: cases = json.load(open(f, encoding="utf-8"))
    except Exception: continue
    for c in cases:
        q = qid(c.get("case_id", ""))
        if q in abp_test or q in mr_test: found[f] += 1
for f in glob.glob("eval_internal/work/**/gen_input_*.json", recursive=True) + glob.glob("eval_internal/work/replay/**/*.jsonl", recursive=True):
    try:
        if f.endswith(".jsonl"):
            rows = [json.loads(l) for l in open(f, encoding="utf-8") if l.strip()]
        else:
            rows = json.load(open(f, encoding="utf-8"))
    except Exception: continue
    for r in rows if isinstance(rows, list) else []:
        q = r.get("case_id") or r.get("id") or ""
        if q in abp_test or q in mr_test: found[f] += 1
for f in glob.glob("reports/eval/**/*.json", recursive=True):
    try: d = json.load(open(f, encoding="utf-8"))
    except Exception: continue
    for run in (d.get("runs") or []) if isinstance(d, dict) else []:
        for r in run.get("rows") or []:
            if r.get("id") in abp_test or r.get("id") in mr_test: found[f] += 1
for f, n in sorted(found.items()):
    print(n, f)
print("files with test ids:", len(found))
