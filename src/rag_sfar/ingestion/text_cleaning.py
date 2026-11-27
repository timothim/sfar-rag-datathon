"""Deterministic clean-up of Chandra OCR Markdown residues in chunk text.

Every rule follows from the OCR output format of the whole corpus (data audit, section 2.2),
never from one document:
- NUL byte pairs standing for one lost non-ASCII character ("R\\x00\\x00serve") are repaired
  from the corpus vocabulary when exactly one candidate letter gives a known word;
- HTML entities (including double-escaped ones: "&amp;gt;") are decoded;
- simple LaTeX (inline "$...$" and "<math>...</math>") becomes Unicode text
  ("$\\geq 2$" -> "≥ 2", "kg/m^2" -> "kg/m²", "\\text{mmHg}" -> "mmHg");
- inline HTML formatting tags left in prose (<sub>, <sup>, <b>, <br/>...) are removed,
  keeping their content;
- doubled list markers ("- • ", "- – • ") and doubled numbering ("1. 1.") are collapsed;
- images: decorative ones (logos, icons, covers, photographs) are dropped; the others keep
  their generated description, explicitly marked as an automatic English description;
- Mermaid flowcharts are rewritten as readable "A → B" lines, marked as a converted flowchart.
"""

from __future__ import annotations

import collections
import html
import re
import unicodedata

NUL_PAIR = "\x00\x00"
UNREADABLE = "\ufffd"  # visible marker of a character lost by the OCR
_NUL_CANDIDATES = "éèêàâîïôûùçëÉÈÊÀÂÎÔÛÇ"
_WORD_RE = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿŒœ\x00]+")


class NulRepairer:
    """Repairs "\\x00\\x00" (one lost two-byte UTF-8 character) from a word vocabulary."""

    def __init__(self, texts: list[str] | None = None) -> None:
        self.vocab: collections.Counter = collections.Counter()
        for t in texts or []:
            if NUL_PAIR in t:
                continue
            self.vocab.update(w.lower() for w in _WORD_RE.findall(t))

    def _fix_word(self, word: str) -> str:
        """Replace each lost character only when the vocabulary designates a single word (or one
        word at least 10 times more frequent than the others); otherwise leave a visible marker
        (U+FFFD) instead of guessing. A pair standing alone (no letter around it) is never
        guessed: it may be a symbol (≥, à, …)."""
        n = word.count(NUL_PAIR)
        if n == 0:
            return word
        if word.replace(NUL_PAIR, "") == "" or n > 3:
            return word.replace(NUL_PAIR, UNREADABLE)
        import itertools

        parts = word.split(NUL_PAIR)
        # Case of the lost letters follows the word (all-caps word -> capital accented letters).
        letters = word.replace(NUL_PAIR, "")
        pool = [c for c in _NUL_CANDIDATES if c.isupper() == (letters.isupper() and len(letters) > 1)]
        cands = []
        for combo in itertools.product(pool, repeat=n):
            w = "".join(p + (combo[k] if k < n else "") for k, p in enumerate(parts))
            c = self.vocab.get(w.lower(), 0)
            if c > 0:
                cands.append((c, w))
        cands.sort(reverse=True)
        if len(cands) == 1 or (len(cands) > 1 and cands[0][0] >= 10 * cands[1][0]):
            return cands[0][1]
        return word.replace(NUL_PAIR, UNREADABLE)

    def __call__(self, text: str) -> str:
        if "\x00" not in text:
            return text
        text = _WORD_RE.sub(lambda m: self._fix_word(m.group(0)) if NUL_PAIR in m.group(0) else m.group(0), text)
        # Any pair left (between non-letters) is not guessed either.
        text = text.replace(NUL_PAIR, UNREADABLE)
        return text.replace("\x00", UNREADABLE)


