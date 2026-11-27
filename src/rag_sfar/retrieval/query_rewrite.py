"""Language-model rewriting of the user's question before retrieval (agent Q2).

The frozen retriever (`SfarRagRetriever`, configuration `C10_context_notes`) is wrapped, never
modified: `QueryRewriteRetriever.retrieve(...)` has the same signature and return value. With
`variant="off"` (the default) it returns the frozen retriever's output unchanged, and
`wrap_retriever` returns the base retriever itself.

Prompt variants (one short call that sees only the question stem; see
reports/agents/Q2_reformulation.md):
- `normalize`: conservative normalisation. Fix spelling and accents, expand abbreviations (long
  form followed by the abbreviation), write a full sentence; adding, removing or replacing any
  clinical information is forbidden; a question already clean is answered "INCHANGEE".
- `reformulate`: free reformulation into the vocabulary of a guideline.
- `hyde`: hypothetical passage (the model writes the guideline passage it expects to find, used as
  a search query only, never shown to the user; Gao et al. 2022, "HyDE").

Use of the rewrite:
- `replace`: retrieve with the rewrite instead of the question.
- `add`: retrieve with the question AND the rewrite; the merged context is the frozen context
  followed by the rewrite's passages that are not already in it, within the same budget
  (`merge_add`). Guarantee: every chunk of the frozen context is kept, in the same order and at
  the same rank; the rewrite can only add chunks, in the space left by the frozen context.

MCQ options. When the query ends with lettered options ("A. ...", "B) ..."), only the stem is
sent to the model and the options are appended back verbatim: the model never sees answer
candidates (it could copy one into the question and steer the search toward it), and options are
already written by the question's author.

Optional deterministic guard (`guard=True`, off by default, measured as its own variant): the
rewrite is discarded (frozen behaviour) when it loses a number, a negation or a population word
of the question, or adds a number.

Language-model calls go through a `responder(system, user) -> str` callable: in the product it
wraps the served model's client (`llm_responder`); in evaluation it looks the answer up in a table
filled from stand-in answers (`eval_internal/q2_rewrite_eval.py`), so the prompts are identical in
both paths. Any answer that does not follow the strict format falls back to the frozen output.

Switch: environment variables RAG_SFAR_QUERY_REWRITE (off | normalize | reformulate | hyde) and
RAG_SFAR_QUERY_REWRITE_USE (replace | add), or the arguments of `wrap_retriever`.

Nothing here names a drug, a procedure, a guideline or an evaluation question (CLAUDE.md,
principle 1); the prompts are domain-neutral and contain no example.
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

VARIANTS = ("off", "normalize", "reformulate", "hyde")
USES = ("replace", "add")
ENV_VARIANT = "RAG_SFAR_QUERY_REWRITE"
ENV_USE = "RAG_SFAR_QUERY_REWRITE_USE"

Responder = Callable[[str, str], str]


@dataclass
class QueryRewriteConfig:
    variant: str = "off"
    use: str = "add"
    guard: bool = False
    # Budget of the generation context (`wide` preset: 40 chunks, 30 000 characters).
    max_chars: int = 30000
    max_chunks: int = 40
    max_tokens: int = 0  # 0 = per-variant default (DEFAULT_MAX_TOKENS)

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown query-rewrite variant {self.variant!r}; known: {VARIANTS}")
        if self.use not in USES:
            raise ValueError(f"unknown query-rewrite use {self.use!r}; known: {USES}")


DEFAULT_MAX_TOKENS = {"normalize": 200, "reformulate": 200, "hyde": 400}


def config_from_env() -> QueryRewriteConfig:
    v = (os.environ.get(ENV_VARIANT, "off").strip().lower() or "off")
    u = (os.environ.get(ENV_USE, "add").strip().lower() or "add")
    return QueryRewriteConfig(variant=v, use=u)


# ---------------------------------------------------------------- prompts (domain-neutral)

_PREAMBLE = (
    "Tu prépares la recherche documentaire d'un moteur de questions-réponses fondé sur des "
    "recommandations professionnelles médicales rédigées en français. Tu reçois la question telle "
    "qu'un soignant l'a tapée, parfois vite : fautes de frappe, accents manquants, abréviations, "
    "style télégraphique. Tu ne réponds jamais à la question."
)

NORMALIZE_SYSTEM = _PREAMBLE + """

