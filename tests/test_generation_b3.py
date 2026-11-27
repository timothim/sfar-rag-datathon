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
