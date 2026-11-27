"""Generation stage (B3): thinking switch, sampling options, generation budget independent of the
retrieval flags, structured context (merging, tables, order, headers), coverage gate.

All texts are synthetic (written for these tests, not taken from an evaluation set)."""

from __future__ import annotations

from rag_sfar.config import RetrievalConfig
from rag_sfar.generation.client import (
    LocalMlxLLM,
    OpenAICompatibleLLM,
    SfarRagEngine,
    build_generation_context,
    strip_reasoning,
)
from rag_sfar.generation.context import (
    assemble_context,
    drop_covered_cards,
    markdown_table_as_rows,
    merge_adjacent_chunks,
)
from rag_sfar.generation.prompts import ABSTENTION_SENTENCE
from rag_sfar.generation.settings import (
    GENERATION_PRESETS,
    GenerationConfig,
    parse_generation_overrides,
    resolve_generation_config,
)
from rag_sfar.schemas import Chunk, QueryAnalysis, RetrievedChunk


def _rc(cid, text, idx, doc="d1", score=1.0, ctype="prose", section="S > A", **kw) -> RetrievedChunk:
    kw.setdefault("doc_title", "Recommandation test")
    kw.setdefault("effective_year", 2024)
    c = Chunk(chunk_id=cid, doc_id=doc, chunk_index=idx, text=text, indexed_text=text, chunk_type=ctype,
              section_path=section, **kw)
    return RetrievedChunk(chunk=c, final_score=score)


def _analysis(q="question test") -> QueryAnalysis:
    return QueryAnalysis(original_query=q, expanded_query=q)


# ---------------------------------------------------------------- thinking / sampling


class _FakeTokenizer:
    def __init__(self):
        self.kwargs = None

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, **kwargs):
        self.kwargs = kwargs
        return "PROMPT"


def test_mlx_passes_enable_thinking_to_chat_template():
    llm = LocalMlxLLM.__new__(LocalMlxLLM)
    llm._tokenizer = _FakeTokenizer()
    llm._format_prompt("sys", "user", enable_thinking=False)
    assert llm._tokenizer.kwargs == {"enable_thinking": False}
    llm._format_prompt("sys", "user", enable_thinking=None)
    assert llm._tokenizer.kwargs == {}  # template default untouched


