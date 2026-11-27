"""R3: print judged cases (input + v3 verdict + v2 verdict if present) for manual review."""
import json, glob, os, sys
d = sys.argv[1]; ids = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else None
ins = [x for f in sorted(glob.glob(f"{d}/judge_input_*.json")) for x in json.load(open(f))]
v3 = {x["case_id"]: x for f in sorted(glob.glob(f"{d}/judge_out_*.json")) for x in json.load(open(f))}
v2 = {x["case_id"]: x for f in sorted(glob.glob(f"{d}/rubric_v2/judge_out_*.json")) for x in json.load(open(f))}
for c in ins:
    qid = c["case_id"].split("::")[-1]
    if ids and qid not in ids: continue
    if c["case_id"] not in v3: continue
    print("=" * 100); print("ID", c["case_id"])
    print("Q:", c["question"][:700])
    print("REF:", c["reference"][:600])
    if c.get("reference_narrative"): print("NARR:", c["reference_narrative"][:900])
    for k in ("expected_behavior", "acceptable_behaviors", "required_missing_information"):
        if k in c: print(k.upper(), c[k])
    for k in ("mandatory_claims", "forbidden_claims"):
        if k in c: print(k.upper(), [(x["id"], x["text"][:160]) for x in c[k]])
    print("ANS:", c["answer"][:1500])
    a = v3[c["case_id"]]
    print("V3:", {k: a.get(k) for k in ("correctness","serious_error","behavior","claims_satisfied","forbidden_violated")}, "|", a.get("justification"))
    if c["case_id"] in v2:
        b = v2[c["case_id"]]
        print("V2:", {k: b.get(k) for k in ("correctness","serious_error","behavior","forbidden_violated")}, "|", b.get("justification"))
