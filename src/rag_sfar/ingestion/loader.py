"""SFAR corpus loader with forensic metadata cleaning, enrichment, and temporal supersession."""

from __future__ import annotations

import collections
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import unquote

from rag_sfar.schemas import DocRole, DocumentMetadata, PopulationScope, SettingScope


@dataclass
class LoadedDocument:
    """In-memory loaded document pairing enriched metadata with cleaned Markdown text."""

    metadata: DocumentMetadata
    text: str


# Canonical SFAR clinical domains and keyword rules for imputing missing subdomains
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "Infectiologie": [
        "antibioprophylaxie",
        "antibiotique",
        "infection",
        "sepsis",
        "septique",
        "antibiothérapi",
        "antibiotherapi",
        "bêta-lactamine",
        "beta-lactamine",
        "betalactamine",
        "ecbu",
        "candidose",
        "aspergillose",
        "pneumonie",
        "pneumopathie",
        "nosocomial",
        "covid",
        "grippe",
        "blse",
        "cathéter",
        "ceftriaxone",
        "cefazoline",
        "cefuroxime",
        "cefoxitine",
        "amoxicilline",
        "vancomycine",
        "teicoplanine",
        "gentamicine",
        "clindamycine",
        "metronidazole",
        "ertapeneme",
        "carbapeneme",
        "piperacilline",
    ],
    "Hématologie – Coagulation – Transfusion": [
        "anticoagulant",
        "anticoagulation",
        "aod",
        "avk",
        "antiplaquettaire",
        "aap",
        "apixaban",
        "rivaroxaban",
        "dabigatran",
        "edoxaban",
        "warfarine",
        "fluindione",
        "heparine",
        "enoxaparine",
        "clopidogrel",
        "ticagrelor",
        "thrombopénie",
        "thrombopenie",
        "thromboembolique",
        "mtev",
        "transfusion",
        "plasma",
        "globules rouges",
        "hémorragi",
        "hemorragi",
        "hémostase",
        "hemostase",
        "anémie",
        "anemie",
        "civd",
        "viscoélastique",
        "thrombose",
        "plyo",
        "gihp",
    ],
    "Voies Aériennes": [
        "voies aériennes",
        "voies aeriennes",
        "intubation",
        "extubation",
        "trachéotomie",
        "tracheotomie",
        "cricothyroïdotomie",
        "curarisation",
        "décurarisation",
        "bris dentaire",
    ],
    "ALR et Douleur": [
        "locorégionale",
        "locoregionale",
        "loco-régionale",
        "alr",
        "périnerveuse",
        "périmédullaire",
        "blocs périphériques",
        "blocs moteurs",
        "douleur",
        "analgésie",
        "analgesie",
        "antalgique",
        "rachianesthésie",
        "péridurale",
    ],
    "Digestif et Nutrition": [
        "intra-abdominale",
        "intra-abdominal",
        "nutrition",
        "pancréatite",
        "pancreatite",
        "hépatique",
        "hepatique",
        "colorectale",
        "colique",
        "proctologie",
        "abdominal",
    ],
    "Neuro-Réanimation": [
        "neuro",
        "crânien",
        "cranien",
        "cranio-encéphalique",
        "vertébro-médullaire",
        "vertebromedullaire",
        "sous-arachnoïdienne",
        "avc",
        "vasculaire cérébral",
        "épileptique",
        "mort encéphalique",
        "revascularisation cérébrale",
    ],
    "Traumatologie": [
        "traumatis",
        "brûlé",
        "brule",
        "pelvien",
        "thoracique",
        "membre",
        "fracture",
    ],
    "Hémodynamique et Cardiologie": [
        "hémodynamique",
        "hemodynamique",
        "remplissage",
        "choc",
        "cardiaque",
        "cardiopathie",
        "coronarien",
        "infarctus",
        "arrêt cardiaque",
        "assistance circulatoire",
        "soluté",
    ],
    "Respiratoire et Ventilation": [
        "ventilation",
        "sdra",
        "asthme",
        "pleural",
        "lobectomie",
        "sevrage",
        "respiratoire",
    ],
    "Obstétrique": [
        "obstétric",
        "obstetric",
        "accouchement",
        "césarienne",
        "cesarienne",
        "pré-éclampsie",
        "pre-eclampsie",
        "prééclampsie",
        "post-partum",
        "grossesse",
        "ivg",
    ],
    "Pédiatrie": [
        "pédiatr",
        "pediatr",
        "enfant",
        "nouveau-né",
        "néonatal",
        "amygdalectomie chez l’enfant",
    ],
    "Sédation et Urgences Vitales": [
        "sédation",
        "sedation",
        "urgence vitale",
        "urgences vitales",
        "structure de médecine d’urgence",
        "structures d’urgence",
    ],
    "Médicaments et Complications": [
        "hypersensibilité",
        "allergique",
        "hyperthermie maligne",
        "erreurs médicamenteuses",
        "hypothermie",
        "nausées",
        "vomissements",
        "oculaire",
        "tabagisme",
        "diabétique",
        "glycémie",
        "rénale",
        "épuration extrarénale",
    ],
    "Ambulatoire et Réhabilitation": [
        "ambulatoire",
        "réhabilitation",
        "rehabilitation",
        "rac",
        "optimisation périopératoire",
    ],
    "Organisation et Professionnel": [
        "dossier anesthésique",
        "téléconsultation",
        "facteurs humains",
        "environnemental",
        "ressources humaines",
        "simulation",
        "tenue vestimentaire",
        "limitation et d’arrêt",
        "usc",
        "surveillance continue",
        "information à la personne",
        "transport intra-hospitalier",
        "infirmier",
        "démarches anticipées",
    ],
}

