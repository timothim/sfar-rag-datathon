"""Normalized evaluation datasets, dev/test splits and the test lockbox.

Format spec: eval/README.md. CLI:
    python -m rag_sfar.evaluation.datasets import --input F --suite S --provenance P [--map k=v ...]
    python -m rag_sfar.evaluation.datasets convert-abp
    python -m rag_sfar.evaluation.datasets convert-enriched [--index index/table_aware_sota]
    python -m rag_sfar.evaluation.datasets split --suite S [--test-fraction 0.4] [--holdout-doc-fraction 0.2]
    python -m rag_sfar.evaluation.datasets lockbox
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

EVAL_DIR = Path("eval")
DATASETS_DIR = EVAL_DIR / "datasets"
SPLITS_DIR = EVAL_DIR / "splits"
LOCKBOX_PATH = EVAL_DIR / "LOCKBOX.md"
INTERNAL_DIR = Path("eval_internal")

QuestionType = Literal["open", "mcq", "clinical_case", "comparison", "table", "abstention"]
Provenance = Literal["physician_validated", "external_benchmark", "llm_synthetic", "team_written"]


class GoldPassage(BaseModel):
    doc_id: str
    quote: str


class EvidencePassage(BaseModel):
    """A reference passage of an expert benchmark, independent of chunking.

    `fragments` are normalized quotes (layout columns re-joined, table headers removed, one per
    table row, >= 6 words) matched against chunks with `harness.passage_match`; an evidence is
    covered when one of its fragments is. When the annotation names the table row
    (`table_coordinates.row`), only the rows that carry that label are kept in `fragments`; the
    other rows of the same layout fragment go to `other_fragments` (context, no credit)."""

    evidence_id: str
    doc_id: str
    page: int | None = None
    fragments: list[str] = Field(default_factory=list)
    other_fragments: list[str] = Field(default_factory=list)  # neighbouring rows, not used for credit
    role: str = ""
    verification_status: str = ""


class EvidenceSet(BaseModel):
    """Evidence that is jointly sufficient (AND inside a set, OR between sets)."""

    set_id: str
    required_evidence_ids: list[str] = Field(default_factory=list)


class EvalItem(BaseModel):
    id: str
    suite: str
    question: str
    question_type: QuestionType
    provenance: Provenance
    choices: dict[str, str] = Field(default_factory=dict)
    reference_answer: str = ""
    answer_key: dict[str, Any] = Field(default_factory=dict)
    should_abstain: bool = False
    gold_doc_ids: list[str] = Field(default_factory=list)
    gold_passages: list[GoldPassage] = Field(default_factory=list)
    current_edition_required: bool = True
    source_doc_ids: list[str] = Field(default_factory=list)
    group: str = ""
    tags: list[str] = Field(default_factory=list)
    meta: dict[str, Any] = Field(default_factory=dict)
    # Optional fields of structured expert benchmarks (benchmark-enrichi). Absent from older
    # files; `write_jsonl` omits them when empty so older suites are rewritten byte-identically.
    mandatory_claims: list[dict[str, Any]] = Field(default_factory=list)  # {claim_id, text, criticality, evidence_ids}
    forbidden_claims: list[dict[str, Any]] = Field(default_factory=list)  # {claim_id, text, severity}
    expected_behavior: str = ""  # answer | clarification | abstention ("" = unspecified)
    acceptable_alternatives: list[dict[str, Any]] = Field(default_factory=list)
    required_missing_information: list[str] = Field(default_factory=list)
    evidence: list[EvidencePassage] = Field(default_factory=list)
    evidence_sets: list[EvidenceSet] = Field(default_factory=list)

    def formatted_query(self) -> str:
        if not self.choices:
            return self.question
        return self.question + "\n" + "\n".join(f"{k}. {v}" for k, v in self.choices.items())


# ---------------------------------------------------------------- IO


def read_jsonl(path: Path) -> list[EvalItem]:
    items = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(EvalItem.model_validate_json(line))
    return items


OPTIONAL_STRUCTURED_FIELDS = (
    "mandatory_claims", "forbidden_claims", "expected_behavior", "acceptable_alternatives",
    "required_missing_information", "evidence", "evidence_sets",
)


def _dump(it: EvalItem) -> dict[str, Any]:
    d = it.model_dump()
    for k in OPTIONAL_STRUCTURED_FIELDS:
        if not d.get(k):
            d.pop(k, None)
    return d


def write_jsonl(items: Iterable[EvalItem], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(_dump(it), ensure_ascii=False, sort_keys=True) + "\n")


def suite_dataset_path(suite: str) -> Path:
    for base in (DATASETS_DIR, INTERNAL_DIR / "datasets"):
        p = base / f"{suite}.jsonl"
        if p.exists():
            return p
    return DATASETS_DIR / f"{suite}.jsonl"


def split_path(suite: str, split: str) -> Path:
    base = SPLITS_DIR if (DATASETS_DIR / f"{suite}.jsonl").exists() else INTERNAL_DIR / "splits"
    return base / suite / f"{split}.jsonl"


# Suites held out from tuning: run by name only, on frozen configurations (each run logged in
# JOURNAL.md). They are never part of `--suite full`.
HELD_OUT_SUITES = ("genprobe",)


def available_suites(include_held_out: bool = False) -> list[str]:
    names = set()
    for base in (SPLITS_DIR, INTERNAL_DIR / "splits"):
        if base.exists():
            names |= {p.name for p in base.iterdir() if p.is_dir()}
    if not include_held_out:
        names -= set(HELD_OUT_SUITES)
    return sorted(names)


def load_suite(suite: str, split: Literal["dev", "test", "all"]) -> list[EvalItem]:
    """Load a split. `suite="full"` concatenates every suite that has splits."""
    if split == "test":
        verify_lockbox(raise_on_error=True)
    suites = available_suites() if suite == "full" else [suite]
    out: list[EvalItem] = []
    for s in suites:
        parts = ["dev", "test"] if split == "all" else [split]
        for part in parts:
            p = split_path(s, part)
            if not p.exists():
                raise FileNotFoundError(f"Missing split {p}; run `datasets split --suite {s}` first.")
            out.extend(read_jsonl(p))
    return out


# ---------------------------------------------------------------- text helpers


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t).strip()


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def _stable_hash(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


# ---------------------------------------------------------------- import / convert


def import_file(input_path: Path, suite: str, provenance: str, mapping: dict[str, str]) -> list[EvalItem]:
    """Import an external benchmark (JSON list, {"questions": [...]}, JSONL or CSV)."""
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        with input_path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    elif suffix == ".jsonl":
        rows = [json.loads(l) for l in input_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    else:
        data = json.loads(input_path.read_text(encoding="utf-8"))
        rows = data.get("questions", data) if isinstance(data, dict) else data
    items = []
    for i, row in enumerate(rows):
        rec: dict[str, Any] = {}
        for field in EvalItem.model_fields:
            src = mapping.get(field, field)
            if src in row and row[src] not in (None, ""):
                rec[field] = row[src]
        for list_field in ("gold_doc_ids", "source_doc_ids", "tags"):
            if isinstance(rec.get(list_field), str):
                rec[list_field] = [x.strip() for x in re.split(r"[;|]", rec[list_field]) if x.strip()]
        for json_field in ("choices", "answer_key", "gold_passages", "meta"):
            if isinstance(rec.get(json_field), str):
                rec[json_field] = json.loads(rec[json_field])
        rec.setdefault("id", f"{suite}-{i + 1:04d}")
        rec["id"] = str(rec["id"])
        rec["suite"] = suite
        rec["provenance"] = provenance
        rec.setdefault("question_type", "mcq" if rec.get("choices") else "open")
        if rec["question_type"] == "mcq" and "answer_key" not in rec and rec.get("reference_answer"):
            letter = str(rec["reference_answer"]).strip().upper()[:1]
            rec["answer_key"] = {"mcq": letter}
        items.append(EvalItem.model_validate(rec))
    return items


ABP_BENCHMARK = Path("data/antibioprophylaxie_benchmark/datasets/sfar_antibioprophylaxie/benchmark.json")


def convert_abp_benchmark(path: Path = ABP_BENCHMARK, gold_doc_ids: list[str] | None = None) -> list[EvalItem]:
    """Convert the official 171-question antibioprophylaxis benchmark to the common format.

    The deterministic key reproduces the benchmark's own scorers (all molecules present for open
    questions, letter for MCQ). Gold documents are given by the caller (the current edition)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = []
    for q in data["questions"]:
        ans = q.get("réponse", "").strip()
        qtype = "mcq" if q.get("type") == "mcq" else "open"
        tags = []
        if "allerg" in fold(q["question"] + " " + q.get("titre", "")):
            tags.append("allergy")
        if re.search(r"\b(enfant|pediatr|nourrisson|neonat)", fold(q["question"])):
            tags.append("pediatric")
        if qtype == "mcq":
            key = {"mcq": ans.upper()}
        elif fold(ans) in ("pas d'antibioprophylaxie", "hors perimetre"):
            key = {"label": fold(ans)}
            tags.append("no_abp" if "pas" in fold(ans) else "out_of_scope")
        else:
            key = {"all_of": [p.strip() for p in re.split(r"[+/]", ans) if p.strip()]}
        items.append(
            EvalItem(
                id=q["id"],
                suite="abp171",
                question=q["question"],
                question_type=qtype,
                provenance="external_benchmark",
                choices=q.get("choices") or {},
                reference_answer=ans,
                answer_key=key,
                should_abstain=fold(ans) == "hors perimetre",
                gold_doc_ids=list(gold_doc_ids or []),
                tags=tags,
                meta={"titre": q.get("titre", ""), "source": data.get("source", ""), "benchmark_version": data.get("version", "")},
            )
        )
    return items


