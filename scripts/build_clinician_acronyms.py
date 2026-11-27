#!/usr/bin/env python
"""Turn a clinicians' abbreviation dictionary (.xlsx: abbr | forme longue | variantes) into
`src/rag_sfar/retrieval/clinician_acronyms.py` and a review sheet.

Usage:
    .venv/bin/python -I scripts/build_clinician_acronyms.py <dictionary.xlsx> [--index index/tas_v6]

The dictionary is data supplied by the project team (a reviewed, merged hospital dictionary); the
rules never read an evaluation question or answer.
The selection rules below are generic (form of the entry, collisions with French function words,
attestation of the words in the corpus); none looks at a question or an answer.

Rules, in order:
  R1  the abbreviation equals its long form (case and accents folded)           -> excluded
  R2  the abbreviation is not a single token of 2 to 12 letters or digits        -> excluded
      (the expander matches whole tokens; an entry with a space or a hyphen can never match)
  R3  the abbreviation, lower-cased, is a French function word or a tokenizer    -> excluded
      stop word ("PAS", "ET", "DE", "LES", "CE", "SA", "TA", ...): text typed in capitals
      would be expanded wrongly
  R4  the long form lists two senses ("... ou ...")                               -> excluded
  R5  the abbreviation is already in the hand-written lexicon                    -> the existing
      expansion is kept
  R6  otherwise the entry is added. Its expansion is the long form, unless the long form has a
      word that the corpus never writes and one of the listed variants is fully attested in the
      corpus: then that variant is used (the dictionary contains typing errors in long forms).
Entries of two letters and entries whose expansion still has a word absent from the corpus are
added but flagged in the review sheet.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "pr": "http://schemas.openxmlformats.org/package/2006/relationships"}
FUNCTION_WORDS = {
    "pas", "ne", "ni", "et", "ou", "de", "du", "des", "le", "la", "les", "un", "une", "ce", "ces",
    "sa", "ses", "son", "ta", "tes", "ton", "ma", "mes", "mon", "en", "au", "aux", "si", "on", "il",
    "elle", "y", "a",
}
TOKEN_RE = re.compile(r"[A-Za-zÀ-ÿ0-9]{2,12}")


def fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")


def read_xlsx(path: Path) -> list[list[str]]:
    """Rows of the first sheet, standard library only (the file is untrusted input: no macro,
    no formula is evaluated; only cell strings are read)."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    target = {r.get("Id"): r.get("Target") for r in rels.findall("pr:Relationship", NS)}
    first = wb.find("m:sheets", NS)[0]
    t = target[first.get("{%s}id" % NS["r"])]
    root = ET.fromstring(z.read(t.lstrip("/") if t.startswith("/") else "xl/" + t))
    rows: list[list[str]] = []
    for row in root.iter("{%s}row" % NS["m"]):
        cells: dict[int, str] = {}
        for c in row.findall("m:c", NS):
            letters = re.match(r"[A-Z]+", c.get("r")).group(0)
            col = 0
            for ch in letters:
                col = col * 26 + (ord(ch) - 64)
            v = c.find("m:v", NS)
            if c.get("t") == "inlineStr":
                val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
            elif v is None:
                val = ""
            elif c.get("t") == "s":
                val = shared[int(v.text)]
            else:
                val = v.text or ""
            cells[col - 1] = val
        if cells:
            rows.append([cells.get(i, "").strip() for i in range(max(cells) + 1)])
    return rows


def corpus_vocabulary(index_dir: Path) -> set[str]:
    """Accent-folded words of 4 letters or more written in the current-edition chunks."""
    con = sqlite3.connect(f"file:{index_dir / 'metadata.sqlite'}?mode=ro", uri=True)
    vocab: set[str] = set()
    for (payload,) in con.execute("select payload_json from chunks where is_latest_edition = 1"):
        text = json.loads(payload).get("text") or ""
        vocab.update(re.findall(r"[a-z0-9]{4,}", fold(text)))
    if not vocab:
        raise SystemExit("empty corpus vocabulary: check the index payload format")
    return vocab


