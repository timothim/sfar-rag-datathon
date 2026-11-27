"""Deterministic answer check: every dose (number + unit), every drug name and every [Sx]
citation of an answer must be found in the excerpts shown to the model.

Generic by construction: units are a closed list of clinical units; drug names are the tracked
molecule list of `verifier.py` plus words carrying an international non-proprietary name (INN)
stem suffix (-cilline, -mycine, -floxacine, -parine, -xaban, ...). No clinical content of an
evaluation set is used.

Levels:
- `unsupported`: the token is in no excerpt shown to the model (strong signal: hallucination or
  parametric knowledge);
- `not_in_cited`: present in the context but not in the excerpts cited by the same sentence
  (weaker: citation error or synthesis).
`flagged` = invalid citation, or at least one `unsupported` dose/drug, or a non-abstention
answer without any citation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag_sfar.generation.verifier import TRACKED_MOLECULES
from rag_sfar.retrieval.medical_lexicon import fold_accents
from rag_sfar.schemas import RetrievedChunk

_UNITS = (
    r"mg/kg/h|mg/kg/j|mg/kg|µg/kg/min|µg/kg/h|µg/kg|μg/kg|mcg/kg|g/kg|ui/kg|u/kg|ml/kg/h|ml/kg|"
    r"mmol/l|mg/l|g/l|g/dl|µg/l|ng/ml|mg/h|ml/h|ml/min|l/min|mmhg|cm\s?h2o|"
    r"mg|g|µg|μg|mcg|ui|u|ml|l|meq|"
    r"minutes?|min|heures?|h|jours?|j|semaines?|mois|ans|"
    r"%"
)
_NUM_UNIT = re.compile(
    rf"(?<![\w.,])(\d+(?:[   ]\d{{3}})*(?:[.,]\d+)?)\s*(?:à|-|–)?\s*({_UNITS})(?![a-z0-9])",
    re.I,
)
_INN = re.compile(
    r"\b[a-z]{3,}(?:cilline|mycine|micine|floxacine|cycline|cefal\w*|parine|xaban|gatran|"
    r"azole|conazole|fungine|penem|peneme|pril|sartan|olol|dipine|prazole|curium|curonium|"
    r"caine|vir|mab|platine|setron|tidine|statine)\b"
)
_CITE_GROUP = re.compile(r"\[(S\d+(?:\s*[,;–-]\s*S?\d+)*)\]")


def cited_ids(text: str) -> list[int]:
    """Source numbers cited in `text`: [S1], [S1, S4], [S2-S4] (range expanded)."""
    out: list[int] = []
    for grp in _CITE_GROUP.findall(text):
        parts = re.split(r"\s*([,;–-])\s*", grp)
        nums = [int(x.lstrip("S")) for x in parts[0::2]]
        seps = parts[1::2]
        out.append(nums[0])
        for sep, n in zip(seps, nums[1:]):
            if sep in "–-" and n > out[-1]:
                out.extend(range(out[-1] + 1, n + 1))
            else:
                out.append(n)
    return out


def _norm_text(text: str) -> str:
    t = fold_accents(text.lower()).replace("μ", "µ")
    t = re.sub(r"(?<=\d)[   ](?=\d{3}\b)", "", t)  # thousands separators
    t = t.replace(",", ".")
    return re.sub(r"\s+", " ", t)


def _norm_dose(num: str, unit: str) -> str:
    n = re.sub(r"[   ]", "", num).replace(",", ".")
    if "." in n:
        n = n.rstrip("0").rstrip(".")
    u = re.sub(r"\s+", "", fold_accents(unit.lower())).replace("μ", "µ").replace("mcg", "µg")
    u = {"heure": "h", "heures": "h", "minute": "min", "minutes": "min", "jour": "j", "jours": "j", "semaine": "semaines"}.get(u, u)
    return f"{n} {u}"


def _pre(text: str) -> str:
    """Typographic normalisation of units: HTML sub/superscripts (cmH<sub>2</sub>O,
    g l<sup>-1</sup>), "x l-1" -> "x/l", "Gauge" -> "G"."""
    t = re.sub(r"</?su[bp]>", "", text, flags=re.I)
    t = re.sub(r"(?i)\b([a-zµμ]{1,4})\s*(?:\.|\s)\s*([a-z]{1,3})\s*-1\b", r"\1/\2", t)
    t = re.sub(r"(?i)\bgauges?\b", "G", t)
    return t


def doses(text: str) -> set[str]:
    return {_norm_dose(m.group(1), m.group(2)) for m in _NUM_UNIT.finditer(_pre(text))}


def drugs(text: str) -> set[str]:
    t = fold_accents(text.lower())
    found = {m for m in TRACKED_MOLECULES if re.search(rf"\b{re.escape(m)}\b", t)}
    found |= set(_INN.findall(t))
    return found


def _sentences(answer: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", answer)
    return [p for p in parts if p.strip()]


@dataclass
class AnswerCheck:
    flagged: bool = False
    invalid_citations: list[str] = field(default_factory=list)
    unsupported_doses: list[str] = field(default_factory=list)
    unsupported_drugs: list[str] = field(default_factory=list)
    doses_not_in_cited: list[str] = field(default_factory=list)
    drugs_not_in_cited: list[str] = field(default_factory=list)
    uncited: bool = False
    n_doses: int = 0
    n_drugs: int = 0

    def reasons(self) -> list[str]:
        out = []
        if self.invalid_citations:
            out.append("citations inexistantes : " + ", ".join(self.invalid_citations))
        if self.unsupported_doses:
            out.append("doses absentes des extraits : " + ", ".join(self.unsupported_doses))
        if self.unsupported_drugs:
            out.append("molécules absentes des extraits : " + ", ".join(self.unsupported_drugs))
        if self.uncited:
            out.append("réponse sans citation")
        return out


def check_answer(answer: str, passages: list[RetrievedChunk], is_abstention: bool = False, query: str = "") -> AnswerCheck:
    """Check an answer against the passages shown to the model ([S1] = passages[0]). Values and
    drug names stated in the question itself (patient data) are accepted."""
    res = AnswerCheck()
    n = len(passages)
    texts = [_norm_text(p.chunk.text) for p in passages]
    ctx_doses = set().union(*(doses(p.chunk.text) for p in passages)) if passages else set()
    ctx_all = " ".join(texts) + " " + _norm_text(query)
    ctx_doses |= doses(query)
    cited = sorted(set(cited_ids(answer)))
    res.invalid_citations = [f"S{i}" for i in cited if i < 1 or i > n]
    res.uncited = (not cited) and not is_abstention

    # Ignore the trailing "Source :" line (titles and years are not doses).
    body = re.split(r"(?im)^\s*\**\s*sources?\s*\**\s*:", answer)[0]
    for sent in _sentences(body):
        s_cites = [i for i in cited_ids(sent) if 1 <= i <= n]
        s_ctx_doses = set().union(*(doses(passages[i - 1].chunk.text) for i in s_cites)) if s_cites else set()
        s_ctx = " ".join(texts[i - 1] for i in s_cites)
        for d in doses(sent):
            res.n_doses += 1
            if d not in ctx_doses:
                res.unsupported_doses.append(d)
            elif s_cites and d not in s_ctx_doses:
                res.doses_not_in_cited.append(d)
        for g in drugs(sent):
            res.n_drugs += 1
            if not re.search(rf"\b{re.escape(g)}\b", ctx_all):
                res.unsupported_drugs.append(g)
            elif s_cites and not re.search(rf"\b{re.escape(g)}\b", s_ctx):
                res.drugs_not_in_cited.append(g)
    for k in ("unsupported_doses", "unsupported_drugs", "doses_not_in_cited", "drugs_not_in_cited"):
        setattr(res, k, sorted(set(getattr(res, k))))
    res.flagged = bool(res.invalid_citations or res.unsupported_doses or res.unsupported_drugs or res.uncited)
    return res
