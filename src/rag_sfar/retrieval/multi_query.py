"""Multi-query retrieval for questions whose answer needs several distant passages (agent X2).

The frozen retriever (`SfarRagRetriever`, configuration `C10_context_notes`) is wrapped, never
modified: `MultiQueryRetriever.retrieve(...)` has the same signature and return value. With
`mode="off"` (the default) it returns the frozen retriever's output unchanged.

Modes (one variable each, see reports/agents/X2_decomposition.md):
- `decompose`: one short language-model call reads ONLY the question and answers either
  "SIMPLE" or "MULTIPLE" followed by 2-3 standalone sub-questions. Each sub-question is retrieved
  with the frozen retriever; results are merged with a guaranteed share per sub-question
  (`merge_results`). Idea from query decomposition / multi-query retrieval (RAG-Fusion,
  Least-to-most, RQ-RAG, Question Decomposition for RAG 2025).
- `ce_gap`: no language model. After the first retrieval, the question is cut into clauses at
  punctuation and French grammatical connectors (`split_clauses`); each clause is scored by the
  cross-encoder against the top passages; when one clause is supported by none of them
  (max score < `gap_threshold`), that clause is retrieved on its own and merged.
- `llm_correct`: the corrective scheme (CRAG, Yan et al. 2024) with a generative evaluator: one
  short call sees the question and the title, section and first line of each retrieved passage
  (not the full context) and answers "COMPLET" or "INCOMPLET" + 1-2 search queries.

Language-model calls go through a `responder(system, user) -> str` callable: in the product it
wraps the served model's client (`llm_responder`); in evaluation it looks the answer up in a table
filled from stand-in answers (`eval_internal/multi_query_eval.py`), so the prompts are identical
in both paths. Any answer that does not follow the strict format falls back to the frozen output.

Nothing here names a drug, a procedure, a guideline or an evaluation question (CLAUDE.md,
principle 1); the prompts are domain-neutral.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable

from rag_sfar.schemas import QueryAnalysis, RetrievedChunk

MODES = ("off", "decompose", "ce_gap", "llm_correct")
ENV_MODE = "RAG_SFAR_MULTI_QUERY"

Responder = Callable[[str, str], str]


@dataclass
class MultiQueryConfig:
    mode: str = "off"
    # Merge: blocks (a ranked passage + its context window) guaranteed to each source, the
    # character and chunk budgets of the generation context (`wide` preset: 30 000 / 40).
    share_per_query: int = 2
    max_chars: int = 30000
    max_chunks: int = 40
    keep_main: bool = True
    # ce_gap
    gap_top_n: int = 8
    gap_threshold: float = 0.05
    gap_min_clause_words: int = 2
    max_extra_queries: int = 3
    # llm_correct
    correct_list_n: int = 16
    correct_first_chars: int = 160

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"unknown multi-query mode {self.mode!r}; known: {MODES}")


def mode_from_env(default: str = "off") -> str:
    """Mode named by the RAG_SFAR_MULTI_QUERY environment variable (off when unset)."""
    m = os.environ.get(ENV_MODE, default).strip().lower() or "off"
    if m not in MODES:
        raise ValueError(f"{ENV_MODE}={m!r}; known: {MODES}")
    return m


# ---------------------------------------------------------------- prompts (domain-neutral)

DECOMPOSE_SYSTEM = """Tu prépares la recherche documentaire d'un moteur de questions-réponses fondé sur des recommandations professionnelles médicales. Tu ne réponds jamais à la question : tu décides seulement si elle doit être cherchée en une seule fois ou en plusieurs parties.

Réponds SIMPLE si la question porte sur un seul sujet, même si elle est longue ou détaillée (une situation, un patient, une conduite à tenir, une liste de choix de QCM) : une seule recherche suffit. C'est le cas le plus fréquent.

Réponds MULTIPLE seulement si une réponse complète exige des informations de nature différente qui se trouvent vraisemblablement dans des textes ou des chapitres distincts, par exemple la gestion d'un traitement ou d'une maladie du patient d'une part et la conduite propre à l'intervention ou à la situation d'autre part. Les choix d'un QCM ne sont pas des parties.

