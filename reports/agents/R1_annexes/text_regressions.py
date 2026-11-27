"""R1: counts of three text regressions in an index chunk store (read-only, CPU):
1. Markdown tables flattened to one line (rows joined, empty cells dropped) by
   text_cleaning.strip_inline_tags: compare the number of table_markdown chunks with >= 2 table rows
   in the tables-only index (tas_v4_t, before the clean-up) and the single-line ones in tas_v4;
2. corrupted micro units ("\\mug", "mug", "mumol") and residual LaTeX commands;
3. doses lost from one algorithm document after the Mermaid rewrite (tas_v3_errata vs tas_v4).
Usage: python text_regressions.py"""
import collections, json, re, sqlite3

def chunks(idx, where="1=1"):
    c = sqlite3.connect(f"index/{idx}/metadata.sqlite")
    for did, ct, p in c.execute(f"select doc_id, chunk_type, payload_json from chunks where {where}"):
        yield did, ct, json.loads(p)["text"]

multi = sum(1 for _, _, t in chunks("tas_v4_t", "chunk_type='table_markdown'")
            if len([l for l in t.split("\n") if l.strip().startswith("|") and "---" not in l]) >= 2)
flat = sum(1 for _, _, t in chunks("tas_v4", "chunk_type='table_markdown'") if "| --- |" in t and t.count("\n") <= 2)
print(f"1. table_markdown with >= 2 rows in tas_v4_t: {multi}; single-line tables in tas_v4: {flat}")
for idx in ("tas_v3_errata", "tas_v4"):
    pat = re.compile(r"(?<![A-Za-zÀ-ÿ])\\?mug(?=/|\b)|mumol|cdot")
    cnt, docs = collections.Counter(), set()
    for did, ct, t in chunks(idx, "chunk_type!='references'"):
        for m in pat.finditer(t):
            cnt[m.group(0)] += 1; docs.add(did)
    print(f"2. {idx}: corrupted micro units {sum(cnt.values())} in {len(docs)} docs {dict(cnt)}")
doc = "2024_Algorithmes_RFE-gestion-de-lanticoagulation-dans-un-contexte-dur_5ab803"
for idx in ("tas_v3_errata", "tas_v4"):
    blob = "\n".join(t for _, _, t in chunks(idx, f"doc_id='{doc}'"))
    print(f"3. {idx}:", {k: blob.count(k) for k in ["5 g IVL", "≤50 ng/mL", "2ème dose", "200 ng/mL"]})
