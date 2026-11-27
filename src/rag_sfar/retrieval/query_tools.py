"""Deterministic query tools for multi-query retrieval (B1, 2026-11-27).

Everything here is based on the form of French clinical questions, never on their content:
- MCQ parsing: a stem followed by option lines "A. …", "B) …";
- negated background of the patient: a negation cue that directly follows the description of
  the patient ("chez un adulte sans X ni Y", "enfant de 30 kg, sans X"), as opposed to a
  negation that defines the act ("hernie sans prothèse", "sans mise en place de matériel").
"""

from __future__ import annotations

import re

from rag_sfar.retrieval.medical_lexicon import tokenize_medical_french
from rag_sfar.retrieval.router import MODIFIER_PATTERNS, is_negated_at

_MCQ_OPTION_RE = re.compile(r"^\s*([A-H])\s*[.)]\s+(.+?)\s*$", re.M)


def split_mcq(query: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (stem, [(letter, option text), ...]); no options when fewer than two are found or
    when the letters are not consecutive from A."""
    matches = list(_MCQ_OPTION_RE.finditer(query))
    if len(matches) < 2:
        return query, []
    letters = [m.group(1) for m in matches]
    if letters != [chr(ord("A") + i) for i in range(len(letters))]:
        return query, []
    stem = query[: matches[0].start()].strip()
    return stem, [(m.group(1), m.group(2).strip()) for m in matches]


# Patient noun phrase (gender and number agreement handled) and the descriptors that may follow
# it before a negation: age, weight, "âgé de", "pesant", commas.
_PATIENT_NOUN = (
    r"(?:patiente?s?|adultes?|enfants?|nourrissons?|nouveau[- ]n[ée]e?s?|adolescente?s?|"
    r"hommes?|femmes?|sujets?|personnes?|parturientes?|b[ée]b[ée]s?|fillettes?|gar[çc]ons?)"
)
_DESCRIPTOR = (
    r"(?:\s*,?\s*(?:[âa]g[ée]e?s?\s+)?(?:de\s+)?\d+(?:[.,]\d+)?\s*(?:ans?|mois|jours?|semaines?|kg)"
    r"|\s*,?\s*pesant\s+\d+(?:[.,]\d+)?\s*kg"
    r"|\s+[âa]g[ée]e?s?"
    r"|\s+(?:de\s+)?(?:r[ée]animation|programm[ée]e?s?|opér[ée]e?s?))"
)
_NEG_CUE = r"(?:sans|ni|non|aucune?|en\s+l['’]absence\s+d[e'’]?)"
_PATIENT_NEG_RE = re.compile(
    rf"\b{_PATIENT_NOUN}(?:{_DESCRIPTOR})*\s*,?\s*(?={_NEG_CUE}\b)",
    re.I,
)
# A negated span: cue, closed-class bridge words, then up to 5 words; stops at punctuation, at
# a clause boundary word, or at a verb/participle introducing the act. "ni" chains the span.
_STOP_WORDS = (
    r"(?:opér[ée]e?s?|devant|pour|qui|avec|chez|lors|avant|apr[èe]s|dans|est|sont|pr[ée]sente\w*|"
    r"programm[ée]e?s?|admise?s?|b[ée]n[ée]ficiant|devant|subissant|candidate?s?|quel\w*|et)"
)
_SPAN_WORD = rf"(?!{_STOP_WORDS}\b)[\w'’\-/]+"
_NEG_SPAN_RE = re.compile(
    rf"\b{_NEG_CUE}\s*(?:(?!ni\b){_SPAN_WORD}\s*){{1,6}}?(?=$|[,;:.?!()\n]|\s*(?:ni\b|{_STOP_WORDS}\b))",
    re.I,
)


def patient_negated_spans(query: str) -> list[tuple[int, int]]:
    """Character spans of negated background terms attached to the patient description.

    "Chez un adulte sans allergie aux X ni BPCO, opéré …" -> spans of "sans allergie aux X" and
    "ni BPCO". A negation that does not directly follow the patient description is left alone
    (it usually defines the act: "cure de hernie sans prothèse"). MCQ option lines are never
    touched (an option's condition is what the question asks about). A span is cut before any
    patient-state term that is not itself negated ("non diabétique allergique à X" keeps
    "allergique à X"), with the router's tight negation scope."""
    stem, options = split_mcq(query)
    limit = len(stem) if options else len(query)
    spans: list[tuple[int, int]] = []
    for m in _PATIENT_NEG_RE.finditer(query[:limit]):
        pos = m.end()
        while True:
            s = _NEG_SPAN_RE.match(query[:limit], pos)
            if not s:
                break
            end = s.end()
            for pat in MODIFIER_PATTERNS.values():
                for t in pat.finditer(query, s.start(), end):
                    if t.start() > s.start() and not is_negated_at(query, t.start()):
                        end = min(end, t.start())
            spans.append((s.start(), end))
            if end < s.end():
                break
            nxt = re.match(r"\s*(?=ni\b)", query[s.end():], re.I)
            if not nxt:
                break
            pos = s.end() + nxt.end()
    return spans


def remove_spans(query: str, spans: list[tuple[int, int]]) -> str:
    """The query with the given spans removed (whitespace and dangling commas tidied)."""
    out, last = [], 0
    for a, b in sorted(spans):
        out.append(query[last:a])
        last = b
    out.append(query[last:])
    text = "".join(out)
    text = re.sub(r"\s*,\s*(?=[,;:.?!])", "", text)
    text = re.sub(r"\s+([,;:.?!])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def negated_token_weights(query: str, spans: list[tuple[int, int]], weight: float) -> dict[str, float]:
    """Lexical weights of the tokens found only inside negated spans (tokens that also occur
    outside a negated span keep weight 1)."""
    if not spans or weight >= 1.0:
        return {}
    inside = set()
    for a, b in spans:
        inside.update(tokenize_medical_french(query[a:b]))
    outside = set(tokenize_medical_french(remove_spans(query, spans)))
    return {t: weight for t in inside - outside}
