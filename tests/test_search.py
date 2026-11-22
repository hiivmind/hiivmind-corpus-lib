"""`corpus.search`: vector, hybrid and reranked search over entries and chunks (SCH-1..3, design §10 errors)."""

import math
import sys
import types

import pytest

pytest.importorskip("lancedb")

from hiivmind_corpus_lib import embeddings as emb
from hiivmind_corpus_lib.chunks import Chunk
from hiivmind_corpus_lib.errors import ExtraMissing, ModelMismatch, NoEmbeddings, NoModel, NoTextIndex
from hiivmind_corpus_lib.search import Mode
from support import TopicEmbedder, open_corpus

E = TopicEmbedder  # topics: expressions->0, lazy->1, reading->2
LANCE = "index-embeddings.lance"


def fresh_corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed"))
    monkeypatch.setattr(emb, "find_spec", lambda name: object())
    return open_corpus(tmp_path)


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    corpus = fresh_corpus(tmp_path, monkeypatch)
    corpus.embeddings.embed(TopicEmbedder())
    return corpus


@pytest.fixture
def chunked(corpus):
    corpus.embeddings.embed_chunks({
        ("polars", "a.md"): [Chunk(0, "Lazy rolling window example.", 120, 171, 0, "Guide > Rolling"),
                             Chunk(1, "Group by.", 172, 200, 5, None)],
        ("polars", "c.md"): [Chunk(0, "Reading files from disk.", 1, 20, 0, None)]}, TopicEmbedder())
    return corpus


def _db(corpus):
    import lancedb

    return lancedb.connect(str(corpus.path / LANCE))


def _overwrite_meta(corpus, model):
    import pyarrow as pa

    _db(corpus).create_table("_meta", data=pa.Table.from_pylist(
        [{"key": "model", "value": model}, {"key": "dimensions", "value": "384"},
         {"key": "generated_at", "value": "2026-11-20T09:00:00Z"}],
        schema=pa.schema([pa.field("key", pa.string()), pa.field("value", pa.string())])), mode="overwrite")


def test_vector_search_ranks_by_cosine(corpus):
    hits = corpus.search.entries("lazy evaluation", top_k=2, embedder=E())
    assert hits[0].id == "polars:b.md" and hits[0].score == 1.0 and hits[0].fields == {}
    assert len(hits) == 2


def test_the_query_is_embedded_with_the_query_prefix(corpus):
    e = E(); corpus.search.entries("lazy evaluation", embedder=e)
    assert e.seen == [["query: lazy evaluation"]]


def test_score_is_one_minus_distance_clamped_rounded_and_descending(tmp_path, monkeypatch):
    corpus = fresh_corpus(tmp_path, monkeypatch)
    near = [0.123456, math.sqrt(1 - 0.123456 ** 2)]
    by_title = {"Expressions": [1.0, 0.0], "Lazy API": near, "IO": [-1.0, 0.0]}

    def embedder(texts):
        return [[*([1.0, 0.0] if t.startswith("query: ") else
                   next(v for k, v in by_title.items() if t.startswith(f"passage: {k} |"))), *([0.0] * 382)] for t in texts]
    corpus.embeddings.embed(embedder)
    hits = corpus.search.entries("anything", embedder=embedder)
    assert [(h.id, h.score) for h in hits] == [("polars:a.md", 1.0), ("polars:b.md", 0.1235), ("polars:c.md", 0.0)]


def test_where_filters_with_a_lancedb_predicate(corpus):
    assert [h.id for h in corpus.search.entries("x", where="array_has_any(tags, ['lazy'])", embedder=E())] == ["polars:b.md"]
    assert [h.id for h in corpus.search.entries("x", where="title LIKE '%IO%'", embedder=E())] == ["polars:c.md"]
    assert corpus.search.entries("x", where="title = 'nope'", embedder=E()) == ()


def test_columns_fill_fields(corpus):
    hit = corpus.search.entries("lazy", columns=("title", "tags"), embedder=E())[0]
    assert dict(hit.fields) == {"title": "Lazy API", "tags": ["lazy"]}
    assert corpus.search.entries("lazy", columns=("nope",), embedder=E())[0].fields == {}
    with pytest.raises(TypeError):
        hit.fields["x"] = 1


