"""K1 — Demonstration only (in memory, nothing wired in, nothing written to index/ or data/).

Candidate fix: a Markdown heading whose text is a grade line ("### GRADE 1 (recommandation forte)",
"#### Avis d'experts (Accord Fort)") is not a section title; render it as a bold body line so it
stays in the chunk of the statement it grades instead of becoming the section path of the
argument that follows. Generic: applies to every document, keyed on the grade vocabulary only.

Measures, on the documents that have such headings, before/after with the frozen chunker:
statements whose grade is in the same chunk, chunks presented under a grade heading.
"""
import collections, copy, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(Path(__file__).parent))
import rag_sfar.ingestion.chunker as ch
from rag_sfar.ingestion.loader import load_sfar_corpus
from corpus_structure_audit import GRADE_ANY, REC_STMT_RE, is_abp

GRADE_HEADING_RE = re.compile(
    r"(?m)^#{1,6}\s*(\**\s*(?:\(?\s*GRADE\s*[12]|AVIS\s+D['’]EXPERTS?|Avis\s+d['’]experts?|ACCORD\s+(?:FORT|FAIBLE)|Accord\s+(?:fort|faible|FORT)|G[12]\s?[+\-])[^\n]{0,80})$"
)


def demote_grade_headings(text: str) -> str:
    return GRADE_HEADING_RE.sub(lambda m: "**" + m.group(1).strip("* ") + "**", text)


def measure(chunks):
    c = collections.Counter()
    flow = [x for x in chunks if x.chunk_type in ("prose", "recommendation_box", "callout_footnote") and not x.is_reference_section]
    for x in chunks:
        if not x.is_reference_section and any(GRADE_ANY.search(p) and re.match(r"\W*(?:GRADE|Grade|AVIS|Avis|ACCORD|Accord|G[12])", p) for p in x.section_path.split(" > ")):
            c["chunks_under_grade_heading"] += 1
    for x in flow:
        ms = list(REC_STMT_RE.finditer(x.text))
        for k, m in enumerate(ms):
            end = ms[k + 1].start() if k + 1 < len(ms) else len(x.text)
            c["stmts"] += 1
            c["stmt_grade_same_chunk"] += bool(GRADE_ANY.search(x.text[m.start():end]))
            c["stmt_in_rec_box"] += x.chunk_type == "recommendation_box"
    return c


def main():
    docs = load_sfar_corpus(ROOT / "data" / "sfar_recommendations" / "output", updates_dir=ROOT / "data" / "corpus_updates")
    targets = [d for d in docs if GRADE_HEADING_RE.search(d.text) and not is_abp(d.metadata.title, d.metadata.doc_id)]
    opts = ch.ChunkOptions()
    tot_b, tot_a = collections.Counter(), collections.Counter()
    per_doc = []
    for d in targets:
        before = measure(ch._chunk_table_aware_sota(d, options=opts))
        d2 = copy.copy(d)
        d2.text = demote_grade_headings(d.text)
        after = measure(ch._chunk_table_aware_sota(d2, options=opts))
        tot_b.update(before); tot_a.update(after)
        per_doc.append((d.metadata.doc_id, dict(before), dict(after)))
    out = {"documents": len(targets), "before": dict(tot_b), "after": dict(tot_a), "per_doc": per_doc}
    (Path(__file__).parent / "demo_grade_heading_fix.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k != "per_doc"}, indent=1))


if __name__ == "__main__":
    main()
