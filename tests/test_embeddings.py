"""`corpus.embeddings`: status, lag and the incremental embed (spec 7.10, EMB-1..6, D11, E7, E8, PKG-8)."""

import subprocess
import sys
import types
from dataclasses import replace
from datetime import UTC, datetime

import pytest

pytest.importorskip("lancedb")

from hiivmind_corpus.embeddings import DIMENSIONS, HASH_COLUMN, META_TABLE, TABLE_NAME, EmbeddingsState, EmbedResult
from hiivmind_corpus.errors import ExtraMissing, NoModel
from hiivmind_corpus.store import save
from support import open_corpus

LANCE = "index-embeddings.lance"
REPO_DIR = "models--qdrant--bge-small-en-v1.5-onnx-q"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setenv("FASTEMBED_CACHE_PATH", str(tmp_path / "fastembed"))
    return open_corpus(tmp_path)


class Embedder:
    def __init__(self):
        self.seen = []

    def __call__(self, texts):
        self.seen.append(list(texts))
        return [[float(len(t))] + [0.0] * (DIMENSIONS - 1) for t in texts]


def _db(corpus):
    import lancedb

    return lancedb.connect(str(corpus.path / LANCE))


def _meta(corpus):
    arrow = _db(corpus).open_table(META_TABLE).to_arrow()
    return dict(zip(arrow.column("key").to_pylist(), arrow.column("value").to_pylist(), strict=True))


def _rows(corpus):
    return _db(corpus).open_table(TABLE_NAME).to_arrow().to_pylist()


def _model(tmp_path, repo=REPO_DIR):
    snap = tmp_path / "fastembed" / repo / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    (snap / "model_optimized.onnx").write_bytes(b"x")


def test_status_absent_without_the_lance_directory(corpus):
    assert corpus.embeddings.status() == EmbeddingsState.ABSENT


def test_status_not_installed(corpus, monkeypatch):
    (corpus.path / LANCE).mkdir()
    monkeypatch.setitem(sys.modules, "lancedb", None)
    assert corpus.embeddings.status() == EmbeddingsState.NOT_INSTALLED


def test_status_no_model(corpus):
    (corpus.path / LANCE).mkdir()
    assert corpus.embeddings.status() == EmbeddingsState.NO_MODEL
    assert not (corpus.path.parent / "fastembed").exists()


@pytest.mark.parametrize("repo", [REPO_DIR, "models--Qdrant--bge-small-en-v1.5-onnx-Q"])
def test_status_ready(corpus, tmp_path, repo):
    (corpus.path / LANCE).mkdir()
    _model(tmp_path, repo)
    assert corpus.embeddings.status() == EmbeddingsState.READY


def test_embed_builds_the_table_and_meta(corpus):
    assert corpus.embeddings.embed(Embedder()) == EmbedResult(total=3, embedded=3, removed=0)
    meta = _meta(corpus)
    assert meta["model"] == "BAAI/bge-small-en-v1.5" and meta["dimensions"] == "384"
    assert meta["generated_at"] == "2026-11-20T09:00:00Z" and meta["entry_count"] == "3"
    table = _db(corpus).open_table(TABLE_NAME)
    assert [f.name for f in table.schema] == ["id", "source", "title", "tags", "concepts", "metadata_text", "vector",
                                              "updated_at", HASH_COLUMN]
    row = next(r for r in _rows(corpus) if r["id"] == "polars:a.md")
    assert row["metadata_text"] == "Expressions | Expressions in Polars. | expressions | expressions"
    assert len(row["text_hash"]) == 64


def test_embed_is_incremental(corpus):
    embedder = Embedder()
    corpus.embeddings.embed(embedder)
    assert corpus.embeddings.embed(embedder) == EmbedResult(3, 0, 0)
    corpus.index.set_summary("polars:a.md", "A new summary.")
    embedder.seen.clear()
    assert corpus.embeddings.embed(embedder) == EmbedResult(3, 1, 0)
    assert len(embedder.seen) == 1 and len(embedder.seen[0]) == 1
    assert embedder.seen[0][0].startswith("passage: Expressions | A new summary.")


def test_embed_removes_rows_of_entries_no_longer_in_the_index(corpus):
    corpus.embeddings.embed(Embedder())
    index = corpus.index.load()
    save(corpus, index=replace(index, entries=index.entries[:-1]))
    assert corpus.embeddings.embed(Embedder()) == EmbedResult(2, 0, 1)
    assert {r["id"] for r in _rows(corpus)} == {e.id for e in index.entries[:-1]}
    assert _meta(corpus)["entry_count"] == "2"