def test_openai_request_sends_chat_template_kwargs_only_when_set():
    llm = OpenAICompatibleLLM.__new__(OpenAICompatibleLLM)
    llm.model, llm.temperature, llm.max_tokens = "m", 0.0, 100
    llm.options = {"enable_thinking": None, "top_p": 0.0, "top_k": 0, "presence_penalty": 0.0}
    kw = llm._request_kwargs(None, None, {})
    assert "extra_body" not in kw and "top_p" not in kw
    kw = llm._request_kwargs(0.7, 50, {"enable_thinking": False, "top_p": 0.8, "top_k": 20, "presence_penalty": 1.5})
    assert kw["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}, "top_k": 20}
    assert kw["top_p"] == 0.8 and kw["presence_penalty"] == 1.5 and kw["temperature"] == 0.7 and kw["max_tokens"] == 50


def test_strip_reasoning():
    assert strip_reasoning("<think>\nplan\n</think>\n\nRéponse [S1]") == "Réponse [S1]"
    assert strip_reasoning("<think>\n\n</think>\n\nRéponse") == "Réponse"
    assert strip_reasoning("<think>coupé en cours de réflexion") == ""
    assert strip_reasoning("Réponse sans balise") == "Réponse sans balise"


def test_overrides_and_presets():
    g = parse_generation_overrides(GenerationConfig(), "max_context_chars=12000+enable_thinking=false+context_order=document+top_p=0.8")
    assert g.max_context_chars == 12000 and g.enable_thinking is False and g.context_order == "document" and g.top_p == 0.8
    assert resolve_generation_config("wide").selection == "budget"
    assert GENERATION_PRESETS["small"].max_context_chunks == 6


# ---------------------------------------------------------------- budget independent of retrieval flags


def test_wide_budget_ignores_retrieval_pruning_flag():
    retrieved = [_rc(f"c{i}", f"Texte numéro {i}. " * 20, i, doc=f"d{i}") for i in range(20)]
    cfg = RetrievalConfig(use_context_pruning=True)
    legacy, _ = build_generation_context(retrieved, _analysis(), cfg, "q")
    assert len(legacy) <= 6
    wide, block = build_generation_context(retrieved, _analysis(), cfg, "q", gen_config=GENERATION_PRESETS["wide"])
    assert len(wide) == 20 and "[S20]" in block
    small = GenerationConfig(selection="budget", max_context_chunks=4, max_context_chars=10**6)
    assert len(build_generation_context(retrieved, _analysis(), cfg, "q", gen_config=small)[0]) == 4


# ---------------------------------------------------------------- structured context


def test_merge_adjacent_chunks_in_reading_order():
    a = _rc("a", "Deuxième paragraphe.", 11, score=0.9)
    b = _rc("b", "Premier paragraphe.", 10, score=0.5)
    c = _rc("c", "Autre partie.", 40, score=0.8)
    passages = merge_adjacent_chunks([a, c, b])
    texts = [[r.chunk.chunk_id for r in p.items] for p in passages]
    assert ["b", "a"] in texts and ["c"] in texts
    out, block = assemble_context([a, c, b], GenerationConfig(context_format="structured", merge_adjacent=True,
                                                               selection="budget", max_context_chunks=99,
                                                               max_context_chars=10**6, context_order="rank"))
    assert len(out) == 2
    assert block.index("Premier paragraphe.") < block.index("Deuxième paragraphe.")
    assert out[0].chunk.chunk_id == "b+a"  # best-ranked passage first, chunks in text order


TABLE = """| Acte | Molécule | Dose |
| --- | --- | --- |
| **Groupe un** |  |  |
| Geste alpha | Produit X | 2 g |
| Geste beta | Produit Y |  |
"""


def test_markdown_table_rows_keep_columns_and_subcategory():
    rows = markdown_table_as_rows(TABLE)
    assert "- [Groupe un] Acte : Geste alpha | Molécule : Produit X | Dose : 2 g" in rows
    # an empty cell is omitted, never shifted into the next column
    assert "- [Groupe un] Acte : Geste beta | Molécule : Produit Y" in rows
    assert "Dose : \n" not in rows


def test_drop_row_card_covered_by_parent_table():
    table = _rc("t", TABLE, 5, ctype="table_markdown")
    card = _rc("r", "Sous-catégorie : Groupe un\nActe : Geste alpha | Molécule : Produit X | Dose : 2 g", 6, ctype="table_row_card")
    other = _rc("o", "Acte : Geste gamma | Molécule : Produit Z | Dose : 1 g", 7, ctype="table_row_card")
    kept = [r.chunk.chunk_id for r in drop_covered_cards([table, card, other])]
    assert kept == ["t", "o"]


def test_rich_header_states_edition_and_strength():
    old = _rc("o", "Ancien texte.", 1, doc="old", is_latest_edition=False, superseded_by="Édition 2026",
              grade_levels=["GRADE 1", "Grade 1", "Accord fort"])
    _, block = assemble_context([old], GenerationConfig(context_format="structured", source_header="rich",
                                                        selection="budget", max_context_chunks=9, max_context_chars=10**6))
    assert "ÉDITION ANTÉRIEURE, remplacée par Édition 2026" in block
    assert "GRADE 1, Accord fort" in block


def test_document_order_groups_documents():
    r = [_rc("x1", "x1", 1, doc="X", score=0.9), _rc("y1", "y1", 1, doc="Y", score=0.8), _rc("x9", "x9", 9, doc="X", score=0.7)]
    out, _ = assemble_context(r, GenerationConfig(context_format="structured", context_order="document",
                                                  selection="budget", max_context_chunks=9, max_context_chars=10**6))
    assert [o.chunk.chunk_id for o in out] == ["x1", "x9", "y1"]


# ---------------------------------------------------------------- coverage gate


class _CountingLLM:
    model = "counting"

    def __init__(self):
        self.n = 0

    def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None, **opts):
        self.n += 1
        self.last_user = user_prompt
        return "Réponse [S1].", {}


