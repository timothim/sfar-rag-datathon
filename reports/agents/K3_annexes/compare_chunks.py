"""K3 - Chunk-level diff index/tas_v6 vs index/tas_v6_tablefix (metadata.sqlite, no models).

Chunk ids carry the position in the document, so chunks are paired per document by aligning the
two ordered lists of texts (difflib); a "changed" chunk is one of a replaced block, paired by
position inside the block; deleted / inserted chunks are listed apart. Writes ids and
counts to compare_chunks.json; a random sample of changed row cards (seed 0, up to 45 per group)
with both texts goes to compare_chunks_sample.local.json for hand labelling (corpus text: not
committed).
"""
from __future__ import annotations

import collections
import difflib
import json
import random
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent


def load(name: str) -> dict:
    con = sqlite3.connect(ROOT / "index" / name / "metadata.sqlite")
    out = collections.defaultdict(list)
    for cid, doc, ctype, payload in con.execute("select chunk_id, doc_id, chunk_type, payload_json from chunks order by idx"):
        p = json.loads(payload)
        out[doc].append({"id": cid, "doc": doc, "type": ctype, "text": p.get("text", "")})
    return out


A, B = load("tas_v6"), load("tas_v6_tablefix")
abp = lambda d: "antibioprophylaxie" in d.lower()  # noqa: E731
a, b = {}, {}
changed, only_a, only_b = [], [], []
for doc in sorted(set(A) | set(B)):
    xa, xb = A.get(doc, []), B.get(doc, [])
    for x in xa:
        a[x["id"]] = x
    sm = difflib.SequenceMatcher(None, [(x["type"], x["text"]) for x in xa], [(x["type"], x["text"]) for x in xb], autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            continue
        n = min(i2 - i1, j2 - j1)
        for k in range(n):
            changed.append(xa[i1 + k]["id"])
            b[xa[i1 + k]["id"]] = xb[j1 + k]
        only_a += [x["id"] for x in xa[i1 + n:i2]]
        only_b += [x["id"] for x in xb[j1 + n:j2]]
by = collections.Counter((("abp" if abp(a[c]["doc"]) else "other"), a[c]["type"]) for c in changed)
docs = collections.Counter(a[c]["doc"] for c in changed + only_a)
res = {
    "chunks_tas_v6": sum(map(len, A.values())), "chunks_tablefix": sum(map(len, B.values())), "changed": len(changed),
    "only_in_tas_v6": only_a, "only_in_tablefix": only_b,
    "changed_by_group_type": {f"{g}/{t}": n for (g, t), n in sorted(by.items())},
    "changed_docs": dict(docs.most_common()),
    "changed_abp_ids": [c for c in changed if abp(a[c]["doc"])],
}
rng = random.Random(0)
sample = {}
for g in ("abp", "other"):
    cards = [c for c in changed if a[c]["type"] == "table_row_card" and (abp(a[c]["doc"]) == (g == "abp"))]
    pick = cards if len(cards) <= 45 else rng.sample(cards, 45)
    sample[g] = [{"chunk_id": c, "before": a[c]["text"][-700:], "after": b[c]["text"][-700:], "after_id": b[c]["id"]} for c in sorted(pick)]
    res[f"row_cards_changed_{g}"] = len(cards)
    res[f"sampled_{g}"] = [s["chunk_id"] for s in sample[g]]
(HERE / "compare_chunks.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
(HERE / "compare_chunks_sample.local.json").write_text(json.dumps(sample, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if not k.startswith(("sampled", "changed_abp_ids", "only"))}, indent=1))
print("only_a", len(only_a), "only_b", len(only_b))