# Curated longitudinal topic lineages respecting clinical scope (adult vs pediatric,
# planned vs emergency, OR vs ICU). Each rule maps matching documents into a shared
# lineage where strictly older editions are flagged as superseded by the latest edition.
LINEAGE_RULES: list[tuple[str, list[str], list[str]]] = [
    # (lineage_id, must_match_any_pattern, must_not_match_any_pattern)
    ("antibioprophylaxie", [r"antibioprophylaxie"], []),
    ("infections_intra_abdominales", [r"infections?\s+intra[- ]abdominales?"], []),
    (
        "anticoagulants_procedure_programmee",
        [
            r"gestion\s+des\s+anticoagulants\s+pour\s+une\s+proc[ée]dure\s+invasive\s+programm",
            r"gestion\s+p[ée]riop[ée]ratoire\s+des\s+patients\s+sous\s+aod\s+pour\s+un\s+acte\s+programm",
            r"^recommandations\s+avk$",
        ],
        [r"urgence", r"covid"],
    ),
    (
        "anticoagulants_urgence",
        [
            r"gestion\s+de\s+l.?anticoagulation\s+dans\s+un\s+contexte\s+d.?urgence",
            r"gestion\s+(?:des\s+patients\s+sous\s+|p[ée]riop[ée]ratoire\s+des\s+)aod.*urgence",
        ],
        [r"programm"],
    ),
    (
        "voies_aeriennes_adulte_bloc",
        [
            r"prise\s+en\s+charge\s+des\s+voies\s+a[ée]riennes\s+de\s+l.?adulte\s+au\s+bloc",
            r"intubation\s+difficile\s+et\s+extubation\s+en\s+anesth[ée]sie\s+chez\s+l.?adulte",
            r"^intubation\s+difficile$",
            r"prise\s+en\s+charge\s+des\s+voies\s+a[ée]riennes\s+en\s+anesth[ée]sie\s+adulte",
        ],
        [r"enfant", r"r[ée]animation", r"hors\s+bloc"],
    ),
    (
        "nutrition_clinique_adulte",
        [
            r"nutrition\s+clinique\s+de\s+l.?adulte",
            r"nutrition\s+artificielle\s+en\s+r[ée]animation",
            r"nutrition\s+p[ée]riop[ée]ratoire",
        ],
        [],
    ),
    (
        "alr_pediatrique",
        [r"anesth[ée]sie\s+loco[- ]?r[ée]gionale\s+en\s+(?:chirurgie\s+)?p[ée]diatri"],
        [],
    ),
    (
        "sedation_urgences",
        [r"s[ée]dation.*urgence"],
        [],
    ),
    (
        "sepsis_general",
        [
            r"prise\s+en\s+charge\s+du\s+sepsis",
            r"prise\s+en\s+charge\s+initiale\s+des\s+[ée]tats\s+septiques",
            r"prise\s+en\s+charge\s+h[ée]modynamique\s+du\s+sepsis",
            r"antibioth[ée]rapie\s+probabiliste\s+des\s+[ée]tats\s+septiques",
        ],
        [r"corticoth[ée]rapie"],
    ),
    (
        "hypersensibilite_allergie_perioperatoire",
        [
            r"r[ée]actions?\s+d.?hypersensibilit[ée]\s+imm[ée]diate\s+p[ée]riop",
            r"pr[ée]vention\s+du\s+risque\s+allergique\s+peranesth",
        ],
        [],
    ),
    (
        "prevention_mtev_perioperatoire",
        [r"pr[ée]vention\s+de\s+la\s+maladie\s+thromboembolique\s+veineuse"],
        [r"covid"],
    ),
    (
        "prevention_erreurs_medicamenteuses",
        [r"pr[ée]vention\s+des\s+erreurs\s+m[ée]dicamenteuses"],
        [],
    ),
    (
        "optimisation_hemodynamique_adulte",
        [
            r"optimisation\s+h[ée]modynamique\s+p[ée]riop[ée]ratoire.*adulte",
            r"strat[ée]gie\s+du\s+remplissage\s+vasculaire\s+p[ée]riop",
        ],
        [r"p[ée]diatrie"],
    ),
    (
        "organisation_anesthesie_pediatrique",
        [
            r"organisation\s+de\s+l.?anesth[ée]sie\s+p[ée]diatrique",
            r"structures\s+et\s+le\s+mat[ée]riel\s+de\s+l.?anesth[ée]sie\s+p[ée]diatrique",
        ],
        [],
    ),
    (
        "pancreatite_aigue",
        [r"pancr[ée]atite\s+aig"],
        [],
    ),
    (
        "preeclampsie_severe",
        [r"pr[ée][- ]?[ée]clampsie"],
        [],
    ),
    (
        "thrombopenie_induite_heparine",
        [r"thrombop[ée]nie\s+induite\s+par\s+l.?h[ée]parine"],
        [],
    ),
    (
        "hyperthermie_maligne",
        [r"hyperthermie\s+maligne"],
        [],
    ),
    (
        "traumatisme_vertebro_medullaire",
        [r"traumatisme\s+vert[ée]bro[- ]?m[ée]dullaire"],
        [],
    ),
    (
        "agents_antiplaquettaires_programme",
        [
            r"gestion\s+des\s+agents\s+antiplaquettaires\s+pour\s+une\s+proc[ée]dure\s+invasive\s+programm",
            r"^agents\s+antiplaquettaires\s+et\s+p[ée]riode\s+p[ée]riop[ée]ratoire$",
            r"gestion\s+du\s+traitement\s+antiplaquettaire\s+oral",
        ],
        [r"non\s+programm", r"urgence"],
    ),
    (
        "douleur_postoperatoire",
        [r"douleur\s+postop[ée]ratoire"],
        [],
    ),
    (
        "blocs_peripheriques_adulte",
        [
            r"anesth[ée]sie\s+loco[- ]r[ée]gionale\s+p[ée]rinerveuse",
            r"blocs\s+p[ée]riph[ée]riques\s+des\s+membres\s+chez\s+l.?adulte",
        ],
        [],
    ),
    (
        "organisation_usc",
        [
            r"fonctionnement\s+des\s+usc",
            r"organisation\s+des\s+unit[ée]s\s+de\s+surveillance\s+continue",
        ],
        [],
    ),
    (
        "delivrance_information_sante",
        [r"d[ée]livrance\s+de\s+l.?information\s+[àa]\s+la\s+personne"],
        [],
    ),
    (
        "urgences_obstetricales_extrahospitalieres",
        [r"urgences\s+obst[ée]tricales\s+extrahospitali"],
        [],
    ),
    (
        "echographie_alr",
        [r"[ée]chographie\s+en\s+anesth[ée]sie\s+locor[ée]gionale"],
        [],
    ),
]


