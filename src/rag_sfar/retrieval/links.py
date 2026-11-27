"""Structural links between chunks, followed after retrieval (post-processing, off by default).

The links are computed offline from the chunk store of an index by `scripts/build_chunk_links.py`
and stored in a sidecar folder next to the index (e.g. `index/tas_v6_links/`): the index itself is
never modified. At query time nothing is searched: a link is followed only from a passage the
retriever already returned, so the linked passage comes from the structure of the document, not
from its similarity to the query.

Two kinds of links:
- **counterparts**: a table row -> the row of the same procedure in the parallel table of another
  population (adult / paediatric / neonatal / obstetric) of the same guideline. A guideline that
  prints one table per population gives a different conduct per population for the same act; when
  the question does not exclude that population, the other population's row is part of the answer
  (or of the condition the answer depends on).
- **notes**: a table chunk -> a footnote it calls that the frozen note reader misses (notes typeset
  in italics). With `notes=True` the step also attaches the called notes of every ranked table
  chunk, not only of the first `context_window_top` ones.

Use: wrap the retriever (`LinkedRetriever(retriever, Path("index/tas_v6_links"), LinkPolicy(
counterparts=True))`), which keeps the `retrieve(query, config, ...)` interface, or call
`apply_links` on the output of `retrieve`. With the default `LinkPolicy()` nothing is enabled and
the output is the retriever's output, unchanged.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rag_sfar.config import RetrievalConfig
from rag_sfar.retrieval.pipeline import _query_subpopulation
from rag_sfar.schemas import Chunk, QueryAnalysis, RetrievedChunk

# Target populations a question allows, by the population the router read in the question.
# "non_specifie" / "mixte": every population of the guideline may be the answer.
_ALLOWED_TARGETS: dict[str, set[str]] = {
    "adulte": {"adulte", "obstetrique"},
    "pediatrie": {"pediatrie", "neonatal"},
}
_ALL_TARGETS = {"adulte", "pediatrie", "neonatal", "obstetrique"}


@dataclass(frozen=True)
class LinkPolicy:
    """What the link step adds. Everything is off by default.

    counterparts: add the counterpart row(s) of the ranked table rows.
    anchor_top: only the first `anchor_top` ranked results are anchors (the frozen configuration
        expands the first 8 ranked results; the same depth is used here).
    max_per_anchor: at most this many counterpart rows per anchor (one per target population).
    max_total: at most this many counterpart rows per question.
    respect_query_population: when the question names a population, only rows of that population
        are added (a paediatric question gets the paediatric row of an adult anchor, never the
        reverse); a question without population gets every population.
    anchor_must_match_query: follow a link only from a row whose act the question names: the
        question must contain min(`anchor_min_terms`, n) of the n discriminative words of the
        row's act label (words rare among the act labels of the guideline, stored in the sidecar
        as 5-character stems). A ranked row about another act is not a reason to add its
        counterpart (it would bring a second off-topic dose).
    notes: attach the notes each ranked table chunk calls (frozen reader + sidecar note links).
    notes_anchor_top: depth of ranked results whose notes are attached.
    char_budget: total context budget in characters (None = `config.context_char_budget`).
    """

    counterparts: bool = False
    anchor_top: int = 8
    max_per_anchor: int = 2
    max_total: int = 4
    respect_query_population: bool = True
    anchor_must_match_query: bool = True
    anchor_min_terms: int = 2
    notes: bool = False
    notes_anchor_top: int = 16
    char_budget: int | None = None

    @property
    def enabled(self) -> bool:
        return self.counterparts or self.notes


class ChunkLinks:
    """Sidecar of structural links (`links.json` + `manifest.json`)."""

    def __init__(self, counterparts: dict[str, list[dict]], notes: dict[str, list[dict]], manifest: dict | None = None,
                 anchor_terms: dict[str, list[str]] | None = None):
        self.counterparts = counterparts
        self.notes = notes
        self.manifest = manifest or {}
        self.anchor_terms = anchor_terms or {}

    @classmethod
    def load(cls, directory: Path, index_dir: Path | None = None) -> "ChunkLinks":
        """Load a sidecar; with `index_dir`, refuse a sidecar built from another index."""
        data = json.loads((directory / "links.json").read_text(encoding="utf-8"))
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if index_dir is not None and (index_dir / "manifest.json").exists():
            import hashlib

            h = hashlib.sha256((index_dir / "manifest.json").read_bytes()).hexdigest()
            if manifest.get("source_manifest_sha256") not in (None, h):
                raise ValueError(f"links in {directory} were built from another index than {index_dir}")
        return cls(data.get("counterparts", {}), data.get("notes", {}), manifest, data.get("anchor_terms", {}))


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t).split())


def _row_label(text: str) -> str:
    for line in text.splitlines():
        if " | " in line and not line.startswith(("Tableau :", "Section :", "Sous-catégorie :", "Périmètre :", "Note")):
            first = line.split(" | ")[0]
            return first.partition(" : ")[2]
    return ""


def query_stems(query: str) -> set[str]:
    return {w[:5] for w in _fold(query).split() if len(w) >= 4 and not w.isdigit()}


def anchor_named_by_query(terms: list[str], qstems: set[str], min_terms: int) -> bool:
    if not terms:
        return False
    return len(set(terms) & qstems) >= min(min_terms, len(terms))


def allowed_targets(analysis: QueryAnalysis | None, query: str, respect: bool) -> set[str]:
    if not respect or analysis is None:
        return set(_ALL_TARGETS)
    allowed = set(_ALLOWED_TARGETS.get(analysis.population, _ALL_TARGETS))
    if analysis.population == "pediatrie":
        sub = _query_subpopulation(query, "pediatrie")
        if sub == "child":
            allowed.discard("neonatal")
        elif sub == "neonatal":
            allowed.discard("pediatrie")
    return allowed


def _visible(target: Chunk, context: list[RetrievedChunk], texts: set[str]) -> bool:
    """The target row is already readable in the context: same chunk, same text, or its own
    table printed in a table chunk that contains its label."""
    if _fold(target.text) in texts:
        return True
    label = _fold(_row_label(target.text))
    for r in context:
        c = r.chunk
        if c.chunk_id == target.chunk_id:
            return True
        if label and c.chunk_type == "table_markdown" and c.doc_id == target.doc_id and c.table_id == target.table_id:
            if label in _fold(c.text):
                return True
    return False


def apply_links(
    results: list[RetrievedChunk],
    analysis: QueryAnalysis | None,
    config: RetrievalConfig,
    store: Any,
    links: ChunkLinks,
    policy: LinkPolicy,
    query: str = "",
    note_reader: Any = None,
) -> tuple[list[RetrievedChunk], dict[str, Any]]:
    """Follow structural links from the ranked results. Returns (new results, stats). The ranked
    results and their windows keep their order; each added chunk is placed right after the block
    of its anchor, within the character budget. Nothing is removed."""
    stats: dict[str, Any] = {"counterparts_added": [], "notes_added": []}
    if not policy.enabled or not results or (analysis is not None and analysis.temporal_mode == "all_versions"):
        return results, stats
    budget = (policy.char_budget or config.context_char_budget) - sum(len(r.chunk.text) for r in results)
    in_ctx = {r.chunk.chunk_id for r in results}
    texts = {_fold(r.chunk.text) for r in results}
    ranked = [r for r in results if not r.is_expanded_context]
    additions: dict[str, list[RetrievedChunk]] = {}

    def add(anchor: RetrievedChunk, ch: Chunk, reason: str) -> bool:
        nonlocal budget
        if ch.chunk_id in in_ctx or len(ch.text) > budget or _fold(ch.text) in texts:
            return False
        in_ctx.add(ch.chunk_id)
        texts.add(_fold(ch.text))
        budget -= len(ch.text)
        additions.setdefault(anchor.chunk.chunk_id, []).append(
            RetrievedChunk(chunk=ch, final_score=round(anchor.final_score * 0.9, 6),
                           is_expanded_context=True, expansion_reason=reason)
        )
        return True

    if policy.counterparts:
        allowed = allowed_targets(analysis, query or (analysis.original_query if analysis else ""),
                                  policy.respect_query_population)
        total = 0
        qstems = query_stems(query or (analysis.original_query if analysis else ""))
        stats["anchors_skipped_not_named"] = 0
        for anchor in ranked[: policy.anchor_top]:
            if total >= policy.max_total:
                break
            c = anchor.chunk
            if c.chunk_type != "table_row_card" or c.chunk_id not in links.counterparts:
                continue
            if policy.anchor_must_match_query and not anchor_named_by_query(
                links.anchor_terms.get(c.chunk_id, []), qstems, policy.anchor_min_terms
            ):
                stats["anchors_skipped_not_named"] += 1
                continue
            per_anchor = 0
            done_pops: set[str] = set()
            for link in links.counterparts.get(c.chunk_id, []):
                pop = link["target_population"]
                if pop not in allowed or pop in done_pops or per_anchor >= policy.max_per_anchor or total >= policy.max_total:
                    continue
                target = store.get_chunk(link["target"])
                if target is None or target.doc_id != c.doc_id or not target.is_latest_edition or not target.is_active:
                    continue
                done_pops.add(pop)  # one row per population, the first (best) link only
                if _visible(target, results, texts):
                    continue
                if add(anchor, target, f"counterpart:{pop}"):
                    per_anchor += 1
                    total += 1
                    stats["counterparts_added"].append(
                        {"anchor": c.chunk_id, "target": target.chunk_id, "population": pop,
                         "match": link.get("match"), "chars": len(target.text)}
                    )

    if policy.notes:
        anchors = [r for r in ranked[: policy.notes_anchor_top] if r.chunk.chunk_type in ("table_row_card", "table_markdown")]
        anchors += [x for xs in additions.values() for x in xs]
        for anchor in anchors:
            c = anchor.chunk
            notes: list[Chunk] = []
            if note_reader is not None:
                notes += note_reader(c, config.table_notes_max_chars, config.table_notes_mode == "called_scope")
            for link in links.notes.get(c.chunk_id, []):
                n = store.get_chunk(link["target"])
                if n is not None and n.doc_id == c.doc_id:
                    notes.append(n)
            for n in notes:
                if add(anchor, n, "linked_note"):
                    stats["notes_added"].append({"anchor": c.chunk_id, "note": n.chunk_id, "chars": len(n.text)})

    if not additions:
        return results, stats
    # Place each addition right after its anchor's block (a ranked result and the expanded chunks
    # that follow it); notes of an added row follow that row.
    chars_added = sum(len(x.chunk.text) for xs in additions.values() for x in xs)
    out: list[RetrievedChunk] = []
    block: list[RetrievedChunk] = []

    def emit_additions(cid: str) -> None:
        for x in additions.pop(cid, []):
            out.append(x)
            emit_additions(x.chunk.chunk_id)

    def close_block() -> None:
        for b in block:
            emit_additions(b.chunk.chunk_id)
        block.clear()

    for r in results:
        if not r.is_expanded_context:
            close_block()
        out.append(r)
        block.append(r)
    close_block()
    for xs in list(additions.values()):
        out.extend(xs)
    stats["chars_added"] = chars_added
    return out, stats


class LinkedRetriever:
    """A retriever followed by the link step, with the same `retrieve(...)` interface."""

    def __init__(self, base: Any, links_dir: Path | None = None, policy: LinkPolicy | None = None,
                 links: ChunkLinks | None = None) -> None:
        self.base = base
        self.policy = policy or LinkPolicy()
        self.links = links if links is not None else (ChunkLinks.load(links_dir) if links_dir else ChunkLinks({}, {}))

    def __getattr__(self, name: str) -> Any:  # store, embedder, reranker, ... of the base retriever
        return getattr(self.base, name)

    def retrieve(self, query: str, config: RetrievalConfig | None = None, **kwargs: Any):
        results, analysis, timings = self.base.retrieve(query, config=config, **kwargs)
        if not self.policy.enabled:
            return results, analysis, timings
        cfg = config or RetrievalConfig()
        t0 = time.perf_counter()
        reader = getattr(self.base, "_called_notes", None) if self.policy.notes else None
        results, stats = apply_links(results, analysis, cfg, self.base.store, self.links, self.policy,
                                     query=query, note_reader=reader)
        timings = dict(timings)
        timings["links_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        timings["links_counterparts"] = len(stats["counterparts_added"])
        timings["links_notes"] = len(stats["notes_added"])
        return results, analysis, timings
