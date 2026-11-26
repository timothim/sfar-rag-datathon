"""01 - Inventaire du corpus : documents, années, types, domaines, langues, tailles,
doublons exacts / quasi-doublons, documents vides ou tronqués, métadonnées manquantes.

Relancer : .venv/bin/python reports/agents/data_audit_scripts/01_inventory.py
Sorties  : out/inventory.json, out/inventory.tsv, out/near_duplicates.json (+ résumé stdout)
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import statistics
from pathlib import Path

import numpy as np
from pypdf import PdfReader

from common import (CHANDRA, CORPUS, PDFS, dec, detect_lang, list_md, load_discovery,
                    map_discovery_to_md, md_year_folder, read, rel, sha256_bytes, write_json)

disc = load_discovery()
d2m, m2d = map_discovery_to_md(disc)
mds = list_md()

# ---------------------------------------------------------------- forme documentaire
FORM_RULES = [
    ("abrogee", r"abrog"),
    ("algorithme_figure", r"algo|arbre-diagnostic|figure|^\d_cricothyro|acar-"),
    ("aide_cognitive_fiche", r"aide[-_ ]cognitive|aides-cognitives|fiche|synthese|fiches[-_]pratiques|document patient|proposition fiche|tableau-de-synthese"),
    ("annexe", r"certificat|liste-des-centres|note-de-cadrage|facturation|fonctionnalites|examen clinique visio|livret|manifeste|referentielcompetences|sans-fond|anti-tabac|annexe|tableaux"),
    ("texte_long_argumentaire", r"texte[-_ ]?long|version-longue|argumentaire|argu_|_long_|3_afar_long"),
    ("texte_court", r"texte[-_ ]?court|version-courte|_court_|recommandations_mel|reco_sepsis"),
]

NATURE_RULES = {
    "RFE_formalisees_experts": r"recommandations? formalis[ée]es? d.experts|\bRFE\b|formalized expert recommendations|guidelines from (?:a )?french",
    "RPP_pratiques_professionnelles": r"recommandations? de pratiques? professionnelles?|\bRPP\b",
    "conference_consensus": r"conf[ée]rence de consensus|consensus conference",
    "conference_experts": r"conf[ée]rence d.experts",
    "RBP_HAS": r"recommandations? de bonnes? pratiques?|haute autorit[ée] de sant[ée]|\bHAS\b|\bANAES\b",
    "propositions_GIHP": r"propositions? du (?:groupe d.int[ée]r[êe]t|GIHP)|\bGIHP\b",
    "preconisations": r"pr[ée]conisations?",
    "avis_experts_reco_experts": r"avis d.experts|recommandations d.experts",
    "referentiel_guide": r"r[ée]f[ée]rentiel|\bguide\b",
}


def doc_form(stem: str, lang: str, n_chars: int) -> str:
    s = dec(stem).lower()
    if lang == "en":
        return "traduction_en"
    for name, pat in FORM_RULES:
        if re.search(pat, s):
            return name
    return "texte_principal"


# ---------------------------------------------------------------- PDF info (léger)
pdf_info: dict[str, dict] = {}


def pdf_for(e: dict, md: Path) -> Path | None:
    fn = e.get("filename") or ""
    cand = PDFS / md_year_folder(md) / fn
    if cand.exists():
        return cand
    hits = list(PDFS.rglob(fn)) if fn else []
    return hits[0] if hits else None


rows = []
for md in mds:
    ids = m2d.get(md, [])
    e = disc[ids[0]] if ids else {}
    text = read(md)
    n = len(text)
    meta_p = md.with_name(md.stem + "_metadata.json")
    cm = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    pages = cm.get("pages", [])
    page_tok = [pg.get("token_count", 0) for pg in pages]
    pdf = pdf_for(e, md)
    pdf_pages = pdf_sha = None
    lfs_oid = None
    if pdf is not None:
        b = pdf.read_bytes()
        pdf_sha = sha256_bytes(b)
        if b.startswith(b"version https://git-lfs"):
            # pointeur Git LFS : le PDF réel n'est pas présent localement
            m_oid = re.search(rb"oid sha256:([0-9a-f]{64})", b)
            lfs_oid = m_oid.group(1).decode() if m_oid else None
            pdf_pages = "lfs_pointer"
        else:
            try:
                pdf_pages = len(PdfReader(str(pdf)).pages)
            except Exception as ex:  # noqa: BLE001
                pdf_pages = f"err:{ex.__class__.__name__}"
    lang = detect_lang(text)
    head = text[:5000]
    natures = [k for k, p in NATURE_RULES.items() if re.search(p, head, re.I)]
    tail = text.rstrip()[-300:]
    rows.append({
        "md": rel(md),
        "year_folder": md_year_folder(md),
        "stem": dec(md.stem),
        "disc_idx": ids,
        "title": e.get("title"),
        "type": e.get("type"),
        "year": e.get("year"),
        "discipline": e.get("discipline"),
        "subdomain": e.get("subdomain"),
        "landing_url": e.get("landing_url"),
        "disc_sha256": e.get("sha256"),
        "pdf_sha256": pdf_sha,
        "pdf_sha_matches_discovery": (pdf_sha == e.get("sha256")) if pdf_sha else None,
        "pdf_is_lfs_pointer": lfs_oid is not None,
        "lfs_oid_matches_discovery": (lfs_oid == e.get("sha256")) if lfs_oid else None,
        "md_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "chars": n,
        "approx_tokens": n // 4,
        "lines": text.count("\n") + 1,
        "chandra_pages": cm.get("num_pages"),
        "chandra_tokens": cm.get("total_token_count"),
        "chandra_images": cm.get("total_images"),
        "pdf_pages": pdf_pages,
        "low_token_pages": sum(1 for t in page_tok if t < 60),
        "chars_per_page": round(n / cm["num_pages"]) if cm.get("num_pages") else None,
        "lang": lang,
        "form": doc_form(md.stem, lang, n),
        "nature_markers_head": natures,
        "n_tables": len(re.findall(r"<table\b", text, re.I)),
        "tail": tail[-120:],
    })

# ---------------------------------------------------------------- doublons exacts
by_md_sha = collections.defaultdict(list)
by_pdf_sha = collections.defaultdict(list)
for r in rows:
    by_md_sha[r["md_sha256"]].append(r["md"])
    if r["pdf_sha256"]:
        by_pdf_sha[r["pdf_sha256"]].append(r["md"])
exact_md_dups = [v for v in by_md_sha.values() if len(v) > 1]
exact_pdf_dups = [v for v in by_pdf_sha.values() if len(v) > 1]
disc_sha = collections.Counter(e.get("sha256") for e in disc if e.get("sha256"))
disc_sha_dups = {k: v for k, v in disc_sha.items() if v > 1}

# ---------------------------------------------------------------- quasi-doublons (MinHash)
TOK = re.compile(r"[a-zàâäçéèêëîïôöùûüœ0-9]+")
K = 5
NPERM = 128
rng = np.random.default_rng(42)
A = rng.integers(1, (1 << 61) - 1, NPERM, dtype=np.uint64)
B = rng.integers(0, (1 << 61) - 1, NPERM, dtype=np.uint64)
shingles = []
sigs = np.zeros((len(rows), NPERM), dtype=np.uint64)
for i, r in enumerate(rows):
    t = re.sub(r"<[^>]+>", " ", read(Path(CORPUS.parents[2] / r["md"])).lower())
    w = TOK.findall(t)
    sh = {hash(" ".join(w[j:j + K])) & ((1 << 61) - 1) for j in range(max(1, len(w) - K + 1))}
    shingles.append(sh)
    if sh:
        arr = np.fromiter(sh, dtype=np.uint64)
        # (a*x + b) mod 2^64 suffit pour une estimation
        h = (np.outer(A, arr) + B[:, None])
        sigs[i] = h.min(axis=1)
near = []
for i in range(len(rows)):
    est = (sigs[i + 1:] == sigs[i]).mean(axis=1)
    for jj in np.nonzero(est > 0.15)[0]:
        j = i + 1 + int(jj)
        si, sj = shingles[i], shingles[j]
        inter = len(si & sj)
        jac = inter / max(1, len(si | sj))
        cont = inter / max(1, min(len(si), len(sj)))
        near.append({"a": rows[i]["md"], "b": rows[j]["md"], "jaccard": round(jac, 3),
                     "containment_min": round(cont, 3), "chars_a": rows[i]["chars"], "chars_b": rows[j]["chars"]})
# containment élevé même si jaccard faible (texte court inclus dans texte long)
for i in range(len(rows)):
    for j in range(i + 1, len(rows)):
        if any((n["a"] == rows[i]["md"] and n["b"] == rows[j]["md"]) for n in near):
            continue
        si, sj = shingles[i], shingles[j]
        small = min(len(si), len(sj))
        if small < 200:
            continue
        # filtre rapide : 300 shingles échantillonnés du plus petit
        s_small, s_big = (si, sj) if len(si) <= len(sj) else (sj, si)
        samp = list(s_small)[:300]
        if sum(1 for x in samp if x in s_big) / len(samp) < 0.4:
            continue
        inter = len(si & sj)
        near.append({"a": rows[i]["md"], "b": rows[j]["md"], "jaccard": round(inter / len(si | sj), 3),
                     "containment_min": round(inter / small, 3), "chars_a": rows[i]["chars"], "chars_b": rows[j]["chars"]})
near.sort(key=lambda x: -x["containment_min"])

# ---------------------------------------------------------------- vides / tronqués
small_docs = [r for r in rows if r["chars"] < 3000]
page_mismatch = [r for r in rows if isinstance(r["pdf_pages"], int) and r["chandra_pages"] and r["pdf_pages"] != r["chandra_pages"]]
low_density = [r for r in rows if r["chars_per_page"] and r["chars_per_page"] < 700 and r["form"] in ("texte_principal", "texte_long_argumentaire", "texte_court")]
blank_pages = [(r["md"], r["low_token_pages"], r["chandra_pages"]) for r in rows if r["low_token_pages"]]

# ---------------------------------------------------------------- métadonnées manquantes
miss = {k: sum(1 for e in disc if e.get(k) in (None, "", [])) for k in
        ["title", "type", "year", "discipline", "subdomain", "landing_url", "filename", "sha256"]}
miss_loaded = {k: sum(1 for r in rows if r[k] in (None, "", [])) for k in ["year", "discipline", "subdomain", "landing_url"]}
title_groups = collections.Counter(r["title"] for r in rows)

summary = {
    "discovery_entries": len(disc),
    "discovery_without_filename": sum(1 for e in disc if not e.get("filename")),
    "md_files": len(rows),
    "md_unmatched_to_discovery": sum(1 for r in rows if not r["disc_idx"]),
    "discovery_with_md": len(d2m),
    "pdf_files": len(list(PDFS.rglob("*.pdf"))),
    "pdf_found_for_md": sum(1 for r in rows if r["pdf_sha256"]),
    "pdf_sha_mismatch_vs_discovery": sum(1 for r in rows if r["pdf_sha_matches_discovery"] is False),
    "pdf_lfs_pointers": sum(1 for r in rows if r["pdf_is_lfs_pointer"]),
    "lfs_oid_equals_discovery_sha": sum(1 for r in rows if r["lfs_oid_matches_discovery"]),
    "by_year_folder": dict(sorted(collections.Counter(r["year_folder"] for r in rows).items())),
    "by_type": collections.Counter(r["type"] for r in rows),
    "by_form": collections.Counter(r["form"] for r in rows),
    "by_lang": collections.Counter(r["lang"] for r in rows),
    "nature_markers_head": collections.Counter(n for r in rows for n in r["nature_markers_head"]),
    "no_nature_marker": sum(1 for r in rows if not r["nature_markers_head"]),
    "distinct_titles": len(title_groups),
    "titles_with_multiple_files": sum(1 for v in title_groups.values() if v > 1),
    "distinct_landing_urls": len({r["landing_url"] for r in rows if r["landing_url"]}),
    "chars_total": sum(r["chars"] for r in rows),
    "approx_tokens_total": sum(r["approx_tokens"] for r in rows),
    "chandra_tokens_total": sum(r["chandra_tokens"] or 0 for r in rows),
    "chars_median": statistics.median(r["chars"] for r in rows),
    "chars_p10_p90": [sorted(r["chars"] for r in rows)[int(len(rows) * q)] for q in (0.1, 0.9)],
    "chars_max": max((r["chars"], r["md"]) for r in rows),
    "pages_total_chandra": sum(r["chandra_pages"] or 0 for r in rows),
    "tables_total": sum(r["n_tables"] for r in rows),
    "docs_with_tables": sum(1 for r in rows if r["n_tables"]),
    "exact_md_duplicates": exact_md_dups,
    "exact_pdf_duplicates": exact_pdf_dups,
    "discovery_sha_duplicates": disc_sha_dups,
    "near_duplicate_pairs_jacc>=0.5": sum(1 for n in near if n["jaccard"] >= 0.5),
    "containment_pairs>=0.5": sum(1 for n in near if n["containment_min"] >= 0.5),
    "small_docs_lt3000": [(r["md"], r["chars"]) for r in small_docs],
    "page_mismatch_pdf_vs_chandra": [(r["md"], r["pdf_pages"], r["chandra_pages"]) for r in page_mismatch],
    "low_density_main_texts": [(r["md"], r["chars_per_page"], r["chandra_pages"]) for r in low_density],
    "docs_with_low_token_pages": len(blank_pages),
    "low_token_pages_total": sum(b[1] for b in blank_pages),
    "missing_discovery_fields_all272": miss,
    "missing_fields_267_loaded": miss_loaded,
    "tokens_by_year": {y: sum(r["approx_tokens"] for r in rows if r["year_folder"] == y) for y in sorted({r["year_folder"] for r in rows})},
}

write_json("inventory.json", {"summary": summary, "rows": rows})
write_json("near_duplicates.json", near)
with open(Path(__file__).parent / "out" / "inventory.tsv", "w") as f:
    cols = ["md", "year_folder", "type", "year", "form", "lang", "chars", "approx_tokens", "chandra_pages", "pdf_pages", "n_tables", "subdomain", "title"]
    f.write("\t".join(cols) + "\n")
    for r in rows:
        f.write("\t".join(str(r[c]) for c in cols) + "\n")

print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))
print("\nTop near-duplicates / containment:")
for n in near[:60]:
    print(f"  J={n['jaccard']:.2f} C={n['containment_min']:.2f}  {Path(n['a']).parent.name[:55]}  <->  {Path(n['b']).parent.name[:55]}")