# ---------------------------------------------------------------- structured expert benchmark (benchmark-enrichi)

ENRICHED_BENCHMARK = Path(
    "data/benchmark_enrichi_alparagsfar/benchmark_enrichi_phase1/questions_enriched_draft.jsonl"
)
DEFAULT_INDEX = Path("index/table_aware_sota")
MIN_FRAGMENT_WORDS = 6
# Separates the table columns of a normalized fragment; `harness.passage_match` builds word
# n-grams inside each column only (no n-gram straddles two cells), see its docstring.
COLUMN_SEP = " ‖ "

# Column headers of the SFAR RFE tables ("Actes chirurgicaux ou interventionnels | Molécules |
# Dose initiale | Réinjections et durée | Force de la recommandation", sometimes "Nomenclature").
# A layout segment made only of these words is a repeated table header, not evidence.
_TABLE_HEADER_WORDS = {
    "actes", "chirurgicaux", "ou", "interventionnels", "nomenclature", "molecules", "dose", "initiale",
    "reinjections", "et", "duree", "force", "de", "la", "recommandation",
}
# Words of the regimen / grading cells, shared by most rows. A row whose remaining words are fewer
# than MIN_SPECIFIC_WORDS ("PAS D'ANTIBIOPROPHYLAXIE (Avis d'experts)", "Céfazoline 2g IVL ...")
# would match many chunks and credit the wrong row: it is kept as context only.
_CELL_BOILERPLATE = {
    "pas", "d", "antibioprophylaxie", "avis", "experts", "grade", "dose", "unique", "ivl", "ivd", "g", "mg", "kg",
    "si", "duree", "h", "puis", "toutes", "les", "jusqu", "a", "fin", "de", "chirurgie", "alternative", "au", "choix",
    "ou", "et", "la", "le", "l", "en", "per", "os", "min", "max", "maximum", "reinjection", "reinjections",
}
MIN_SPECIFIC_WORDS = 3
_BULLET_RE = re.compile(r"^(?:[§▪■•○◦\-]|o(?= ))\s*")  # list markers, absent or different in chunks
_SEGMENT_RE = re.compile(r"\S+(?: \S+)*")  # runs separated by >= 2 spaces = layout columns


