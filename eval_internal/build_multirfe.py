"""Build the internal multi-RFE generalization set (synthetic, NOT medically validated).

Pipeline (all API calls through the Batch API, logged in reports/cost_ledger.csv):
  1. sample   : pick current, French recommendation documents (excluding the antibioprophylaxis
                lineage, covered by the official benchmark) stratified by year and domain; pick
                up to 3 anchor passages per document (graded recommendation, table, other).
  2. generate : Sonnet 5.5 writes one question per passage, anchored on a verbatim gold quote.
                Edition-comparison questions from lineages with several editions.
                Abstention questions on topics the catalogue does not cover.
  3. verify   : Opus 5.5, independent pass (answer present and unambiguous in the source,
                no verbatim copy, self-contained, clinically sensible) + programmatic checks
                (quote really in the passage, no 6-word overlap with the passage).
  4. write    : eval_internal/datasets/multirfe_synth.jsonl (common format, provenance
                llm_synthetic) and an audit trail in eval_internal/work/.

Usage:
  .venv/bin/python eval_internal/build_multirfe.py sample --n-docs 70
  .venv/bin/python eval_internal/build_multirfe.py generate
  .venv/bin/python eval_internal/build_multirfe.py verify
  .venv/bin/python eval_internal/build_multirfe.py write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag_sfar.evaluation.anthropic_batch import run_batch  # noqa: E402
from rag_sfar.evaluation.cost_ledger import estimate_cost  # noqa: E402
from rag_sfar.evaluation.datasets import EvalItem, GoldPassage, fold, tokens, write_jsonl  # noqa: E402

INDEX = ROOT / "index/table_aware_sota/metadata.sqlite"
WORK = ROOT / "eval_internal/work"
OUT = ROOT / "eval_internal/datasets/multirfe_synth.jsonl"
GEN_MODEL = "claude-sonnet-5-5"
VERIFY_MODEL = "claude-opus-5-5"
SEED = "multirfe-2026"
EXCLUDED_LINEAGES = {"antibioprophylaxie"}

RECO_RE = re.compile(
    r"\b(il (?:ne )?faut(?: probablement)?(?: pas)?|il est recommande|il n'est pas recommande|"
    r"les experts (?:suggerent|proposent|recommandent)|nous recommandons|nous suggerons|grade ?[12]|avis d'experts?)\b"
)


def _h(*parts: str) -> int:
    return int(hashlib.sha256("|".join(parts).encode()).hexdigest()[:12], 16)


# ------------------------------------------------------------------ 1. sample


def sample(n_docs: int, per_doc: int) -> None:
    db = sqlite3.connect(INDEX)
    docs = []
    for doc_id, title, year, payload in db.execute(
        "select doc_id, title, effective_year, payload_json from documents where is_latest_edition=1 and language='fr'"
    ):
        p = json.loads(payload)
        if p.get("doc_role") not in ("recommandation", "texte_court", "argumentaire", "tableaux_synthese"):
            continue
        if p.get("topic_lineage") in EXCLUDED_LINEAGES or "antibioprophylaxie" in fold(title):
            continue
        docs.append({"doc_id": doc_id, "title": title, "year": year or 0, "domain": (p.get("domains") or ["-"])[0],
                     "doc_type": p.get("doc_type"), "lineage": p.get("topic_lineage")})
    # Stratify: round-robin over (decade bucket, domain) in seeded order.
    buckets: dict[tuple, list] = defaultdict(list)
    for d in docs:
        buckets[(d["year"] // 5 * 5, d["domain"])].append(d)
    for b in buckets.values():
        b.sort(key=lambda d: _h(SEED, d["doc_id"]))
    order = sorted(buckets, key=lambda k: _h(SEED, str(k)))
    picked: list[dict] = []
    while len(picked) < n_docs and any(buckets.values()):
        for k in order:
            if buckets[k] and len(picked) < n_docs:
                picked.append(buckets[k].pop(0))

    anchors = []
    for d in picked:
        rows = db.execute(
            "select chunk_id, chunk_type, payload_json from chunks where doc_id=? and is_reference_section=0",
            (d["doc_id"],),
        ).fetchall()
        cands = {"reco": [], "table": [], "other": []}
        for chunk_id, ctype, payload in rows:
            p = json.loads(payload)
            text = p["text"]
            if not (250 <= len(text) <= 2500):
                continue
            if ctype in ("table_row_card", "table_markdown"):
                cands["table"].append((chunk_id, ctype, p))
            elif ctype == "recommendation_box" or RECO_RE.search(fold(text)):
                cands["reco"].append((chunk_id, ctype, p))
            elif ctype == "prose":
                cands["other"].append((chunk_id, ctype, p))
        chosen = []
        for kind in ("reco", "table", "other", "reco"):
            pool = sorted(cands[kind], key=lambda c: _h(SEED, c[0]))
            pool = [c for c in pool if c[0] not in {x[0] for x, _ in chosen}]
            if pool and len(chosen) < per_doc:
                chosen.append((pool[0], kind))
        for (chunk_id, ctype, p), kind in chosen:
            anchors.append({
                "anchor_id": f"{d['doc_id']}::{chunk_id}", "doc_id": d["doc_id"], "doc_title": d["title"],
                "year": d["year"], "domain": d["domain"], "kind": kind, "chunk_id": chunk_id,
                "section_path": p.get("section_path", ""), "text": p["text"],
            })

    # Edition-comparison anchors: lineages with >= 2 editions (latest vs previous).
    comps = []
    lineages: dict[str, list] = defaultdict(list)
    for doc_id, title, year, latest, payload in db.execute(
        "select doc_id, title, effective_year, is_latest_edition, payload_json from documents where language='fr'"
    ):
        p = json.loads(payload)
        lin = p.get("topic_lineage")
        if lin and lin not in EXCLUDED_LINEAGES and p.get("doc_role") in ("recommandation", "texte_court"):
            lineages[lin].append({"doc_id": doc_id, "title": title, "year": year or 0, "latest": bool(latest)})
    for lin, eds in sorted(lineages.items()):
        eds.sort(key=lambda e: e["year"])
        cur = [e for e in eds if e["latest"]]
        old = [e for e in eds if not e["latest"]]
        if not cur or not old:
            continue
        new_e, old_e = cur[-1], old[-1]

        def boxes(doc_id: str) -> str:
            rows = db.execute(
                "select payload_json from chunks where doc_id=? and is_reference_section=0 order by idx", (doc_id,)
            ).fetchall()
            texts = [json.loads(r[0])["text"] for r in rows]
            recos = [t for t in texts if RECO_RE.search(fold(t)) and len(t) < 1500]
            return "\n---\n".join(recos[:25])[:12000]

        new_text, old_text = boxes(new_e["doc_id"]), boxes(old_e["doc_id"])
        if len(new_text) < 500 or len(old_text) < 500:
            continue
        comps.append({
            "anchor_id": f"compare::{lin}", "lineage": lin, "new": new_e, "old": old_e,
            "new_text": new_text, "old_text": old_text,
        })

    catalogue = sorted({f"{t} ({y})" for (t, y) in db.execute("select title, effective_year from documents where language='fr'")})
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "anchors.json").write_text(json.dumps(anchors, ensure_ascii=False, indent=1), encoding="utf-8")
    (WORK / "compare_anchors.json").write_text(json.dumps(comps, ensure_ascii=False, indent=1), encoding="utf-8")
    (WORK / "catalogue.json").write_text(json.dumps(catalogue, ensure_ascii=False, indent=1), encoding="utf-8")
    kinds = defaultdict(int)
    for a in anchors:
        kinds[a["kind"]] += 1
    print(f"{len(picked)} docs, {len(anchors)} anchors {dict(kinds)}, {len(comps)} comparison lineages, {len(catalogue)} catalogue titles")


# ------------------------------------------------------------------ 2. generate

GEN_SYSTEM = """Tu construis un jeu de questions d'évaluation INTERNE pour un système de recherche documentaire sur les recommandations de la SFAR (anesthésie-réanimation). Ces questions servent à mesurer la généralisation du système ; elles seront marquées comme synthétiques et non validées médicalement.

