"""Stricter context metrics on dev suites: C9W (C9 + windows) vs C10 (B1 rows) or any pair.
- ranked gold rank (position of the first gold-matching chunk among ranked results only)
- hit@8 / hit@16 over ranked results
- share of context characters from a gold document; chunks/chars from other documents
Broken down by question type and by features of the gold document."""
import sys, os, collections, statistics
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, items, chunks
from rag_sfar.evaluation.harness import passage_match, paired_bootstrap_diff
byid, allc = chunks()
A, B = (sys.argv[1], sys.argv[2]) if len(sys.argv) > 2 else ("C9W", "C10")
suite = sys.argv[3] if len(sys.argv) > 3 else "multirfe_synth"
doc_tab = collections.Counter(); doc_pedtab = collections.Counter()
for c in allc:
    if c.chunk_type in ("table_row_card", "table_markdown"):
        doc_tab[c.doc_id] += 1
        if c.population_hint == "pediatrie": doc_pedtab[c.doc_id] += 1

def metrics(it, row):
    gold = set(it.gold_doc_ids)
    ids = row["chunks"]; rs = row.get("reasons") or [None] * len(ids)
    ranked = [c for c, r in zip(ids, rs) if r is None]
    def is_gold(cid):
        return any(passage_match(gp.quote, byid[cid].text) for gp in it.gold_passages)
    rk = next((i + 1 for i, c in enumerate(ranked) if is_gold(c)), None) if it.gold_passages else None
    tot = sum(len(byid[c].text) for c in ids) or 1
    gchars = sum(len(byid[c].text) for c in ids if byid[c].doc_id in gold)
    return dict(rank=rk, hit8=None if not it.gold_passages else float(rk is not None and rk <= 8),
                hit16=None if not it.gold_passages else float(rk is not None and rk <= 16),
                any=row.get("passage_hit"),
                gold_share=gchars / tot if gold else None,
                off_chunks=sum(1 for c in ids if byid[c].doc_id not in gold) if gold else None,
                off_chars=sum(len(byid[c].text) for c in ids if byid[c].doc_id not in gold) if gold else None,
                docs=len({byid[c].doc_id for c in ids}),
                doc_recall=len({byid[c].doc_id for c in ids} & gold) / len(gold) if gold else None,
                n_chars=row["n_chars"])

RA, RB, I = rows(A, suite), rows(B, suite), items(suite)
groups = collections.defaultdict(list)
for qid, it in I.items():
    if qid not in RA or qid not in RB: continue
    ma, mb = metrics(it, RA[qid]), metrics(it, RB[qid])
    g = set(it.gold_doc_ids)
    feats = ["all", f"qtype={it.question_type}"]
    if it.should_abstain: feats.append("abstain")
    if g:
        feats.append("gold_doc_has_table=" + str(any(doc_tab[d] for d in g)))
        feats.append("gold_doc_has_ped_table=" + str(any(doc_pedtab[d] for d in g)))
        if len(g) > 1: feats.append("multi_doc")
    feats.append("pop=" + RB[qid].get("pop", "?"))
    for f in feats:
        groups[f].append((qid, ma, mb))

def agg(lst, k, fn=statistics.mean):
    a = [x[1][k] for x in lst if x[1][k] is not None and x[2][k] is not None]
    b = [x[2][k] for x in lst if x[1][k] is not None and x[2][k] is not None]
    if not a: return None
    return a, b
print(f"{A} -> {B} on {suite} dev")
for f in sorted(groups):
    lst = groups[f]
    out = [f"{f} (n={len(lst)})"]
    for k in ("any", "hit8", "hit16", "gold_share", "off_chunks", "off_chars", "docs", "doc_recall", "n_chars"):
        r = agg(lst, k)
        if not r: continue
        a, b = r
        if k in ("any", "hit8", "hit16", "gold_share", "doc_recall") and len(a) >= 5:
            d = paired_bootstrap_diff(a, b)
            out.append(f"{k} {statistics.mean(a):.3f}->{statistics.mean(b):.3f} d={d['diff']:+.3f}[{d['ci_low']:+.3f};{d['ci_high']:+.3f}]")
        else:
            out.append(f"{k} {statistics.mean(a):.2f}->{statistics.mean(b):.2f}")
    ranks = [(x[1]["rank"], x[2]["rank"]) for x in lst if x[1]["rank"] or x[2]["rank"]]
    better = sum(1 for a, b in ranks if (b or 99) < (a or 99)); worse = sum(1 for a, b in ranks if (b or 99) > (a or 99))
    out.append(f"ranked-gold-rank better={better} worse={worse}")
    print("  " + " | ".join(out))