def _layout_segments(line: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(0)) for m in _SEGMENT_RE.finditer(line)]


def _is_header_segment(seg: str) -> bool:
    toks = tokens(seg)
    return bool(toks) and all(t in _TABLE_HEADER_WORDS for t in toks)


def _is_heading(text: str) -> bool:
    """All-caps section titles ("CHIRURGIE HEPATO-BILIAIRE ...") locate a passage but carry no
    clinical content; chunk texts keep them in `section_path`, not in the text."""
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.8


def is_content_token(t: str) -> bool:
    """False for regimen/grading vocabulary and quantities ("2g", "4h", "30", "mg")."""
    return t not in _CELL_BOILERPLATE and not re.fullmatch(r"\d+[a-z]{0,2}", t)


def _is_specific(text: str) -> bool:
    return sum(1 for t in tokens(text) if is_content_token(t)) >= MIN_SPECIFIC_WORDS


def normalize_layout_fragment(text: str, col_tol: int = 4) -> list[str]:
    """Turn one `pdftotext -layout` fragment into chunking-independent quotes.

    The layout text interleaves table columns line by line ("§ Prothèse de hanche ... Céfazoline
    2g IVL ..."), which no chunk reproduces. Generic, structure-based steps:
    1. split lines into column segments (runs separated by >= 2 spaces) and drop segments made
       only of table-header words;
    2. split into table rows: a blank line, a line starting with the RFE bullet "§" or a
       first-column line starting with a capital (sub-category label) opens a row; list markers
       ("§", "o", "▪") are removed;
    3. inside a row, cluster segments by start column (±`col_tol`) and read column by column,
       columns separated by COLUMN_SEP;
    4. drop all-caps headings and rows with < MIN_FRAGMENT_WORDS words or < MIN_SPECIFIC_WORDS
       words outside the regimen/grading vocabulary (they would match many rows); when no row is
       left, the whole fragment is kept as one quote if it passes the same test.
    """
    blocks: list[list[list[tuple[int, str]]]] = []
    cur: list[list[tuple[int, str]]] = []
    for line in text.replace("\r", "").split("\n"):
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = []
            continue
        # A row starts with the RFE bullet "§" or, in the first column, with a capital letter
        # (sub-category label); lower-case or "(" lines in the first column continue the act.
        if re.match(r"^\s{0,3}(?:§|[A-ZÀ-Ý])", line) and cur:
            blocks.append(cur)
            cur = []
        segs = [(st, _BULLET_RE.sub("", sg)) for st, sg in _layout_segments(line) if not _is_header_segment(sg)]
        segs = [(st, sg) for st, sg in segs if sg]
        if segs:
            cur.append(segs)
    if cur:
        blocks.append(cur)
    quotes: list[str] = []
    for block in blocks:
        cols: list[list[Any]] = []  # [first_start, last_start, [segments]]
        for segs in block:
            for st, sg in segs:
                col = next((c for c in cols if abs(c[1] - st) <= col_tol or 0 <= st - c[0] <= col_tol), None)
                if col is None:
                    col = [st, st, []]
                    cols.append(col)
                col[1] = st
                col[2].append(sg)
        cols.sort(key=lambda c: c[0])
        quote = COLUMN_SEP.join(" ".join(c[2]) for c in cols).strip()
        if quote and not _is_heading(quote):
            quotes.append(quote)
    strong = [q for q in quotes if not _is_weak(q)]
    if strong:
        return strong
    # Only short rows (a shared "PAS D'ANTIBIOPROPHYLAXIE" cell followed by bare act bullets):
    # the fragment is kept whole.
    whole = COLUMN_SEP.join(quotes)
    return [whole] if not _is_weak(whole) else []