Règles :
- La réponse doit se trouver explicitement et sans ambiguïté dans le passage fourni. Ne fais appel à aucune connaissance extérieure.
- La question doit être autonome : un anesthésiste qui ne voit pas le passage doit la comprendre (précise la population, le contexte clinique, l'acte). N'écris jamais « selon ce texte », « dans ce passage », ni le numéro d'une recommandation.
- Reformule : la question ne doit pas recopier le passage (aucune suite de 6 mots identique).
- `gold_quote` est une copie EXACTE (verbatim, au caractère près) d'un extrait du passage de 8 à 60 mots qui contient la réponse.
- `reference_answer` est courte (une phrase au plus). `key_terms` contient 1 à 3 termes ou valeurs courts (molécule, dose avec unité, seuil, conduite) qui doivent figurer dans une réponse correcte, écrits comme dans le passage.
- Si le passage ne permet pas une bonne question clinique (texte administratif, méthodologie, liste de références, contenu trop vague), mets `usable` à false.
"""

KIND_HINT = {
    "reco": "Le passage contient une recommandation. Pose une question dont la réponse est la conduite recommandée (et sa force si elle est indiquée).",
    "table": "Le passage est un tableau ou une ligne de tableau. Pose une question précise sur une valeur (dose, seuil, délai, indication) de ce tableau. question_type = table.",
    "other": "Pose de préférence un court cas clinique (2 phrases : patient, situation) suivi de la question « quelle conduite tenir ? ». question_type = clinical_case.",
}

GEN_SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "question": {"type": "string"},
        "question_type": {"type": "string", "enum": ["open", "table", "clinical_case"]},
        "reference_answer": {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "gold_quote": {"type": "string"},
        "tags": {"type": "array", "items": {"type": "string", "enum": ["dosage", "pediatric", "obstetric", "emergency", "icu", "drug_choice", "threshold", "timing", "contraindication"]}},
    },
    "required": ["usable", "question", "question_type", "reference_answer", "key_terms", "gold_quote", "tags"],
    "additionalProperties": False,
}

COMP_SYSTEM = """Tu construis des questions d'évaluation INTERNES (synthétiques, non validées médicalement) sur l'évolution des recommandations SFAR entre deux éditions.

À partir des extraits de recommandations de l'ancienne et de la nouvelle édition, écris UNE question sur un point qui a réellement changé (conduite, seuil, molécule, force de recommandation), formulée comme le ferait un clinicien (« qu'est-ce qui a changé entre … et … concernant … ? »). La réponse doit être explicite dans les deux extraits. `quote_new` et `quote_old` sont des copies EXACTES (8 à 60 mots) de chaque édition. Si aucun changement net et vérifiable n'apparaît, mets `usable` à false.
"""

COMP_SCHEMA = {
    "type": "object",
    "properties": {
        "usable": {"type": "boolean"},
        "question": {"type": "string"},
        "reference_answer": {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "quote_new": {"type": "string"},
        "quote_old": {"type": "string"},
    },
    "required": ["usable", "question", "reference_answer", "key_terms", "quote_new", "quote_old"],
    "additionalProperties": False,
}

ABST_SYSTEM = """Tu construis des questions d'évaluation INTERNES (synthétiques) pour mesurer si un système documentaire sait dire « le corpus ne couvre pas cette question ».

