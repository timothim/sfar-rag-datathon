"""Per-rule firing, relevance and post-hoc necessity of C10's additions (B1 rows or R2 rows)."""
import sys, os, collections, json
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks, attribute, SUITES
from rag_sfar.schemas import RetrievedChunk
from rag_sfar.evaluation.harness import evidence_metrics, passage_match

NAME = sys.argv[1] if len(sys.argv) > 1 else "C10"
byid, _ = chunks()
def rc(cid): return RetrievedChunk(chunk=byid[cid], final_score=0.0)

def success(it, cids):
    ret = [rc(c) for c in cids]
    if it.evidence_sets:
        m = evidence_metrics(it, ret)
        if m: return m["sufficiency"]
    if it.gold_passages:
        return 1.0 if any(passage_match(gp.quote, r.chunk.text) for gp in it.gold_passages for r in ret) else 0.0
    return None

def relevant(it, cid):
    """Does this chunk alone cover an evidence fragment / gold passage?"""
    r = [rc(cid)]
    if it.evidence_sets:
        m = evidence_metrics(it, r)
        return bool(m and m["evidence_hit"])
    if it.gold_passages:
        return any(passage_match(gp.quote, byid[cid].text) for gp in it.gold_passages)
    return None

def group(owner):
    if owner == "ranked": return "ranked"
    if owner.startswith("population:"): return owner
    if owner.startswith("mcq_option"): return "mcq"
    return owner

report = {}
samples = collections.defaultdict(list)
for s in SUITES:
    R = rows(NAME, s); I = items(s)
    stat = collections.defaultdict(lambda: collections.Counter())
    for qid, row in R.items():
        it = I[qid]
        own = [group(o) for o in attribute(row)]
        reasons = row["reasons"]
        gold_docs = set(it.gold_doc_ids)
        base_ok = success(it, row["chunks"])
        # cap binding: ranked items per doc
        rk = collections.Counter(byid[c].doc_id for c, r in zip(row["chunks"], reasons) if r is None)
        if rk and max(rk.values()) > 7:
            stat["cap>7"]["questions"] += 1
        for g in ["population:adulte", "population:pediatrie", "mcq", "table_note"]:
            if g == "table_note":
                idx = [i for i, r in enumerate(reasons) if r == "table_note"]
            else:
                idx = [i for i, o in enumerate(own) if o == g]
            if not idx:
                continue
            st = stat[g]
            st["questions"] += 1
            anchors = [i for i in idx if reasons[i] not in ("context_window", "table_note")] if g != "table_note" else idx
            st["anchors"] += len(anchors)
            st["chunks_incl_windows"] += len(idx)
            st["chars"] += sum(len(byid[row["chunks"][i]].text) for i in idx)
            for i in anchors:
                cid = row["chunks"][i]
                rel = relevant(it, cid)
                st["anchor_relevant"] += 1 if rel else 0
                st["anchor_rel_known"] += 0 if rel is None else 1
                if gold_docs:
                    st["anchor_in_gold_doc"] += byid[cid].doc_id in gold_docs
                samples[(s, g)].append((qid, cid))
            if base_ok is not None:
                keep = [c for j, c in enumerate(row["chunks"]) if j not in set(idx)]
                if success(it, keep) < base_ok:
                    st["needed"] += 1
                    st.setdefault("needed_ids", 0)
                    stat[g + "_needed_ids"][qid] += 1
    report[s] = {k: dict(v) for k, v in stat.items()}
    print("==", s, "n=", len(R))
    for k, v in stat.items():
        print("  ", k, dict(v))
json.dump({f"{a}|{b}": v for (a, b), v in samples.items()}, open(os.path.join(os.path.dirname(__file__), f"samples_{NAME}.json"), "w"))