def test_coverage_gate_refuse_and_note():
    retrieved = [_rc("a", "Texte voisin.", 1)]
    llm = _CountingLLM()
    eng = SfarRagEngine(retriever=None, llm=llm)
    timings = {"coverage_supported": 0.0}
    r = eng.generate("q", retrieved, _analysis(), timings, mode="clinical_concise", config=RetrievalConfig(),
                     gen_config=GENERATION_PRESETS["wide"].replace(coverage_gate="refuse"))
    assert r.answer == ABSTENTION_SENTENCE and llm.n == 0 and r.extra["coverage_refused"]
    r = eng.generate("q", retrieved, _analysis(), timings, mode="clinical_concise", config=RetrievalConfig(),
                     gen_config=GENERATION_PRESETS["wide"].replace(coverage_gate="note"))
    assert llm.n == 1 and "aucun passage proche" in llm.last_user
    # covered query: no note, LLM called
    eng.generate("q", retrieved, _analysis(), {"coverage_supported": 1.0}, mode="clinical_concise",
                 config=RetrievalConfig(), gen_config=GENERATION_PRESETS["wide"].replace(coverage_gate="refuse"))
    assert llm.n == 2 and "aucun passage proche" not in llm.last_user


# ---------------------------------------------------------------- answer check


def test_answer_check_doses_drugs_citations():
    from rag_sfar.generation.answer_check import check_answer, doses

    assert doses("2g IVL puis 1 g toutes les 4h, 30 mg/kg") == {"2 g", "1 g", "4 h", "30 mg/kg"}
    passages = [_rc("a", "Produit : céfazoline 2g IVL, réinjection 1g si durée > 4h.", 1),
                _rc("b", "Autre : vancomycine 15 mg/kg.", 2)]
    ok = check_answer("Céfazoline 2 g IV, réinjection 1 g après 4 h [S1].\nSource : RFE 2024", passages)
    assert not ok.flagged and ok.n_doses == 3
    bad = check_answer("Céfazoline 3 g [S1] ou gentamicine [S2] [S7].", passages)
    assert bad.flagged and "3 g" in bad.unsupported_doses and "gentamicine" in bad.unsupported_drugs
    assert bad.invalid_citations == ["S7"]
    swapped = check_answer("Vancomycine 15 mg/kg [S1].", passages)
    assert not swapped.flagged and swapped.doses_not_in_cited == ["15 mg/kg"]
    assert check_answer("Pas de recommandation.", passages).uncited
    assert not check_answer("Les recommandations ne traitent pas cette question.", passages, is_abstention=True).flagged


def test_section_population_in_rich_header():
    from rag_sfar.generation.context import section_populations

    assert section_populations("Champ 3. Disciplines pédiatriques et néonatales > Partie 1") == ["enfant", "nouveau-né"]
    assert section_populations("Champ 2. Disciplines adultes > Orthopédie") == ["adulte"]
    rc = _rc("p", "Ligne.", 1, section="Champ 3. Disciplines pédiatriques > Partie 1")
    _, block = assemble_context([rc], GenerationConfig(context_format="structured", source_header="rich",
                                                       selection="budget", max_context_chunks=9, max_context_chars=10**6))
    assert "Population (titre de section) : enfant" in block


def test_cited_ids_groups_and_ranges():
    from rag_sfar.generation.answer_check import cited_ids

    assert cited_ids("a [S1] b [S1, S4] c [S2-S4] d [S5–6]") == [1, 1, 4, 2, 3, 4, 5, 6]


def test_answer_check_erratum_superseded_value():
    from rag_sfar.generation.answer_check import check_answer

    p = [_rc("e", "Dose de 10 µg/kg [corrigé selon l'erratum officiel publié dans le même document ; "
                  "texte initial : « 10 mg/kg »] en intraveineux.", 1)]
    assert not check_answer("10 µg/kg en IV [S1] (valeur corrigée par erratum).", p).flagged
    bad = check_answer("10 mg/kg en IV [S1].", p)
    assert bad.flagged and bad.unsupported_doses == ["10 mg/kg"]


