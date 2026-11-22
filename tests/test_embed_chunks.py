"""`corpus.embeddings.embed_chunks`: the chunks table, its indexes and `_meta` (EMB-1..4, P-5, CMP-4)."""

import sys

import pytest

pytest.importorskip("lancedb")

from hiivmind_corpus_lib import embeddings as emb
from hiivmind_corpus_lib.chunks import Chunk
from hiivmind_corpus_lib.corpus import Corpus
from hiivmind_corpus_lib.embeddings import META_TABLE, ChunkEmbedResult
from hiivmind_corpus_lib.errors import ExtraMissing, NoModel
from support import FIXED, LengthEmbedder, corpus_dir, open_corpus

LANCE = "index-embeddings.lance"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed"))
    monkeypatch.setattr(emb, "find_spec", lambda name: object())
    return open_corpus(tmp_path)


def _db(corpus):
    import lancedb

    return lancedb.connect(str(corpus.path / LANCE))


def _meta(corpus):
    arrow = _db(corpus).open_table(META_TABLE).to_arrow()
    return dict(zip(arrow.column("key").to_pylist(), arrow.column("value").to_pylist(), strict=True))


def _rows(corpus, table):
    return _db(corpus).open_table(table).to_arrow().to_pylist()


def ch(i, text, a, b, ctx=None, overlap=0):
    return Chunk(index=i, text=text, line_start=a, line_end=b, overlap_previous=overlap, heading_context=ctx)


def test_embed_chunks_builds_the_chunks_table(corpus):
    given = {("polars", "a.md"): [ch(0, "Getting started.", 1, 10), ch(1, "The API.", 8, 20, overlap=3)],
             ("polars", "docs/none.md"): [ch(0, "Perf.", 1, 15)]}
    assert corpus.embeddings.embed_chunks(given, LengthEmbedder()) == ChunkEmbedResult(files=2, total=3, embedded=3, removed=0)
    table = _db(corpus).open_table("chunks")
    assert [f.name for f in table.schema] == ["id", "parent", "source", "path", "chunk_index", "chunk_text", "heading_context",
                                              "line_start", "line_end", "overlap_previous", "vector", "updated_at", "text_hash"]
    rows = {r["id"]: r for r in _rows(corpus, "chunks")}
    assert set(rows) == {"polars:a.md#0", "polars:a.md#1", "polars:docs/none.md#0"}
    assert rows["polars:a.md#1"]["parent"] == "polars:a.md" and rows["polars:a.md#1"]["overlap_previous"] == 3
    assert (rows["polars:a.md#1"]["line_start"], rows["polars:a.md#1"]["line_end"]) == (8, 20)
    assert rows["polars:docs/none.md#0"]["parent"] is None


def test_the_vector_text_is_heading_context_pipe_text(corpus):
    embedder = LengthEmbedder()
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "Install it.", 1, 5, "Install > From PyPI"), ch(1, "Configure.", 6, 9)]}, embedder)
    assert embedder.seen == [["Install > From PyPI | Install it.", "Configure."]]


def test_an_unchanged_chunk_is_not_embedded_again(corpus):
    embedder = LengthEmbedder()
    given = {("polars", "a.md"): [ch(0, "One.", 1, 2), ch(1, "Two.", 3, 4)]}
    corpus.embeddings.embed_chunks(given, embedder); embedder.seen.clear()
    assert corpus.embeddings.embed_chunks(given, embedder) == ChunkEmbedResult(1, 2, 0, 0) and embedder.seen == []
    moved = {("polars", "a.md"): [ch(0, "One.", 1, 2), ch(1, "Two.", 30, 40)]}
    assert corpus.embeddings.embed_chunks(moved, embedder).embedded == 0
    assert {r["id"]: r["line_start"] for r in _rows(corpus, "chunks")}["polars:a.md#1"] == 30


def test_the_old_vector_is_kept_for_an_unchanged_chunk(corpus):
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "One.", 1, 2)]}, LengthEmbedder())
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "One.", 5, 6)]}, lambda texts: [[9.0] * 384 for _ in texts])
    row = _rows(corpus, "chunks")[0]
    assert row["vector"][0] == 4.0 and row["line_start"] == 5