def test_hybrid_fuses_text_and_vector_with_lancedbs_rrf(corpus, monkeypatch):
    from lancedb import rerankers
    made = []

    class Spy(rerankers.RRFReranker):
        def __init__(self, *a, **k): made.append(1); super().__init__(*a, **k)
    monkeypatch.setattr(rerankers, "RRFReranker", Spy)
    e = E(queries={"query: Reading files": 0})
    assert corpus.search.entries("Reading files", embedder=e)[0].id == "polars:a.md"
    hits = corpus.search.entries("Reading files", mode=Mode.HYBRID, embedder=e)
    assert hits[0].id == "polars:c.md" and made and 0 < hits[0].score < 1
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_hybrid_honours_where_and_columns(corpus):
    hits = corpus.search.entries("lazy", mode=Mode.HYBRID, where="id != 'polars:b.md'", columns=("title",), embedder=E())
    assert "polars:b.md" not in [h.id for h in hits] and all("title" in h.fields for h in hits)


def test_chunk_hits_carry_parent_and_lines(corpus, chunked):
    hits = corpus.search.chunks("rolling window example", embedder=E(queries={"query: rolling window example": 1}), top_k=10)
    assert [(h.id, h.score) for h in hits][0] == ("polars:a.md#0", 1.0)
    assert dict(hits[0].fields) == {"parent": "polars:a.md", "line_start": 120, "line_end": 171}
    assert corpus.search.chunks("x", embedder=E(), columns=("heading_context",))[0].fields.keys() == {"parent", "line_start", "line_end", "heading_context"}


def test_chunks_hybrid(corpus, chunked):
    hits = corpus.search.chunks("Reading files from disk", mode=Mode.HYBRID, embedder=E(), top_k=3)
    assert hits[0].id == "polars:c.md#0" and hits[0].fields["parent"] == "polars:c.md"


def test_rerank_rescores_with_the_injected_reranker(corpus):
    seen = []

    def reranker(query, texts):
        seen.append((query, list(texts)))
        return [float(len(t)) for t in texts]
    hits = corpus.search.entries("lazy", rerank=True, embedder=E(), reranker=reranker)
    assert seen[0][0] == "lazy" and "Expressions | Expressions in Polars. | expressions | expressions" in seen[0][1]
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True) and hits[0].id == "polars:a.md"
    assert hits[0].fields == {}


def test_default_reranker_is_fastembeds_cross_encoder_from_the_cache(corpus, tmp_path, monkeypatch):
    snap = tmp_path / "fastembed" / "models--Xenova--ms-marco-MiniLM-L-6-v2" / "snapshots" / "x" / "onnx"
    snap.mkdir(parents=True); (snap / "model.onnx").write_bytes(b"x")
    calls = {}

    class FakeEncoder:
        def __init__(self, model_name, **kwargs): calls["init"] = (model_name, kwargs)
        def rerank(self, query, documents):
            docs = list(documents); calls["rerank"] = (query, docs); return iter(float(i) for i in range(len(docs)))
    import importlib.machinery
    for name in ("fastembed", "fastembed.rerank", "fastembed.rerank.cross_encoder"):
        module = types.ModuleType(name)
        module.__spec__ = importlib.machinery.ModuleSpec(name, None)
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules["fastembed.rerank.cross_encoder"].TextCrossEncoder = FakeEncoder
    corpus.search.entries("lazy", rerank=True, embedder=E())
    assert calls["init"] == ("Xenova/ms-marco-MiniLM-L-6-v2", {"local_files_only": True}) and calls["rerank"][0] == "lazy"


# --- §10 errors ---
def test_no_embeddings_for_entries(tmp_path):
    corpus = open_corpus(tmp_path)
    with pytest.raises(NoEmbeddings) as caught: corpus.search.entries("x", embedder=E())
    assert str(caught.value) == "search: polars has no embeddings; run embed first." and caught.value.code == "no-embeddings"


def test_no_embeddings_wins_over_a_missing_reranker(tmp_path, monkeypatch):
    corpus = fresh_corpus(tmp_path, monkeypatch)
    with pytest.raises(NoEmbeddings): corpus.search.entries("x", rerank=True)


