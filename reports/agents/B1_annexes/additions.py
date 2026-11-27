"""Per-suite analysis of a result set: context size, share of the context from a gold
document, and (for guaranteed population passages) firing, relevance and "other act" rows.

usage: additions.py <res_dir> <name> [index]"""
import gzip, json, sqlite3, sys, statistics
from pathlib import Path
from rag_sfar.evaluation.datasets import load_suite
from rag_sfar.evaluation.harness import tokens, _shingles, _column_shingles, COLUMN_SEP
from rag_sfar.retrieval.pipeline import _act_tokens, _labels_match

res_dir, name = Path(sys.argv[1]), sys.argv[2]
idx = sys.argv[3] if len(sys.argv) > 3 else "tas_v3_errata"
db = sqlite3.connect(f"index/{idx}/metadata.sqlite")
def chunk(cid):
    row = db.execute("select doc_id, payload_json from chunks where chunk_id=?", (cid,)).fetchone()
    return row[0], json.loads(row[1])["text"]
def covers(frag, text):
    t = tokens(text); sh = _shingles(t) | _shingles(t, 2)
    q = _column_shingles(frag) if COLUMN_SEP in frag else _shingles(tokens(frag))
    return bool(q) and len(q & sh) / len(q) >= 0.5
for suite in ("abpe171", "abp171", "multirfe_synth"):
    p = res_dir / f"{name}__{suite}.json"
    gz = Path(str(p) + ".gz")
    if not p.exists() and not gz.exists():
        continue
    items = {i.id: i for i in load_suite(suite, "dev")}
    rows = json.loads(p.read_text() if p.exists() else gzip.open(gz).read())["rows"]
    share, fired, adds, relevant, other_act, add_chars, dup = [], 0, 0, 0, 0, 0, 0
    for r in rows:
        it = items[r["id"]]
        gold_docs = set(it.gold_doc_ids) | {g.doc_id for g in it.gold_passages}
        texts = [chunk(c) for c in r["chunks"]]
        tot = sum(len(t) for _, t in texts) or 1
        norm = [" ".join(t.lower().split()) for _, t in texts]
        dup += len(norm) != len(set(norm))
        if gold_docs:
            share.append(sum(len(t) for d, t in texts if d in gold_docs) / tot)
        frags = [f for e in it.evidence for f in e.fragments] or [g.quote for g in it.gold_passages]
        acts = [_act_tokens(f.split(" ‖ ")[0].replace("‖", " ")) for f in frags]
        added = [(c, t) for c, why, (d, t) in zip(r["chunks"], r.get("reasons") or [None] * len(r["chunks"]), texts) if (why or "").startswith("population")]
        if added:
            fired += 1
        for c, t in added:
            adds += 1
            add_chars += len(t)
            if any(covers(f, t) for f in frags):
                relevant += 1
            elif frags and not any(_labels_match(_act_tokens(t), a) for a in acts if len(a) >= 2):
                other_act += 1
    print(f"{name} {suite}: chars {statistics.mean(r['n_chars'] for r in rows):.0f} chunks {statistics.mean(r['n_chunks'] for r in rows):.1f} "
          f"gold-doc share {100*statistics.mean(share):.1f}% | contexts with duplicate text {dup} | population fired on {fired}/{len(rows)} questions, "
          f"{adds} additions, {relevant} cover required evidence/gold, {other_act} rows of another act, {add_chars} chars added")
