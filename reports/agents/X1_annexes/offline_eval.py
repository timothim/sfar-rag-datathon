"""X1 offline evaluation of the link step on the cached frozen output (exact: the step is a pure
function of the retriever output, the query and the chunk store). Prints metrics with paired
bootstrap CIs vs the frozen configuration, by subgroup, firing counts and the additions."""
import argparse, gzip, json, sqlite3, collections, statistics, sys
from pathlib import Path
from rag_sfar.schemas import Chunk, RetrievedChunk
from rag_sfar.evaluation.harness import retrieval_metrics, paired_bootstrap_diff, bootstrap_ci, select_configs
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.retrieval.router import analyze_query
from rag_sfar.retrieval.pipeline import SfarRagRetriever
from rag_sfar.retrieval.links import ChunkLinks, LinkPolicy, apply_links

RES = Path(__file__).parent / "res"

class Store:
    def __init__(self):
        con = sqlite3.connect("index/tas_v6/metadata.sqlite")
        self.by = {c.chunk_id: c for c in (Chunk.model_validate_json(r[0]) for r in con.execute("select payload_json from chunks"))}
    def get_chunk(self, cid): return self.by.get(cid)

def rebuild(row, store):
    return [RetrievedChunk(chunk=store.get_chunk(cid), final_score=s, rerank_score=ce, is_expanded_context=e, expansion_reason=r)
            for cid, s, ce, e, r in zip(row["chunks"], row["scores"], row["ce"], row["expanded"], row["reasons"])]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--policy", default='{"counterparts": true}')
    ap.add_argument("--links", default="index/tas_v6_links")
    ap.add_argument("--name", default="")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--base", default="base", help="base rows: 'base' (X1 capture of C10) or a B1 res prefix like tas_v6_C9")
    a = ap.parse_args()
    store = Store(); links = ChunkLinks.load(Path(a.links), Path("index/tas_v6"))
    pol = LinkPolicy(**json.loads(a.policy)); cfg = select_configs("C10_context_notes")[0]
    R = SfarRagRetriever.__new__(SfarRagRetriever); R.store = store
    report = {}
    for suite, key in (("abpe171", ["sufficiency", "evidence_recall"]), ("multirfe_synth", ["passage_hit"])):
        if a.base == "base":
            base = {r["id"]: r for r in json.load(gzip.open(RES / f"base__{suite}.json.gz"))["rows"]}
        else:  # B1 cached rows: no scores / flags; expanded = has an expansion reason
            base = {}
            for r in json.load(gzip.open(Path("reports/agents/B1_annexes/res") / f"{a.base}__{suite}.json.gz"))["rows"]:
                r["scores"] = [1.0 - i * 1e-3 for i in range(len(r["chunks"]))]
                r["expanded"] = [x is not None for x in r["reasons"]]
                r["population"] = r["pop"]
                base[r["id"]] = r
        items = load_suite(suite, "dev")
        rows = []
        for it in items:
            b = base[it.id]; q = it.formatted_query()
            ctx = rebuild(b, store)
            if a.base != "base":
                cfg_eval = cfg  # budget of the frozen config
            an = analyze_query(q, use_lexicon=cfg.use_medical_lexicon)
            assert an.population == b["population"], (it.id, an.population, b["population"])
            new, st = apply_links(ctx, an, cfg, store, links, pol, query=q, note_reader=R._called_notes)
            m = retrieval_metrics(it, new, 64)
            m.update(id=it.id, tags=it.tags, pop=an.population, n_chars=sum(len(r.chunk.text) for r in new),
                     base_chars=b["n_chars"], stats=st, base={k: b.get(k) for k in key})
            rows.append(m)
        out = {}
        for k in key:
            A = [r["base"][k] for r in rows]; B = [r.get(k) for r in rows]
            d = paired_bootstrap_diff(A, B)
            va = [x for x in A if x is not None]; vb = [x for x in B if x is not None]
            out[k] = dict(base=round(100*sum(va)/len(va), 1), new=round(100*sum(vb)/len(vb), 1),
                          diff=round(100*d["diff"], 1), ci=[round(100*d["ci_low"], 1), round(100*d["ci_high"], 1)],
                          changed=[(r["id"], r["base"][k], r.get(k)) for r in rows if r["base"][k] != r.get(k)])
            # subgroups
            for g, f in (("pediatric_tag", lambda r: "pediatric" in r["tags"]), ("not_pediatric_tag", lambda r: "pediatric" not in r["tags"]),
                         ("query_pop_non_specifie", lambda r: r["pop"] == "non_specifie"), ("query_pop_named", lambda r: r["pop"] != "non_specifie")):
                sub = [r for r in rows if f(r) and r["base"][k] is not None]
                if sub:
                    dd = paired_bootstrap_diff([r["base"][k] for r in sub], [r[k] for r in sub])
                    out[k][g] = dict(n=len(sub), base=round(100*statistics.mean(r["base"][k] for r in sub), 1),
                                     new=round(100*statistics.mean(r[k] for r in sub), 1), diff=round(100*dd["diff"], 1),
                                     ci=[round(100*dd["ci_low"], 1), round(100*dd["ci_high"], 1)])
        fired = [r for r in rows if r["stats"]["counterparts_added"] or r["stats"]["notes_added"]]
        out["fired_questions"] = len(fired); out["n"] = len(rows)
        out["counterparts_added"] = sum(len(r["stats"]["counterparts_added"]) for r in rows)
        out["notes_added"] = sum(len(r["stats"]["notes_added"]) for r in rows)
        out["chars_added_mean_all"] = round(statistics.mean(r["n_chars"] - r["base_chars"] for r in rows))
        out["chars_added_mean_fired"] = round(statistics.mean(r["n_chars"] - r["base_chars"] for r in fired)) if fired else 0
        out["context_chars_mean"] = [round(statistics.mean(r["base_chars"] for r in rows)), round(statistics.mean(r["n_chars"] for r in rows))]
        out["additions"] = [dict(id=r["id"], pop=r["pop"], tags=[t for t in r["tags"] if t.startswith("population") or t == "pediatric"],
                                 **{k: (r["base"][k], r.get(k)) for k in key}, cp=r["stats"]["counterparts_added"], notes=r["stats"]["notes_added"]) for r in fired]
        report[suite] = out
        print(suite, json.dumps({k: v for k, v in out.items() if k != "additions"}, ensure_ascii=False))
    if a.name:
        (RES / f"offline_{a.name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1))
    if a.show:
        for suite, out in report.items():
            for ad in out["additions"]:
                print(suite, ad["id"], ad["pop"], ad["tags"], {k: v for k, v in ad.items() if k in ("sufficiency", "evidence_recall", "passage_hit")})
                for c in ad["cp"]:
                    print("   CP", c["population"], c["match"], "anchor:", c["anchor"][-14:], "->", c["target"][-14:])
                for n in ad["notes"]:
                    print("   NOTE", n["anchor"][-14:], "->", n["note"][-14:])

if __name__ == "__main__":
    main()
