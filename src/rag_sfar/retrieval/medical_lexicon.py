"""French anesthesia & critical care medical lexicon, acronym expander, and tokenizer."""

from __future__ import annotations

import re
import unicodedata

from rag_sfar.retrieval.clinician_acronyms import CLINICIAN_ACRONYMS

# High-value French anesthesia-reanimation & surgical acronyms/abbreviations (written by hand)
HANDWRITTEN_ACRONYMS: dict[str, str] = {
    # Prothèses & Orthopédie / Neurochirurgie
    "PTH": "prothèse totale de hanche",
    "PTG": "prothèse totale de genou",
    "PTE": "prothèse totale d'épaule",
    "DVE": "dérivation ventriculaire externe",
    "DVP": "dérivation ventriculo-péritonéale",
    "LCA": "ligament croisé antérieur",
    "MI": "membre inférieur",
    "MS": "membre supérieur",
    "AMO": "ablation de matériel d'ostéosynthèse",
    # Antibioprophylaxie & Infectiologie
    "ABP": "antibioprophylaxie",
    "ATBP": "antibioprophylaxie",
    "ATB": "antibiothérapie antibiotique",
    "ISO": "infection du site opératoire",
    "IIA": "infection intra-abdominale péritonite",
    "C1G": "céphalosporine de première génération céfazoline",
    "C2G": "céphalosporine de deuxième génération céfuroxime céfoxitine",
    "C3G": "céphalosporine de troisième génération céfotaxime ceftriaxone",
    "SARM": "Staphylococcus aureus résistant à la méticilline",
    "BLSE": "bêta-lactamase à spectre élargi entérobactérie",
    "EBLSE": "entérobactérie productrice de bêta-lactamase à spectre élargi",
    "BMR": "bactérie multirésistante",
    "ECBU": "examen cytobactériologique des urines",
    "PAVM": "pneumonie acquise sous ventilation mécanique",
    # "PAS" (pneumonie associée aux soins) is deliberately absent: it collides with the French
    # negation "pas", including in upper case ("NE PAS", "PAS D'…").
    # Coagulation & Antithrombotiques
    "AOD": "anticoagulant oral direct apixaban rivaroxaban dabigatran edoxaban",
    "AVK": "antivitamine K warfarine fluindione acénocoumarol",
    "AAP": "agent antiplaquettaire aspirine clopidogrel prasugrel ticagrélor",
    "HBPM": "héparine de bas poids moléculaire énoxaparine tinzaparine",
    "HNF": "héparine non fractionnée",
    "TIH": "thrombopénie induite par l'héparine",
    "MTEV": "maladie thromboembolique veineuse",
    "TVP": "thrombose veineuse profonde",
    "EP": "embolie pulmonaire",
    "FA": "fibrillation atriale",
    "CIVD": "coagulation intravasculaire disséminée",
    "INR": "INR rapport normalisé international",
    "CCP": "concentré de complexe prothrombinique",
    "PFC": "plasma frais congelé",
    "CGR": "concentré de globules rouges",
    "GIHP": "Groupe d'Intérêt en Hémostase Périopératoire",
    # Voies aériennes, ALR, Réanimation, Chirurgie
    "ALR": "anesthésie locorégionale",
    "AG": "anesthésie générale",
    "APD": "analgésie péridurale",
    "RAC": "réhabilitation améliorée après chirurgie",
    "SDRA": "syndrome de détresse respiratoire aiguë",
    "VNI": "ventilation non invasive",
    "IOT": "intubation orotrachéale",
    "ID": "intubation difficile",
    "CEC": "circulation extracorporelle",
    "TAVI": "remplacement valvulaire aortique percutané TAVI",
    "FOP": "foramen ovale perméable",
    "CPRE": "cholangiopancréatographie rétrograde endoscopique",
    "RTUP": "résection transurétrale de prostate",
    "RTUV": "résection transurétrale de vessie",
    "HBP": "hypertrophie bénigne de prostate",
    "ORL": "oto-rhino-laryngologie ORL",
    "DIU": "dispositif intra-utérin",
    "IVG": "interruption volontaire de grossesse",
    "HPP": "hémorragie du post-partum",
    "IRA": "insuffisance rénale aiguë",
    "IRC": "insuffisance rénale chronique",
    "DFG": "débit de filtration glomérulaire clairance créatinine",
    "ClCr": "clairance de la créatinine fonction rénale",
    "TC": "traumatisme crânien",
    "TCG": "traumatisme crânien grave",
    "TVM": "traumatisme vertébro-médullaire",
    "HSA": "hémorragie sous-arachnoïdienne",
    "AVC": "accident vasculaire cérébral",
    "NVPO": "nausées et vomissements postopératoires",
    "HM": "hyperthermie maligne",
    "USC": "unité de surveillance continue",
    "LAT": "limitation et arrêt des traitements",
    "IVL": "intraveineuse lente",
    "IMC": "indice de masse corporelle obésité",
}