def test_engine_routes_lettered_options_to_mcq_mode():
    from rag_sfar.generation.client import has_lettered_options, route_mode

    q = "Quelle conduite est exacte ?\nA. Première option\nB. Deuxième option\nC. Troisième"
    assert has_lettered_options(q) and route_mode(q, "clinical_concise") == "clinical_mcq"
    assert not has_lettered_options("Faut-il une dose de 2 g ?\nA noter : patient obèse")
    assert route_mode("Question ouverte ?", "clinical_concise") == "clinical_concise"
    assert route_mode(q, "benchmark_open") == "benchmark_open"  # explicit modes untouched

    class _MCQLLM:
        model = "m"

        def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None, **o):
            self.system = system_prompt
            return "A : faux\nB : exact [S1]\nRÉPONSE : B (SFAR 2024 [S1])", {}

    llm = _MCQLLM()
    r = SfarRagEngine(retriever=None, llm=llm).generate(q, [_rc("a", "Texte.", 1)], _analysis(q), {},
                                                      mode="clinical_concise", config=RetrievalConfig())
    assert r.mode == "clinical_mcq" and r.answer.startswith("B") and "QCM" not in r.answer


def test_population_dependency_signal():
    from rag_sfar.generation.context import population_dependency

    a = _rc("a", "Acte : X | Molécule : P", 1, ctype="table_row_card", populations=["adulte"])
    k = _rc("k", "Acte : X | Molécule : P 30 mg/kg", 2, ctype="table_row_card", populations=["pediatrie"])
    assert population_dependency("Quelle antibioprophylaxie pour l'acte X ?", [a, k])
    assert not population_dependency("Quelle antibioprophylaxie pour l'acte X chez un enfant de 4 ans ?", [a, k])
    assert not population_dependency("Quelle antibioprophylaxie pour l'acte X ?", [a])


# ---------------------------------------------------------------- production profile: served == evaluated

import importlib.util
import json as _json
from pathlib import Path as _Path

_ROOT = _Path(__file__).resolve().parents[1]


def _gen_replay():
    spec = importlib.util.spec_from_file_location("gen_replay", _ROOT / "eval_internal" / "gen_replay.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Recorder:
    model = "recorder"

    def __init__(self):
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=None, max_tokens=None, **opts):
        self.calls.append((system_prompt, user_prompt, max_tokens, dict(opts)))
        return "Réponse : B\nLa conduite est décrite [S1].", {}


def _synthetic_retriever():
    from rag_sfar.retrieval.bm25 import BM25Index
    from rag_sfar.retrieval.pipeline import SfarRagRetriever
    from rag_sfar.retrieval.vector_store import LocalVectorStore
    from rag_sfar.schemas import DocumentMetadata

    texts = [
        ("t", "table_markdown", "| Acte | Molécule | Dose |\n| --- | --- | --- |\n| Geste alpha | Produit X | 2 g |"),
        ("r", "table_row_card", "Acte : Geste alpha | Molécule : Produit X | Dose : 2 g"),
        ("p", "prose", "Le geste alpha expose à un risque infectieux faible ; la prophylaxie est brève."),
        ("q", "prose", "Le geste beta ne nécessite pas de prophylaxie."),
    ]
    chunks = []
    for i, (cid, ctype, text) in enumerate(texts):
        chunks.append(Chunk(chunk_id=f"d1__{cid}", doc_id="d1", chunk_index=i, chunk_type=ctype, text=text,
                            indexed_text=text, section_path="Partie 1 > Gestes", doc_title="Recommandation test",
                            effective_year=2026, populations=["adulte"]))
    meta = DocumentMetadata(doc_id="d1", title="Recommandation test", filename="d1.pdf", md_path="d1.md",
                            effective_year=2026)
    store = LocalVectorStore(chunks=chunks, documents=[meta], embeddings=None,
                             bm25=BM25Index().build([c.indexed_text for c in chunks]),
                             manifest={"embedding_provider": "none", "embedding_model": "none"})
    return SfarRagRetriever(store=store)