On te donne la liste des titres des recommandations SFAR disponibles. Écris 40 questions cliniques réalistes d'anesthésie, réanimation ou médecine périopératoire, posées comme par un interne, portant sur des sujets qui ne sont PAS traités par ces documents (vérifie avec les titres). Varie les spécialités. Évite les sujets trop proches d'un titre de la liste. Pas de questions hors médecine.
"""

ABST_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {"type": "object", "properties": {"question": {"type": "string"}, "topic": {"type": "string"}}, "required": ["question", "topic"], "additionalProperties": False}}},
    "required": ["questions"],
    "additionalProperties": False,
}


def _req(custom_id: str, model: str, system: str, user: str, schema: dict, max_tokens: int = 4000, effort: str = "medium") -> dict:
    return {
        "custom_id": custom_id,
        "params": {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        },
    }


def _cid(s: str) -> str:
    return "g" + hashlib.sha256(s.encode()).hexdigest()[:20]


def generate() -> None:
    anchors = json.loads((WORK / "anchors.json").read_text(encoding="utf-8"))
    comps = json.loads((WORK / "compare_anchors.json").read_text(encoding="utf-8"))
    catalogue = json.loads((WORK / "catalogue.json").read_text(encoding="utf-8"))
    reqs = []
    for a in anchors:
        user = (
            f"Document : {a['doc_title']} ({a['year']})\nSection : {a['section_path']}\n\n"
            f"Passage :\n<<<\n{a['text']}\n>>>\n\n{KIND_HINT[a['kind']]}"
        )
        reqs.append(_req(_cid("q::" + a["anchor_id"]), GEN_MODEL, GEN_SYSTEM, user, GEN_SCHEMA))
    for c in comps:
        user = (
            f"Recommandation : {c['lineage']}\n\nANCIENNE édition — {c['old']['title']} ({c['old']['year']}) :\n<<<\n{c['old_text']}\n>>>\n\n"
            f"NOUVELLE édition — {c['new']['title']} ({c['new']['year']}) :\n<<<\n{c['new_text']}\n>>>"
        )
        reqs.append(_req(_cid("c::" + c["anchor_id"]), GEN_MODEL, COMP_SYSTEM, user, COMP_SCHEMA, max_tokens=6000))
    reqs.append(_req(_cid("abstention"), GEN_MODEL, ABST_SYSTEM, "Titres disponibles :\n" + "\n".join(catalogue), ABST_SCHEMA, max_tokens=8000))
    est = sum(
        estimate_cost(GEN_MODEL, 1, len(r["params"]["system"] + r["params"]["messages"][0]["content"]) // 3, 1500, batch=True)
        for r in reqs
    )
    print(f"{len(reqs)} generation requests, estimated {est:.2f} $")
    run_batch(reqs, "eval_internal_generate", WORK / "gen_results.jsonl", est)


# ------------------------------------------------------------------ 3. verify

VERIFY_SYSTEM = """Tu es un relecteur exigeant (anesthésiste-réanimateur et méthodologiste). On te donne un passage d'une recommandation SFAR et une question d'évaluation générée automatiquement avec sa réponse de référence. Juge sans complaisance :
- answer_in_source : la réponse de référence est-elle explicitement et entièrement soutenue par le passage ?
- unambiguous : une seule réponse correcte possible au vu du passage ?
- self_contained : la question se comprend sans voir le passage (population, contexte précisés ; pas de « selon ce texte ») ?
- not_copied : la question reformule au lieu de recopier le passage ?
- clinically_sensible : la question a-t-elle un sens pour un clinicien ?
- verdict : keep si tous les critères sont vrais, sinon drop. Si seule la réponse de référence est imprécise, donne `corrected_answer` et garde.
"""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "answer_in_source": {"type": "boolean"},
        "unambiguous": {"type": "boolean"},
        "self_contained": {"type": "boolean"},
        "not_copied": {"type": "boolean"},
        "clinically_sensible": {"type": "boolean"},
        "corrected_answer": {"type": "string"},
        "verdict": {"type": "string", "enum": ["keep", "drop"]},
        "reason": {"type": "string"},
    },
    "required": ["answer_in_source", "unambiguous", "self_contained", "not_copied", "clinically_sensible", "corrected_answer", "verdict", "reason"],
    "additionalProperties": False,
}


def _quote_in(quote: str, text: str) -> bool:
    q, t = tokens(quote), " ".join(tokens(text))
    return len(q) >= 6 and " ".join(q) in t


def _max_overlap(question: str, text: str, n: int = 6) -> int:
    qt, tt = tokens(question), " ".join(tokens(text))
    best = 0
    for size in range(n, len(qt) + 1):
        if any(" ".join(qt[i : i + size]) in tt for i in range(len(qt) - size + 1)):
            best = size
        else:
            break
    return best


def _parse(rec: dict) -> dict | None:
    if rec.get("status") != "succeeded" or rec.get("stop_reason") not in ("end_turn", "stop_sequence"):
        return None
    try:
        return json.loads(rec["text"])
    except (json.JSONDecodeError, KeyError):
        return None


def _candidates() -> list[dict]:
    anchors = {a["anchor_id"]: a for a in json.loads((WORK / "anchors.json").read_text(encoding="utf-8"))}
    comps = {c["anchor_id"]: c for c in json.loads((WORK / "compare_anchors.json").read_text(encoding="utf-8"))}
    from rag_sfar.evaluation.anthropic_batch import read_cache

    gen = read_cache(WORK / "gen_results.jsonl")
    out = []
    for aid, a in anchors.items():
        g = _parse(gen.get(_cid("q::" + aid), {}))
        if not g or not g["usable"]:
            continue
        checks = {"quote_in_passage": _quote_in(g["gold_quote"], a["text"]), "max_copied_words": _max_overlap(g["question"], a["text"])}
        out.append({"cand_id": _cid("q::" + aid), "kind": a["kind"], "anchor": a, "gen": g, "checks": checks,
                    "source_text": a["text"], "doc_ids": [a["doc_id"]]})
    for aid, c in comps.items():
        g = _parse(gen.get(_cid("c::" + aid), {}))
        if not g or not g["usable"]:
            continue
        checks = {"quote_in_passage": _quote_in(g["quote_new"], c["new_text"]) and _quote_in(g["quote_old"], c["old_text"]),
                  "max_copied_words": 0}
        src = f"ANCIENNE ({c['old']['year']}):\n{c['old_text']}\n\nNOUVELLE ({c['new']['year']}):\n{c['new_text']}"
        out.append({"cand_id": _cid("c::" + aid), "kind": "comparison", "anchor": c, "gen": g, "checks": checks,
                    "source_text": src, "doc_ids": [c["new"]["doc_id"], c["old"]["doc_id"]]})
    ab = _parse(gen.get(_cid("abstention"), {}))
    if ab:
        for i, q in enumerate(ab["questions"]):
            out.append({"cand_id": f"abst{i:03d}", "kind": "abstention", "anchor": {}, "gen": q, "checks": {}, "source_text": "", "doc_ids": []})
    return out


ABST_VERIFY_SYSTEM = """On te donne une question clinique et les 10 passages les plus pertinents trouvés dans le corpus des recommandations SFAR. Indique si ces passages permettent de répondre à la question (même partiellement). Sois strict : si un passage traite directement du sujet, réponds covered = true."""

ABST_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"covered": {"type": "boolean"}, "reason": {"type": "string"}},
    "required": ["covered", "reason"],
    "additionalProperties": False,
}


def _bm25_top(question: str, k: int = 10) -> str:
    from rag_sfar.retrieval.vector_store import LocalVectorStore

    global _STORE
    try:
        _STORE
    except NameError:
        _STORE = LocalVectorStore.load(ROOT / "index/table_aware_sota")
    hits = _STORE.bm25.search(question, top_k=k * 3) if hasattr(_STORE, "bm25") else []
    texts = []
    for idx, _score in hits:
        ch = _STORE.chunks[idx]
        if ch.is_reference_section:
            continue
        texts.append(f"[{ch.doc_title} {ch.effective_year}] {ch.text[:900]}")
        if len(texts) >= k:
            break
    return "\n---\n".join(texts)


def verify() -> None:
    cands = _candidates()
    reqs = []
    for c in cands:
        if c["kind"] == "abstention":
            ctx = _bm25_top(c["gen"]["question"])
            user = f"Question : {c['gen']['question']}\n\nPassages :\n<<<\n{ctx}\n>>>"
            reqs.append(_req("v" + c["cand_id"], VERIFY_MODEL, ABST_VERIFY_SYSTEM, user, ABST_VERIFY_SCHEMA, max_tokens=3000, effort="low"))
            continue
        if not c["checks"]["quote_in_passage"] or c["checks"]["max_copied_words"] >= 8:
            continue  # programmatic rejection, no API call
        user = (
            f"Passage source :\n<<<\n{c['source_text']}\n>>>\n\nQuestion : {c['gen']['question']}\n"
            f"Réponse de référence : {c['gen']['reference_answer']}"
        )
        reqs.append(_req("v" + c["cand_id"], VERIFY_MODEL, VERIFY_SYSTEM, user, VERIFY_SCHEMA, max_tokens=4000, effort="medium"))
    est = sum(
        estimate_cost(VERIFY_MODEL, 1, len(r["params"]["system"] + r["params"]["messages"][0]["content"]) // 3, 1200, batch=True)
        for r in reqs
    )
    print(f"{len(cands)} candidates, {len(reqs)} verification requests, estimated {est:.2f} $")
    run_batch(reqs, "eval_internal_verify", WORK / "verify_results.jsonl", est)


# ------------------------------------------------------------------ 4. write


def write() -> None:
    from rag_sfar.evaluation.anthropic_batch import read_cache

    cands = _candidates()
    ver = read_cache(WORK / "verify_results.jsonl")
    items, audit = [], []
    for c in cands:
        v = _parse(ver.get("v" + c["cand_id"], {}))
        g = c["gen"]
        status = "kept"
        if c["kind"] == "abstention":
            if not v or v["covered"]:
                status = "dropped_covered_or_unverified"
        elif not c["checks"].get("quote_in_passage"):
            status = "dropped_quote_not_in_passage"
        elif c["checks"].get("max_copied_words", 0) >= 8:
            status = "dropped_copied"
        elif not v or v["verdict"] != "keep":
            status = "dropped_verifier"
        audit.append({"cand_id": c["cand_id"], "kind": c["kind"], "status": status, "question": g.get("question"),
                      "checks": c["checks"], "verifier": v})
        if status != "kept":
            continue
        if c["kind"] == "abstention":
            items.append(EvalItem(
                id=f"MR-{c['cand_id']}", suite="multirfe_synth", question=g["question"], question_type="abstention",
                provenance="llm_synthetic", should_abstain=True, current_edition_required=False,
                tags=["abstention"], group=c["cand_id"], meta={"topic": g.get("topic", "")},
            ))
            continue
        ref = (v.get("corrected_answer") or "").strip() or g["reference_answer"]
        if c["kind"] == "comparison":
            a = c["anchor"]
            items.append(EvalItem(
                id=f"MR-{c['cand_id']}", suite="multirfe_synth", question=g["question"], question_type="comparison",
                provenance="llm_synthetic", reference_answer=ref, answer_key={"all_of": g["key_terms"]} if g["key_terms"] else {},
                gold_doc_ids=c["doc_ids"],
                gold_passages=[GoldPassage(doc_id=a["new"]["doc_id"], quote=g["quote_new"]), GoldPassage(doc_id=a["old"]["doc_id"], quote=g["quote_old"])],
                current_edition_required=False, source_doc_ids=[a["new"]["doc_id"]], group=a["lineage"],
                tags=["edition_diff"], meta={"lineage": a["lineage"], "verifier_reason": v.get("reason", "")},
            ))
            continue
        a = c["anchor"]
        qtype = g["question_type"] if g["question_type"] in ("open", "table", "clinical_case") else "open"
        items.append(EvalItem(
            id=f"MR-{c['cand_id']}", suite="multirfe_synth", question=g["question"], question_type=qtype,
            provenance="llm_synthetic", reference_answer=ref,
            answer_key={"all_of": g["key_terms"]} if g["key_terms"] else {},
            gold_doc_ids=[a["doc_id"]], gold_passages=[GoldPassage(doc_id=a["doc_id"], quote=g["gold_quote"])],
            source_doc_ids=[a["doc_id"]], group=a["doc_id"], tags=sorted(set(g.get("tags", [])) | {a["kind"]}),
            meta={"doc_title": a["doc_title"], "year": a["year"], "domain": a["domain"], "chunk_id": a["chunk_id"],
                  "anchor_kind": a["kind"], "verifier_reason": v.get("reason", "")},
        ))
    write_jsonl(items, OUT)
    (WORK / "audit_trail.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")
    counts = defaultdict(int)
    for r in audit:
        counts[(r["kind"], r["status"])] += 1
    for k, n in sorted(counts.items()):
        print(k, n)
    print(f"{len(items)} items -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n-docs", type=int, default=70)
    s.add_argument("--per-doc", type=int, default=3)
    sub.add_parser("generate")
    sub.add_parser("verify")
    sub.add_parser("write")
    args = ap.parse_args()
    {"sample": lambda: sample(args.n_docs, args.per_doc), "generate": generate, "verify": verify, "write": write}[args.cmd]()
