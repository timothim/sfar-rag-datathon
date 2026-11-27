"""Build structural links between chunks of an existing index, offline, into a sidecar folder.

No LLM, no embedding, no similarity search: the links come from the structure the index already
stores (table ids, population labels written by ingestion, the first cell of each table row card,
the reading order of chunks, footnote call marks). The source index is read only.

Two kinds of links:

1. Counterpart links (`counterparts`): a table row card -> the row card(s) of the SAME procedure
   in a table of ANOTHER population (adult / paediatric / neonatal / obstetric) of the same
   document. Rules (strict on purpose: a wrong link puts another procedure's dose in the context):
   - same document, current edition, active;
   - both rows carry a single population class whose label comes from the table or the section
     (`population_source` in {table, section}); a document-level label never separates two tables
     of the same document;
   - different `table_id`, different population class;
   - the label columns have the same header (first segment of the first cell header, normalised),
     i.e. the two tables are parallel;
   - the label of the source row is split into items (";" separates the acts of one cell); every
     item of the source must appear, normalised, among the items of the target (the linked row
     covers every act named by the retrieved row). Labels without an item of >= 6 characters and
     a word of >= 4 letters are not linked;
   - at most `--max-per-population` targets per (source, target population), exact label first,
     then the target with the fewest extra items; when more candidates than that exist the link
     is ambiguous and dropped.
2. Note links (`notes`): a table chunk -> the footnote chunk(s) whose mark it calls, found by the
   same walk as the frozen retrieval (`_called_notes`: notes linked at ingestion and the note
   paragraphs right after the current table, continuation tables with the same header row
   included), but with a note mark reader that also accepts notes typeset in italics
   ("*\\*note …*"), which the frozen reader misses. Only links the frozen reader does not already
   produce are written (`method = "italic_mark"`), so following them adds only what is missing.

Usage:
    .venv/bin/python scripts/build_chunk_links.py --index index/tas_v6 --out index/tas_v6_links
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import sqlite3
import subprocess
import unicodedata
from pathlib import Path

from rag_sfar.retrieval.pipeline import (
    _BIBLIO_OR_ADDRESS_RE,
    _NOTE_START_RE,
    SfarRagRetriever,
    _call_marks,
    _first_line,
    _note_marks,
)
from rag_sfar.schemas import Chunk

CONTEXT_PREFIXES = ("Tableau :", "Section :", "Sous-catégorie :", "Périmètre :", "Note")
POP_SOURCES = ("table", "section")


def fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower().replace("\\", "")
    t = re.sub(r"[*#†‡^]", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def cell_line(text: str) -> str:
    """The cell line of a row card ("Header : value | Header : value"), context lines excluded."""
    for line in text.splitlines():
        if " | " in line and not line.startswith(CONTEXT_PREFIXES):
            return line
    return ""


def row_label(text: str) -> tuple[str, str]:
    """(normalised header of the label column, raw label) of a row card; ("", "") if none."""
    first = cell_line(text).split(" | ")[0]
    header, sep, value = first.partition(" : ")
    if not sep or not value.strip():
        return "", ""
    return fold(header.split(" / ")[0]), value.strip()


def label_items(label: str) -> frozenset[str]:
    items = {fold(x) for x in label.split(";")}
    return frozenset(x for x in items if x)


def informative(items: frozenset[str]) -> bool:
    return any(len(x) >= 6 and any(len(w) >= 4 and not w.isdigit() for w in x.split()) for x in items)


def population_class(c: Chunk) -> str:
    """Single population class of a chunk from a table- or section-level label, else ""."""
    if c.population_source not in POP_SOURCES:
        return ""
    s = set(c.populations or [])
    if s == {"adulte"}:
        return "adulte"
    if s == {"pediatrie"}:
        return "pediatrie"
    if s in ({"neonatal"}, {"neonatal", "pediatrie"}):
        return "neonatal"
    if s in ({"obstetrique"}, {"adulte", "obstetrique"}):
        return "obstetrique"
    return ""


def stem(word: str) -> str:
    """Crude French stem shared by the builder and the retrieval step: first 5 characters."""
    return word[:5]


def anchor_terms(chunks: list[Chunk], sources: set[str], max_df: float) -> dict[str, list[str]]:
    """Discriminative words of the act label of each linked row: label words (>= 4 letters,
    stemmed) that occur in at most `max_df` of the labelled row cards of the same document.
    Frequent label words ("chirurgie", "pose", "matériel") name a whole family of acts, not one
    act. The retrieval step follows a link only from a row whose label shares one of these words
    with the question."""
    labels: dict[str, dict[str, set[str]]] = collections.defaultdict(dict)
    for c in chunks:
        if c.chunk_type != "table_row_card" or not c.is_latest_edition or not c.is_active:
            continue
        _, label = row_label(c.text)
        if label:
            labels[c.doc_id][c.chunk_id] = {stem(w) for w in fold(label).split() if len(w) >= 4 and not w.isdigit()}
    out: dict[str, list[str]] = {}
    for doc, rows in labels.items():
        if not any(cid in sources for cid in rows):
            continue
        df = collections.Counter(t for toks in rows.values() for t in toks)
        n = len(rows)
        for cid, toks in rows.items():
            if cid in sources:
                out[cid] = sorted(t for t in toks if df[t] <= max_df * n)
    return out


def build_counterparts(chunks: list[Chunk], max_per_pop: int) -> tuple[dict, dict]:
    rows_by_doc: dict[str, list] = collections.defaultdict(list)
    seen_text: set[tuple[str, str]] = set()
    stats = collections.Counter()
    for c in chunks:
        if c.chunk_type != "table_row_card" or not c.is_latest_edition or not c.is_active:
            continue
        stats["row_cards"] += 1
        pop = population_class(c)
        if not pop:
            continue
        stats["row_cards_single_population"] += 1
        header, label = row_label(c.text)
        items = label_items(label)
        if not header or not informative(items):
            continue
        key = (c.doc_id, re.sub(r"\W+", " ", cell_line(c.text).lower()).strip())
        if key in seen_text:  # the same row printed twice in the index: link the first copy only
            stats["duplicate_row_cards"] += 1
            continue
        seen_text.add(key)
        stats["row_cards_linkable"] += 1
        rows_by_doc[c.doc_id].append((c, pop, header, items))
    out: dict[str, list[dict]] = {}
    for doc, rows in rows_by_doc.items():
        for c, pop, header, items in rows:
            cands: dict[str, list] = collections.defaultdict(list)
            for d, dpop, dheader, ditems in rows:
                if dpop == pop or d.table_id == c.table_id or dheader != header:
                    continue
                if items <= ditems:
                    cands[dpop].append((len(ditems - items), d))
            links = []
            for dpop, lst in cands.items():
                lst.sort(key=lambda t: (t[0], t[1].chunk_index))
                if len(lst) > max_per_pop:
                    stats["ambiguous_dropped"] += 1
                    continue
                for extra, d in lst:
                    links.append({
                        "target": d.chunk_id,
                        "source_population": pop,
                        "target_population": dpop,
                        "match": "exact" if extra == 0 else "subset",
                        "target_table_id": d.table_id,
                    })
            if links:
                out[c.chunk_id] = links
    stats["sources_with_link"] = len(out)
    stats["links"] = sum(len(v) for v in out.values())
    return out, dict(stats)


# An escaped mark at the start of a line ("\*", "\*\*", "\#"), optionally inside an italic
# wrapper ("*\*note*", "_\*note_"): the backslash makes it a literal mark, so it may be glued to
# the first word of the note.
_ESCAPED_MARK_RE = re.compile(r"^[*_]?((?:\\\*){1,4}|\\#)(?![\\*#])")


# A bibliographic reference typeset as a footnote: "volume(issue): pages" or "; 32; (9): 660-4".
_CITATION_RE = re.compile(r"\d+\s*;?\s*\(\s*\d+\s*\)\s*:\s*\d+\s*[-–]\s*\d+|\b(?:19|20)\d\d\s*;\s*\d+")


def note_marks_relaxed(text: str) -> set[str]:
    """Marks that start a note line: the frozen reader (`_note_marks`) plus escaped marks glued
    to the note or wrapped in italics, which the frozen reader misses."""
    marks = set(_note_marks(text))
    for line in text.splitlines():
        m = _ESCAPED_MARK_RE.match(line.strip())
        if m:
            marks.add(m.group(1).replace("\\", ""))
    return marks


def embedded_note_marks(text: str) -> set[str]:
    """Marks of the notes an index already printed inside the card ("Note (*) : …")."""
    marks: set[str] = set()
    for line in text.splitlines():
        m = re.match(r"Note\s*(?:\(([^)]*)\))?\s*:\s*(.*)", line)
        if m:
            marks |= set(re.findall(r"\*{1,4}|#|†|‡", m.group(1) or ""))
            marks |= note_marks_relaxed(m.group(2))
    return marks


class _Store:
    def __init__(self, chunks: list[Chunk]):
        self.by_id = {c.chunk_id: c for c in chunks}

    def get_chunk(self, cid: str) -> Chunk | None:
        return self.by_id.get(cid)


def build_note_links(chunks: list[Chunk], max_chars: int) -> tuple[dict, dict]:
    store = _Store(chunks)
    retr = SfarRagRetriever.__new__(SfarRagRetriever)
    retr.store = store
    stats = collections.Counter()
    out: dict[str, list[dict]] = {}

    def eligible(n: Chunk | None, doc_id: str) -> bool:
        return (
            n is not None
            and n.doc_id == doc_id
            and n.chunk_type not in ("callout_allergy", "references")
            and not n.is_reference_section
            and len(n.text) <= max_chars
            and not _BIBLIO_OR_ADDRESS_RE.search(n.text)
            and not _CITATION_RE.search(n.text)
        )

    for c in chunks:
        if c.chunk_type not in ("table_row_card", "table_markdown") or not c.is_latest_edition or not c.is_active:
            continue
        calls = _call_marks(c.text)
        if not calls:
            continue
        stats["table_chunks_with_calls"] += 1
        frozen = {n.chunk_id for n in retr._called_notes(c, max_chars, True)}
        covered = embedded_note_marks(c.text)
        for nid in frozen:
            covered |= _note_marks(store.get_chunk(nid).text)
        # Same candidate set as the frozen reader: linked notes, then the notes after the table.
        cands: list[Chunk] = [store.get_chunk(cid) for cid in c.linked_callout_ids]
        tid = c.table_id or ""
        cur = c
        if c.chunk_type == "table_markdown":
            nxt = store.get_chunk(c.next_chunk_id) if c.next_chunk_id else None
            while nxt is not None and nxt.chunk_type == "table_row_card" and nxt.doc_id == c.doc_id:
                cur, nxt = nxt, (store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None)
        header = retr._table_header(c)
        nxt = store.get_chunk(cur.next_chunk_id) if cur.next_chunk_id else None
        cont = 0
        while nxt is not None and nxt.doc_id == c.doc_id:
            if nxt.chunk_type == "table_row_card" and (not tid or (nxt.table_id or "") in ("", tid)):
                pass
            elif nxt.chunk_type == "table_markdown" and header and _first_line(nxt.text) == header and cont < 6:
                cont += 1
                tid = nxt.table_id or ""
            else:
                break
            nxt = store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None
        taken = 0
        while nxt is not None and taken < 2 and nxt.doc_id == c.doc_id and _NOTE_START_RE.match(nxt.text):
            cands.append(nxt)
            taken += 1
            nxt = store.get_chunk(nxt.next_chunk_id) if nxt.next_chunk_id else None
        links = []
        for n in cands:
            if not eligible(n, c.doc_id) or n.chunk_id in frozen:
                continue
            new = (calls & note_marks_relaxed(n.text)) - covered - _note_marks(n.text)
            if new:
                links.append({"target": n.chunk_id, "marks": sorted(new), "method": "italic_mark"})
                covered |= new
        if links:
            out[c.chunk_id] = links
    stats["sources_with_link"] = len(out)
    stats["links"] = sum(len(v) for v in out.values())
    return out, dict(stats)


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", default="index/tas_v6")
    ap.add_argument("--out", default="index/tas_v6_links")
    ap.add_argument("--max-per-population", type=int, default=2)
    ap.add_argument("--note-max-chars", type=int, default=1200)
    ap.add_argument("--anchor-max-df", type=float, default=0.05)
    a = ap.parse_args()
    src, out = Path(a.index), Path(a.out)
    if out.resolve() == src.resolve():
        raise SystemExit("the sidecar must not be written into the source index")
    con = sqlite3.connect(f"file:{src / 'metadata.sqlite'}?mode=ro", uri=True)
    chunks = [Chunk.model_validate_json(r[0]) for r in con.execute("SELECT payload_json FROM chunks ORDER BY idx")]
    con.close()
    counterparts, cstats = build_counterparts(chunks, a.max_per_population)
    terms = anchor_terms(chunks, set(counterparts), a.anchor_max_df)
    cstats["sources_without_discriminative_term"] = sum(1 for s in counterparts if not terms.get(s))
    notes, nstats = build_note_links(chunks, a.note_max_chars)
    by_doc = collections.Counter()
    for sid in counterparts:
        by_doc[sid.split("__c")[0]] += len(counterparts[sid])
    out.mkdir(parents=True, exist_ok=True)
    (out / "links.json").write_text(
        json.dumps({"counterparts": counterparts, "anchor_terms": terms, "notes": notes}, ensure_ascii=False, indent=0, sort_keys=True),
        encoding="utf-8",
    )
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        commit = ""
    manifest = {
        "source_index": str(src),
        "source_metadata_sha256": sha256_file(src / "metadata.sqlite"),
        "source_manifest_sha256": sha256_file(src / "manifest.json") if (src / "manifest.json").exists() else None,
        "links_sha256": sha256_file(out / "links.json"),
        "built_at": dt.datetime.now().isoformat(timespec="seconds"),
        "git_commit": commit,
        "params": {"max_per_population": a.max_per_population, "note_max_chars": a.note_max_chars,
                   "anchor_max_df": a.anchor_max_df,
                   "population_sources": list(POP_SOURCES)},
        "counterparts": {**cstats, "links_by_document": dict(by_doc.most_common())},
        "notes": nstats,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