Pour MULTIPLE, écris 2 ou 3 sous-questions autonomes :
- chacune nomme explicitement son sujet, la population et le contexte utiles (aucun pronom ni renvoi à une autre sous-question) ;
- reprends les termes de la question ; n'ajoute aucune information médicale absente de la question ; ne donne aucune réponse.

Format de sortie strict, sans aucun autre texte :
SIMPLE
ou
MULTIPLE
1. <sous-question>
2. <sous-question>
3. <sous-question, facultative>"""

DECOMPOSE_USER = "Question :\n{question}"

CORRECT_SYSTEM = """Tu contrôles la recherche documentaire d'un moteur de questions-réponses fondé sur des recommandations professionnelles médicales. Tu reçois une question et la liste des passages retrouvés, chacun réduit à son document, sa section et sa première ligne. Tu ne réponds pas à la question.

Décide si ces passages couvrent toutes les parties de la question. Une partie est couverte si au moins un passage traite de ce sujet pour la même situation, même si sa première ligne ne donne pas la réponse. En cas de doute, considère la partie comme couverte : la plupart des questions n'ont qu'une partie et sont déjà couvertes.

Si une partie nécessaire n'est couverte par aucun passage, écris une requête de recherche pour cette partie seulement : une phrase autonome qui nomme le sujet, la population et le contexte, reprend les termes de la question, n'ajoute aucune information médicale et ne contient aucune réponse.