def _strip_accents(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def clean_chandra_markdown(text: str) -> str:
    """Repair known Chandra OCR 2 Markdown artifacts before parsing.

    Specifically fixes:
    - Inline concatenated headings missing a leading newline (e.g. `48h maximum.## PARTIE 2`)
    - Unicode normalization (NFC) and stray zero-width/control characters
    """
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Insert missing newlines before concatenated markdown headings (`sentence.## HEADING`)
    # Avoid touching URL anchors like `http://...#anchor` or `#` footnotes like `**#**`
    text = re.sub(
        r"(?<=[^\n#\s/(\[])(#{1,4}\s+(?:\*\*)?[A-ZÀ-ÖØ-Þ0-9])",
        r"\n\n\1",
        text,
    )
    # Also handle `V3.0 du 04/05/2026### INTRODUCTION` or `maximum.# CHIRURGIE`
    text = re.sub(
        r"(?<=[0-9\.\)\*])(#{1,4}\s+(?:\*\*)?[A-ZÀ-ÖØ-Þ])",
        r"\n\n\1",
        text,
    )
    return text


def clean_title(title: str) -> str:
    """Clean minor punctuation artifacts in discovery.json titles."""
    t = unicodedata.normalize("NFC", title or "").strip()
    t = re.sub(r"^\*+\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def detect_language(text: str, filename: str) -> Literal["fr", "en", "bilingual"]:
    """Detect primary body language while avoiding English-abstract false positives.

    Samples the middle body (20%-80% of the document) rather than page 1, because many
    French AFAR/ACCPM articles include an English abstract on page 1 before the French body.
    """
    fn_low = filename.lower()
    if any(tok in fn_low for tok in ["anglais", "english", "guidelines-for-", "guidelines-on-", "management-of-", "-in-surgery-", "hospital-acquired-", "eye-protection-", "chest-trauma-", "severe-pelvic-", "bja-2015", "accpm-335"]):
        return "en"

    n = len(text)
    if n > 4000:
        sample = text[int(n * 0.2) : int(n * 0.8)]
        sample = sample[:30000]
    else:
        sample = text
    # Strip HTML tags before counting stopwords
    sample_clean = " " + re.sub(r"<[^>]+>", " ", sample).lower() + " "

    en_words = [" the ", " and ", " of ", " with ", " for ", " in ", " are ", " patients ", " should ", " recommended "]
    fr_words = [" les ", " des ", " une ", " dans ", " pour ", " avec ", " par ", " est ", " chez ", " recommand"]
    en_score = sum(sample_clean.count(w) for w in en_words)
    fr_score = sum(sample_clean.count(w) for w in fr_words)

    if en_score >= 25 and en_score > fr_score * 2.2:
        return "en"
    if en_score >= 20 and fr_score >= 20 and 0.55 <= (en_score / max(1, fr_score)) <= 1.8:
        return "bilingual"
    return "fr"


def infer_effective_year_and_version(
    raw_year: int | None, filename: str, title: str, text_head: str
) -> tuple[int | None, str | None, bool]:
    """Determine true effective clinical year & version label.

    Corrects known discovery.json mismatches:
    - `RFE-antibioprophylaxie-2023_V3.0_pour-mise-sur-site-juin-2026` -> effective_year=2026, V3.0 (04/05/2026)
    - `2013 AFAR GIHP.pdf` (tagged 2021 in discovery.json) -> effective_year=2013
    - Imputes the 22 `year=None` documents from filename / opening text.
    """
    fn_decoded = unquote(filename)
    fn_low = fn_decoded.lower()
    version_label: str | None = None

    # Check explicit version pattern (e.g. V3.0 du 04/05/2026)
    ver_match = re.search(r"\b(V\d+\.\d+)\s+du\s+(\d{2}/\d{2}/(\d{4}))", text_head[:4000])
    if ver_match:
        version_label = f"{ver_match.group(1)} ({ver_match.group(2)})"
        ver_year = int(ver_match.group(3))
        if raw_year is None or ver_year > raw_year:
            return ver_year, version_label, (raw_year is None)

    # Check explicit update year in filename (e.g. juin-2026, 14-08-26, 20.4.2026)
    if "juin-2026" in fn_low or "2026" in fn_low:
        if raw_year is None or raw_year < 2026:
            return 2026, version_label or "Mise à jour 2026", (raw_year is None)

    # Specific known historical file tagged with later upload year
    m_prefix_year = re.match(r"^(199\d|200\d|201\d|202[0-6])\b", fn_decoded.strip())
    if m_prefix_year:
        prefix_yr = int(m_prefix_year.group(1))
        if raw_year is not None and prefix_yr <= raw_year - 5 and "afar" in fn_low:
            return prefix_yr, f"Edition {prefix_yr}", False

    if raw_year is not None:
        return raw_year, version_label, False

    # Impute missing year from filename first, then title, then opening 3500 chars
    fn_years = [int(y) for y in re.findall(r"(?<!\d)(199\d|200\d|201\d|202[0-6])(?!\d)", fn_decoded)]
    if fn_years:
        return max(fn_years), version_label, True

    if "covid" in fn_low or "anticovid" in fn_low or "vaccination" in fn_low:
        head_years = [int(y) for y in re.findall(r"\b(202[0-3])\b", text_head[:4000])]
        return (max(head_years) if head_years else 2021), version_label, True

    head_years = [int(y) for y in re.findall(r"\b(199\d|200\d|201\d|202[0-6])\b", text_head[:4000])]
    if head_years:
        # Take the most recent plausible publication year (ignoring stray historical refs)
        counts = collections.Counter(head_years)
        inferred = counts.most_common(1)[0][0]
        return inferred, version_label, True

    return None, version_label, False


def normalize_disciplines(raw_discipline: str | None) -> list[str]:
    if not raw_discipline:
        return []
    parts = [p.strip() for p in raw_discipline.split("|") if p.strip()]
    seen: list[str] = []
    for p in parts:
        norm = {"Anesthesie": "Anesthésie", "Reanimation": "Réanimation"}.get(p, p)
        if norm not in seen:
            seen.append(norm)
    return seen


def normalize_and_impute_domains(
    raw_subdomain: str | None, title: str, text_head: str
) -> tuple[list[str], bool]:
    """Normalize messy subdomain strings and impute domains for untagged docs (2023-2026!)."""
    domains: list[str] = []
    if raw_subdomain:
        for part in raw_subdomain.split("|"):
            p = re.sub(r"\s*[-–—]\s*", " – ", part.strip())
            p = re.sub(r"\s+", " ", p)
            if p and p not in domains:
                domains.append(p)

    # Always enrich with canonical domains derived from title (+ opening headings) so
    # recent 2023-2026 docs (which have raw_subdomain=None!) are never orphaned!
    search_blob = f"{title} {text_head[:1500]}".lower()
    inferred: list[str] = []
    for domain, kws in DOMAIN_KEYWORDS.items():
        if any(kw in search_blob for kw in kws):
            inferred.append(domain)

    was_imputed = len(domains) == 0 and len(inferred) > 0
    for d in inferred:
        if d not in domains:
            domains.append(d)
    if not domains:
        domains = ["Général"]
    return domains, was_imputed


def classify_doc_role(filename: str, title: str, language: str, char_count: int) -> DocRole:
    fn = unquote(filename).lower()
    tl = title.lower()
    if "abrog" in fn or "abrog" in tl:
        return "abrogee"
    if language == "en":
        return "traduction_en"
    if any(k in fn for k in ["algo", "algorithme", "arbre-diagnostic"]):
        return "algorithme"
    if any(k in fn for k in ["aide-cognitive", "aide_cognitive", "acar-", "aides-cognitives", "fiche_synthese", "fiches-synthese", "fiche_sepsis"]):
        return "aide_cognitive"
    if any(k in fn for k in ["tableau", "tableaux", "synthese", "synthèse"]):
        return "tableaux_synthese"
    if any(k in fn for k in ["argumentaire", "argu_", "version-longue", "texte-long", "texte_long", "_long_"]):
        return "argumentaire"
    if any(k in fn for k in ["version-courte", "texte-court", "texte_court", "short"]):
        return "texte_court"
    if any(k in fn for k in ["annexe", "certificat", "liste-des-centres", "note-de-cadrage", "facturation", "document patient", "sans-fond", "livret", "manifeste"]):
        return "annexe"
    return "recommandation"


def infer_population_scope(title: str, filename: str, text_head: str) -> PopulationScope:
    blob = f"{title} {unquote(filename)}".lower()
    has_ped = any(w in blob for w in ["pédiatr", "pediatr", "enfant", "nouveau-né", "néonatal", "nourrisson"])
    has_adult = any(w in blob for w in ["adulte", "adult"])
    if has_ped and has_adult:
        return "mixte"
    if has_ped:
        return "pediatrie"
    if has_adult:
        # Check if V3.0 antibioprophylaxie added pediatric Champ 3!
        if "pédiatrique" in text_head[:1500].lower() and "adulte" in text_head[:1500].lower():
            return "mixte"
        return "adulte"
    if "pédiatrique" in text_head[:1500].lower() and "adulte" in text_head[:1500].lower():
        return "mixte"
    return "non_specifie"


def infer_setting_scope(title: str, filename: str, disciplines: list[str]) -> SettingScope:
    blob = f"{title} {unquote(filename)}".lower()
    has_urg = any(w in blob for w in ["urgence", "non programm", "non-elective", "aigu", "aiguë", "phase précoce", "hors bloc"])
    has_prog = any(w in blob for w in ["programm", "élective", "elective", "ambulatoire", "périopératoire", "perioperatoire", "bloc opératoire"])
    has_rea = any(w in blob for w in ["réanimation", "reanimation", "soins critiques", "icu"])
    if has_urg and not has_prog:
        return "urgence"
    if has_prog and not has_urg:
        return "programme"
    if has_rea and not has_prog and not has_urg:
        return "reanimation"
    if has_urg and has_prog:
        return "mixte"
    if disciplines == ["Réanimation"]:
        return "reanimation"
    if disciplines == ["Urgences"]:
        return "urgence"
    return "non_specifie"


def match_topic_lineage(title: str, filename: str) -> str | None:
    tl = clean_title(title).lower()
    fn = unquote(filename).lower()
    combined = f"{tl} {fn}"
    for lineage_id, include_pats, exclude_pats in LINEAGE_RULES:
        if any(re.search(p, tl) or re.search(p, combined) for p in include_pats):
            if exclude_pats and any(re.search(ep, combined) for ep in exclude_pats):
                continue
            return lineage_id
    return None


def _estimate_reference_ratio(text: str) -> float:
    if not text:
        return 0.0
    parts = re.split(r"(?m)^(#{1,6}\s+.*)$", text)
    in_ref = False
    ref_chars = 0
    for part in parts:
        if part.startswith("#"):
            in_ref = bool(re.search(r"\b(r[eé]f[eé]rences?|bibliographie)\b", part.lower()))
        elif in_ref:
            ref_chars += len(part)
    return round(ref_chars / max(1, len(text)), 4)


def load_sfar_corpus(
    corpus_dir: Path,
    include_english: bool = True,
    deduplicate_sha256: bool = True,
) -> list[LoadedDocument]:
    """Load and enrich all available SFAR Chandra-converted Markdown documents.

    Parameters
    ----------
    corpus_dir : Path
        Path to `sfar_recommendations/output` (containing `discovery.json` and `chandra/`).
    include_english : bool
        Keep English translations in the loaded corpus (still tagged `language='en'` so
        retrieval can filter/downweight them during ablation).
    deduplicate_sha256 : bool
        Remove exact duplicate files (e.g., `2_AFAR_echographie-en-anesthesie-locoregionale`
        present in both `2011/` and `unknown/`), keeping the dated copy.
    """
    discovery_path = corpus_dir / "discovery.json"
    chandra_dir = corpus_dir / "chandra"
    if not discovery_path.exists():
        raise FileNotFoundError(f"discovery.json not found at {discovery_path}")

    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    raw_docs = discovery.get("documents", [])

    # Build fast lookup maps for Chandra outputs
    md_by_yr_stem: dict[tuple[str, str], Path] = {}
    md_by_stem: dict[str, list[Path]] = collections.defaultdict(list)
    for md_path in chandra_dir.rglob("*.md"):
        yr_folder = md_path.parts[-3]
        md_by_yr_stem[(yr_folder, md_path.stem)] = md_path
        md_by_stem[md_path.stem].append(md_path)

    loaded: list[LoadedDocument] = []
    seen_sha: dict[str, LoadedDocument] = {}

    for entry in raw_docs:
        fn = entry.get("filename") or ""
        if not fn:
            continue
        stem = Path(fn).stem
        yr_str = str(entry.get("year") or "unknown")
        md_path = md_by_yr_stem.get((yr_str, stem))
        if md_path is None and stem in md_by_stem:
            md_path = md_by_stem[stem][0]
        if md_path is None or not md_path.exists():
            continue

        raw_text = md_path.read_text(encoding="utf-8", errors="ignore")
        cleaned_text = clean_chandra_markdown(raw_text)

        sha = entry.get("sha256") or hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
        title = clean_title(entry.get("title") or stem)
        lang = detect_language(cleaned_text, fn)
        if not include_english and lang == "en":
            continue

        eff_year, ver_label, yr_imputed = infer_effective_year_and_version(
            entry.get("year"), fn, title, cleaned_text[:5000]
        )
        disciplines = normalize_disciplines(entry.get("discipline"))
        domains, sub_imputed = normalize_and_impute_domains(
            entry.get("subdomain"), title, cleaned_text[:2000]
        )
        doc_role = classify_doc_role(fn, title, lang, len(cleaned_text))
        pop_scope = infer_population_scope(title, fn, cleaned_text[:2500])
        set_scope = infer_setting_scope(title, fn, disciplines)
        lineage = match_topic_lineage(title, fn)

        # Read Chandra sidecar _metadata.json for page count
        meta_path = md_path.with_name(f"{md_path.stem}_metadata.json")
        num_pages: int | None = None
        if meta_path.exists():
            try:
                cmeta = json.loads(meta_path.read_text(encoding="utf-8"))
                num_pages = cmeta.get("num_pages")
            except Exception:
                num_pages = None

        landing_url = entry.get("landing_url") or entry.get("download_url") or ""
        family_slug = hashlib.md5(landing_url.encode("utf-8")).hexdigest()[:10]
        doc_id = f"{eff_year or 'unk'}_{stem[:64]}_{sha[:6]}"
        doc_id = re.sub(r"[^a-zA-Z0-9_\-]", "_", doc_id)

        table_count = len(re.findall(r"<table\b", cleaned_text, re.I))
        ref_ratio = _estimate_reference_ratio(cleaned_text)

        meta = DocumentMetadata(
            doc_id=doc_id,
            title=title,
            filename=fn,
            md_path=str(md_path),
            sha256=sha,
            landing_url=landing_url,
            download_url=entry.get("download_url") or "",
            doc_type=entry.get("type") or "RFE",
            raw_year=entry.get("year"),
            raw_discipline=entry.get("discipline"),
            raw_subdomain=entry.get("subdomain"),
            source_tabs=entry.get("source_tabs") or [],
            effective_year=eff_year,
            version_label=ver_label,
            disciplines=disciplines,
            domains=domains,
            subdomain_was_imputed=sub_imputed,
            year_was_imputed=yr_imputed,
            language=lang,
            doc_role=doc_role,
            reco_family_id=f"fam_{family_slug}",
            topic_lineage=lineage,
            is_active=(doc_role != "abrogee"),
            is_latest_edition=True,
            population_scope=pop_scope,
            setting_scope=set_scope,
            num_pages=num_pages,
            char_count=len(cleaned_text),
            table_count=table_count,
            reference_char_ratio=ref_ratio,
        )

        # Deduplicate identical files by sha256 (prefer the copy with explicit raw_year)
        if deduplicate_sha256 and sha in seen_sha:
            prev = seen_sha[sha]
            if prev.metadata.raw_year is None and meta.raw_year is not None:
                loaded.remove(prev)
                doc_obj = LoadedDocument(metadata=meta, text=cleaned_text)
                seen_sha[sha] = doc_obj
                loaded.append(doc_obj)
            continue

        doc_obj = LoadedDocument(metadata=meta, text=cleaned_text)
        seen_sha[sha] = doc_obj
        loaded.append(doc_obj)

    # Resolve longitudinal supersession across topic lineages
    _apply_temporal_supersession(loaded)
    return loaded


def _apply_temporal_supersession(docs: list[LoadedDocument]) -> None:
    """Flag superseded historical editions within each clinical topic lineage."""
    by_lineage: dict[str, list[LoadedDocument]] = collections.defaultdict(list)
    for d in docs:
        if d.metadata.topic_lineage and d.metadata.is_active:
            by_lineage[d.metadata.topic_lineage].append(d)

    for lineage, group in by_lineage.items():
        # Consider French active editions to determine the latest authoritative year
        fr_dated = [
            d
            for d in group
            if d.metadata.language != "en" and d.metadata.effective_year is not None
        ]
        if not fr_dated:
            continue
        max_year = max(d.metadata.effective_year for d in fr_dated if d.metadata.effective_year)
        latest_docs = [d for d in fr_dated if d.metadata.effective_year == max_year]
        # Prefer primary recommendation doc as canonical superseding reference
        canonical = sorted(
            latest_docs,
            key=lambda x: (x.metadata.doc_role != "recommandation", -x.metadata.char_count),
        )[0]

        for d in group:
            yr = d.metadata.effective_year
            # Mark strictly older editions (or undated duplicates in same lineage) as superseded
            if yr is None or yr < max_year:
                d.metadata.is_latest_edition = False
                d.metadata.superseded_by = canonical.metadata.doc_id
                d.metadata.superseded_by_year = max_year
            elif d.metadata.language == "en" and any(
                x.metadata.effective_year == yr and x.metadata.language == "fr" for x in group
            ):
                # Same-year English translation is kept active, but French edition is primary
                d.metadata.is_latest_edition = True
