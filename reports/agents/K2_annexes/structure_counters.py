"""K2 — K1's structural counters, corpus-wide, on any index (read-only sqlite). Regexes imported
from reports/agents/K1_annexes/corpus_structure_audit.py (K1's definitions, unchanged).

    .venv/bin/python reports/agents/K2_annexes/structure_counters.py tas_v6 tas_v7
"""
import collections, json, re, sqlite3, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "reports/agents/K1_annexes"))
from corpus_structure_audit import CLINICAL_RE, GRADE_ANY, REC_STMT_RE, biblio_hits, is_abp  # noqa: E402

GRADE_HEAD = re.compile(r"(?:^|> )\W*(?:GRADE|Grade|AVIS|Avis|ACCORD|Accord|G[12][+\-])")
CLS = {m["doc_id"]: m["cls"] for m in json.loads((ROOT / "reports/agents/K1_annexes/doc_metrics.json").read_text())}


def count(index: str) -> dict:
    con = sqlite3.connect(ROOT / "index" / index / "metadata.sqlite")
    c = collections.Counter()
    for (p,) in con.execute("select payload_json from chunks order by idx"):
        x = json.loads(p)
        t, sp, ct, ref = x["text"], x["section_path"], x["chunk_type"], x["is_reference_section"]
        g1 = CLS.get(x["doc_id"], "").startswith("G1")
        if ref:
            c["ref_flagged"] += 1
            continue
        if GRADE_ANY.search(sp) and GRADE_HEAD.search(sp):
            c["chunks_under_grade_heading"] += 1
        if ct not in ("table_row_card", "table_markdown"):
            h = biblio_hits(t); lines = [ln for ln in t.splitlines() if ln.strip()]
            if h >= 3 and h / max(1, len(lines)) >= 0.5 and not CLINICAL_RE.search(t):
                c["unflagged_biblio_like"] += 1
        if ct in ("prose", "recommendation_box", "callout_footnote"):
            ms = list(REC_STMT_RE.finditer(t))
            grades = set()
            for k, m in enumerate(ms):
                end = ms[k + 1].start() if k + 1 < len(ms) else len(t)
                g = GRADE_ANY.search(t[m.start():end])
                for pre in ("", "G1:"):
                    if pre and not g1:
                        continue
                    c[pre + "stmts"] += 1
                    c[pre + "stmt_grade_same_chunk"] += bool(g)
                    c[pre + "stmt_typed_recommendation"] += ct == "recommendation_box"
                    c[pre + "stmt_typed_note"] += ct == "callout_footnote"
                if g:
                    grades.add(re.sub(r"\s+", " ", g.group(0)).upper())
            if len(ms) >= 2:
                c["chunks_ge2_stmts"] += 1
                c["chunks_ge2_stmts_diff_grades"] += len(grades) >= 2
        c["recommendation_box"] += ct == "recommendation_box"
        c["grade_levels_nonempty"] += bool(x.get("grade_levels"))
    return dict(c)


if __name__ == "__main__":
    out = {ix: count(ix) for ix in sys.argv[1:]}
    (Path(__file__).resolve().parent / "structure_counters.json").write_text(json.dumps(out, indent=1))
    keys = sorted(set().union(*[set(v) for v in out.values()]))
    for k in keys:
        print(f"{k:40s}", *[f"{out[ix].get(k, 0):>8}" for ix in out])
