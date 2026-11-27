"""K1 — Additional corpus-wide counters on index/tas_v6 (read-only, CPU).

1. Grade lines turned into Markdown headings: chunks whose section_path contains a grade label
   (the following argument text is then presented under "Section : ... > GRADE 1 ...").
2. Statements whose section_path ends in an "Argumentaire" heading of the previous question.
3. Recommendation-id formats in the text that the chunker's REC_ID_RE does not capture
   ("R1 –", "R 1.1 :", "Recommandation 3"), per document.
4. Prose chunks that contain a recommendation formula AND a grade label but are not typed
   recommendation_box (shown to the generator as "Nature : texte").
5. Chunk length distribution per class (from doc_metrics.json classes).
"""

from __future__ import annotations

import collections
import json
import re
import sqlite3
import statistics
from pathlib import Path

from corpus_structure_audit import GRADE_ANY, GRADE_CAPTURED, REC_ID_RE, REC_STMT_RE, RECO_VERB_RE, biblio_hits

OUT = Path(__file__).resolve().parent
DB = OUT.parents[2] / "index" / "tas_v6" / "metadata.sqlite"


def main() -> None:
    cls_of = {m["doc_id"]: m["cls"] for m in json.loads((OUT / "doc_metrics.json").read_text())}
    cur = {m["doc_id"]: (m["latest"] and m["active"]) for m in json.loads((OUT / "doc_metrics.json").read_text())}
    con = sqlite3.connect(DB)
    cnt = collections.defaultdict(collections.Counter)
    docs_hit = collections.defaultdict(lambda: collections.defaultdict(set))
    ex = collections.defaultdict(list)
    lens = collections.defaultdict(list)
    for (p,) in con.execute("select payload_json from chunks order by idx"):
        c = json.loads(p)
        cls = cls_of[c["doc_id"]]
        t, sp, ct = c["text"], c["section_path"], c["chunk_type"]
        if c["is_reference_section"]:
            continue
        lens[cls].append(len(t))
        last = sp.split(" > ")[-1] if sp else ""
        if GRADE_ANY.search(sp) and re.search(r"(?:^|> )\W*(?:GRADE|Grade|AVIS|Avis|ACCORD|Accord|G[12][+\-])", sp):
            cnt[cls]["chunks_under_grade_heading"] += 1
            docs_hit[cls]["chunks_under_grade_heading"].add(c["doc_id"])
            if len(ex["grade_heading"]) < 30:
                ex["grade_heading"].append((c["chunk_id"], ct, sp[-90:]))
        if REC_STMT_RE.search(t) and re.search(r"argumentaire|rationnel", last, re.I):
            cnt[cls]["stmt_chunk_under_argumentaire_heading"] += 1
            docs_hit[cls]["stmt_chunk_under_argumentaire_heading"].add(c["doc_id"])
            if len(ex["stmt_under_arg"]) < 30:
                ex["stmt_under_arg"].append((c["chunk_id"], sp[-80:]))
        if ct in ("prose", "callout_footnote") and RECO_VERB_RE.search(t) and GRADE_ANY.search(t) and not REC_ID_RE.search(t):
            cnt[cls]["prose_with_reco_formula_and_grade_not_box"] += 1
            docs_hit[cls]["prose_with_reco_formula_and_grade_not_box"].add(c["doc_id"])
        if ct in ("prose", "callout_footnote", "recommendation_box"):
            for m in REC_STMT_RE.finditer(t):
                if not REC_ID_RE.fullmatch(m.group(1)):
                    cnt[cls]["stmt_id_uncaptured"] += 1
                    docs_hit[cls]["stmt_id_uncaptured"].add(c["doc_id"])
        if ct in ("prose", "recommendation_box") and GRADE_ANY.search(t) and not GRADE_CAPTURED.search(t) and (RECO_VERB_RE.search(t) or REC_STMT_RE.search(t)):
            cnt[cls]["stmt_like_chunk_grade_uncaptured"] += 1
            docs_hit[cls]["stmt_like_chunk_grade_uncaptured"].add(c["doc_id"])
            if len(ex["grade_uncaptured"]) < 30:
                m = GRADE_ANY.search(t)
                ex["grade_uncaptured"].append((c["chunk_id"], m.group(0)))
        if ct == "table_row_card" and REC_ID_RE.search(t):
            cnt[cls]["row_cards_holding_reco_id"] += 1
            docs_hit[cls]["row_cards_holding_reco_id"].add(c["doc_id"])
    out = {}
    for cls in sorted(cnt.keys() | lens.keys()):
        L = lens[cls]
        out[cls] = {
            **dict(cnt[cls]),
            **{f"docs:{k}": len(v) for k, v in docs_hit[cls].items()},
            "len_p10": sorted(L)[len(L) // 10] if L else 0,
            "len_median": statistics.median(L) if L else 0,
            "len_p90": sorted(L)[9 * len(L) // 10] if L else 0,
            "lt100": sum(1 for x in L if x < 100),
            "gt2000": sum(1 for x in L if x > 2000),
            "n": len(L),
        }
    (OUT / "extra_counters.json").write_text(json.dumps({"by_class": out, "examples": ex}, ensure_ascii=False, indent=1))
    for k, v in out.items():
        print(k, v)
    for k, v in ex.items():
        print(k, v[:6])


if __name__ == "__main__":
    main()