Format de sortie strict, sans aucun autre texte :
COMPLET
ou
INCOMPLET
REQUETE: <requête>
REQUETE: <requête, facultative>"""

CORRECT_USER = "Question :\n{question}\n\nPassages retrouvés :\n{passages}"


def decompose_prompt(question: str) -> tuple[str, str]:
    return DECOMPOSE_SYSTEM, DECOMPOSE_USER.format(question=question.strip())


def _one_line(text: str, n: int) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def passage_digest(items: list[RetrievedChunk], n: int = 16, first_chars: int = 160) -> str:
    """Title, year, section and first characters of the ranked passages (context windows left
    out): what the corrective call sees instead of the full context."""
    lines = []
    for rc in [r for r in items if not r.is_expanded_context][:n]:
        c = rc.chunk
        head = f"{c.doc_title or c.doc_id} ({c.effective_year or 's.d.'})"
        sec = _one_line(c.section_path, 120)
        lines.append(f"[{len(lines) + 1}] {head} — {sec} — {_one_line(c.text, first_chars)}")
    return "\n".join(lines) if lines else "(aucun passage)"


def correct_prompt(question: str, items: list[RetrievedChunk], n: int = 16, first_chars: int = 160) -> tuple[str, str]:
    return CORRECT_SYSTEM, CORRECT_USER.format(question=question.strip(), passages=passage_digest(items, n, first_chars))


def prompt_key(system: str, user: str) -> str:
    """Stable key of a prompt (answer tables of the evaluation path)."""
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------- strict parsers


class FormatError(ValueError):
    pass


def _lines(text: str) -> list[str]:
    return [l.strip() for l in (text or "").strip().splitlines() if l.strip()]


_NUM_RE = re.compile(r"^([1-3])[.)]\s+(\S.{7,})$")


def parse_decomposition(text: str) -> list[str]:
    """[] for SIMPLE, else 2-3 sub-questions. Raises FormatError on anything else."""
    ls = _lines(text)
    if not ls:
        raise FormatError("empty answer")
    head = ls[0].upper()
    if head == "SIMPLE":
        if len(ls) != 1:
            raise FormatError("text after SIMPLE")
        return []
    if head != "MULTIPLE":
        raise FormatError(f"first line must be SIMPLE or MULTIPLE, got {ls[0][:40]!r}")
    subs = []
    for i, l in enumerate(ls[1:], start=1):
        m = _NUM_RE.match(l)
        if not m or int(m.group(1)) != i:
            raise FormatError(f"line {i + 1} is not '{i}. <sous-question>'")
        subs.append(m.group(2).strip())
    if not 2 <= len(subs) <= 3:
        raise FormatError(f"{len(subs)} sub-questions (2 or 3 expected)")
    return subs


_REQ_RE = re.compile(r"^REQU[EÊ]TE\s*:\s*(\S.{7,})$", re.I)


def parse_correction(text: str) -> list[str]:
    """[] for COMPLET, else 1-2 search queries. Raises FormatError on anything else."""
    ls = _lines(text)
    if not ls:
        raise FormatError("empty answer")
    head = ls[0].upper()
    if head == "COMPLET":
        if len(ls) != 1:
            raise FormatError("text after COMPLET")
        return []
    if head != "INCOMPLET":
        raise FormatError(f"first line must be COMPLET or INCOMPLET, got {ls[0][:40]!r}")
    qs = []
    for l in ls[1:]:
        m = _REQ_RE.match(l)
        if not m:
            raise FormatError(f"line is not 'REQUETE: <requête>': {l[:40]!r}")
        qs.append(m.group(1).strip())
    if not 1 <= len(qs) <= 2:
        raise FormatError(f"{len(qs)} queries (1 or 2 expected)")
    return qs


# ---------------------------------------------------------------- clauses (ce_gap)

# French grammatical words that open a new constituent; nothing domain-specific.
_CONNECTORS = (
    r"et|ou|mais|chez|avec|sans|sous|lors\s+d['’]?\w*|en\s+cas\s+d['’]?\w*|au\s+cours\s+d['’]?\w*|"
    r"associée?s?\s+[àa]|après|avant|pendant|pour|qui|dont|ayant|devant|alors\s+que|lorsque|si"
)
_SPLIT_RE = re.compile(rf"[,;:?!()\n]|\s(?=(?:{_CONNECTORS})\s)", re.I)
_STOP = frozenset(
    "les des une un le la de du au aux et ou en est sont quel quelle quels quelles quoi comment "
    "faut doit peut pour par sur dans avec chez sans sous que qui dont son ses leur leurs cette "
    "ces ce cet il elle ils elles on lors cas avant apres pendant tout tous toute toutes plus "
    "moins tres entre selon faire etre avoir patient patiente".split()
)


def _fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", _fold(text)) if len(w) >= 3 and w not in _STOP]


def split_clauses(question: str, min_words: int = 2) -> list[str]:
    """Cut the question (stem only, MCQ options dropped) at punctuation and connectors; segments
    with fewer than `min_words` content words are glued to the previous one."""
    stem = re.split(r"\n\s*[A-E][.)]\s", "\n" + question.strip(), maxsplit=1)[0].strip()
    parts = [p.strip() for p in _SPLIT_RE.split(stem) if p and p.strip()]
    out: list[str] = []
    for p in parts:
        if out and len(content_words(p)) < min_words:
            out[-1] = f"{out[-1]} {p}"
        elif not out or len(content_words(out[-1])) >= min_words:
            out.append(p)
        else:
            out[-1] = f"{out[-1]} {p}"
    return [o for o in out if len(content_words(o)) >= min_words]


# ---------------------------------------------------------------- merge


def _blocks(items: list[RetrievedChunk]) -> list[list[RetrievedChunk]]:
    """A block = a ranked passage followed by its context window (expanded items)."""
    blocks: list[list[RetrievedChunk]] = []
    for rc in items:
        if blocks and rc.is_expanded_context:
            blocks[-1].append(rc)
        else:
            blocks.append([rc])
    return blocks


def merge_results(
    sources: list[list[RetrievedChunk]], share: int, max_chars: int, max_chunks: int,
    labels: list[str] | None = None,
) -> list[RetrievedChunk]:
    """Merge the outputs of several retrievals (sources[0] = main query when kept).

    Phase 1: round-robin over sources, `share` blocks each (the guaranteed share). Phase 2: the
    rest of the main source, then the rest of the others round-robin. A chunk already placed (same
    id or same text) is skipped; a block that overflows the character budget keeps its ranked
    passage alone if that fits. Stops at `max_chunks` chunks / `max_chars` characters."""
    labels = labels or [f"q{i}" for i in range(len(sources))]
    blocks = [_blocks(s) for s in sources]
    out: list[RetrievedChunk] = []
    ids: set[str] = set()
    texts: set[str] = set()
    used = 0

    def place(block: list[RetrievedChunk], label: str) -> None:
        nonlocal used
        for j, rc in enumerate(block):
            if len(out) >= max_chunks:
                return
            t = rc.chunk.text
            if rc.chunk.chunk_id in ids or t in texts:
                continue
            if used + len(t) > max_chars:
                if j == 0:
                    return  # the anchor does not fit: drop the whole block
                continue
            ids.add(rc.chunk.chunk_id)
            texts.add(t)
            used += len(t)
            if label != "main":
                rc = rc.model_copy(update={"expansion_reason": f"multi_query:{label}:{rc.expansion_reason or 'ranked'}"})
            out.append(rc)

    cursor = [0] * len(blocks)
    for r in range(share):
        for i, bl in enumerate(blocks):
            if r < len(bl):
                place(bl[r], labels[i])
                cursor[i] = r + 1
    if blocks:
        for bl in blocks[0][cursor[0]:]:
            place(bl, labels[0])
        cursor[0] = len(blocks[0])
    others = list(range(1, len(blocks)))
    progressed = True
    while progressed:
        progressed = False
        for i in others:
            if cursor[i] < len(blocks[i]):
                place(blocks[i][cursor[i]], labels[i])
                cursor[i] += 1
                progressed = True
    return out


# ---------------------------------------------------------------- wrapper


@dataclass
class MultiQueryTrace:
    mode: str
    fired: bool = False
    extra_queries: list[str] = field(default_factory=list)
    prompt_key: str = ""
    raw_answer: str = ""
    format_error: str = ""
    clause_support: list[tuple[str, float]] = field(default_factory=list)
    llm_ms: float = 0.0
    extra_retrieval_ms: float = 0.0


class MultiQueryRetriever:
    """Same `retrieve` interface as `SfarRagRetriever`; off by default (frozen output)."""

    def __init__(self, base: Any, config: MultiQueryConfig | None = None, responder: Responder | None = None) -> None:
        self.base = base
        self.config = config or MultiQueryConfig()
        self.responder = responder
        self.last_trace: MultiQueryTrace | None = None
        if self.config.mode in ("decompose", "llm_correct") and responder is None:
            raise ValueError(f"mode {self.config.mode!r} needs a responder (language-model call)")

    # attributes of the base retriever used by callers (store, reranker, last_coverage...)
    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def retrieve(
        self,
        query: str,
        config: Any = None,
        override_latest_only: bool | None = None,
        override_domains: list[str] | None = None,
        override_doc_ids: list[str] | None = None,
    ) -> tuple[list[RetrievedChunk], QueryAnalysis, dict[str, float]]:
        kw = dict(config=config, override_latest_only=override_latest_only,
                  override_domains=override_domains, override_doc_ids=override_doc_ids)
        mode = self.config.mode
        self.last_trace = MultiQueryTrace(mode=mode)
        if mode == "off":
            return self.base.retrieve(query, **kw)
        if mode == "decompose":
            return self._decompose(query, kw)
        main, analysis, timings = self.base.retrieve(query, **kw)
        if analysis.temporal_mode == "all_versions":
            return main, analysis, timings  # edition comparisons keep their own interleaving
        if mode == "ce_gap":
            extra = self._ce_gap_queries(query, main)
        else:
            extra = self._llm_correct_queries(query, main)
        return self._finish(query, main, analysis, timings, extra, kw)

    # -- decomposition before retrieval
    def _decompose(self, query: str, kw: dict) -> tuple:
        tr = self.last_trace
        system, user = decompose_prompt(query)
        subs = self._ask(system, user, parse_decomposition)
        main, analysis, timings = self.base.retrieve(query, **kw)
        if not subs or analysis.temporal_mode == "all_versions":
            return main, analysis, timings
        return self._finish(query, main, analysis, timings, subs, kw)

    # -- corrective pass, cross-encoder signal
    def clause_support(self, query: str, main: list[RetrievedChunk]) -> list[tuple[str, float]]:
        reranker = getattr(self.base, "reranker", None)
        clauses = split_clauses(query, self.config.gap_min_clause_words)
        if reranker is None or len(clauses) < 2:
            return []
        anchors = [r for r in main if not r.is_expanded_context][: self.config.gap_top_n]
        texts = [r.chunk.indexed_text for r in anchors]
        if not texts:
            return []
        out = []
        for cl in clauses:
            scores = reranker.score_pairs(cl, texts)
            out.append((cl, max(scores) if scores else 0.0))
        return out

    def _ce_gap_queries(self, query: str, main: list[RetrievedChunk]) -> list[str]:
        sup = self.clause_support(query, main)
        self.last_trace.clause_support = sup
        gaps = [cl for cl, s in sorted(sup, key=lambda x: x[1]) if s < self.config.gap_threshold]
        return gaps[: self.config.max_extra_queries]

    # -- corrective pass, language model
    def _llm_correct_queries(self, query: str, main: list[RetrievedChunk]) -> list[str]:
        system, user = correct_prompt(query, main, self.config.correct_list_n, self.config.correct_first_chars)
        return self._ask(system, user, parse_correction)

    def _ask(self, system: str, user: str, parser: Callable[[str], list[str]]) -> list[str]:
        tr = self.last_trace
        tr.prompt_key = prompt_key(system, user)
        t0 = time.perf_counter()
        try:
            raw = self.responder(system, user)  # type: ignore[misc]
        except Exception as e:  # unavailable model: frozen behaviour
            tr.format_error = f"responder error: {type(e).__name__}"
            return []
        finally:
            tr.llm_ms = round((time.perf_counter() - t0) * 1000, 1)
        tr.raw_answer = raw
        try:
            return parser(raw)
        except FormatError as e:
            tr.format_error = str(e)
            return []

    def _finish(self, query, main, analysis, timings, extra: list[str], kw: dict) -> tuple:
        tr = self.last_trace
        extra = [q for q in extra if q.strip() and q.strip() != query.strip()][: self.config.max_extra_queries]
        if not extra:
            return main, analysis, timings
        tr.fired = True
        tr.extra_queries = extra
        t0 = time.perf_counter()
        results = [self.base.retrieve(q, **kw)[0] for q in extra]
        tr.extra_retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
        c = self.config
        sources = ([main] if c.keep_main else []) + results
        labels = (["main"] if c.keep_main else []) + [f"sub{i + 1}" for i in range(len(results))]
        merged = merge_results(sources, c.share_per_query, c.max_chars, c.max_chunks, labels)
        timings = {**timings, "multi_query_llm_ms": tr.llm_ms, "multi_query_extra_ms": tr.extra_retrieval_ms,
                   "multi_query_n": float(len(extra))}
        return merged, analysis, timings


def llm_responder(llm: Any, max_tokens: int = 200) -> Responder:
    """Product path: the served model through the existing client (`OpenAICompatibleLLM` or
    any object with `complete(system, user, temperature=, max_tokens=) -> (text, usage)`)."""

    def respond(system: str, user: str) -> str:
        text, _usage = llm.complete(system, user, temperature=0.0, max_tokens=max_tokens)
        return text

    return respond


def wrap_retriever(base: Any, llm: Any = None, mode: str | None = None, **config: Any) -> Any:
    """Return `base` itself when the mode is off (default, or RAG_SFAR_MULTI_QUERY unset), else
    a `MultiQueryRetriever`. The language-model modes need `llm`."""
    m = mode if mode is not None else mode_from_env()
    if m == "off":
        return base
    responder = llm_responder(llm) if (llm is not None and m in ("decompose", "llm_correct")) else None
    return MultiQueryRetriever(base, MultiQueryConfig(mode=m, **config), responder)
