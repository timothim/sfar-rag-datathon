"""R1: on how many documents / tables does each B2 rule fire? Re-chunks the corpus in memory with
the default ChunkOptions (CPU only, nothing written to index/), counting per document through
TABLE_STATS deltas and wrappers around the rule functions."""
import collections, json, re
from pathlib import Path
from rag_sfar.ingestion import loader as L, chunker as C, table_parser as T
from rag_sfar.ingestion.text_cleaning import NulRepairer

docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
cur = {"doc": None}
fires = collections.defaultdict(collections.Counter)  # rule -> doc -> count
examples = collections.defaultdict(list)

orig_kind = T.full_width_row_kind
def kind(text, tr):
    k = orig_kind(text, tr)
    fires[f"full_width_{k}"][cur["doc"]] += 1
    if len(examples[f"full_width_{k}"]) < 400: examples[f"full_width_{k}"].append((cur["doc"][:50], text[:140]))
    return k
T.full_width_row_kind = kind

orig_hdr = T._looks_like_header_row
def hdr(row):
    r = orig_hdr(row)
    if r: fires["td_header_heuristic"][cur["doc"]] += 1
    return r
T._looks_like_header_row = hdr

orig_parse = T.parse_html_table
def parse(tok, **kw):
    p = orig_parse(tok, **kw)
    if p.carried_first_cell: fires["carry_first_cell"][cur["doc"]] += 1
    if p.inherited_headers: fires["inherited_headers"][cur["doc"]] += 1
    if p.headers and p.headers[0] == "Catégorie" and p.inherited_headers: fires["invented_Categorie_header"][cur["doc"]] += 1
    # parallel <li> de-merge (ABP-specific "PAS D'ANTIBIOPROPHYLAXIE" rule): detect via re-parse difference
    return p
T.parse_html_table = parse
C.parse_html_table = parse

repairer = NulRepairer([d.text for d in docs])
opts = C.ChunkOptions()
for d in docs:
    cur["doc"] = d.metadata.doc_id
    before = C.TABLE_STATS.copy()
    chunks = C._chunk_table_aware_sota(d, options=opts, nul_repairer=repairer)
    after = C.TABLE_STATS
    for k in ("footnotes_linked", "with_scope_note", "titled", "tables_under_reference_heading", "carried_first_cell", "full_width_notes"):
        dlt = after[k] - before[k]
        if dlt: fires[k][d.metadata.doc_id] += dlt
    n_tables = after["tables"] - before["tables"]
    if n_tables: fires["tables"][d.metadata.doc_id] += n_tables
    for c in chunks:
        if c.chunk_type == "callout_allergy": fires["callout_allergy"][d.metadata.doc_id] += 1
        if "[Organigramme" in c.text: fires["mermaid_rewritten_chunk"][d.metadata.doc_id] += 1
        if re.search(r"^Note \([^)]*\) :", c.text, re.M): fires["chunk_with_linked_footnote"][d.metadata.doc_id] += 1

# ABP-specific parallel list de-merge: count tables where the "pas d'antibioprophylaxie" condition holds
for d in docs:
    for tok in re.findall(r"<table\b.*?</table>", d.text, flags=re.S | re.I):
        if re.search(r"pas d.antibioprophylaxie", tok, re.I) and re.search(r"rowspan", tok):
            fires["demerge_candidate_tables(PAS D'ABP + rowspan)"][d.metadata.doc_id] += 1

summary = {r: {"n_docs": len(c), "n_events": sum(c.values()), "top_docs": c.most_common(6)} for r, c in fires.items()}
json.dump(summary, open("reports/agents/R1_annexes/rule_firing.json", "w"), ensure_ascii=False, indent=1)
for r, s in sorted(summary.items()):
    print(f"{r:45s} docs={s['n_docs']:4d} events={s['n_events']:6d} top={[(d[:38], n) for d, n in s['top_docs'][:4]]}")
with open("reports/agents/R1_annexes/full_width_examples.txt", "w") as f:
    for k in ("full_width_note", "full_width_label"):
        f.write(f"== {k}\n")
        for e in examples[k]: f.write(f"{e[0]}\t{e[1]}\n")
