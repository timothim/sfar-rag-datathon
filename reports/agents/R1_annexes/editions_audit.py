"""R1: audit of B2's two generic edition rules on the whole corpus (CPU only, no index build).

Lists (1) every document whose status changes with each rule, and (2) near misses:
- explicit-update rule: paragraphs with an update word + year Y where an older doc of year Y has
  >= 2/3 of its title words in the paragraph (instead of all), or passes all but the
  "half of the title in the new title" condition;
- abrogated-twin rule: Jaccard of word 5-grams in [0.5, 1] between any active document and an
  abrogated one (without the year/length guards), and every pair of documents with Jaccard in
  [0.8, 0.9) (could flip with a slightly lower threshold).
"""
import copy, itertools, re, sys
from pathlib import Path
from rag_sfar.ingestion import loader as L

docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
print("documents", len(docs))
by_id = {d.metadata.doc_id: d for d in docs}
print("\n== Documents with supersession_evidence from the two new rules ==")
for d in docs:
    ev = d.metadata.supersession_evidence
    if ev and not ev.startswith("lignée"):
        m = d.metadata
        print(f"- {m.doc_id} ({m.effective_year}) active={m.is_active} latest={m.is_latest_edition} -> {m.superseded_by}\n    {ev[:400]}")

# Re-evaluate the update rule with relaxed conditions to show near misses
print("\n== Near misses of _apply_explicit_update_mentions ==")
cw = L._content_words
for new in docs:
    nm = new.metadata
    if not nm.effective_year or nm.language == "en" or not nm.is_active:
        continue
    for para in re.split(r"\n\s*\n", new.text[:40000]):
        if not L._UPDATE_RE.search(para):
            continue
        words = cw(para)
        for y in {int(x) for x in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", para)}:
            if y >= nm.effective_year:
                continue
            for old in docs:
                om = old.metadata
                if om.effective_year != y or om.language == "en" or om.reco_family_id == nm.reco_family_id:
                    continue
                tw = cw(om.title)
                if len(tw) < 2:
                    continue
                inpara = len(tw & words) / len(tw)
                intitle = len(tw & cw(nm.title)) / len(tw)
                full = len(tw) >= 3 and inpara == 1 and intitle >= 0.5 and nm.doc_role in ("recommandation", "texte_court", "argumentaire")
                if inpara >= 2 / 3 and (intitle >= 0.34 or inpara == 1):
                    tag = "FIRES" if full else "near"
                    print(f"[{tag}] new={nm.doc_id} ({nm.effective_year}, role={nm.doc_role}) old={om.doc_id} ({y}) title_in_para={inpara:.2f} title_in_newtitle={intitle:.2f} |tw|={len(tw)}\n     old title: {om.title}\n     new title: {nm.title}\n     para: {re.sub(chr(10),' ',para)[:260]}")

print("\n== Jaccard 5-grams: abrogated vs any document (>=0.5) and all pairs in [0.8,0.9) ==")
sh = {d.metadata.doc_id: L._shingles(d.text) for d in docs}
ids = list(sh)
for a, b in itertools.combinations(ids, 2):
    sa, sb = sh[a], sh[b]
    if not sa or not sb:
        continue
    # cheap bound
    if min(len(sa), len(sb)) / max(len(sa), len(sb)) < 0.5:
        continue
    j = len(sa & sb) / len(sa | sb)
    ab = (not by_id[a].metadata.is_active) or (not by_id[b].metadata.is_active)
    if (ab and j >= 0.5) or (0.8 <= j < 0.9) or j >= 0.9:
        ma, mb = by_id[a].metadata, by_id[b].metadata
        print(f"J={j:.3f} {a} ({ma.effective_year}, active={ma.is_active}, latest={ma.is_latest_edition}) ~ {b} ({mb.effective_year}, active={mb.is_active}, latest={mb.is_latest_edition})")
