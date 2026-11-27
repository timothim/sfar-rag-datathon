"""R1: Mermaid flowcharts — number of edges and of edge labels (yes/no conditions) in the source
block vs arrows / conditions in B2's rewritten text (text_cleaning.mermaid_to_text). CPU only."""
import re, collections
from pathlib import Path
from rag_sfar.ingestion import loader as L
from rag_sfar.ingestion.text_cleaning import _MERMAID_BLOCK_RE, mermaid_to_text
docs = L.load_sfar_corpus(Path("data/sfar_recommendations/output"), updates_dir=Path("data/corpus_updates"), use_corpus_updates=True)
EDGE = re.compile(r"-->|---|==>|-\.->|-\.-|--o|--x")
LAB = re.compile(r"-->\s*\|([^|]*)\||--\s*([^->|;\n][^>;\n]*?)\s*-->|==\s*([^=>;\n]+?)\s*==>|-\.\s*([^.;\n]+?)\s*\.->")
tot = collections.Counter(); bad = []
for d in docs:
    for m in _MERMAID_BLOCK_RE.finditer(d.text):
        src = m.group(1)
        body = "\n".join(l for l in src.splitlines() if not l.strip().lower().startswith(("style", "classdef", "class ", "linkstyle", "%%", "click")))
        n_edges = len(EDGE.findall(body))
        n_amp = len(re.findall(r"-->[^\n;]*&", body))
        labs = [next(g for g in mm.groups() if g is not None).strip() for mm in LAB.finditer(body)]
        out = mermaid_to_text(src)
        n_arrows = out.count(" → ")
        n_cond = len(re.findall(r"→ \(([^)]*)\)", out))
        tot["blocks"] += 1; tot["edges"] += n_edges; tot["arrows"] += n_arrows; tot["labels"] += len(labs); tot["conds"] += n_cond
        miss_labs = [l for l in labs if l and f"({l}" not in out and f"({re.sub(chr(34),'',l)}" not in out]
        if n_arrows < n_edges or miss_labs or n_amp:
            bad.append((d.metadata.doc_id, n_edges, n_arrows, len(labs), n_cond, n_amp, miss_labs[:4]))
print(dict(tot))
print("blocks with fewer arrows than source edges, missing edge labels, or '&' fan-out:", len(bad))
for b in bad: print("  ", b)

# Clinical tokens (numbers, units, comparators) and words present in a source block but absent from its rewrite
TOK = re.compile(r"[<>≤≥]?\s*\d+(?:[.,]\d+)?(?:\s*(?:-|à)\s*\d+(?:[.,]\d+)?)?\s*(?:mg/kg|µg/kg|UI/kg|ng/mL|mg|g|UI|mL|h|min|%|mmHg|SA|ans)?", re.I)
WRD = re.compile(r"[A-Za-zÀ-ÿ]{5,}")
print("\n== blocks whose rewrite loses numeric tokens or words ==")
nb = 0
for d in docs:
    for m in _MERMAID_BLOCK_RE.finditer(d.text):
        src = m.group(1)
        body = "\n".join(l for l in src.splitlines() if not l.strip().lower().startswith(("style", "classdef", "class ", "linkstyle", "%%", "click")))
        out = mermaid_to_text(src)
        o = re.sub(r"\s+", "", out)
        lost_t = sorted({re.sub(r"\s+", "", t) for t in TOK.findall(body) if re.search(r"\d", t)} - {t for t in {re.sub(r"\s+", "", t) for t in TOK.findall(body)} if t in o})
        ids = set(re.findall(r"(?m)^\s*([A-Za-z0-9_]+)\s*[\[({>]", body)) | set(re.findall(r"-->\s*(?:\|[^|]*\|)?\s*([A-Za-z0-9_]+)", body))
        lost_w = sorted({w for w in WRD.findall(re.sub(r"\b(?:%s)\b" % "|".join(map(re.escape, ids)) if ids else "^$", " ", body)) if w.lower() not in out.lower() and w.lower() not in ("graph", "flowchart", "style", "classdef", "subgraph")})
        if lost_t or lost_w:
            nb += 1
            print(f"  {d.metadata.doc_id[:70]}  lost_numbers={lost_t[:8]}  lost_words={lost_w[:8]}")
print("blocks with losses:", nb)
