"""Programmatic checks of the internal probe set `genprobe` (agent E1).

`genprobe` is a small held-out set of synthetic questions (not a benchmark, not medically
validated) that exercises table notes, population contrasts, multiple-choice questions and
two-source questions on guidelines other than antibioprophylaxis. See eval_internal/README.md.

Checks (exit code 1 if any hard check fails):
- every item parses with the common format (`EvalItem`), ids unique, suite = genprobe,
  provenance = llm_synthetic, exactly one family tag;
- every quote (gold_passages and evidence fragments) is found verbatim in the source Markdown of
  its document after HTML-tag stripping, whitespace / case / apostrophe normalisation; a quote
  with " ‖ " is checked cell by cell, and all cells must sit in the same table row (<tr>);
- quotes are 8 to 40 words long;
- every gold / source document is a current edition of index/tas_v3_errata
  (is_latest_edition = 1) and none belongs to the antibioprophylaxis guideline (any edition);
- MCQ: 4 or 5 choices, answer_key.mcq is one of them, question_type = mcq;
- evidence_sets refer to existing evidence ids; evidence documents are gold documents;
- population_unspecified items carry meta.expected_behavior = conditional_or_clarification;
- the question does not copy 8 consecutive words of its quotes nor the document title (warning);
- counts per family, per document, per year, share of table questions.

With --mapping, also reports for each quote whether at least one chunk of the index matches it
with `harness.passage_match` (CPU only, no model), i.e. whether the index's chunking can credit it.

Usage:
    .venv/bin/python eval_internal/build_genprobe_checks.py [--input eval_internal/datasets/genprobe.jsonl] [--mapping] [--json out.json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.evaluation.datasets import EvalItem, tokens  # noqa: E402

INDEX = ROOT / "index" / "tas_v3_errata"
DEFAULT_INPUT = ROOT / "eval_internal" / "datasets" / "genprobe.jsonl"
SEP = "‖"
FAMILIES = ("fam:mcq", "fam:table_note", "fam:population", "fam:two_source")
EXCLUDED_TOPIC = "antibioprophylax"


def norm(text: str) -> str:
    """Lower-case, HTML-unescaped, tags and markdown emphasis removed, apostrophes and spaces unified."""
    # strip real tags first (a literal "<" in the text, e.g. "< 30 ml/min", is not a tag), then unescape
    t = re.sub(r"</?[A-Za-z][^<>]*>", " ", text)
    t = html.unescape(t)
    t = unicodedata.normalize("NFC", t)
    t = t.replace("’", "'").replace("‘", "'").replace("`", "'").replace(" ", " ").replace(" ", " ")
    t = t.replace("**", " ").replace("*", " ").replace("\\", "")
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()


def cells(quote: str) -> list[str]:
    return [c.strip() for c in quote.split(SEP) if c.strip()]


def n_words(quote: str) -> int:
    return len(re.findall(r"\w+", quote.replace(SEP, " ")))


def load_docs() -> dict[str, dict]:
    con = sqlite3.connect(INDEX / "metadata.sqlite")
    try:
        rows = con.execute("SELECT doc_id, title, effective_year, is_latest_edition, topic_lineage, payload_json FROM documents").fetchall()
    finally:
        con.close()
    out = {}
    for doc_id, title, year, latest, lineage, payload in rows:
        p = json.loads(payload)
        out[doc_id] = {"title": title, "year": year, "latest": bool(latest), "lineage": lineage or "", "md_path": p.get("md_path", "")}
    return out


class Source:
    """Normalised Markdown of one document, plus its table rows."""

    def __init__(self, md_path: Path):
        raw = md_path.read_text(encoding="utf-8")
        self.text = norm(raw)
        self.rows = [norm(r) for r in re.split(r"<tr[^>]*>", raw)[1:]]
        self.rows = [r.split("</tr>")[0] if "</tr>" in r else r for r in self.rows]

    def check(self, quote: str) -> tuple[bool, str]:
        if SEP not in quote:
            ok = norm(quote) in self.text
            return ok, "" if ok else "not found verbatim"
        cs = [norm(c) for c in cells(quote)]
        missing = [c for c in cs if c not in self.text]
        if missing:
            return False, f"cells not found: {missing}"
        if any(all(c in r for c in cs) for r in self.rows):
            return True, ""
        # pipe tables or tables broken by OCR: accept cells within a short window, flagged
        positions = [self.text.find(c) for c in cs]
        if max(positions) - min(positions) < 1500:
            return True, "cells found near each other but not in one <tr> row"
        return False, "cells found but not in the same row"


def copied_ngram(question: str, quote: str, n: int = 8) -> str | None:
    q = tokens(question)
    s = " " + " ".join(tokens(quote.replace(SEP, " "))) + " "
    for i in range(len(q) - n + 1):
        g = " ".join(q[i : i + n])
        if f" {g} " in s:
            return g
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    ap.add_argument("--mapping", action="store_true", help="also check that index chunks match each quote (passage_match)")
    ap.add_argument("--json", type=Path, help="write the full report as JSON")
    args = ap.parse_args()

    docs = load_docs()
    sources: dict[str, Source] = {}
    errors: list[str] = []
    warnings: list[str] = []
    raw_lines = [l for l in args.input.read_text(encoding="utf-8").splitlines() if l.strip()]
    items: list[EvalItem] = []
    for i, line in enumerate(raw_lines, 1):
        try:
            items.append(EvalItem.model_validate_json(line))
        except Exception as e:  # noqa: BLE001
            errors.append(f"line {i}: does not parse: {e}")

    ids = Counter(it.id for it in items)
    errors += [f"{k}: duplicate id" for k, v in ids.items() if v > 1]

    quote_report = []
    for it in items:
        tag = f"{it.id}"
        if it.suite != "genprobe":
            errors.append(f"{tag}: suite {it.suite!r}")
        if it.provenance != "llm_synthetic":
            errors.append(f"{tag}: provenance {it.provenance!r}")
        fams = [t for t in it.tags if t in FAMILIES]
        if len(fams) != 1:
            errors.append(f"{tag}: family tags {fams}")
        if it.meta.get("author") != "claude-opus (agent E1)":
            errors.append(f"{tag}: meta.author")
        if not it.reference_answer.strip():
            errors.append(f"{tag}: empty reference_answer")
        all_docs = set(it.gold_doc_ids) | set(it.source_doc_ids) | {gp.doc_id for gp in it.gold_passages} | {e.doc_id for e in it.evidence}
        for d in sorted(all_docs):
            if d not in docs:
                errors.append(f"{tag}: unknown doc_id {d}")
                continue
            m = docs[d]
            if not m["latest"]:
                errors.append(f"{tag}: {d} is not a current edition")
            if EXCLUDED_TOPIC in (m["lineage"] + " " + m["title"] + " " + d).lower():
                errors.append(f"{tag}: {d} is an antibioprophylaxis document")
        for gp in it.gold_passages:
            if gp.doc_id not in it.gold_doc_ids:
                errors.append(f"{tag}: passage doc {gp.doc_id} not in gold_doc_ids")
        if not it.gold_passages:
            errors.append(f"{tag}: no gold passage")
        # MCQ
        if "fam:mcq" in it.tags or it.question_type == "mcq":
            keys = list(it.choices)
            if it.question_type != "mcq":
                errors.append(f"{tag}: mcq family but question_type {it.question_type}")
            if not (4 <= len(keys) <= 5) or keys != [chr(65 + k) for k in range(len(keys))]:
                errors.append(f"{tag}: choices keys {keys}")
            if it.answer_key.get("mcq") not in keys:
                errors.append(f"{tag}: answer_key {it.answer_key}")
        # population
        if "population_unspecified" in it.tags and it.meta.get("expected_behavior") != "conditional_or_clarification":
            errors.append(f"{tag}: population_unspecified without meta.expected_behavior")
        # evidence
        ev_ids = {e.evidence_id for e in it.evidence}
        for s in it.evidence_sets:
            for r in s.required_evidence_ids:
                if r not in ev_ids:
                    errors.append(f"{tag}: evidence set {s.set_id} refers to unknown {r}")
        for e in it.evidence:
            if e.doc_id not in it.gold_doc_ids:
                errors.append(f"{tag}: evidence doc {e.doc_id} not in gold_doc_ids")
        if not it.evidence_sets:
            warnings.append(f"{tag}: no evidence_sets (sufficiency not computed)")
        # quotes
        quotes = [(gp.doc_id, gp.quote, "gold_passage") for gp in it.gold_passages]
        quotes += [(e.doc_id, f, f"evidence:{e.evidence_id}") for e in it.evidence for f in e.fragments]
        for doc_id, q, kind in quotes:
            if doc_id not in docs:
                continue
            if doc_id not in sources:
                sources[doc_id] = Source(ROOT / docs[doc_id]["md_path"])
            ok, why = sources[doc_id].check(q)
            nw = n_words(q)
            if not ok:
                errors.append(f"{tag} [{kind}]: quote {why}: {q[:90]!r}")
            elif why:
                warnings.append(f"{tag} [{kind}]: {why}: {q[:90]!r}")
            if not (8 <= nw <= 40):
                errors.append(f"{tag} [{kind}]: quote has {nw} words (8-40): {q[:60]!r}")
            if kind == "gold_passage":
                quote_report.append({"id": it.id, "doc_id": doc_id, "quote": q, "verbatim": ok, "note": why})
            g = copied_ngram(it.question, q)
            if g:
                warnings.append(f"{tag}: question copies 8 words of a quote: '{g}'")
        for d in it.gold_doc_ids:
            if d in docs and norm(docs[d]["title"]) in norm(it.question):
                warnings.append(f"{tag}: question contains the document title")

    # counts
    fam_count = Counter(next((t for t in it.tags if t in FAMILIES), "?") for it in items)
    doc_count = Counter(d for it in items for d in it.gold_doc_ids)
    titles = Counter(docs[d]["title"] for d in doc_count if d in docs)
    years = Counter(docs[d]["year"] for d in doc_count if d in docs)
    n_table = sum(1 for it in items if "table" in it.tags)
    summary = {
        "n_items": len(items),
        "per_family": dict(fam_count),
        "per_question_type": dict(Counter(it.question_type for it in items)),
        "n_documents": len(doc_count),
        "n_guidelines_by_title": len(titles),
        "per_document": dict(doc_count.most_common()),
        "years": dict(sorted(years.items(), key=lambda kv: (kv[0] is None, kv[0]))),
        "table_questions": n_table,
        "population_unspecified": sum("population_unspecified" in it.tags for it in items),
        "two_documents": sum("two_documents" in it.tags for it in items),
        "two_sections": sum("two_sections" in it.tags for it in items),
        "gold_passages": len(quote_report),
        "gold_passages_verbatim": sum(q["verbatim"] for q in quote_report),
    }

    mapping = None
    if args.mapping:
        from rag_sfar.evaluation.harness import passage_match

        wanted = set(doc_count)
        con = sqlite3.connect(INDEX / "metadata.sqlite")
        try:
            chunks = defaultdict(list)
            for d, p in con.execute("SELECT doc_id, payload_json FROM chunks"):
                if d in wanted:
                    chunks[d].append(json.loads(p)["text"])
        finally:
            con.close()
        unmatched = []
        n_ok = 0
        suff_ok = 0
        n_sets = 0
        for it in items:
            for gp in it.gold_passages:
                ok = any(passage_match(gp.quote, t) for t in chunks[gp.doc_id])
                n_ok += ok
                if not ok:
                    unmatched.append({"id": it.id, "doc_id": gp.doc_id, "quote": gp.quote})
            if it.evidence_sets:
                n_sets += 1
                ev_ok = {e.evidence_id: any(passage_match(f, t) for f in e.fragments for t in chunks[e.doc_id]) for e in it.evidence}
                suff_ok += any(all(ev_ok.get(r) for r in s.required_evidence_ids) for s in it.evidence_sets)
        mapping = {"gold_passages": summary["gold_passages"], "matched": n_ok, "unmatched": unmatched,
                   "items_with_sets": n_sets, "items_sufficiency_mappable": suff_ok}

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if mapping:
        print(f"\nMapping coverage (index {INDEX.name}): {mapping['matched']}/{mapping['gold_passages']} gold passages matched by a chunk; "
              f"sufficiency mappable for {mapping['items_sufficiency_mappable']}/{mapping['items_with_sets']} items")
        for u in mapping["unmatched"]:
            print(f"  UNMATCHED {u['id']} {u['doc_id']}: {u['quote'][:120]!r}")
    for w in warnings:
        print("WARNING", w)
    for e in errors:
        print("ERROR", e)
    print(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "mapping": mapping, "errors": errors, "warnings": warnings,
                                         "quotes": quote_report}, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