def test_no_embeddings_for_entries_when_only_chunks_are_embedded(tmp_path):
    corpus = open_corpus(tmp_path)
    corpus.embeddings.embed_chunks({("polars", "a.md"): [Chunk(0, "A0", 1, 2, 0, None)]}, E())
    with pytest.raises(NoEmbeddings) as caught: corpus.search.entries("x", embedder=E())
    assert str(caught.value) == "search: polars has no embeddings; run embed first."


def test_no_chunk_embeddings(corpus):
    with pytest.raises(NoEmbeddings) as caught: corpus.search.chunks("x", embedder=E())
    assert str(caught.value) == "search: polars has no chunk embeddings; run embed_chunks first."


def test_model_mismatch(corpus):
    _overwrite_meta(corpus, model="all-MiniLM-L6-v2")
    with pytest.raises(ModelMismatch) as caught: corpus.search.entries("x", embedder=E())
    assert str(caught.value) == ("search: the embeddings were built with all-MiniLM-L6-v2, not BAAI/bge-small-en-v1.5; run embed again.")
    assert caught.value.code == "model-mismatch"


def test_no_text_index_is_an_error_not_a_vector_fallback(corpus):
    _db(corpus).open_table("embeddings").drop_index("metadata_text_idx")
    with pytest.raises(NoTextIndex) as caught: corpus.search.entries("x", mode=Mode.HYBRID, embedder=E())
    assert str(caught.value) == "search: polars's embeddings have no text index; run embed again." and caught.value.code == "no-text-index"
    assert corpus.search.entries("x", embedder=E())


def test_vector_search_works_on_a_database_the_plugin_built(tmp_path):
    import json, lancedb, pyarrow as pa
    corpus = open_corpus(tmp_path)
    lance = corpus.path / "index-embeddings.lance"
    db = lancedb.connect(str(lance))
    db.create_table("embeddings", pa.table({
        "id": ["polars:a.md", "polars:b.md"], "source": ["polars"] * 2, "title": ["A", "B"],
        "tags": [[], []], "concepts": [[], []], "metadata_text": ["alpha", "beta"],
        "vector": pa.array([E()(["alpha"])[0], E()(["beta"])[0]], type=pa.list_(pa.float32(), 384)),
        "updated_at": ["2026-01-01T00:00:00Z"] * 2}))
    (lance / "_meta.json").write_text(json.dumps({"model": "BAAI/bge-small-en-v1.5", "dimensions": 384,
                                                 "generated_at": "2026-01-01T00:00:00Z", "entry_count": 2}))
    assert corpus.embeddings.meta().model == "BAAI/bge-small-en-v1.5"
    assert [h.id for h in corpus.search.entries("alpha", top_k=1, embedder=E())] == ["polars:a.md"]
    with pytest.raises(NoTextIndex):
        corpus.search.entries("alpha", mode=Mode.HYBRID, embedder=E())


def test_no_model_for_the_query_embedding(corpus):
    with pytest.raises(NoModel) as caught: corpus.search.entries("x")
    assert "BAAI/bge-small-en-v1.5" in str(caught.value) and not (corpus.path.parent / "fastembed").exists()


def test_no_model_for_the_reranker(corpus):
    with pytest.raises(NoModel) as caught: corpus.search.entries("x", rerank=True, embedder=E())
    assert "Xenova/ms-marco-MiniLM-L-6-v2" in str(caught.value) and "nothing was downloaded" in str(caught.value)
    assert not (corpus.path.parent / "fastembed").exists()


def test_search_without_the_extra_raises_extra_missing(corpus, monkeypatch):
    monkeypatch.setitem(sys.modules, "lancedb", None)
    with pytest.raises(ExtraMissing): corpus.search.entries("x", embedder=E())


def test_search_writes_nothing(corpus):
    before = sorted(p.name for p in (corpus.path / "index-embeddings.lance").rglob("*"))
    corpus.search.entries("lazy", mode=Mode.HYBRID, embedder=E())
    assert sorted(p.name for p in (corpus.path / "index-embeddings.lance").rglob("*")) == before