def test_embed_chunks_replaces_a_files_rows_and_keeps_other_files(corpus):
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2), ch(1, "A1", 3, 4), ch(2, "A2", 5, 6)],
                                    ("polars", "b.md"): [ch(0, "B0", 1, 2)]}, LengthEmbedder())
    result = corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0 new", 1, 9)]}, LengthEmbedder())
    assert result == ChunkEmbedResult(files=1, total=1, embedded=1, removed=2)
    assert sorted(r["id"] for r in _rows(corpus, "chunks")) == ["polars:a.md#0", "polars:b.md#0"]
    assert next(r for r in _rows(corpus, "chunks") if r["id"] == "polars:a.md#0")["chunk_text"] == "A0 new"


def test_a_file_given_no_chunks_loses_its_rows(corpus):
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2)], ("polars", "b.md"): [ch(0, "B0", 1, 2)]}, LengthEmbedder())
    assert corpus.embeddings.embed_chunks({("polars", "a.md"): []}, LengthEmbedder()) == ChunkEmbedResult(1, 0, 0, 1)
    assert [r["id"] for r in _rows(corpus, "chunks")] == ["polars:b.md#0"]


def test_embed_chunks_with_nothing_to_write_creates_no_table(corpus):
    assert corpus.embeddings.embed_chunks({("polars", "a.md"): []}, LengthEmbedder()) == ChunkEmbedResult(1, 0, 0, 0)
    assert "chunks" not in _db(corpus).list_tables().tables


def test_chunks_get_a_full_text_index(corpus):  # EMB-2
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "text", 1, 2)]}, LengthEmbedder())
    assert [(i.index_type, i.columns) for i in _db(corpus).open_table("chunks").list_indices()] == [("FTS", ["chunk_text"])]


@pytest.mark.parametrize("n, vector_index", [(500, False), (501, True)])
def test_chunks_get_a_cosine_vector_index_above_500_rows(corpus, n, vector_index):  # EMB-3
    corpus.embeddings.embed_chunks({("polars", "big.md"): [ch(i, f"t{i}", i + 1, i + 1) for i in range(n)]}, LengthEmbedder())
    table = _db(corpus).open_table("chunks")
    vector = [i.name for i in table.list_indices() if i.index_type == "IvfPq"]
    assert bool(vector) is vector_index
    assert all(table.index_stats(name).distance_type == "cosine" for name in vector)


def test_chunk_meta_keeps_the_entry_count_and_embed_keeps_the_chunk_count(corpus):  # EMB-4
    corpus.embeddings.embed(LengthEmbedder())
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2), ch(1, "A1", 3, 4)]}, LengthEmbedder())
    assert _meta(corpus) | {} == {"model": "BAAI/bge-small-en-v1.5", "dimensions": "384", "generated_at": "2026-11-20T09:00:00Z",
                                  "entry_count": "3", "chunk_count": "2"}
    corpus.index.set_summary("polars:a.md", "Changed.")
    corpus.embeddings.embed(LengthEmbedder())
    assert _meta(corpus)["chunk_count"] == "2" and _meta(corpus)["entry_count"] == "3"


def test_chunk_count_counts_the_table_not_the_call(corpus):  # EMB-4
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2)]}, LengthEmbedder())
    corpus.embeddings.embed_chunks({("polars", "b.md"): [ch(0, "B0", 1, 2), ch(1, "B1", 3, 4)]}, LengthEmbedder())
    assert corpus.embeddings.meta().chunk_count == 3


def test_embed_chunks_keeps_generated_at_of_the_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed")); monkeypatch.setattr(emb, "find_spec", lambda name: object())
    now = [FIXED]; corpus = Corpus.open(corpus_dir(tmp_path), clock=lambda: now[0])
    corpus.embeddings.embed(LengthEmbedder()); now[0] = FIXED.replace(day=25)
    corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2)]}, LengthEmbedder())
    assert corpus.embeddings.meta().generated_at == FIXED


def test_embed_chunks_without_the_model_or_the_extra(corpus, monkeypatch):  # P-5, CMP-4
    with pytest.raises(NoModel) as caught:
        corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2)]})
    assert "nothing was downloaded" in str(caught.value) and not (corpus.path / LANCE).exists()
    monkeypatch.setitem(sys.modules, "lancedb", None)
    with pytest.raises(ExtraMissing):
        corpus.embeddings.embed_chunks({("polars", "a.md"): [ch(0, "A0", 1, 2)]}, LengthEmbedder())


def test_embed_chunks_with_nothing_to_write_creates_no_lance_directory(corpus):
    assert corpus.embeddings.embed_chunks({}, LengthEmbedder()) == ChunkEmbedResult(0, 0, 0, 0)
    assert corpus.embeddings.embed_chunks({("polars", "a.md"): []}, LengthEmbedder()).total == 0
    assert not (corpus.path / LANCE).exists()
