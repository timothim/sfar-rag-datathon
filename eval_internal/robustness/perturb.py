"""Deterministic perturbations of the dev questions (typos, accents, abbreviations, telegraphic).

    .venv/bin/python eval_internal/robustness/perturb.py [--seed 20261127]

Reads the dev splits only (abpe171, multirfe_synth), never a test split. Only the question stem
is perturbed (MCQ choices, gold passages, evidence and keys are unchanged, so retrieval metrics
apply as is). Output: eval_internal/robustness/sets/<suite>/<perturbation>.jsonl (EvalItem format,
`meta.perturbation` describes the edit) and sets/counts.json. The abpe171 files contain the
expert benchmark's text and are git-ignored.

Abbreviations come only from the glossary extracted from the corpus (glossary_tas_v6.json,
entries defined in >= 2 documents), never from the evaluation questions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path

from rag_sfar.evaluation.datasets import load_suite, write_jsonl
from rag_sfar.retrieval.corpus_glossary import fold, is_french_word, load_glossary, norm, usable_entries

HERE = Path(__file__).resolve().parent
SUITES = ("abpe171", "multirfe_synth")
PERTURBATIONS = ("clean", "typo1", "typo3", "noaccent", "abbr", "expand", "telegraphic", "abbr_user")

# Diagnostic only, NOT corpus-derived: the abbreviations quoted by the user in the request that
# commissioned this study (2026-11-27), with their standard long forms. Used to measure the case
# the corpus glossary cannot produce (an abbreviation the guidelines never write, e.g. "ABP").
USER_CITED_ABBREVIATIONS = [
    {"abbr": "ABP", "long_form": "antibioprophylaxie", "variants": ["antibioprophylaxie"]},
    {"abbr": "ATB", "long_form": "antibiotique", "variants": ["antibiotique", "antibiothérapie"]},
    {"abbr": "IOT", "long_form": "intubation orotrachéale", "variants": ["intubation orotrachéale", "intubation oro-trachéale"]},
    {"abbr": "ALR", "long_form": "anesthésie locorégionale", "variants": ["anesthésie locorégionale", "anesthésie loco-régionale"]},
    {"abbr": "RTUP", "long_form": "résection transurétrale de prostate", "variants": ["résection transurétrale de prostate", "résection transurétrale de la prostate", "résection trans-urétrale de prostate", "résection trans-urétrale de la prostate"]},
    {"abbr": "PTH", "long_form": "prothèse totale de hanche", "variants": ["prothèse totale de hanche"]},
    {"abbr": "VNI", "long_form": "ventilation non invasive", "variants": ["ventilation non invasive", "ventilation non-invasive"]},
]

# Function words (never typo targets; dropped by the telegraphic style). Negations and
# "sans/avec" are kept by the telegraphic style because they carry clinical meaning.
FUNCTION_WORDS = set("""
le la les l un une des du de d au aux et ou mais car donc or que qu qui quoi dont en dans sur sous par
pour vers chez ce cet cette ces c son sa ses leur leurs mon ma mes ton ta tes notre nos votre vos
est sont etre ete etait sera serait a ont avait fait faire peut peuvent doit doivent faut il elle ils
elles on nous vous je j se s y quel quelle quels quelles comment quand combien pourquoi est-ce lors
afin ainsi alors aussi tres plus moins entre selon cas type quoi lequel laquelle lesquels lesquelles
recommande recommandee recommandees recommandes recommandation recommandations sfar actuelle actuelles
il-elle faut-il doit-on peut-on peut-il doit-il lui leur ceux celle celui""".split())
KEEP_TELEGRAPHIC = {"sans", "avec", "non", "pas", "ni", "ne", "aucun", "aucune", "apres", "avant", "si"}

# AZERTY neighbours (lower case letters), for "neighbouring key" substitutions.
AZERTY_ROWS = ["azertyuiop", "qsdfghjklm", "wxcvbn"]


def _neighbours() -> dict[str, str]:
    pos = {c: (r, i) for r, row in enumerate(AZERTY_ROWS) for i, c in enumerate(row)}
    out = {}
    for c, (r, i) in pos.items():
        nb = []
        for rr in (r - 1, r, r + 1):
            if 0 <= rr < len(AZERTY_ROWS):
                for ii in (i - 1, i, i + 1):
                    if 0 <= ii < len(AZERTY_ROWS[rr]) and (rr, ii) != (r, i):
                        nb.append(AZERTY_ROWS[rr][ii])
        out[c] = "".join(nb)
    return out


NEIGHBOURS = _neighbours()
WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿœŒ]+")


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def rng_for(seed: int, *parts: str) -> random.Random:
    return random.Random(int(hashlib.sha256("|".join([str(seed), *parts]).encode()).hexdigest()[:16], 16))


def content_spans(text: str) -> list[tuple[int, int]]:
    """Spans of content words: letters only, >= 4 letters, not a function word, not an
    abbreviation (>= 2 capitals), not adjacent to a digit."""
    out = []
    for m in WORD_RE.finditer(text):
        w = m.group(0)
        if len(w) < 4 or fold(w) in FUNCTION_WORDS:
            continue
        if sum(1 for c in w if c.isupper()) >= 2:
            continue
        s, e = m.start(), m.end()
        if (s > 0 and text[s - 1].isdigit()) or (e < len(text) and text[e].isdigit()):
            continue
        out.append((s, e))
    return out


def typo_word(word: str, rng: random.Random) -> tuple[str, str]:
    ops = ["delete", "transpose", "neighbour"]
    if strip_accents(word) != word:
        ops.append("accent")
    op = rng.choice(ops)
    if op == "accent":
        idx = [i for i, c in enumerate(word) if strip_accents(c) != c]
        i = rng.choice(idx)
        return word[:i] + strip_accents(word[i]) + word[i + 1:], op
    if op == "delete":
        i = rng.randrange(1, len(word))  # keep the first letter
        return word[:i] + word[i + 1:], op
    if op == "transpose":
        cand = [i for i in range(1, len(word) - 1) if word[i] != word[i + 1]]
        if cand:
            i = rng.choice(cand)
            return word[:i] + word[i + 1] + word[i] + word[i + 2:], op
        op = "neighbour"
    idx = [i for i in range(1, len(word)) if strip_accents(word[i]).lower() in NEIGHBOURS]
    if not idx:
        i = rng.randrange(1, len(word))
        return word[:i] + word[i + 1:], "delete"
    i = rng.choice(idx)
    base = strip_accents(word[i]).lower()
    rep = rng.choice(NEIGHBOURS[base])
    if word[i].isupper():
        rep = rep.upper()
    return word[:i] + rep + word[i + 1:], "neighbour"


def apply_typos(text: str, n: int, rng: random.Random) -> tuple[str, list[dict]]:
    spans = content_spans(text)
    if not spans:
        return text, []
    chosen = sorted(rng.sample(spans, min(n, len(spans))), reverse=True)
    edits = []
    for s, e in chosen:
        new, op = typo_word(text[s:e], rng)
        edits.append({"op": op, "from": text[s:e], "to": new})
        text = text[:s] + new + text[e:]
    return text, edits


def in_upper_run(text: str, s: int, e: int) -> bool:
    """True when the token sits in upper-case running text ("NE PAS", "PAS D'ANTIBIOTIQUE"): an
    adjacent word of >= 2 letters is also fully upper case."""
    before = re.findall(r"[A-Za-zÀ-ÿ']+", text[:s])[-1:]
    after = re.findall(r"[A-Za-zÀ-ÿ']+", text[e:])[:1]
    return any(len(re.sub(r"[^A-Za-zÀ-ÿ]", "", w)) >= 2 and w.upper() == w for w in before + after)


def _align_text(text: str) -> str:
    """Folded text, hyphens/apostrophes as spaces, same length as `text` (index-aligned)."""
    return "".join(" " if c in "-‐–'’" else c for c in fold(text))


class AbbrTool:
    def __init__(self, glossary_path: Path | None, min_docs: int = 2, entries: list[dict] | None = None) -> None:
        self.entries = entries if entries is not None else usable_entries(load_glossary(glossary_path), min_docs=min_docs)
        pats = []
        for e in self.entries:
            for v in e["variants"]:
                nv = norm(v)
                if len(nv) >= 4 and " " in nv or len(nv) >= 8:
                    pats.append((nv, e["abbr"]))
        pats.sort(key=lambda p: -len(p[0]))
        def word_rx(t: str) -> str:  # singular / plural agnostic (final s or x optional)
            stem = t[:-1] if len(t) > 3 and t[-1] in "sx" else t
            return re.escape(stem) + ("[sx]?" if len(t) > 3 else "")

        self.long_patterns = [(re.compile(r"(?<!\w)" + r"\s+".join(word_rx(t) for t in nv.split()) + r"(?!\w)"), abbr, nv) for nv, abbr in pats]
        self.abbr_to_long = {e["abbr"]: e["long_form"] for e in self.entries}

    def abbreviate(self, text: str) -> tuple[str, list[dict]]:
        """Long forms -> abbreviation (longest first, non-overlapping)."""
        aligned = _align_text(text)
        taken = [False] * len(text)
        hits = []
        for rx, abbr, nv in self.long_patterns:
            for m in rx.finditer(aligned):
                if any(taken[m.start():m.end()]):
                    continue
                for i in range(m.start(), m.end()):
                    taken[i] = True
                hits.append((m.start(), m.end(), abbr))
        edits = []
        for s, e, abbr in sorted(hits, reverse=True):
            edits.append({"op": "abbreviate", "from": text[s:e], "to": abbr})
            text = text[:s] + abbr + text[e:]
        return text, edits

    def expand(self, text: str) -> tuple[str, list[dict]]:
        """Abbreviations (case-sensitive whole tokens) -> primary long form."""
        edits = []

        def rep(m: re.Match) -> str:
            tok = m.group(0)
            lf = self.abbr_to_long.get(tok)
            if not lf or in_upper_run(text, m.start(), m.end()) or is_french_word(tok):
                return tok
            edits.append({"op": "expand", "from": tok, "to": lf})
            return lf

        new = re.sub(r"(?<![\w-])[A-Za-z][A-Za-z0-9\-]{1,9}(?![\w-])", rep, text)
        return new, edits


def telegraphic(text: str) -> tuple[str, list[dict]]:
    toks = re.findall(r"[\wÀ-ÿœŒ]+(?:[-'’/.][\wÀ-ÿœŒ]+)*|[<>≥≤=+%]", text)
    kept = []
    for t in toks:
        base = re.split(r"['’]", t)[-1] if re.match(r"^(?:[ldjnsc]|qu)['’]", t, re.I) else t
        f = fold(base)
        if f in KEEP_TELEGRAPHIC or not (f in FUNCTION_WORDS or (len(f) <= 2 and f.isalpha() and not base.isupper())):
            kept.append(base)
    new = " ".join(kept)
    return new, ([{"op": "telegraphic", "dropped_tokens": len(toks) - len(kept)}] if new != text else [])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=20261127)
    ap.add_argument("--glossary", default=str(HERE / "glossary_tas_v6.json"))
    ap.add_argument("--out", default=str(HERE / "sets"))
    args = ap.parse_args()
    tool = AbbrTool(Path(args.glossary))
    user_tool = AbbrTool(None, entries=USER_CITED_ABBREVIATIONS)
    counts: dict[str, dict] = {}
    for suite in SUITES:
        items = load_suite(suite, "dev")
        counts[suite] = {"n": len(items)}
        for pert in PERTURBATIONS:
            out_items, changed, ops = [], 0, {}
            for it in items:
                q = it.question
                if pert == "clean":
                    new, edits = q, []
                elif pert == "typo1":
                    new, edits = apply_typos(q, 1, rng_for(args.seed, pert, it.id))
                elif pert == "typo3":
                    r = rng_for(args.seed, pert, it.id)
                    new, edits = apply_typos(q, r.choice([2, 3]), r)
                elif pert == "noaccent":
                    new = strip_accents(q)
                    edits = [{"op": "noaccent"}] if new != q else []
                elif pert == "abbr":
                    new, edits = tool.abbreviate(q)
                elif pert == "expand":
                    new, edits = tool.expand(q)
                elif pert == "abbr_user":
                    new, edits = user_tool.abbreviate(q)
                else:
                    new, edits = telegraphic(q)
                for e in edits:
                    ops[e["op"]] = ops.get(e["op"], 0) + 1
                changed += new != q
                meta = dict(it.meta)
                meta["perturbation"] = {"name": pert, "seed": args.seed, "changed": new != q, "edits": edits}
                out_items.append(it.model_copy(update={"question": new, "meta": meta}))
            write_jsonl(out_items, Path(args.out) / suite / f"{pert}.jsonl")
            counts[suite][pert] = {"changed": changed, "ops": ops}
            print(f"{suite:15s} {pert:12s} changed {changed}/{len(items)} {ops}")
    (Path(args.out) / "counts.json").write_text(json.dumps(counts, indent=1, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
