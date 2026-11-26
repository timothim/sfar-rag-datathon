"""Reference-guided LLM-as-a-judge with explicit rubric, structured output and calibration.

The judge scores one answer against the reference answer (and, when given, the cited sources):
  correctness      : correct | partial | incorrect
  abstained        : the answer declines to answer / says the corpus does not cover it
  serious_error    : none | wrong_drug | wrong_dose | obsolete_as_current | unsupported_claim |
                     missing_abstention | other   (principle 7, counted apart)
  faithful         : every clinical claim is supported by the provided sources (None if no sources)
  justification    : one short sentence

Backends: any object with `complete(system_prompt, user_prompt) -> (text, usage)` (local MLX or
OpenAI-compatible clients from generation/client.py), or `AnthropicJudgeBackend` (logs cost).

A judge is only used for a conclusion if its measured agreement is sufficient: `calibrate()`
computes Cohen's kappa between the judge's correctness and deterministic answer keys on
closed questions (MCQ, molecule lists), plus position/length bias probes.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

JUDGE_SYSTEM = """Tu es un évaluateur clinique rigoureux (anesthésie-réanimation). Tu compares la réponse d'un système à la réponse de référence d'une question portant sur les recommandations de la SFAR.

Grille :
- correctness : "correct" si la réponse donne la même conduite que la référence (synonymes, formulations et détails supplémentaires exacts acceptés) ; "partial" si elle est incomplète mais sans contresens ; "incorrect" si elle contredit la référence, propose une autre molécule/dose/conduite, ou répond à côté. Une réponse qui propose plusieurs options dont une seule correcte sans trancher est "partial".
- abstained : true si la réponse refuse de répondre ou dit que les documents ne couvrent pas la question.
- serious_error : l'erreur la plus grave, parmi : none, wrong_drug (mauvaise molécule), wrong_dose (dose, unité, fréquence ou seuil faux), obsolete_as_current (recommandation périmée présentée comme en vigueur), unsupported_claim (affirmation clinique importante absente des sources fournies), missing_abstention (répond alors que la référence indique que la question n'est pas couverte), other.
- faithful : si des sources sont fournies, true si chaque affirmation clinique de la réponse est soutenue par elles ; sinon null.
- justification : une phrase courte.

Ne te laisse pas influencer par la longueur ni par le ton assuré de la réponse. Réponds uniquement par un objet JSON avec ces 5 clés."""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "correctness": {"type": "string", "enum": ["correct", "partial", "incorrect"]},
        "abstained": {"type": "boolean"},
        "serious_error": {"type": "string", "enum": ["none", "wrong_drug", "wrong_dose", "obsolete_as_current", "unsupported_claim", "missing_abstention", "other"]},
        "faithful": {"type": ["boolean", "null"]},
        "justification": {"type": "string"},
    },
    "required": ["correctness", "abstained", "serious_error", "faithful", "justification"],
    "additionalProperties": False,
}

_DEFAULT = {"correctness": "incorrect", "abstained": False, "serious_error": "other", "faithful": None,
            "justification": "unparseable judge output", "parse_error": True}


def build_user_prompt(question: str, reference: str, answer: str, sources: str = "", should_abstain: bool = False) -> str:
    ref = reference or ("(La question n'est pas couverte par les recommandations : la bonne réponse est de s'abstenir.)" if should_abstain else "(aucune)")
    parts = [f"Question :\n{question}", f"Réponse de référence :\n{ref}", f"Réponse du système :\n{answer}"]
    if sources:
        parts.append(f"Sources fournies au système :\n<<<\n{sources[:12000]}\n>>>")
    return "\n\n".join(parts)


def parse_judgement(text: str) -> dict[str, Any]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return dict(_DEFAULT)
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return dict(_DEFAULT)
    out = dict(_DEFAULT)
    out.pop("parse_error")
    for k in JUDGE_SCHEMA["properties"]:
        if k in obj:
            out[k] = obj[k]
    if out["correctness"] not in ("correct", "partial", "incorrect"):
        out["correctness"] = "incorrect"
    return out


class AnthropicJudgeBackend:
    """Claude judge with structured outputs; every call is logged in the cost ledger."""

    def __init__(self, model: str = "claude-sonnet-5-5", experiment: str = "judge", effort: str = "low") -> None:
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model
        self.experiment = experiment
        self.effort = effort

    def complete(self, system_prompt: str, user_prompt: str) -> tuple[str, dict[str, int]]:
        from rag_sfar.evaluation.cost_ledger import record_usage

        msg = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": JUDGE_SCHEMA}},
        )
        record_usage(self.experiment, self.model, msg.usage)
        text = next((b.text for b in msg.content if b.type == "text"), "")
        return text, {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}


class Judge:
    def __init__(self, backend: Any, label: str = "") -> None:
        self.backend = backend
        self.label = label or getattr(backend, "model", "judge")

    def judge(self, question: str, reference: str, answer: str, sources: str = "", should_abstain: bool = False) -> dict[str, Any]:
        text, _usage = self.backend.complete(JUDGE_SYSTEM, build_user_prompt(question, reference, answer, sources, should_abstain))
        return parse_judgement(text)


# ---------------------------------------------------------------- calibration


def cohen_kappa(a: list[int], b: list[int]) -> float:
    n = len(a)
    if n == 0:
        return float("nan")
    labels = sorted(set(a) | set(b))
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pe = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def calibrate(judge: Judge, cases: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """`cases`: dicts with question, reference, answer, truth (1/0 from a deterministic key).

    Returns agreement, kappa, confusion counts and a length-bias probe (accuracy of the judge on
    answers padded with irrelevant but true-sounding text should not change)."""
    truth, pred, rows = [], [], []
    for c in cases:
        j = judge.judge(c["question"], c["reference"], c["answer"])
        p = 1 if j["correctness"] == "correct" else 0
        truth.append(int(c["truth"]))
        pred.append(p)
        rows.append({**c, "judge": j})
    agree = sum(1 for x, y in zip(truth, pred) if x == y) / max(1, len(truth))
    conf = {"tp": sum(1 for x, y in zip(truth, pred) if x and y), "tn": sum(1 for x, y in zip(truth, pred) if not x and not y),
            "fp": sum(1 for x, y in zip(truth, pred) if not x and y), "fn": sum(1 for x, y in zip(truth, pred) if x and not y)}
    return {"judge": judge.label, "n": len(truth), "agreement": agree, "kappa": cohen_kappa(truth, pred),
            "confusion": conf, "parse_errors": sum(1 for r in rows if r["judge"].get("parse_error")), "rows": rows}


LENGTH_PADDING = (
    " Il convient par ailleurs de rappeler l'importance d'une évaluation préopératoire soigneuse, "
    "d'une traçabilité rigoureuse dans le dossier et d'une concertation pluridisciplinaire adaptée au contexte."
)


def length_bias_probe(judge: Judge, cases: list[dict[str, Any]]) -> dict[str, Any]:
    """Same answers with neutral padding: a robust judge gives the same verdicts."""
    changed = 0
    for c in cases:
        a = judge.judge(c["question"], c["reference"], c["answer"])["correctness"]
        b = judge.judge(c["question"], c["reference"], c["answer"] + LENGTH_PADDING)["correctness"]
        changed += a != b
    return {"n": len(cases), "verdict_changed": changed, "rate": changed / max(1, len(cases))}