Ta seule tâche est de normaliser l'écriture de la question :
- corriger les fautes de frappe et d'orthographe ;
- rétablir les accents ;
- développer chaque abréviation dont le sens est certain dans le contexte de la question, en écrivant la forme complète suivie de l'abréviation entre parenthèses ; si le sens d'une abréviation n'est pas certain, la laisser telle quelle ;
- si la question est en style télégraphique, l'écrire en une phrase complète avec exactement les mêmes éléments.

Interdictions absolues :
- ne rien ajouter : aucune population, aucun âge, aucun antécédent, aucun traitement, aucune dose, aucune durée, aucune circonstance qui ne figure pas dans la question ;
- ne rien retirer : garder chaque élément clinique, chaque nombre avec son unité, chaque négation (« sans », « pas de », « non », « ni »), chaque population, chaque antécédent et chaque précision ;
- ne rien remplacer : ne pas substituer un terme par un synonyme, un terme voisin, plus général ou plus précis ; garder les noms de médicaments, d'actes, de maladies et de dispositifs tels qu'ils sont écrits, en corrigeant seulement une faute de frappe évidente ; si tu n'es pas certain de la correction d'un nom, le laisser tel quel ;
- ne pas répondre, ne rien expliquer, ne rien commenter.

Si la question est déjà correctement écrite (aucune faute, accents présents, aucune abréviation à développer, phrase complète), réponds INCHANGEE. C'est le cas le plus fréquent.

Format de sortie strict, une seule ligne, sans aucun autre texte :
INCHANGEE
ou
NORMALISEE: <la question normalisée>"""

REFORMULATE_SYSTEM = _PREAMBLE + """

Réécris la question sous la forme la plus adaptée à une recherche dans des recommandations professionnelles : le vocabulaire précis et les termes techniques qu'emploient ces textes, l'orthographe et les accents corrigés, les abréviations développées, une phrase complète, explicite et sans ambiguïté. Tu peux reformuler librement et préciser la terminologie pour que la question soit la plus claire possible, en gardant le sens de la question. N'écris aucune réponse et aucune recommandation.

Format de sortie strict, une seule ligne, sans aucun autre texte :
REFORMULEE: <la question reformulée>"""

HYDE_SYSTEM = _PREAMBLE + """

