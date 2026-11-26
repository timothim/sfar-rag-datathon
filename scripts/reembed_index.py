"""Re-embed an existing index with another dense model, without re-chunking.

Copies chunks, metadata, BM25 and char n-gram indexes from --src into a NEW folder --dst and
recomputes only the dense embeddings (non-bibliography chunks, as in the original build), so the
only variable that changes is the embedding model.

    HF_HUB_OFFLINE=0 .venv/bin/python scripts/reembed_index.py \
        --src index/table_aware_sota --dst index/tas_qwen3emb06 --model Qwen/Qwen3-Embedding-0.6B
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path

import numpy as np

from rag_sfar.retrieval.embedder import build_embedder
from rag_sfar.retrieval.vector_store import LocalVectorStore


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, required=True)
    ap.add_argument("--dst", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--device", default=None)
    args = ap.parse_args()

    if args.dst.exists():
        raise SystemExit(f"{args.dst} exists; refusing to overwrite an index.")
    store = LocalVectorStore.load(args.src)
    t0 = time.perf_counter()
    emb = build_embedder(provider="sentence_transformer", model_name=args.model, device=args.device)
    active = [i for i, c in enumerate(store.chunks) if not c.is_reference_section]
    texts = [store.chunks[i].indexed_text for i in active]
    vecs = emb.embed_documents(texts, batch_size=args.batch_size)
    embeddings = np.zeros((len(store.chunks), vecs.shape[1]), dtype=np.float32)
    embeddings[active] = vecs

    args.dst.mkdir(parents=True)
    for name in ("metadata.sqlite", "bm25.pkl", "subword.pkl"):
        if (args.src / name).exists():
            shutil.copy2(args.src / name, args.dst / name)
    np.save(args.dst / "embeddings.npy", embeddings)
    manifest = json.loads((args.src / "manifest.json").read_text(encoding="utf-8"))
    manifest.update(
        embedding_provider="sentence_transformer",
        embedding_model=args.model,
        embedding_dim=int(vecs.shape[1]),
        reembedded_from=str(args.src),
        reembed_seconds=round(time.perf_counter() - t0, 1),
    )
    (args.dst / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(active)} chunks embedded with {args.model} ({vecs.shape[1]}d) in {manifest['reembed_seconds']}s -> {args.dst}")


if __name__ == "__main__":
    main()