def _is_weak(text: str) -> bool:
    return len(tokens(text)) < MIN_FRAGMENT_WORDS or not _is_specific(text)


def select_row_fragments(units: list[str], row_label: str, min_overlap: float = 0.6) -> tuple[list[str], list[str]]:
    """Keep the table rows that carry the annotated row label (>= `min_overlap` of its words).

    Layout fragments often span several rows; crediting any of them would reward a neighbouring
    row. Without a label, or when no row carries it (free-text labels), every row is kept."""
    label = set(tokens(row_label))
    if len(label) < 1 or len(units) <= 1:
        return list(units), []
    key = [u for u in units if len(label & set(tokens(u))) / len(label) >= min_overlap]
    if not key:
        return list(units), []
    return key, [u for u in units if u not in key]


def current_edition_doc_ids(index_dir: Path = DEFAULT_INDEX, topic_lineage: str = "antibioprophylaxie") -> list[str]:
    """`doc_id`s of the edition in force for a recommendation lineage, read from an index."""
    import sqlite3

    db = index_dir / "metadata.sqlite"
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT doc_id FROM documents WHERE topic_lineage = ? AND is_latest_edition = 1 ORDER BY doc_id",
            (topic_lineage,),
        ).fetchall()
    finally:
        con.close()
    return [r[0] for r in rows]


