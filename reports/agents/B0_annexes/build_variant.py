"""Build an ablation index variant without changing the code base.
usage: build_variant.py <output_dir> [--nointro] [--updates DIR]"""
import re, sys
from pathlib import Path
from rag_sfar.config import Settings
from rag_sfar.ingestion import chunker
from rag_sfar.cli import build_and_save_index

args = sys.argv[1:]
out = Path(args[0])
updates = Path(args[args.index("--updates") + 1]) if "--updates" in args else None
if "--nointro" in args:
    orig = chunker._semantic_heading_level
    def patched(raw_level, htext, has_champ_or_partie=False):
        if re.match(r"^INTRODUCTION\b", htext.strip().upper()) and raw_level <= 2:
            return max(3, raw_level) if has_champ_or_partie else raw_level
        return orig(raw_level, htext, has_champ_or_partie)
    chunker._semantic_heading_level = patched
s = Settings()
build_and_save_index(corpus_dir=s.corpus_dir, output_dir=out, strategy="table_aware_sota",
                     embedding_provider=s.embedding_provider, embedding_model=s.embedding_model,
                     batch_size=s.embedding_batch_size, corpus_updates_dir=updates)
