"""Edition / abrogation / language / bibliography status of every chunk in the C10 contexts,
by expansion path; duplicates and budget."""
import sys, os, collections
sys.path.insert(0, os.path.dirname(__file__))
from common import rows, chunks, attribute, SUITES
byid, allc = chunks()
# Are the mask attributes constant within a document? (neighbours inherit the anchor's status)
by_doc = collections.defaultdict(set)
for c in allc:
    by_doc[c.doc_id].add((c.is_latest_edition, c.is_active, c.language != "en"))
mixed = {d: v for d, v in by_doc.items() if len(v) > 1}
print("documents with mixed latest/active/french status across chunks:", len(mixed), list(mixed)[:5])
for name in sys.argv[1:] or ["C10"]:
    tot = collections.Counter()
    for s in SUITES:
        R = rows(name, s)
        if not R: continue
        for qid, row in R.items():
            own = attribute(row)
            ids = row["chunks"]
            if len(ids) != len(set(ids)): tot["questions_with_duplicate_ids"] += 1
            texts = [byid[c].text.strip() for c in ids]
            if len(texts) != len(set(texts)): tot["questions_with_duplicate_text"] += 1
            if row["n_chars"] > 30000: tot["over_30000"] += 1
            for cid, r, o in zip(ids, row.get("reasons") or [None] * len(ids), own):
                c = byid[cid]
                path = r if r in ("context_window", "table_note") else ("ranked" if r is None else r.split(":")[0])
                tot["chunks"] += 1
                if not c.is_latest_edition: tot[f"superseded:{path}"] += 1
                if not c.is_active: tot[f"abrogated:{path}"] += 1
                if c.language == "en": tot[f"english:{path}"] += 1
                if c.is_reference_section: tot[f"bibliography:{path}"] += 1
    print(name, dict(tot))