_EXPECTED_BEHAVIOR = {
    "answer_with_evidence": "answer",
    "conditional_answer": "answer",
    "ask_clarification": "clarification",
    "abstain": "abstention",
    "abstention": "abstention",
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", fold(text)).strip("_")


def convert_enriched_benchmark(
    path: Path = ENRICHED_BENCHMARK,
    gold_doc_ids: list[str] | None = None,
    index_dir: Path = DEFAULT_INDEX,
    suite: str = "abpe171",
) -> list[EvalItem]:
    """Convert the benchmark-enrichi consolidated JSONL (phase 1, V3.1 provisional reference).

    - question / choices: `proposed` (the text given to the system), id = legacy id (Q01...).
    - evidence: `evidence_current` (V3.1), fragments normalized by `normalize_layout_fragment`;
      `gold_passages` = one passage per useful fragment; `evidence_sets` kept as is.
    - gold_doc_ids: current edition of the antibioprophylaxis RFE in the index (or given).
    - answer_key: MCQ letter only when `mcq_option_status == "single_supported"`; nothing else
      (open answers are scored on claims by the judge).
    - expected_behavior: answer | clarification | abstention; should_abstain only for abstention.
    """
    if gold_doc_ids is None:
        gold_doc_ids = current_edition_doc_ids(index_dir)
    gold = list(gold_doc_ids)
    gold_doc = gold[0] if gold else ""
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        prop = r.get("proposed") or {}
        ref = r.get("reference_answer") or {}
        cls = r.get("classification") or {}
        fmt = prop.get("format") or r.get("legacy_format") or "open"
        behavior = _EXPECTED_BEHAVIOR.get(prop.get("expected_behavior") or "", prop.get("expected_behavior") or "")
        answerability = prop.get("answerability") or ""
        should_abstain = behavior == "abstention" or answerability in ("unanswerable", "out_of_scope")
        qtype = "mcq" if fmt == "mcq" else ("abstention" if should_abstain else "open")

        key: dict[str, Any] = {}
        if fmt == "mcq" and prop.get("mcq_option_status") == "single_supported" and isinstance(prop.get("mcq_correct_option"), str):
            key = {"mcq": prop["mcq_correct_option"].strip().upper()}

        evidence: list[EvidencePassage] = []
        passages: list[GoldPassage] = []
        for e in r.get("evidence_current") or []:
            units: list[str] = []
            for f in e.get("exact_fragments") or []:
                for q in normalize_layout_fragment(f.get("text", "")):
                    if q not in units:
                        units.append(q)
            frags, others = select_row_fragments(units, ((e.get("table_coordinates") or {}).get("row") or ""))
            evidence.append(EvidencePassage(
                evidence_id=e["evidence_id"], doc_id=gold_doc or e.get("doc_id", ""), page=e.get("pdf_page"),
                fragments=frags, other_fragments=others, role=e.get("evidence_role") or "",
                verification_status=e.get("verification_status") or "",
            ))
            for q in frags:
                if all(gp.quote != q for gp in passages):
                    passages.append(GoldPassage(doc_id=gold_doc, quote=q))
        sets = [EvidenceSet(set_id=s.get("set_id", f"S{i + 1}"), required_evidence_ids=list(s.get("required_evidence_ids") or []))
                for i, s in enumerate(r.get("evidence_sets") or [])]

        mandatory = [{"claim_id": c.get("claim_id") or f"{r['legacy_id']}-C{i + 1}", "text": c.get("text_fr", ""),
                      "criticality": c.get("criticality", ""), "evidence_ids": list(c.get("evidence_ids") or [])}
                     for i, c in enumerate(ref.get("mandatory_claims") or [])]
        forbidden = [{"claim_id": c.get("claim_id") or f"{r['legacy_id']}-F{i + 1}", "text": c.get("text_fr", ""),
                      "severity": c.get("severity", "")}
                     for i, c in enumerate(ref.get("forbidden_claims") or [])]
        missing = [m if isinstance(m, str) else (m.get("text_fr") or m.get("variable") or json.dumps(m, ensure_ascii=False))
                   for m in ref.get("required_missing_information") or []]

        tags = []
        if cls.get("primary_category"):
            tags.append(f"cat:{cls['primary_category']}")
        if cls.get("difficulty"):
            tags.append(f"difficulty:{cls['difficulty']}")
        if cls.get("adult_or_pediatric"):
            tags.append(f"population:{cls['adult_or_pediatric']}")
        if cls.get("adult_or_pediatric") in ("pediatric", "adult_and_pediatric"):
            tags.append("pediatric")
        tags += [f"challenge:{c}" for c in cls.get("retrieval_challenges") or []]
        tags += [f"special:{_slug(p)}" for p in cls.get("special_population") or []]
        if behavior and behavior != "answer":
            tags.append(f"behavior:{behavior}")
        if fmt == "mcq" and not key:
            tags.append(f"mcq:{prop.get('mcq_option_status') or 'no_key'}")

        items.append(EvalItem(
            id=r["legacy_id"],
            suite=suite,
            question=prop.get("question") or (r.get("legacy") or {}).get("question", ""),
            question_type=qtype,
            provenance="physician_validated" if (r.get("review") or {}).get("decision") == "approved" else "external_benchmark",
            choices=prop.get("choices") or {},
            reference_answer=ref.get("short_answer") or ref.get("narrative_fr") or "",
            answer_key=key,
            should_abstain=should_abstain,
            gold_doc_ids=gold,
            gold_passages=passages,
            current_edition_required=True,
            source_doc_ids=gold,
            tags=tags,
            mandatory_claims=mandatory,
            forbidden_claims=forbidden,
            expected_behavior=behavior,
            acceptable_alternatives=list(ref.get("acceptable_alternatives") or []),
            required_missing_information=missing,
            evidence=evidence,
            evidence_sets=sets,
            meta={
                "question_id": r.get("question_id"),
                "legacy_id": r.get("legacy_id"),
                "narrative": ref.get("narrative_fr", ""),
                "answerability": answerability,
                "expected_behavior_raw": prop.get("expected_behavior"),
                "mcq_option_status": prop.get("mcq_option_status"),
                "mcq_correct_option": prop.get("mcq_correct_option"),
                "question_edit_status": prop.get("question_edit_status"),
                "primary_category": cls.get("primary_category"),
                "secondary_categories": cls.get("secondary_categories") or [],
                "template_family": cls.get("template_family"),
                "reference_version": r.get("current_reference_version"),
                "review_decision": (r.get("review") or {}).get("decision"),
                "citation_verified": (r.get("review") or {}).get("citation_verified"),
                "source": "benchmark_enrichi_phase1/questions_enriched_draft.jsonl",
            },
        ))
    return items


def split_like(items: list[EvalItem], reference_suite: str) -> tuple[list[EvalItem], list[EvalItem]]:
    """Reuse another suite's dev/test assignment by id (same legacy identifiers).

    Reads the reference test file only for its ids (no evaluation)."""
    def ids(part: str) -> set[str]:
        p = split_path(reference_suite, part)
        return {json.loads(l)["id"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip()}

    dev_ids, test_ids = ids("dev"), ids("test")
    unknown = [it.id for it in items if it.id not in dev_ids | test_ids]
    if unknown or dev_ids & test_ids:
        raise ValueError(f"cannot reuse split of {reference_suite}: unknown ids {unknown[:5]}, overlap {sorted(dev_ids & test_ids)[:5]}")
    return [it for it in items if it.id in dev_ids], [it for it in items if it.id in test_ids]


def mapping_coverage(items: list[EvalItem], index_dir: Path = DEFAULT_INDEX, doc_ids: list[str] | None = None) -> dict[str, Any]:
    """Share of gold passages / evidence / sufficient sets that `passage_match` finds in at least
    one chunk of an index (restricted to `doc_ids`, default: each item's gold documents).

    This is the ceiling of the passage-level retrieval metrics for that index; the unmatched
    fragments point at ingestion defects (OCR, split tables, missing headings)."""
    import sqlite3

    from rag_sfar.evaluation.harness import passage_match

    wanted = set(doc_ids or {d for it in items for d in it.gold_doc_ids})
    con = sqlite3.connect(index_dir / "metadata.sqlite")
    try:
        texts = [json.loads(p)["text"] for (d, p) in con.execute("SELECT doc_id, payload_json FROM chunks") if d in wanted]
    finally:
        con.close()
    cache: dict[str, bool] = {}

    def found(q: str) -> bool:
        if q not in cache:
            cache[q] = any(passage_match(q, t) for t in texts)
        return cache[q]

    n_pass = n_pass_ok = n_ev = n_ev_ok = n_ev_empty = n_sets_items = n_suff = 0
    unmatched: list[dict[str, Any]] = []
    per_item: dict[str, dict[str, Any]] = {}
    for it in items:
        for gp in it.gold_passages:
            n_pass += 1
            n_pass_ok += found(gp.quote)
        ev_ok = {}
        for e in it.evidence:
            n_ev += 1
            if not e.fragments:
                n_ev_empty += 1
                ev_ok[e.evidence_id] = False
                unmatched.append({"id": it.id, "evidence_id": e.evidence_id, "page": e.page, "fragment": None})
                continue
            ok = any(found(q) for q in e.fragments)
            ev_ok[e.evidence_id] = ok
            n_ev_ok += ok
            for q in e.fragments:
                if not found(q):
                    unmatched.append({"id": it.id, "evidence_id": e.evidence_id, "page": e.page, "fragment": q})
        if it.evidence_sets:
            n_sets_items += 1
            suff = any(all(ev_ok.get(i, False) for i in s.required_evidence_ids) for s in it.evidence_sets)
            n_suff += suff
            per_item[it.id] = {"sufficient_mappable": suff,
                               "missing": sorted({i for s in it.evidence_sets for i in s.required_evidence_ids if not ev_ok.get(i)})}
    return {
        "n_items": len(items), "n_chunks": len(texts),
        "gold_passages": n_pass, "gold_passages_found": n_pass_ok,
        "evidence": n_ev, "evidence_found": n_ev_ok, "evidence_without_useful_fragment": n_ev_empty,
        "items_with_sets": n_sets_items, "items_sufficiency_mappable": n_suff,
        "unmatched": unmatched, "per_item": per_item,
    }


# ---------------------------------------------------------------- split


def _near_duplicate_groups(items: list[EvalItem], threshold: float = 0.6) -> dict[str, str]:
    """Union-find over question token Jaccard similarity; explicit `group` fields are kept."""
    parent = {it.id: (it.group or it.id) for it in items}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent[x], parent[x])
            x = parent[x]
        return x

    for it in items:
        parent.setdefault(it.group or it.id, it.group or it.id)
    # Ignore template words shared by many questions ("quelle est la recommandation ...").
    raw = {it.id: set(tokens(it.formatted_query())) for it in items}
    df: dict[str, int] = defaultdict(int)
    for ts in raw.values():
        for t in ts:
            df[t] += 1
    max_df = max(2, int(0.15 * len(items)))
    toks = {k: {t for t in ts if df[t] <= max_df} for k, ts in raw.items()}
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            ta, tb = toks[a.id], toks[b.id]
            if ta and tb and len(ta & tb) / len(ta | tb) >= threshold:
                ra, rb = find(a.id), find(b.id)
                if ra != rb:
                    parent[rb] = ra
    return {it.id: find(it.id) for it in items}


def make_split(
    items: list[EvalItem],
    test_fraction: float = 0.4,
    holdout_doc_fraction: float = 0.0,
    seed: str = "sfar-2026",
    strata_fn=None,
) -> tuple[list[EvalItem], list[EvalItem], dict[str, Any]]:
    """Deterministic stratified split.

    1. If `holdout_doc_fraction` > 0, a fraction of source documents is held out entirely:
       every question citing one of them goes to test (tag `unseen_doc`).
    2. Remaining questions are grouped (near-duplicates together) and, within each stratum
       (question_type + first source doc + answer class), groups are assigned to test in a
       seeded order until the stratum reaches `test_fraction`.
    """
    strata_fn = strata_fn or (
        lambda it: (
            it.question_type,
            (it.source_doc_ids or ["-"])[0],
            next(iter(it.answer_key), "-"),
            "allergy" in it.tags,
        )
    )
    info: dict[str, Any] = {"seed": seed, "test_fraction": test_fraction}

    held_docs: set[str] = set()
    if holdout_doc_fraction > 0:
        docs = sorted({d for it in items for d in it.source_doc_ids})
        docs.sort(key=lambda d: _stable_hash(seed, "doc", d))
        held_docs = set(docs[: max(1, round(len(docs) * holdout_doc_fraction))])
        info["holdout_docs"] = sorted(held_docs)

    test_ids: set[str] = set()
    for it in items:
        if held_docs & set(it.source_doc_ids):
            test_ids.add(it.id)

    rest = [it for it in items if it.id not in test_ids]
    groups = _near_duplicate_groups(rest)
    by_group: dict[str, list[EvalItem]] = defaultdict(list)
    for it in rest:
        by_group[groups[it.id]].append(it)

    strata: dict[tuple, list[str]] = defaultdict(list)
    for g, members in by_group.items():
        strata[strata_fn(members[0])].append(g)
    for key, gs in sorted(strata.items(), key=lambda kv: str(kv[0])):
        gs.sort(key=lambda g: _stable_hash(seed, g))
        total = sum(len(by_group[g]) for g in gs)
        target = test_fraction * total
        taken = 0
        for g in gs:
            if taken + len(by_group[g]) / 2 > target:
                break
            for it in by_group[g]:
                test_ids.add(it.id)
            taken += len(by_group[g])

    dev = [it for it in items if it.id not in test_ids]
    test = []
    for it in items:
        if it.id in test_ids:
            if held_docs & set(it.source_doc_ids) and "unseen_doc" not in it.tags:
                it = it.model_copy(update={"tags": it.tags + ["unseen_doc"]})
            test.append(it)
    info.update(
        n_dev=len(dev),
        n_test=len(test),
        n_groups=len(by_group),
        n_multi_member_groups=sum(1 for m in by_group.values() if len(m) > 1),
    )
    return dev, test, info


# ---------------------------------------------------------------- lockbox


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _all_test_files() -> list[Path]:
    files = []
    for base in (SPLITS_DIR, INTERNAL_DIR / "splits"):
        if base.exists():
            files += sorted(base.glob("*/test.jsonl"))
    return files


def write_lockbox(note: str = "") -> str:
    lines = [
        "# LOCKBOX — empreintes des jeux de test",
        "",
        "Ces fichiers ne doivent pas être modifiés après leur mise sous coffre-fort, ni évalués pendant la mise au point.",
        "Vérification automatique : `pytest tests/test_lockbox.py`. Toute modification exige l'accord de l'utilisateur",
        "et une nouvelle entrée datée ci-dessous expliquant pourquoi.",
        "",
        "| Fichier | Questions | SHA-256 |",
        "|---|---:|---|",
    ]
    for p in _all_test_files():
        n = sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
        lines.append(f"| `{p.as_posix()}` | {n} | `{sha256_file(p)}` |")
    history = ""
    if LOCKBOX_PATH.exists():
        prev = LOCKBOX_PATH.read_text(encoding="utf-8")
        if "## Historique" in prev:
            history = prev.split("## Historique", 1)[1].strip()
    if note:
        history = (history + "\n" + note).strip()
    if history:
        lines += ["", "## Historique", "", history]
    text = "\n".join(lines) + "\n"
    LOCKBOX_PATH.write_text(text, encoding="utf-8")
    return text


def read_lockbox() -> dict[str, str]:
    if not LOCKBOX_PATH.exists():
        return {}
    out = {}
    for m in re.finditer(r"\| `([^`]+)` \| \d+ \| `([0-9a-f]{64})` \|", LOCKBOX_PATH.read_text(encoding="utf-8")):
        out[m.group(1)] = m.group(2)
    return out


# Suites whose files are git-ignored (third-party benchmark, redistribution rights unconfirmed).
LOCAL_ONLY_SUITES = ("abpe171",)


def verify_lockbox(raise_on_error: bool = False) -> list[str]:
    """Return a list of problems (missing, modified or unregistered test files)."""
    registered = read_lockbox()
    problems = []
    for rel, digest in registered.items():
        p = Path(rel)
        if not p.exists():
            # Suites built from third-party data that we do not redistribute are regenerated
            # locally; their hash is still registered so a regenerated file is checked.
            if any(f"/{s}/" in f"/{rel}" for s in LOCAL_ONLY_SUITES):
                continue
            problems.append(f"missing: {rel}")
        elif sha256_file(p) != digest:
            problems.append(f"modified: {rel}")
    for p in _all_test_files():
        if p.as_posix() not in registered:
            problems.append(f"unregistered: {p.as_posix()}")
    if problems and raise_on_error:
        raise RuntimeError("Lockbox check failed: " + "; ".join(problems))
    return problems


# ---------------------------------------------------------------- CLI


def _cli() -> None:
    ap = argparse.ArgumentParser(description="RAG-SFAR evaluation datasets")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_imp = sub.add_parser("import")
    p_imp.add_argument("--input", type=Path, required=True)
    p_imp.add_argument("--suite", required=True)
    p_imp.add_argument("--provenance", required=True, choices=list(Provenance.__args__))
    p_imp.add_argument("--map", nargs="*", default=[], help="field=source_column pairs")
    p_imp.add_argument("--out-dir", type=Path, default=DATASETS_DIR)

    p_abp = sub.add_parser("convert-abp")
    p_abp.add_argument("--gold-doc-id", action="append", default=[])

    p_enr = sub.add_parser("convert-enriched", help="benchmark-enrichi JSONL -> eval/datasets/abpe171.jsonl + split reused from abp171")
    p_enr.add_argument("--input", type=Path, default=ENRICHED_BENCHMARK)
    p_enr.add_argument("--suite", default="abpe171")
    p_enr.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="index whose metadata gives the current-edition doc_ids")
    p_enr.add_argument("--gold-doc-id", action="append", default=[])
    p_enr.add_argument("--split-like", default="abp171", help="suite whose dev/test assignment (by id) is reused; '' to skip")
    p_enr.add_argument("--force", action="store_true", help="Overwrite a locked test split (needs user approval).")

    p_cov = sub.add_parser("coverage", help="share of gold passages/evidence found in an index (dev only by default)")
    p_cov.add_argument("--suite", default="abpe171")
    p_cov.add_argument("--split", default="dev", choices=["dev"])
    p_cov.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    p_cov.add_argument("--out", type=Path, default=None)

    p_split = sub.add_parser("split")
    p_split.add_argument("--suite", required=True)
    p_split.add_argument("--test-fraction", type=float, default=0.4)
    p_split.add_argument("--holdout-doc-fraction", type=float, default=0.0)
    p_split.add_argument("--seed", default="sfar-2026")
    p_split.add_argument("--force", action="store_true", help="Overwrite an existing test split (needs user approval once locked).")

    sub.add_parser("lockbox")
    sub.add_parser("verify")

    args = ap.parse_args()
    if args.cmd == "import":
        mapping = dict(kv.split("=", 1) for kv in args.map)
        items = import_file(args.input, args.suite, args.provenance, mapping)
        out = args.out_dir / f"{args.suite}.jsonl"
        write_jsonl(items, out)
        print(f"{len(items)} questions -> {out}")
    elif args.cmd == "convert-abp":
        items = convert_abp_benchmark(gold_doc_ids=args.gold_doc_id)
        write_jsonl(items, DATASETS_DIR / "abp171.jsonl")
        print(f"{len(items)} questions -> {DATASETS_DIR / 'abp171.jsonl'}")
    elif args.cmd == "convert-enriched":
        items = convert_enriched_benchmark(args.input, args.gold_doc_id or None, args.index, args.suite)
        out = DATASETS_DIR / f"{args.suite}.jsonl"
        write_jsonl(items, out)
        print(f"{len(items)} questions -> {out} (gold docs: {items[0].gold_doc_ids if items else []})")
        if args.split_like:
            test_p = split_path(args.suite, "test")
            if test_p.exists() and test_p.as_posix() in read_lockbox() and not args.force:
                print(f"{test_p} is locked: split files left untouched.")
            else:
                dev, test = split_like(items, args.split_like)
                write_jsonl(dev, split_path(args.suite, "dev"))
                write_jsonl(test, test_p)
                info = {"split_like": args.split_like, "n_dev": len(dev), "n_test": len(test)}
                (test_p.parent / "split_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
                print(json.dumps(info))
    elif args.cmd == "coverage":
        cov = mapping_coverage(read_jsonl(split_path(args.suite, args.split)), args.index)
        brief = {k: v for k, v in cov.items() if k not in ("unmatched", "per_item")}
        print(json.dumps(brief, ensure_ascii=False))
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(cov, ensure_ascii=False, indent=1), encoding="utf-8")
    elif args.cmd == "split":
        src = suite_dataset_path(args.suite)
        items = read_jsonl(src)
        test_p = split_path(args.suite, "test")
        if test_p.exists() and test_p.as_posix() in read_lockbox() and not args.force:
            raise SystemExit(f"{test_p} is locked; re-splitting needs the user's approval (--force).")
        dev, test, info = make_split(items, args.test_fraction, args.holdout_doc_fraction, args.seed)
        write_jsonl(dev, split_path(args.suite, "dev"))
        write_jsonl(test, test_p)
        (test_p.parent / "split_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(info, ensure_ascii=False))
    elif args.cmd == "lockbox":
        print(write_lockbox())
    elif args.cmd == "verify":
        problems = verify_lockbox()
        print("OK" if not problems else "\n".join(problems))
        raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    _cli()
