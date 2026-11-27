"""Why does the link step not change sufficiency on dev? For every insufficient question of a base
(C9 / C9W / C10 on tas_v6), find the chunks of the index that cover each missing evidence and say
whether a counterpart link could bring them (target of a link whose source is in the context)."""
import gzip, json, sys, sqlite3, collections
from pathlib import Path
from rag_sfar.schemas import Chunk, RetrievedChunk
from rag_sfar.evaluation.harness import evidence_metrics
from rag_sfar.evaluation.datasets import load_suite
base = sys.argv[1]
con = sqlite3.connect("index/tas_v6/metadata.sqlite")
chunks = [Chunk.model_validate_json(r[0]) for r in con.execute("select payload_json from chunks")]
by = {c.chunk_id: c for c in chunks}
L = json.load(open("index/tas_v6_links/links.json"))
target_of = collections.defaultdict(list)
for s, ls in L["counterparts"].items():
    for l in ls: target_of[l["target"]].append(s)
path = Path("reports/agents/X1_annexes/res/base__abpe171.json.gz") if base == "base" else Path(f"reports/agents/B1_annexes/res/{base}__abpe171.json.gz")
rows = {r["id"]: r for r in json.load(gzip.open(path))["rows"]}
summary = collections.Counter()
for it in load_suite("abpe171", "dev"):
    r = rows[it.id]
    if r.get("sufficiency") != 0.0: continue
    ctx = set(r["chunks"])
    missing = [e for e, rk in r["evidence_ranks"].items() if rk is None]
    gold_docs = {e.doc_id for e in it.evidence if e.evidence_id in missing}
    for eid in missing:
        ev = next(e for e in it.evidence if e.evidence_id == eid)
        cands = [c for c in chunks if c.doc_id == ev.doc_id and c.is_latest_edition and evidence_metrics(
            it.model_copy(update={"evidence_sets": [type(it.evidence_sets[0])(set_id="x", required_evidence_ids=[eid])]}),
            [RetrievedChunk(chunk=c, final_score=1.0)]).get("sufficiency") == 1.0] if ev.doc_id else []
        kinds = collections.Counter(c.chunk_type for c in cands)
        linked = [c for c in cands if c.chunk_id in target_of]
        src_in_ctx = [c for c in linked if any(s in ctx for s in target_of[c.chunk_id])]
        tag = "no_chunk" if not cands else ("not_link_target" if not linked else ("source_not_in_context" if not src_in_ctx else "reachable"))
        summary[tag] += 1
        print(it.id, eid, "pediatric" in it.tags, tag, dict(kinds), [ (c.chunk_id[-14:], c.populations) for c in cands[:3]])
print(base, dict(summary))