def test_api_prompt_identical_to_replay_prompt():
    """The prompt the HTTP API sends to the LLM is byte-identical to the one the replay tool
    builds from a cached retrieval, for open questions and routed MCQs, on both endpoints."""
    from fastapi.testclient import TestClient

    from rag_sfar.config import Settings
    from rag_sfar.generation.profile import PRODUCTION, build_engine
    from rag_sfar.interfaces.api import create_app

    gr = _gen_replay()
    retriever = _synthetic_retriever()
    app = create_app(settings=Settings(reranker_provider="none"), enable_llm=False, retriever=retriever)
    served = _Recorder()
    app.state.engine.llm = served
    client = TestClient(app)
    questions = [
        "Quelle prophylaxie pour le geste alpha ?",
        "Pour le geste alpha, quelle proposition est exacte ?\nA. Produit X 2 g\nB. Aucune prophylaxie\nC. Produit Y",
    ]
    for q in questions:
        assert client.post("/api/query", json={"query": q}).status_code == 200
        assert client.post("/v1/chat/completions", json={"messages": [{"role": "user", "content": q}]}).status_code == 200

    replayed = _Recorder()
    engine = build_engine(None, replayed, PRODUCTION)
    cfg = PRODUCTION.retrieval_config()
    for q in questions:
        retrieved, analysis, timings = retriever.retrieve(q, config=cfg)
        row = gr.cache_row(q, retrieved, analysis, timings)
        meta_cfg = gr.config_from_meta({"config_params": _json.loads(_json.dumps(__import__("dataclasses").asdict(cfg)))})
        gr.replay_generate(engine, row, meta_cfg, PRODUCTION.generation_config(), PRODUCTION.open_mode)

    # each question was served twice (two endpoints), replayed once
    assert len(served.calls) == 4 and len(replayed.calls) == 2
    for i in range(2):
        for served_call in (served.calls[2 * i], served.calls[2 * i + 1]):
            assert served_call[:2] == replayed.calls[i][:2]  # system + user prompt, byte-identical
            assert served_call[2:] == replayed.calls[i][2:]  # same token cap and call options
    assert "QUESTION QCM" in served.calls[2][1]  # MCQ routed by the engine, not by the caller
    # served profile = evaluated profile
    eng = app.state.engine
    assert eng.default_config.name == "C10_context_notes" and eng.attach_provenance is False
    g = eng.gen_config
    assert (g.answer_check, g.molecule_repair, g.dependency_note, g.coverage_gate, g.context_format) == (
        "flag", False, False, "off", "structured")


def test_replay_split_guard_and_dev_only_proxy():
    import pytest

    gr = _gen_replay()
    with pytest.raises(SystemExit):
        gr.check_split("test", allow_test=False)
    gr.check_split("dev", allow_test=False)
    assert gr.proxy_items("abpe171", "test") == {}


def test_replay_reproduces_existing_dev_prompts(tmp_path, monkeypatch):
    """The replay tool with --profile production rebuilds, byte for byte, the dev prompts exported
    for the confirmation run (local caches; skipped where they are absent)."""
    import argparse

    import pytest

    old_dir = _ROOT / "eval_internal/work/replay/frontier/v6_c10n_confirm"
    if not (old_dir.exists() and (_ROOT / "eval_internal/work/replay/c10notes_v6/abpe171.jsonl").exists()):
        pytest.skip("local replay caches not available")
    gr = _gen_replay()
    monkeypatch.setattr(gr, "KEYS", tmp_path / "keys")
    old = {c["case_id"]: c for f in old_dir.glob("gen_input_*.json") for c in _json.loads(f.read_text(encoding="utf-8"))}
    ids = [i for i in sorted(old) if i.startswith("Q")][:6] + [i for i in sorted(old) if i.startswith("MR-")][:3]
    ids_file = tmp_path / "ids.json"
    ids_file.write_text(_json.dumps(ids))
    args = argparse.Namespace(
        cache="c10notes_v6", suite="abpe171,multirfe_synth", split="dev", allow_test=False, profile="production",
        ids_file=str(ids_file), preset="", gen="", gen_mode="", mcq_mode="", backend="record", mlx_model_path="",
        model="", base_url="", api_key="", max_tokens=1024, tokenizer="none", limit=0, tag="pytest_repro",
        system_file="", drop_rule="", export_frontier=str(tmp_path / "export"), per_part=8)
    monkeypatch.setattr(gr, "_save", lambda *a, **k: None)
    gr.run(args)
    keys = _json.loads((tmp_path / "keys" / "export.json").read_text(encoding="utf-8"))
    assert len(keys["cases"]) == len(ids)
    for c in keys["cases"]:
        assert (c["system"], c["user"]) == (old[c["id"]]["system"], old[c["id"]]["user"])
        assert c["id"] not in _json.dumps(_json.loads((tmp_path / "export" / c["part"] / "gen_input.json").read_text()))
