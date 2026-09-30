"""RAG corpus / vector store / NIM client tests (no network)."""
import numpy as np
import pytest

from engine import config, nim, rag


def test_chunking_counts_ids_and_title_prefix():
    chunks = rag.load_chunks()
    assert 15 <= len(chunks) <= 30
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    assert {c.kind for c in chunks} == {"runbook", "incident"}
    for c in chunks:
        assert c.text.startswith("# " + c.title)
        assert c.chunk_id.split("#")[1].isdigit()
        assert c.source.startswith(("runbooks/", "incidents/"))


def test_chunk_markdown_merges_tiny_sections(tmp_path):
    p = tmp_path / "x.md"
    p.write_text("# T\n\n## A\nshort\n\n## B\n" + "word " * 120 + "\n\n## C\ntail\n")
    chunks = rag.chunk_markdown(p, "runbook")
    assert [c.chunk_id for c in chunks] == ["x#0"]
    assert "short" in chunks[0].text and "tail" in chunks[0].text


def test_vector_store_cosine_ranking():
    store = rag.SimpleVectorStore()
    store.add(["a", "b", "c"], ["ta", "tb", "tc"],
              np.array([[1, 0], [0, 5], [1, 1]], dtype=float), [{"n": 1}, {"n": 2}, {"n": 3}])
    hits = store.query(np.array([0.1, 1.0]), k=2)
    assert [h[1] for h in hits] == ["b", "c"]
    assert hits[0][0] == pytest.approx(0.995, abs=1e-3)
    assert hits[0][3] == {"n": 2}


def test_query_text_uses_query_input_type(monkeypatch):
    calls = []

    def fake(texts, input_type="passage"):
        calls.append(input_type)
        return np.array([[1.0, 0.0]] * len(texts))

    monkeypatch.setattr(nim, "embed", fake)
    store = rag.SimpleVectorStore()
    store.add(["a", "b"], ["ta", "tb"], np.array([[1, 0], [0, 1]]))
    assert store.query("hello", k=1)[0][1] == "a"
    assert calls == ["query"]


def test_embedding_cache_reuse(tmp_path, monkeypatch):
    monkeypatch.setattr(rag, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(rag, "EMB_NPZ", tmp_path / "embeddings.npz")
    monkeypatch.setattr(rag, "EMB_INDEX", tmp_path / "embeddings_index.json")
    monkeypatch.setattr(nim, "embed_model", lambda: "fake-model")
    calls = []

    def fake(texts, input_type="passage"):
        calls.append(len(texts))
        return np.array([[len(t) % 7 + 1, len(t) % 5 + 1, 1.0] for t in texts])

    monkeypatch.setattr(nim, "embed", fake)
    first = rag.build_store()
    second = rag.build_store()
    assert calls == [len(first)]          # second build made no API call
    assert len(second) == len(first)
    rag.build_store(force=True)
    assert len(calls) == 2


def test_nim_unavailable_when_key_empty(monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_EMBED_API_KEY", "")
    monkeypatch.setattr(config, "NVIDIA_CHAT_API_KEY", "")
    with pytest.raises(nim.NimUnavailable):
        nim.embed(["x"])
    with pytest.raises(nim.NimUnavailable):
        nim.chat([{"role": "user", "content": "hi"}])


def test_pick_models_preferences():
    ids = ["meta/llama-3.1-8b-instruct", "google/gemma-3-27b-it", "google/gemma-4-31b-it",
           "nvidia/llama-3.2-nv-embedqa-1b-v2", "nvidia/nemotron-3-embed-1b"]
    assert nim.pick_models(ids) == {"chat": "google/gemma-4-31b-it", "embed": "nvidia/nemotron-3-embed-1b"}
    fb = nim.pick_models(ids[:2] + ids[3:4])
    assert fb == {"chat": "google/gemma-3-27b-it", "embed": "nvidia/llama-3.2-nv-embedqa-1b-v2"}
    assert nim.pick_models(["x/some-embed-model", "y/foo-chat"])["embed"] == "x/some-embed-model"


def test_resolve_models_with_mocked_get(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "NVIDIA_CHAT_API_KEY", "test-key")
    monkeypatch.setattr(nim, "MODELS_CACHE", tmp_path / "nim_models.json")
    monkeypatch.setattr(nim, "_verify", lambda: True)

    class Resp:
        status_code = 200
        url = nim.MODELS_URL

        def json(self):
            ids = ["google/gemma-4-31b-it", "nvidia/nemotron-3-embed-1b"]
            return {"data": [{"id": i} for i in ids]}

    calls = []
    monkeypatch.setattr(nim.requests, "get", lambda *a, **k: calls.append(1) or Resp())
    assert nim.resolve_models() == {"chat": "google/gemma-4-31b-it", "embed": "nvidia/nemotron-3-embed-1b"}
    assert (tmp_path / "nim_models.json").exists()
    nim.resolve_models()
    assert len(calls) == 1               # second call served from cache