def test_a_table_without_the_hash_column_is_rebuilt_once(corpus):
    import lancedb
    import pyarrow as pa

    schema = pa.schema([pa.field("id", pa.string()), pa.field("source", pa.string()), pa.field("title", pa.string()),
                        pa.field("tags", pa.list_(pa.string())), pa.field("concepts", pa.list_(pa.string())),
                        pa.field("metadata_text", pa.string()), pa.field("vector", pa.list_(pa.float32(), DIMENSIONS)),
                        pa.field("updated_at", pa.string())])
    old = [{"id": "polars:a.md", "source": "polars", "title": "t", "tags": [], "concepts": [], "metadata_text": "m",
            "vector": [0.0] * DIMENSIONS, "updated_at": "x"}]
    lancedb.connect(str(corpus.path / LANCE)).create_table(TABLE_NAME, data=pa.Table.from_pylist(old, schema=schema))
    embedder = Embedder()
    assert corpus.embeddings.embed(embedder) == EmbedResult(3, 3, 0)
    assert HASH_COLUMN in [f.name for f in _db(corpus).open_table(TABLE_NAME).schema]
    assert corpus.embeddings.embed(embedder) == EmbedResult(3, 0, 0)


def test_lag(corpus):
    assert corpus.embeddings.lag() is None
    corpus.embeddings.embed(Embedder())
    assert corpus.embeddings.lag() == 0
    index = corpus.index.load()
    later = datetime(2026, 11, 21, tzinfo=UTC)
    entries = tuple(replace(e, last_indexed=later) if n < 2 else e for n, e in enumerate(index.entries))
    save(corpus, index=replace(index, entries=entries))
    assert corpus.embeddings.lag() == 2


def test_lag_without_meta_and_with_the_old_generated_at(corpus):
    import lancedb
    import pyarrow as pa

    db = lancedb.connect(str(corpus.path / LANCE))
    db.create_table(TABLE_NAME, data=pa.Table.from_pylist([{"id": "x"}]))
    assert corpus.embeddings.lag() is None
    schema = pa.schema([pa.field("key", pa.string()), pa.field("value", pa.string())])
    db.create_table(META_TABLE, data=pa.Table.from_pylist(
        [{"key": "generated_at", "value": "2026-11-19T11:53:39.123456+00:00"}], schema=schema))
    assert corpus.embeddings.lag() == 0
    index = corpus.index.load()
    entries = (replace(index.entries[0], last_indexed=datetime(2026, 11, 19, 12, tzinfo=UTC)), *index.entries[1:])
    save(corpus, index=replace(index, entries=entries))
    assert corpus.embeddings.lag() == 1


def test_embed_without_the_model_raises_no_model(corpus, monkeypatch):
    monkeypatch.setitem(sys.modules, "fastembed", types.ModuleType("fastembed"))  # not a dev dependency
    with pytest.raises(NoModel) as caught:
        corpus.embeddings.embed()
    assert caught.value.code == "no-model" and "nothing was downloaded" in str(caught.value)
    assert not (corpus.path / LANCE).exists()
    assert not (corpus.path.parent / "fastembed").exists()
    corpus.embeddings.embed(Embedder())


def test_embed_and_lag_without_the_extra_raise_extra_missing(corpus, monkeypatch):
    assert corpus.embeddings.lag() is None
    (corpus.path / LANCE).mkdir()
    monkeypatch.setitem(sys.modules, "lancedb", None)
    with pytest.raises(ExtraMissing) as caught:
        corpus.embeddings.embed(Embedder())
    assert caught.value.code == "extra-missing" and "install hiivmind-corpus-lib[embeddings]" in str(caught.value)
    with pytest.raises(ExtraMissing):
        corpus.embeddings.lag()
    (corpus.path / LANCE).rmdir()
    assert corpus.embeddings.lag() is None


def test_embed_of_an_empty_index_creates_no_table(corpus):
    save(corpus, index=replace(corpus.index.load(), entries=()))
    assert corpus.embeddings.embed(Embedder()) == EmbedResult(0, 0, 0)
    assert not (corpus.path / LANCE / f"{TABLE_NAME}.lance").exists()


def test_importing_the_package_imports_no_embedding_library():
    code = "import sys, hiivmind_corpus; assert not {'fastembed', 'lancedb', 'pyarrow'} & set(sys.modules)"
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