Écris le passage de recommandation professionnelle française qui répondrait à cette question, tel que tu t'attends à le trouver dans le texte d'une recommandation : son style, son vocabulaire, sa structure (population, situation clinique, conduite à tenir et, s'il y a lieu, traitement, posologie, durée, niveau de preuve). Ce passage sert uniquement de requête de recherche documentaire ; il ne sera jamais montré à l'utilisateur. Trois à cinq phrases.

Format de sortie strict, une seule ligne, sans aucun autre texte :
PASSAGE: <le passage>"""

USER_TEMPLATE = "Question :\n{question}"

SYSTEMS = {"normalize": NORMALIZE_SYSTEM, "reformulate": REFORMULATE_SYSTEM, "hyde": HYDE_SYSTEM}


def rewrite_prompt(variant: str, stem: str) -> tuple[str, str]:
    return SYSTEMS[variant], USER_TEMPLATE.format(question=stem.strip())


def prompt_key(system: str, user: str) -> str:
    """Stable key of a prompt (answer tables of the evaluation path)."""
    return hashlib.sha256((system + "\x00" + user).encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------- MCQ options

_OPTION_RE = re.compile(r"\n\s*[A-H][.)]\s")


def split_options(query: str) -> tuple[str, str]:
    """(stem, options block). The options block starts at the first line "A. ..." / "A) ..."
    (or any letter A-H) and is returned verbatim, with its leading newline; "" when none."""
    m = _OPTION_RE.search(query)
    if not m:
        return query, ""
    return query[: m.start()], query[m.start():]


# ---------------------------------------------------------------- strict parser


class FormatError(ValueError):
    pass


_KEYWORDS = {"normalize": "NORMALISEE", "reformulate": "REFORMULEE", "hyde": "PASSAGE"}


def _plain(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def parse_rewrite(variant: str, text: str) -> str | None:
    """None = keep the question (INCHANGEE, normalize only); else the rewrite (one line).
    Raises FormatError on anything else."""
    lines = [l.strip() for l in (text or "").strip().splitlines() if l.strip()]
    if not lines:
        raise FormatError("empty answer")
    if len(lines) != 1:
        raise FormatError(f"{len(lines)} lines (one expected)")
    line = lines[0]
    head = _plain(line).upper()
    if variant == "normalize" and head.rstrip(" .") == "INCHANGEE":
        return None
    kw = _KEYWORDS[variant]
    m = re.match(rf"^{kw}\s*:\s*(\S.*)$", _plain(line), re.I)
    if not m:
        raise FormatError(f"answer must start with '{kw}:'" + (" or be INCHANGEE" if variant == "normalize" else "")
                          + f", got {line[:40]!r}")
    # keep the original characters (accents) after the keyword
    body = line[line.index(":") + 1:].strip()
    if len(body) < 8:
        raise FormatError("rewrite too short")
    return body


# ---------------------------------------------------------------- deterministic guard

_NEG_RE = re.compile(r"\b(?:sans|pas|non|ni|aucun|aucune|jamais|ne|n)\b")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
# Generic population / age vocabulary of clinical texts (not tied to any guideline): word-start
# patterns, whole words for the short ones.
_POP_PATTERNS = ("adulte", "enfant", "pediatr", "nourrisson", "nouveau-ne", "nouveau ne", "neonat", "premature",
                 "adolescent", "enceinte", "grossesse", "obstetric", "parturiente", "allait", "age[es]*\\b",
                 "ans\\b", "mois\\b", "semaines?\\b")


def fold(s: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", _plain(s.lower())))


def _numbers(s: str) -> list[str]:
    return sorted(n.replace(",", ".") for n in _NUM_RE.findall(s))


def _pop_words(s: str) -> set[str]:
    f = " " + fold(s) + " "
    return {re.sub(r"\\b|\[[^\]]*\]\*|s\?", "", p) for p in _POP_PATTERNS if re.search(rf"\b{p}", f)}


def guard_violations(original: str, rewrite: str) -> list[str]:
    """Reasons to discard a rewrite: lost or added number, lost negation, lost population word."""
    out = []
    no, nr = _numbers(original), _numbers(rewrite)
    lost = [n for n in set(no) if no.count(n) > nr.count(n)]
    added = [n for n in set(nr) if nr.count(n) > no.count(n)]
    if lost:
        out.append(f"number lost: {sorted(lost)}")
    if added:
        out.append(f"number added: {sorted(added)}")
    neg_o, neg_r = _NEG_RE.findall(fold(original)), _NEG_RE.findall(fold(rewrite))
    lost_neg = [w for w in set(neg_o) if w not in ("ne", "n") and neg_o.count(w) > neg_r.count(w)]
    if lost_neg:
        out.append(f"negation lost: {sorted(lost_neg)}")
    lost_pop = _pop_words(original) - _pop_words(rewrite)
    if lost_pop:
        out.append(f"population lost: {sorted(lost_pop)}")
    return out


def same_text(a: str, b: str) -> bool:
    """Equal up to case, accents, punctuation and spacing (then the rewrite is not used)."""
    return fold(a) == fold(b)


# ---------------------------------------------------------------- merge (add mode)


def _blocks(items: list[RetrievedChunk]) -> list[list[RetrievedChunk]]:
    """A block = a ranked passage followed by its context window (expanded items)."""
    blocks: list[list[RetrievedChunk]] = []
    for rc in items:
        if blocks and rc.is_expanded_context:
            blocks[-1].append(rc)
        else:
            blocks.append([rc])
    return blocks


def merge_add(original: list[RetrievedChunk], rewrite: list[RetrievedChunk], max_chars: int,
              max_chunks: int) -> list[RetrievedChunk]:
    """Frozen context first, unchanged; then the rewrite's blocks in rank order, skipping chunks
    already present (same id or same text), while the budget allows. A rewrite block whose ranked
    passage does not fit is dropped whole; its window chunks are skipped one by one if they do not
    fit. The frozen context is never cut, even if it alone exceeds the budget (it does not in the
    frozen configuration: <= 30 000 characters, <= 38 chunks on dev)."""
    out = list(original)
    ids = {rc.chunk.chunk_id for rc in out}
    texts = {rc.chunk.text for rc in out}
    used = sum(len(rc.chunk.text) for rc in out)
    for block in _blocks(rewrite):
        for j, rc in enumerate(block):
            if len(out) >= max_chunks:
                return out
            t = rc.chunk.text
            if rc.chunk.chunk_id in ids or t in texts:
                continue
            if used + len(t) > max_chars:
                if j == 0:
                    break  # the anchor does not fit: drop the whole block
                continue
            ids.add(rc.chunk.chunk_id)
            texts.add(t)
            used += len(t)
            out.append(rc.model_copy(update={"expansion_reason": f"query_rewrite:{rc.expansion_reason or 'ranked'}"}))
    return out


# ---------------------------------------------------------------- wrapper


@dataclass
class QueryRewriteTrace:
    variant: str
    use: str
    stem: str = ""
    rewrite: str | None = None
    used: bool = False  # the rewrite changed the retrieval query
    prompt_key: str = ""
    raw_answer: str = ""
    format_error: str = ""
    guard_rejected: list[str] = field(default_factory=list)
    llm_ms: float = 0.0
    extra_retrieval_ms: float = 0.0
    n_added: int = 0


class QueryRewriteRetriever:
    """Same `retrieve` interface as `SfarRagRetriever`; off by default (frozen output)."""

    def __init__(self, base: Any, config: QueryRewriteConfig | None = None, responder: Responder | None = None) -> None:
        self.base = base
        self.config = config or QueryRewriteConfig()
        self.responder = responder
        self.last_trace: QueryRewriteTrace | None = None
        if self.config.variant != "off" and responder is None:
            raise ValueError(f"variant {self.config.variant!r} needs a responder (language-model call)")

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base, name)

    def rewrite(self, query: str) -> tuple[str | None, str]:
        """(full rewritten query or None when the question is kept, stem). Never raises."""
        c = self.config
        tr = self.last_trace
        stem, options = split_options(query)
        tr.stem = stem
        system, user = rewrite_prompt(c.variant, stem)
        tr.prompt_key = prompt_key(system, user)
        t0 = time.perf_counter()
        try:
            raw = self.responder(system, user)  # type: ignore[misc]
        except Exception as e:  # unavailable model: frozen behaviour
            tr.format_error = f"responder error: {type(e).__name__}"
            return None, stem
        finally:
            tr.llm_ms = round((time.perf_counter() - t0) * 1000, 1)
        tr.raw_answer = raw
        try:
            body = parse_rewrite(c.variant, raw)
        except FormatError as e:
            tr.format_error = str(e)
            return None, stem
        tr.rewrite = body
        if body is None or same_text(body, stem):
            return None, stem
        if c.guard:
            v = guard_violations(stem, body)
            if v:
                tr.guard_rejected = v
                return None, stem
        return body + options, stem

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
        c = self.config
        self.last_trace = QueryRewriteTrace(variant=c.variant, use=c.use)
        if c.variant == "off":
            return self.base.retrieve(query, **kw)
        new_query, _stem = self.rewrite(query)
        if new_query is None:
            return self.base.retrieve(query, **kw)
        tr = self.last_trace
        tr.used = True
        if c.use == "replace":
            items, analysis, timings = self.base.retrieve(new_query, **kw)
            return items, analysis, {**timings, "query_rewrite_llm_ms": tr.llm_ms}
        main, analysis, timings = self.base.retrieve(query, **kw)
        if analysis.temporal_mode == "all_versions":
            return main, analysis, timings  # edition comparisons keep their own interleaving
        t0 = time.perf_counter()
        extra, _a, _t = self.base.retrieve(new_query, **kw)
        tr.extra_retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
        merged = merge_add(main, extra, c.max_chars, c.max_chunks)
        tr.n_added = len(merged) - len(main)
        return merged, analysis, {**timings, "query_rewrite_llm_ms": tr.llm_ms,
                                  "query_rewrite_extra_ms": tr.extra_retrieval_ms}


def llm_responder(llm: Any, max_tokens: int = 200) -> Responder:
    """Product path: the served model through the existing client (`OpenAICompatibleLLM` or any
    object with `complete(system, user, temperature=, max_tokens=) -> (text, usage)`)."""

    def respond(system: str, user: str) -> str:
        text, _usage = llm.complete(system, user, temperature=0.0, max_tokens=max_tokens)
        return text

    return respond


def wrap_retriever(base: Any, llm: Any = None, variant: str | None = None, use: str | None = None,
                   **config: Any) -> Any:
    """Return `base` itself when the variant is off (default, or RAG_SFAR_QUERY_REWRITE unset),
    else a `QueryRewriteRetriever` calling `llm` (required)."""
    env = config_from_env()
    v = variant if variant is not None else env.variant
    u = use if use is not None else env.use
    cfg = QueryRewriteConfig(variant=v, use=u, **config)
    if cfg.variant == "off":
        return base
    if llm is None:
        raise ValueError(f"query-rewrite variant {cfg.variant!r} needs the served language model")
    return QueryRewriteRetriever(base, cfg, llm_responder(llm, cfg.max_tokens or DEFAULT_MAX_TOKENS[cfg.variant]))
