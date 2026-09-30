"""Runbook / past-incident corpus: markdown chunking + NIM embeddings + cosine search.

Chunks are `##` sections (prefixed with the `# Title`), merged until they reach
MIN_WORDS. Embeddings are cached on disk by sha256(chunk text + model id), so
repeat runs never call the API again for unchanged chunks.

CLI:  python -m engine.rag "query" [-k 3]     |     python -m engine.rag --chunks
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import numpy as np

from . import nim
from .config import CACHE_DIR, ROOT

CORPUS = (("runbooks", "runbook"), ("incidents", "incident"))
MIN_WORDS = 100
EMB_NPZ = CACHE_DIR / "embeddings.npz"
EMB_INDEX = CACHE_DIR / "embeddings_index.json"


@dataclass
class Chunk:
    chunk_id: str
    source: str
    kind: str
    title: str
    text: str


def chunk_markdown(path: Path, kind: Optional[str] = None) -> list[Chunk]:
    path = Path(path)
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next((l[2:].strip() for l in lines if l.startswith("# ")), path.stem)
    sections: list[list[str]] = [[]]
    for line in lines:
        if line.startswith("# "):
            continue
        if line.startswith("## ") and sections[-1]:
            sections.append([])
        sections[-1].append(line)
    merged: list[str] = []
    buf = ""
    for sec in ("\n".join(s).strip() for s in sections):
        if not sec:
            continue
        buf = f"{buf}\n\n{sec}" if buf else sec
        if len(buf.split()) >= MIN_WORDS:
            merged.append(buf)
            buf = ""
    if buf:
        if merged:
            merged[-1] += "\n\n" + buf
        else:
            merged.append(buf)
    try:
        source = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = path.as_posix()
    kind = kind or path.parent.name.rstrip("s")
    return [Chunk(f"{path.stem}#{n}", source, kind, title, f"# {title}\n\n{body}")
            for n, body in enumerate(merged)]


def load_chunks(root: Path = ROOT) -> list[Chunk]:
    chunks: list[Chunk] = []
    for folder, kind in CORPUS:
        for path in sorted((root / folder).glob("*.md")):
            chunks.extend(chunk_markdown(path, kind))
    return chunks


class SimpleVectorStore:
    """In-memory cosine-similarity index."""

    def __init__(self) -> None:
        self.ids: list[str] = []
        self.texts: list[str] = []
        self.metadata: list[dict] = []
        self._vectors: Optional[np.ndarray] = None  # L2-normalised rows

    def __len__(self) -> int:
        return len(self.ids)

    @staticmethod
    def _normalize(v: np.ndarray) -> np.ndarray:
        v = np.asarray(v, dtype=np.float32)
        norms = np.linalg.norm(v, axis=-1, keepdims=True)
        return v / np.where(norms == 0, 1, norms)

    def add(self, ids, texts, vectors, metadata=None) -> None:
        vectors = self._normalize(np.atleast_2d(vectors))
        self.ids.extend(ids)
        self.texts.extend(texts)
        self.metadata.extend(metadata or [{} for _ in ids])
        self._vectors = vectors if self._vectors is None else np.vstack([self._vectors, vectors])

    def query(self, vector_or_text: Union[str, np.ndarray], k: int = 3) -> list[tuple]:
        if self._vectors is None:
            return []
        if isinstance(vector_or_text, str):
            vector_or_text = nim.embed([vector_or_text], input_type="query")[0]
        scores = self._vectors @ self._normalize(vector_or_text)
        top = np.argsort(-scores)[:k]
        return [(float(scores[i]), self.ids[i], self.texts[i], self.metadata[i]) for i in top]


def _key(text: str, model: str) -> str:
    return hashlib.sha256(f"{model}\n{text}".encode("utf-8")).hexdigest()


def _load_cache() -> dict[str, np.ndarray]:
    try:
        index = json.loads(EMB_INDEX.read_text())
        matrix = np.load(EMB_NPZ)["vectors"]
        return {k: matrix[i] for k, i in index.items()}
    except (OSError, ValueError, KeyError):
        return {}


def _save_cache(cache: dict[str, np.ndarray]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    keys = list(cache)
    np.savez_compressed(EMB_NPZ, vectors=np.vstack([cache[k] for k in keys]))
    EMB_INDEX.write_text(json.dumps({k: i for i, k in enumerate(keys)}))


def build_store(force: bool = False) -> SimpleVectorStore:
    chunks = load_chunks()
    model = nim.embed_model()
    cache = {} if force else _load_cache()
    keys = [_key(c.text, model) for c in chunks]
    missing = [i for i, k in enumerate(keys) if k not in cache]
    if missing:
        vecs = nim.embed([chunks[i].text for i in missing], input_type="passage")
        for i, v in zip(missing, vecs):
            cache[keys[i]] = v
        _save_cache(cache)
    store = SimpleVectorStore()
    if chunks:
        store.add([c.chunk_id for c in chunks], [c.text for c in chunks],
                  np.vstack([cache[k] for k in keys]),
                  [{"source": c.source, "kind": c.kind, "title": c.title} for c in chunks])
    return store


def main() -> None:
    ap = argparse.ArgumentParser(description="Search the runbook/incident corpus.")
    ap.add_argument("query", nargs="?")
    ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--chunks", action="store_true", help="list chunks (no network)")
    args = ap.parse_args()
    if args.chunks or not args.query:
        chunks = load_chunks()
        for c in chunks:
            print(f"{c.chunk_id:48} {c.kind:9} {len(c.text.split()):4}w  {c.title}")
        print(f"{len(chunks)} chunks")
        return
    try:
        hits = build_store().query(args.query, args.k)
    except nim.NimUnavailable as exc:
        raise SystemExit(f"NIM unavailable: {exc}")
    for score, cid, text, meta in hits:
        print(f"[{score:.3f}] {cid}  ({meta['source']})")
        print("    " + text.replace("\n", " ")[:240] + "...")


if __name__ == "__main__":
    main()