def unattested(text: str, vocab: set[str]) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]{4,}", fold(text)) if w not in vocab]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("--index", type=Path, default=ROOT / "index/tas_v6")
    ap.add_argument("--out-module", type=Path, default=ROOT / "src/rag_sfar/retrieval/clinician_acronyms.py")
    ap.add_argument("--out-review", type=Path, default=ROOT / "reports/lexique_cliniciens_a_verifier.csv")
    args = ap.parse_args()

    from rag_sfar.retrieval.medical_lexicon import FRENCH_STOPWORDS, HANDWRITTEN_ACRONYMS

    rows = read_xlsx(args.xlsx)
    header, body = rows[0], rows[1:]
    assert [h.lower() for h in header[:2]] == ["abbr", "forme longue"], header
    vocab = corpus_vocabulary(args.index)
    blocked = FUNCTION_WORDS | set(FRENCH_STOPWORDS)

    added: dict[str, str] = {}
    review: list[dict[str, str]] = []
    for r in body:
        r = (r + ["", "", ""])[:3]
        abbr, long_form, variants = r[0].strip(), " ".join(r[1].split()), r[2].strip()
        var_list = [" ".join(v.split()) for v in variants.split(";") if v.strip()]
        status, used, flags = "", "", []
        if fold(abbr) == fold(long_form):
            status = "exclu : identique à la forme longue"
        elif not TOKEN_RE.fullmatch(abbr):
            status = "exclu : espace, tiret ou longueur (jamais reconnu par le mécanisme)"
        elif abbr.lower() in blocked:
            status = "exclu : mot grammatical français (un texte en capitales serait mal développé)"
        elif re.search(r"\s+ou\s+", long_form):
            status = "exclu : deux sens dans la forme longue"
        elif abbr in HANDWRITTEN_ACRONYMS:
            status = "déjà présent : forme du lexique existant conservée"
            used = HANDWRITTEN_ACRONYMS[abbr]
        else:
            used = long_form
            missing = unattested(long_form, vocab)
            if missing:
                better = [v for v in var_list if not re.search(r"\s+ou\s+", v) and not unattested(v, vocab)]
                if better:
                    used = better[0]
                    flags.append("forme longue remplacée par une variante attestée dans le corpus")
                else:
                    flags.append("mots absents du corpus : " + ", ".join(missing))
            if len(abbr) <= 2:
                flags.append("sigle de 2 lettres")
            if any(re.search(r"\s+ou\s+", v) for v in var_list):
                flags.append("une variante indique un autre sens")
            added[abbr] = used
            status = "ajouté"
        review.append({"sigle": abbr, "forme longue fournie": long_form, "variantes fournies": variants,
                       "statut": status, "développement utilisé": used, "à vérifier": " ; ".join(flags),
                       "correct (oui/non)": "", "correction": "", "relecteur": ""})

    sha = hashlib.sha256(args.xlsx.read_bytes()).hexdigest()
    lines = [
        '"""Clinicians\' abbreviation dictionary (generated file: do not edit by hand).',
        "",
        f"Source: {args.xlsx.name} (sha256 {sha[:16]}…), {len(body)} entries, supplied by the project team as a",
        f"reviewed, merged dictionary. Generated on {date.today().isoformat()} by scripts/build_clinician_acronyms.py, whose",
        "docstring states the selection rules. Each value is the plain long form of the abbreviation:",
        "no drug name, class member or other term is added. Merged into the lexicon by",
        '`medical_lexicon.py`; the hand-written entries take precedence."""',
        "",
        "from __future__ import annotations",
        "",
        "CLINICIAN_ACRONYMS: dict[str, str] = {",
    ]
    for k in sorted(added, key=lambda s: (s.upper(), s)):
        lines.append(f"    {k!r}: {added[k]!r},")
    lines.append("}")
    args.out_module.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with open(args.out_review, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(review[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(review)

    counts: dict[str, int] = {}
    for row in review:
        key = row["statut"].split(" :")[0]
        counts[key] = counts.get(key, 0) + 1
    print(f"{len(body)} entries -> {counts}")
    print("flagged among added:", sum(1 for row in review if row["statut"] == "ajouté" and row["à vérifier"]))
    for reason in sorted({row["statut"] for row in review if row["statut"].startswith("exclu")}):
        print(" ", reason, ":", [row["sigle"] for row in review if row["statut"] == reason])


if __name__ == "__main__":
    main()
