"""List possible edition links that the loader does NOT apply (for clinical review).

Pairs of active French documents of different years and different families whose titles share
at least 40 % of their content words (Jaccard), the older one still marked current, plus the
current supersessions with their evidence. Read-only; prints Markdown.
Usage: HF_HUB_OFFLINE=1 .venv/bin/python reports/agents/B2_annexes/edition_candidates.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from rag_sfar.config import Settings  # noqa: E402
from rag_sfar.ingestion.loader import _content_words, load_sfar_corpus  # noqa: E402

docs = [d.metadata for d in load_sfar_corpus(Settings().corpus_dir)]
print("## Supersessions appliquées\n\n| Document remplacé | Année | Remplacé par | Preuve |\n|---|---:|---|---|")
for m in sorted(docs, key=lambda m: (m.topic_lineage or "~", m.effective_year or 0)):
    if not m.is_latest_edition or not m.is_active:
        print(f"| {m.title[:70]} (`{m.doc_id[:45]}`) | {m.effective_year} | `{(m.superseded_by or 'abrogé')[:45]}` | {m.supersession_evidence[:160]} |")
print("\n## Candidats non appliqués (titres proches, aucune mention explicite)\n\n| Ancien | Année | Récent | Année | Jaccard titres |\n|---|---:|---|---:|---:|")
act = [m for m in docs if m.is_active and m.is_latest_edition and m.language != "en" and m.effective_year]
seen = set()
for a in act:
    for b in act:
        if a.effective_year >= b.effective_year or a.reco_family_id == b.reco_family_id:
            continue
        wa, wb = _content_words(a.title), _content_words(b.title)
        if len(wa) < 2 or not wb:
            continue
        j = len(wa & wb) / len(wa | wb)
        key = (a.title, b.title)
        if j >= 0.4 and key not in seen:
            seen.add(key)
            print(f"| {a.title[:60]} | {a.effective_year} | {b.title[:60]} | {b.effective_year} | {j:.2f} |")
