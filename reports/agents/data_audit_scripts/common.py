"""Utilitaires communs pour l'audit des données SFAR (lecture seule du corpus).

Usage : importer depuis les scripts 0X_*.py ; ne modifie aucun fichier du corpus.
"""
from __future__ import annotations

import collections
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "data" / "sfar_recommendations" / "output"
CHANDRA = CORPUS / "chandra"
PDFS = CORPUS / "pdfs"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)


def load_discovery() -> list[dict]:
    return json.loads((CORPUS / "discovery.json").read_text(encoding="utf-8"))["documents"]


def list_md() -> list[Path]:
    return sorted(CHANDRA.rglob("*.md"))


def md_year_folder(p: Path) -> str:
    return p.parts[-3]


def rel(p: Path) -> str:
    return str(p.relative_to(ROOT))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def norm_for_match(s: str) -> str:
    s = strip_accents(unicodedata.normalize("NFC", s)).lower()
    s = s.replace("’", "'").replace("‘", "'")
    return s


def map_discovery_to_md(disc: list[dict]) -> tuple[dict[int, Path], dict[Path, list[int]]]:
    """Reproduit la logique de jointure de loader.py (année + stem, sinon stem seul)."""
    by_yr_stem: dict[tuple[str, str], Path] = {}
    by_stem: dict[str, list[Path]] = collections.defaultdict(list)
    for p in list_md():
        by_yr_stem[(md_year_folder(p), p.stem)] = p
        by_stem[p.stem].append(p)
    d2m: dict[int, Path] = {}
    m2d: dict[Path, list[int]] = collections.defaultdict(list)
    for i, e in enumerate(disc):
        fn = e.get("filename") or ""
        if not fn:
            continue
        stem = Path(fn).stem
        yr = str(e.get("year") or "unknown")
        p = by_yr_stem.get((yr, stem))
        if p is None and stem in by_stem:
            p = by_stem[stem][0]
        if p is not None:
            d2m[i] = p
            m2d[p].append(i)
    return d2m, m2d


REF_HEAD = re.compile(r"^#{1,6}\s*(?:\*\*)?\s*(?:\d+[\.\)]?\s*)?(r[ée]f[ée]rences?(?: bibliographiques)?|bibliographie|references)\b", re.I)


def split_lines(text: str) -> list[str]:
    return text.split("\n")


def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s)


FR_SW = [" les ", " des ", " une ", " dans ", " pour ", " avec ", " par ", " est ", " chez ", " sont ", " qui ", " sur "]
EN_SW = [" the ", " and ", " with ", " for ", " are ", " patients ", " should ", " which ", " this ", " from ", " was ", " were "]


def lang_scores(text: str) -> tuple[int, int]:
    t = " " + re.sub(r"\s+", " ", strip_html(text)).lower() + " "
    return sum(t.count(w) for w in FR_SW), sum(t.count(w) for w in EN_SW)


def detect_lang(text: str) -> str:
    """Langue du corps (20 %-80 % du texte, références exclues grossièrement)."""
    n = len(text)
    body = text[int(n * 0.2): int(n * 0.8)] if n > 4000 else text
    fr, en = lang_scores(body)
    tot = fr + en
    if tot < 30:
        return "indetermine"
    r = en / tot
    if r > 0.75:
        return "en"
    if r > 0.35:
        return "bilingue"
    return "fr"


def write_json(name: str, obj) -> Path:
    p = OUT / name
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return p


def dec(s: str) -> str:
    return unquote(s or "")