# Lexicon used by `expand_medical_query`: the hand-written entries above, plus the clinicians'
# abbreviation dictionary (plain long forms, see clinician_acronyms.py). A hand-written entry
# takes precedence over a dictionary entry with the same abbreviation.
MEDICAL_ACRONYMS: dict[str, str] = {**CLINICIAN_ACRONYMS, **HANDWRITTEN_ACRONYMS}

CLINICAL_SYNONYMS: dict[str, str] = {
    "augmentin": "amoxicilline clavulanate",
    "bactrim": "triméthoprime sulfaméthoxazole",
    "tazocilline": "pipéracilline tazobactam",
    "flagyl": "métronidazole",
    "rocephine": "ceftriaxone",
    "claforan": "céfotaxime",
    "dalacine": "clindamycine",
    "eliquis": "apixaban AOD",
    "xarelto": "rivaroxaban AOD",
    "pradaxa": "dabigatran AOD",
    "lixiana": "edoxaban AOD",
    "coumadine": "warfarine AVK",
    "previscan": "fluindione AVK",
    "sintrom": "acénocoumarol AVK",
    "plavix": "clopidogrel AAP",
    "brilique": "ticagrélor AAP",
    "efient": "prasugrel AAP",
    "kardegic": "aspirine AAP",
    "lovenox": "énoxaparine HBPM",
    "innohep": "tinzaparine HBPM",
    "calciparine": "héparine calcique HNF",
    "betalactamine": "bêtalactamines céphalosporine pénicilline",
    "betalactamines": "bêtalactamines céphalosporine pénicilline",
    "penicilline": "pénicillines bêtalactamines",
    "penicillines": "pénicillines bêtalactamines",
}

FRENCH_STOPWORDS: frozenset[str] = frozenset(
    {
        "le", "la", "les", "un", "une", "des", "du", "de", "d", "l", "au", "aux",
        "et", "ou", "ni", "mais", "car", "donc", "or", "que", "qui", "quoi", "dont",
        "en", "dans", "sur", "sous", "par", "pour", "avec", "sans", "vers", "chez",
        "ce", "cet", "cette", "ces", "son", "sa", "ses", "leur", "leurs", "mon", "ma",
        "est", "sont", "etre", "ete", "fait", "faire", "peut", "doit", "faut", "il",
        "elle", "ils", "elles", "on", "nous", "vous", "se", "si", "ne", "pas", "plus",
        "quelle", "quel", "quelles", "quels", "comment", "quand", "est-ce", "y", "a",
        "the", "of", "and", "in", "to", "for", "with", "on", "at", "by", "from", "is",
        "recommandation", "recommandations", "sfar", "question", "patient", "patients",
    }
)


def fold_accents(text: str) -> str:
    """Remove French diacritics for accent-insensitive lexical matching."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    )


def expand_medical_query(query: str) -> tuple[str, dict[str, str]]:
    """Expand recognized French anesthesia/ICU acronyms and brand names in a query.

    Acronyms are matched case-sensitively on whole tokens (as written in the dictionary, e.g.
    "AOD", "ClCr"): a lower-case French word ("pas", "ira", "rac", "iso") is never read as an
    acronym. Brand names and drug-class synonyms are matched case- and accent-insensitively."""
    expansions: dict[str, str] = {}
    for tok in re.findall(r"(?<!\w)[A-Za-zÀ-ÿ0-9]{2,12}(?!\w)", query):
        if tok in MEDICAL_ACRONYMS:
            expansions[tok] = MEDICAL_ACRONYMS[tok]
        else:
            folded = fold_accents(tok.lower())
            if folded in CLINICAL_SYNONYMS:
                expansions[tok] = CLINICAL_SYNONYMS[folded]

    if not expansions:
        return query, {}

    extra_terms = " ".join(dict.fromkeys(expansions.values()))
    return f"{query} ({extra_terms})", expansions


def tokenize_medical_french(text: str, remove_stopwords: bool = True) -> list[str]:
    """Tokenize French clinical text preserving dosages (`j-3`, `2g`, `c1g`, `r1.1`)
    and splitting slash/hyphen compounds while retaining compound tokens."""
    folded = fold_accents(text.lower())
    raw_tokens = re.findall(r"[a-z0-9]+(?:[./-][a-z0-9]+)?", folded)
    tokens: list[str] = []
    for tok in raw_tokens:
        if len(tok) < 2 and not tok.isdigit():
            continue
        if remove_stopwords and tok in FRENCH_STOPWORDS:
            continue
        tokens.append(tok)
        if "/" in tok or "-" in tok:
            for sub in re.split(r"[/-]", tok):
                if len(sub) >= 2 and (not remove_stopwords or sub not in FRENCH_STOPWORDS):
                    tokens.append(sub)
    return tokens
