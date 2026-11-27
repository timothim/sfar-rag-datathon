"""R3: deterministic answer check (generation/answer_check.py) on the Sonnet answers of the frozen
configuration, recomputed read-only from the replay cache (gen_replay.recheck without writing)."""
import json, sys, glob, collections
sys.path.insert(0, "src"); sys.path.insert(0, "eval_internal")
from gen_replay import load_cache, config_from_meta
from rag_sfar.generation.client import build_generation_context
from rag_sfar.generation.settings import GenerationConfig
from rag_sfar.generation.answer_check import check_answer
from rag_sfar.evaluation import harness
from rag_sfar.schemas import RetrievedChunk, QueryAnalysis
for p in sorted(glob.glob("reports/eval/b3/*b3_v6_c10n_*claude-sonnet-5-5.json")):
    rep = json.load(open(p)); suite = rep["suite"]
    meta, cache = load_cache(rep["replay"]["cache"], suite); cfg = config_from_meta(meta)
    g = GenerationConfig(**rep["replay"]["gen_config"])
    flags = collections.Counter(); ex = []
    rows = [r for r in rep["runs"][0]["rows"] if "answer" in r]
    for r in rows:
        c = cache[r["id"]]
        retrieved = [RetrievedChunk.model_validate(x) for x in c["retrieved"]]
        an = QueryAnalysis.model_validate(c["analysis"])
        chunks, _ = build_generation_context(retrieved, an, cfg, c["query"], r.get("mode", ""), g)
        chk = check_answer(r["answer"], chunks, is_abstention=harness.is_abstention(r["answer"]), query=c["query"])
        flags["n"] += 1
        flags["flagged"] += chk.flagged
        flags["unsupported_dose"] += bool(chk.unsupported_doses)
        flags["unsupported_drug"] += bool(chk.unsupported_drugs)
        flags["invalid_cit"] += bool(chk.invalid_citations)
        flags["uncited"] += chk.uncited
        flags["not_in_cited"] += bool(chk.doses_not_in_cited or chk.drugs_not_in_cited)
        if chk.unsupported_doses or chk.unsupported_drugs or chk.invalid_citations:
            ex.append((r["id"], chk.unsupported_doses, chk.unsupported_drugs, chk.invalid_citations, r.get("judge", {}).get("correctness")))
    print(p.split("/")[-1][:75], dict(flags))
    for e in ex: print("   ", e)