_SUPERSCRIPT = str.maketrans("0123456789+-−", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻")

_LATEX_SYMBOLS = {
    r"\geq": "≥", r"\geqslant": "≥", r"\ge": "≥", r"\leq": "≤", r"\leqslant": "≤", r"\le": "≤",
    r"\times": "×", r"\pm": "±", r"\approx": "≈", r"\sim": "~", r"\simeq": "≃", r"\neq": "≠",
    r"\cdot": "·", r"\bullet": "•", r"\rightarrow": "→", r"\to": "→", r"\Rightarrow": "⇒",
    r"\leftarrow": "←", r"\uparrow": "↑", r"\downarrow": "↓", r"\infty": "∞", r"\circ": "°",
    r"\degree": "°", r"\mu": "µ", r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\Delta": "Δ", r"\kappa": "κ", r"\lambda": "λ", r"\sigma": "σ", r"\tau": "τ", r"\%": "%",
    r"\,": " ", r"\;": " ", r"\:": " ", r"\!": "", r"\quad": " ", r"\qquad": " ", r"\ ": " ",
    r"\&": "&", r"\_": "_", r"\{": "{", r"\}": "}", r"\ldots": "…", r"\dots": "…", r"\cdots": "…",
    r"\prime": "′", r"\textless": "<", r"\textgreater": ">", r"\lt": "<", r"\gt": ">",
}
# Symbols that are written glued to a unit letter in the corpus ("\\mu g", "\\mu\\text{g}" -> "µg",
# "\\Omega" in "kΩ", "\\circ C"): matched even when a letter follows. Every other command must end
# at a word boundary ("\\le" must not eat "\\left").
_UNIT_SYMBOLS = {r"\mu", r"\Omega", r"\circ", r"\degree"}
_LATEX_SYMBOLS[r"\Omega"] = "Ω"
_LATEX_SYMBOL_RE = re.compile(
    "|".join(
        re.escape(k) + (r"(?![A-Za-z])" if k[-1].isalpha() and k not in _UNIT_SYMBOLS else "")
        for k in sorted(_LATEX_SYMBOLS, key=len, reverse=True)
    )
)
_LATEX_TEXT_CMD_RE = re.compile(r"\\(?:text|mathrm|textrm|mathit|textit|textbf|mathbf|operatorname|mbox|mathsf|rm)\s*\{([^{}]*)\}")
_LATEX_FRAC_RE = re.compile(r"\\[dt]?frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}")
_LATEX_SQRT_RE = re.compile(r"\\sqrt\s*\{([^{}]*)\}")
_LATEX_SUP_RE = re.compile(r"\^\s*(?:\{([^{}]*)\}|([0-9A-Za-z+\-−]))")
_LATEX_SUB_RE = re.compile(r"_\s*(?:\{([^{}]*)\}|([0-9A-Za-z]))")
_LATEX_LEFTRIGHT_RE = re.compile(r"\\(?:left|right|big|Big|bigg|Bigg)\s*([()\[\]|.])")


def latex_to_text(expr: str) -> str:
    """Unicode rendering of a simple LaTeX expression (no layout, no arrays)."""
    s = _LATEX_SYMBOL_RE.sub(lambda m: _LATEX_SYMBOLS[m.group(0)], expr)
    for _ in range(3):
        s2 = _LATEX_TEXT_CMD_RE.sub(r"\1", s)
        s2 = _LATEX_FRAC_RE.sub(r"\1/\2", s2)
        s2 = _LATEX_SQRT_RE.sub(r"√(\1)", s2)
        if s2 == s:
            break
        s = s2
    s = _LATEX_LEFTRIGHT_RE.sub(lambda m: "" if m.group(1) == "." else m.group(1), s)
    s = _LATEX_SYMBOL_RE.sub(lambda m: _LATEX_SYMBOLS[m.group(0)], s)

    def _sup(m: re.Match) -> str:
        val = (m.group(1) if m.group(1) is not None else m.group(2)).strip()
        if re.fullmatch(r"[0-9+\-−]+", val):
            return val.translate(_SUPERSCRIPT)
        return "^" + val

    s = _LATEX_SUP_RE.sub(_sup, s)
    s = _LATEX_SUB_RE.sub(lambda m: (m.group(1) if m.group(1) is not None else m.group(2)), s)
    s = s.replace("{", "").replace("}", "")
    s = re.sub(r"\\([A-Za-z]+)", r"\1", s)  # unknown command: keep its name as a word
    return re.sub(r"[ \t]+", " ", s).strip()


_MATH_TAG_RE = re.compile(r"<math\b[^>]*>(.*?)</math>", re.S | re.I)
# Inline math: "$...$" on one line, not "$$", not a currency amount ("10 $").
_DOLLAR_RE = re.compile(r"(?<![\\$\w])\$(?!\$)([^$\n]{1,200}?)(?<![\\\s])\$(?!\$)")
_DOLLAR_LOOSE_RE = re.compile(r"(?<![\\$])\$(?!\$)([^$\n]{1,200}?)\$(?!\$)")


def replace_math(text: str) -> str:
    text = _MATH_TAG_RE.sub(lambda m: latex_to_text(m.group(1)), text)

    def _rep(m: re.Match) -> str:
        inner = m.group(1)
        if not re.search(r"[\\^_{}<>=≥≤]|[A-Za-z]|\d", inner):
            return m.group(0)
        return latex_to_text(inner)

    text = re.sub(r"\$\$(.{1,600}?)\$\$", lambda m: latex_to_text(m.group(1)), text, flags=re.S)
    text = _DOLLAR_LOOSE_RE.sub(_rep, text)
    # Bare LaTeX left without delimiters (e.g. inside table cells once <math> tags are dropped)
    if "\\" in text:
        text = _LATEX_SYMBOL_RE.sub(lambda m: _LATEX_SYMBOLS[m.group(0)], text)
        for _ in range(2):
            text = _LATEX_TEXT_CMD_RE.sub(r"\1", text)
            text = _LATEX_FRAC_RE.sub(r"\1/\2", text)
        text = _LATEX_LEFTRIGHT_RE.sub(lambda m: "" if m.group(1) == "." else m.group(1), text)
        text = _LATEX_SYMBOL_RE.sub(lambda m: _LATEX_SYMBOLS[m.group(0)], text)
    text = re.sub(r"(?<=[A-Za-z])\^\{?([0-9])\}?(?![0-9])", lambda m: m.group(1).translate(_SUPERSCRIPT), text)
    return text


def decode_entities(text: str) -> str:
    for _ in range(3):
        new = html.unescape(text)
        if new == text:
            break
        text = new
    return text.replace("\xa0", " ")


_SUP_TAG_RE = re.compile(r"<sup>\s*([^<]{0,20}?)\s*</sup>", re.I)
_SUB_TAG_RE = re.compile(r"<sub>\s*([^<]{0,20}?)\s*</sub>", re.I)
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_INLINE_TAG_RE = re.compile(
    r"</?(?:b|i|u|em|strong|span|font|p|div|small|big|mark|s|strike|center|sub|sup|input|label|ins|del)\b[^<>]{0,300}>",
    re.I,
)


_ORPHAN_CELL_RE = re.compile(r"</?(?:td|th)\b[^<>]{0,300}>", re.I)
_ORPHAN_ROW_RE = re.compile(r"</?(?:tr|tbody|thead|table)\b[^<>]{0,300}>", re.I)


def strip_inline_tags(text: str) -> str:
    def _sup(m: re.Match) -> str:
        v = m.group(1)
        return v.translate(_SUPERSCRIPT) if re.fullmatch(r"[0-9+\-−]+", v) else v

    text = _SUP_TAG_RE.sub(_sup, text)
    text = _SUB_TAG_RE.sub(r"\1", text)
    text = _BR_RE.sub("\n", text)
    text = re.sub(r'<input\b[^>]*type="checkbox"[^>]*checked[^>]*>', "☒ ", text, flags=re.I)
    text = re.sub(r"<input\b[^>]*>", "☐ ", text, flags=re.I)
    # Table fragments outside a complete <table> (OCR page cuts): cells -> " | ", rows -> newline
    # Only the separators produced here are collapsed: Markdown tables (rows, empty cells) are
    # never touched.
    text = _ORPHAN_ROW_RE.sub("\n", text)
    text = _ORPHAN_CELL_RE.sub("\u241f", text)
    text = re.sub(r"(?:[ \t]*\u241f[ \t]*)+", " | ", text)
    return _INLINE_TAG_RE.sub("", text)


_DOUBLE_BULLET_RE = re.compile(r"(?m)^(\s*)[-*+]\s+(?:[-–—•●■▪◦○]\s+)+")
_DOUBLE_NUM_RE = re.compile(r"(?m)^(\s*)(\d{1,2}[.)])\s+\2\s+")


def collapse_list_markers(text: str) -> str:
    text = _DOUBLE_BULLET_RE.sub(r"\1- ", text)
    return _DOUBLE_NUM_RE.sub(r"\1\2 ", text)


_IMAGE_RE = re.compile(r"!\[([^\]]{0,2000})\]\(([^)]*)\)")
_DECORATIVE_ALT_RE = re.compile(
    r"\b(?:logo|logos|icon|icons|ic[ôo]ne|banner|wristband|photograph|photo|picture of|cover of|"
    r"qr ?code|signature|arrow pointing|decorative|header image|footer)\b",
    re.I,
)
_EN_WORDS_RE = re.compile(r"\b(?:the|with|and|of|showing|shows|which|are|is|a|an|in|on|for)\b", re.I)


def is_english(text: str) -> bool:
    words = re.findall(r"[A-Za-zÀ-ÿ']+", text)
    if len(words) < 4:
        return bool(_EN_WORDS_RE.search(text)) and not re.search(r"\b(?:le|la|les|des|du|une)\b", text, re.I)
    en = len(_EN_WORDS_RE.findall(text))
    fr = len(re.findall(r"\b(?:le|la|les|des|du|une|un|et|avec|pour|dans|sur)\b", text, re.I))
    return en >= 2 and en > fr


def rewrite_images(text: str) -> str:
    def _rep(m: re.Match) -> str:
        alt = re.sub(r"\s+", " ", m.group(1)).strip()
        if not alt or _DECORATIVE_ALT_RE.search(alt) or len(alt) < 12:
            return ""
        if is_english(alt):
            return f"[Image, description automatique en anglais : {alt}]"
        return f"[Image : {alt}]"

    return _IMAGE_RE.sub(_rep, text)


_MERMAID_BLOCK_RE = re.compile(r"```[ \t]*(?:mermaid)?\s*\n\s*((?:graph|flowchart)\s+[A-Z]{2}\b.*?)```", re.S | re.I)
_SHAPES = [("([", "])"), ("[[", "]]"), ("[(", ")]"), ("((", "))"), ("{{", "}}"), ("[/", "/]"), ("[\\", "\\]"),
           ("[", "]"), ("(", ")"), ("{", "}"), (">", "]")]
# Edges: labelled forms first ("-- label -->", "-. label .->", "== label ==>"; a label may contain
# ">" or "<"), then bidirectional and plain arrows, each with an optional "|label|".
_EDGE_AT_RE = re.compile(
    r"\s*(?:--\s*([^\s>\-;][^;\n]*?)\s*-->|==\s*([^\s=>;][^;\n]*?)\s*==>|-\.\s*([^\s.;][^;\n]*?)\s*\.->|"
    r"<-->|<-\.->|<==>|-->|---|-\.->|==>|-\.-|--o|--x)(?:\s*\|([^|]*)\|)?\s*"
)
_ID_RE = re.compile(r"\s*([A-Za-z0-9_\u00C0-\u017F]+)")


def _mermaid_label(raw: str) -> str:
    lab = re.sub(r"<br\s*/?>|\\n", " ", raw)
    lab = lab.strip().strip('"').strip("'")
    return re.sub(r"\s+", " ", lab).strip()


def _read_node(stmt: str, pos: int, labels: dict[str, str]) -> tuple[str | None, int]:
    m = _ID_RE.match(stmt, pos)
    if not m:
        return None, pos
    nid, pos = m.group(1), m.end()
    for op, cl in _SHAPES:
        if stmt.startswith(op, pos):
            j = pos + len(op)
            in_q = False
            depth = 0
            k = j
            while k < len(stmt):
                ch = stmt[k]
                if ch == '"':
                    in_q = not in_q
                elif not in_q and len(op) == 1 and ch == op and op in "[({":
                    depth += 1  # nested bracket inside the label ("[AOD]")
                elif not in_q and stmt.startswith(cl, k):
                    if depth == 0:
                        break
                    depth -= 1
                k += 1
            lab = _mermaid_label(stmt[j:k])
            if lab:
                old = labels.get(nid)
                if old is None or old in lab:
                    labels[nid] = lab
                elif lab not in old:
                    labels[nid] = f"{old} / {lab}"  # node redefined with another label
            return nid, min(len(stmt), k + len(cl))
    return nid, pos


def _split_statements(body: str) -> list[str]:
    out, buf, depth, in_q = [], [], 0, False
    for ch in body:
        if ch == '"':
            in_q = not in_q
        elif not in_q and ch in "[({":
            depth += 1
        elif not in_q and ch in "])}" and depth > 0:
            depth -= 1
        if not in_q and depth == 0 and ch in ";\n":
            cur = "".join(buf)
            # A newline inside an open edge label ("-- COMFORT > 26\nOu ... -->") does not end it
            if ch == "\n" and re.search(r"(?<![-<])--\s+(?!.*-->)[^;]*$", cur):
                buf.append(" ")
                continue
            out.append(cur)
            buf = []
            continue
        buf.append(" " if ch == "\n" else ch)
    out.append("".join(buf))
    return [x.strip() for x in out if x.strip()]


def mermaid_to_text(block: str) -> str:
    """Readable rendering of a Mermaid flowchart: one "A → (condition) B" line per edge chain."""
    body = block.split(None, 2)[2] if len(block.split(None, 2)) > 2 else ""
    labels: dict[str, str] = {}
    chains: list[list[tuple[str, str]]] = []
    for stmt in _split_statements(body):
        low = stmt.lower()
        if low.startswith(("%%", "style ", "classdef ", "class ", "linkstyle ", "click ", "direction ")) or low == "end":
            continue
        if low.startswith("subgraph"):
            t = _mermaid_label(stmt[len("subgraph"):])
            t = re.sub(r"^[\w]+\s*\[(.*)\]$", r"\1", t)
            if t:
                chains.append([("", f"[{t}]")])
            continue
        pos = 0
        chain: list[tuple[str, str]] = []
        nid, pos = _read_node(stmt, pos, labels)
        if nid is None:
            continue
        chain.append(("", nid))
        while pos < len(stmt):
            e = _EDGE_AT_RE.match(stmt, pos)
            if not e:
                break
            cond = next((g for g in e.groups() if g), "") or ""
            pos = e.end()
            nid, pos2 = _read_node(stmt, pos, labels)
            if nid is None:
                break
            pos = pos2
            chain.append((_mermaid_label(cond), nid))
        chains.append(chain)
    lines: list[str] = []
    used: set[str] = set()
    shown: set[str] = set()

    def _lab(nid: str) -> str:
        # Full label at first mention, then a short reminder (first 6 words) to keep the
        # flowchart about as long as its source.
        lab = labels.get(nid, nid)
        if nid in shown:
            words = lab.split()
            return " ".join(words[:6]) + (" …" if len(words) > 6 else "")
        shown.add(nid)
        return lab

    for chain in chains:
        if len(chain) == 1 and chain[0][1].startswith("["):
            lines.append(chain[0][1])
            continue
        if len(chain) < 2:
            continue
        txt = _lab(chain[0][1])
        used.add(chain[0][1])
        for cond, nid in chain[1:]:
            used.add(nid)
            lab = _lab(nid)
            txt += f" → ({cond}) {lab}" if cond else f" → {lab}"
        lines.append(txt)
    for nid, lab in labels.items():  # isolated nodes keep their text
        if nid not in used:
            lines.append(lab)
    return "[Organigramme (converti depuis le schéma OCR)]\n" + "\n".join(f"- {ln}" for ln in lines)


_MERMAID_KEYWORDS = {
    "graph", "flowchart", "subgraph", "end", "style", "classdef", "class", "linkstyle", "click",
    "fill", "stroke", "none", "width", "color",
}
_MERMAID_ID_RE = re.compile(
    r"(?:\b(\w+)\s*(?=\(\[|\[\[|\[\(|\(\(|\{\{|\[|\(|\{))"
    r"|(?:(?:^|[;\n&]|-->|---|==>|\.->|-\.-|<-->|\|)\s*(\w+)\s*(?=$|[;\n&]|-->|---|==>|-\.|--|<--|\||:::))",
    re.M,
)


def _fold_tokens(text: str) -> set[str]:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    out: set[str] = set()
    for tok in re.findall(r"[a-z0-9_]+(?:[.,]\d+)?", t):
        if tok.isalpha():
            if len(tok) >= 4:
                out.add(tok)
        elif tok[0].isdigit():  # "2", "0,5", "50ng" -> its leading number
            out.add(re.match(r"\d+(?:[.,]\d+)?", tok).group(0))
        # tokens starting with a letter and containing digits/underscores are identifiers
    return out


def mermaid_required_tokens(block: str) -> set[str]:
    """Numbers and words (>= 4 letters) of the labels of a Mermaid block: every token of the
    source except node identifiers and Mermaid keywords."""
    stmts = [x for x in _split_statements(block.split(None, 2)[2] if len(block.split(None, 2)) > 2 else "")]
    stmts = [x for x in stmts if not re.match(r"(?i)(?:%%|style|classdef|class|linkstyle|click|direction)\b", x)]
    body = "\n".join(stmts)
    ids = {(a or b).lower() for a, b in _MERMAID_ID_RE.findall(body)}
    return {t for t in _fold_tokens(body) if t not in ids and t not in _MERMAID_KEYWORDS}


def mermaid_block_to_text(block: str) -> str:
    """Rewritten flowchart, or the raw block (marked) when the rewrite would lose a number or a
    word of the source labels (fidelity guard)."""
    out = mermaid_to_text(block)
    if mermaid_required_tokens(block) - _fold_tokens(out):
        return "[Organigramme (syntaxe d'origine conservée)]\n" + block.strip()
    return out


def convert_mermaid(text: str) -> str:
    return _MERMAID_BLOCK_RE.sub(lambda m: mermaid_block_to_text(m.group(1)) + "\n", text)


# "µ g/kg" (LaTeX "\\mu g") -> "µg/kg": the micro sign always belongs to the unit that follows.
_MICRO_SPACE_RE = re.compile(r"µ[ \t]+(g|mg|mol|mmol|l|L|m|U|UI|s|V)\b")


def clean_chunk_text(text: str, nul_repairer: NulRepairer | None = None) -> str:
    """Full deterministic clean-up applied to the text of every table_aware_sota chunk."""
    if "\x00" in text:
        text = (nul_repairer or NulRepairer())(text)
    text = convert_mermaid(text)
    text = decode_entities(text)
    text = replace_math(text)
    text = strip_inline_tags(text)
    text = decode_entities(text)
    text = rewrite_images(text)
    text = collapse_list_markers(text)
    text = unicodedata.normalize("NFC", text)
    text = _MICRO_SPACE_RE.sub(r"µ\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
