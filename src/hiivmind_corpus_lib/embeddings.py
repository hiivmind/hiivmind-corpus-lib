"""`corpus.embeddings`: the Lance table of entry vectors, its status, lag and incremental embed (spec 7.10).

`fastembed`, `lancedb` and `pyarrow` are imported only when an operation needs them (PKG-8).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from importlib.util import find_spec
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any

from .errors import ExtraMissing, NoModel
from .schema import parse_timestamp, stamp

if TYPE_CHECKING:
    from .chunks import Chunk
    from .corpus import Corpus

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
TABLE_NAME = "embeddings"
META_TABLE = "_meta"
PASSAGE_PREFIX = "passage: "
QUERY_PREFIX = "query: "
CHUNKS_TABLE = "chunks"
VECTOR_INDEX_THRESHOLD = 500
FTS_COLUMN = {TABLE_NAME: "metadata_text", CHUNKS_TABLE: "chunk_text"}
HASH_COLUMN = "text_hash"
LANCE_DIR = "index-embeddings.lance"
MODEL_REPO_DIR = "models--qdrant--bge-small-en-v1.5-onnx-q"
MODEL_FILE = "model_optimized.onnx"
EXTRA_HINT = "install hiivmind-corpus-lib[embeddings]"

Embedder = Callable[[Sequence[str]], Sequence[Sequence[float]]]


class EmbeddingsState(StrEnum):
    ABSENT = "absent"
    NOT_INSTALLED = "not-installed"
    NO_MODEL = "no-model"
    READY = "ready"


@dataclass(frozen=True)
class EmbedResult:
    total: int
    embedded: int
    removed: int


@dataclass(frozen=True)
class ChunkEmbedResult:
    files: int
    total: int
    embedded: int
    removed: int


@dataclass(frozen=True)
class EmbeddingsMeta:
    model: str
    dimensions: int
    generated_at: datetime
    entry_count: int | None
    chunk_count: int | None


def cache_dir() -> Path:
    given = os.environ.get("FASTEMBED_CACHE_PATH")
    return Path(given) if given else Path(tempfile.gettempdir()) / "fastembed_cache"


def cached_file(name: str, repo_dir: str = MODEL_REPO_DIR) -> Path | None:
    """The first `<cache>/<repo dir>/snapshots/*/<name>`. Creates nothing: fastembed's own lookup would create the directory."""
    try:
        repos = [p for p in cache_dir().iterdir() if p.name.lower() == repo_dir]
    except OSError:
        return None
    for repo in repos:
        for found in (repo / "snapshots").glob(f"*/{name}"):
            return found
    return None


def _model_cached() -> bool:
    return cached_file(MODEL_FILE) is not None


TOKENIZER_FILE = "tokenizer.json"


def cached_tokenizer_file() -> Path | None:
    """The model's tokenizer file, only when the extras are importable and the model itself is cached."""
    if find_spec("fastembed") is None or find_spec("tokenizers") is None or not _model_cached():
        return None
    return cached_file(TOKENIZER_FILE)


def _text_of(entry) -> str:
    return f"{entry.title or ''} | {entry.summary or ''} | {', '.join(entry.tags or ())} | {', '.join(entry.concepts or ())}"


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _default_embedder() -> Embedder:
    from fastembed import TextEmbedding

    model: Any = TextEmbedding(model_name=MODEL_NAME, local_files_only=True)  # embed() yields numpy arrays of several dtypes
    return lambda texts: [vector.tolist() for vector in model.embed(list(texts))]


def require_lance(*, fastembed: bool = True) -> tuple[ModuleType, ModuleType]:
    """The libraries of the extra; `fastembed` is only looked for, never imported (it loads onnxruntime)."""
    try:
        import lancedb
        import pyarrow
    except ImportError as exc:
        raise ExtraMissing(f"the embeddings extra is not installed: {EXTRA_HINT}") from exc
    if fastembed and find_spec("fastembed") is None:
        raise ExtraMissing(f"the embeddings extra is not installed: {EXTRA_HINT}")
    return lancedb, pyarrow


def lance_dir(corpus: Corpus) -> Path:
    return corpus.path / LANCE_DIR


def resolve_embedder(embedder: Embedder | None) -> Embedder:
    """The injected embedder, else the cached model's; never downloads."""
    if embedder is not None:
        return embedder
    if not _model_cached():
        raise NoModel(f"the model {MODEL_NAME} is not in the fastembed cache {cache_dir()}; nothing was downloaded")
    return _default_embedder()


def _ensure_indexes(table, name: str, changed: bool) -> None:
    """Full-text index, and a cosine vector index above the threshold; rebuilt when rows changed or the text index is missing."""
    from lancedb.index import FTS, IvfPq

    if not changed and any(i.index_type == "FTS" for i in table.list_indices()):
        return
    table.create_index(FTS_COLUMN[name], config=FTS(), replace=True)
    if table.count_rows() > VECTOR_INDEX_THRESHOLD:
        table.create_index("vector", config=IvfPq(distance_type="cosine"), replace=True)


def _read_meta(db, directory: Path) -> dict[str, str]:
    """The `_meta` table, else the legacy `_meta.json`; empty when neither exists."""
    if META_TABLE in db.list_tables().tables:
        arrow = db.open_table(META_TABLE).to_arrow()
        return dict(zip(arrow.column("key").to_pylist(), arrow.column("value").to_pylist(), strict=True))
    legacy = directory / "_meta.json"
    if legacy.is_file():
        return {k: str(v) for k, v in json.loads(legacy.read_text(encoding="utf-8")).items() if v is not None}
    return {}


def _write_meta(db, pa, directory: Path, now: str, *, generated_at: str | None = None,
                entry_count: int | None = None, chunk_count: int | None = None) -> None:
    """Overwrite `_meta`: each argument, else the existing value (`generated_at` finally `now`)."""
    old = _read_meta(db, directory)
    meta = {"model": MODEL_NAME, "dimensions": str(DIMENSIONS), "generated_at": generated_at or old.get("generated_at") or now}
    for key, count in (("entry_count", entry_count), ("chunk_count", chunk_count)):
        value = str(count) if count is not None else old.get(key)
        if value is not None:
            meta[key] = value
    fields = pa.schema([pa.field("key", pa.string()), pa.field("value", pa.string())])
    data = pa.Table.from_pylist([{"key": k, "value": v} for k, v in meta.items()], schema=fields)
    db.create_table(META_TABLE, data=data, mode="overwrite")


class EmbeddingsCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    @property
    def _dir(self) -> Path:
        return lance_dir(self._corpus)

    def _require(self, *, fastembed: bool = True):
        return require_lance(fastembed=fastembed)

    def status(self) -> EmbeddingsState:
        if not self._dir.is_dir():
            return EmbeddingsState.ABSENT
        try:
            self._require()
        except ExtraMissing:
            return EmbeddingsState.NOT_INSTALLED
        return EmbeddingsState.READY if _model_cached() else EmbeddingsState.NO_MODEL

    def lag(self) -> int | None:
        """Entries indexed after the table was generated; `None` when there is no table or no `_meta`."""
        if not self._dir.is_dir():
            return None
        lancedb, _ = self._require()
        db = lancedb.connect(str(self._dir))
        if META_TABLE not in db.list_tables().tables:
            return None
        arrow = db.open_table(META_TABLE).to_arrow()
        meta = dict(zip(arrow.column("key").to_pylist(), arrow.column("value").to_pylist(), strict=True))
        generated = meta.get("generated_at")
        if generated is None:
            return None
        when = parse_timestamp(generated, LANCE_DIR, "_meta.generated_at")
        return sum(1 for e in self._corpus.index.load().entries
                   if isinstance(e.last_indexed, datetime) and e.last_indexed > when)

    def embed(self, embedder: Embedder | None = None) -> EmbedResult:
        lancedb, pa = self._require(fastembed=embedder is None)
        embedder = resolve_embedder(embedder)
        entries = self._corpus.index.load().entries
        db = lancedb.connect(str(self._dir)) if entries or self._dir.is_dir() else None
        if db is None:
            return EmbedResult(0, 0, 0)

        rows = {}
        for entry in entries:
            text = _text_of(entry)
            rows[entry.id] = (entry, text.strip(), hashlib.sha256((PASSAGE_PREFIX + text).strip().encode("utf-8")).hexdigest())

        existing: dict[str, str | None] = {}
        table = None
        rebuild = False
        if TABLE_NAME in db.list_tables().tables:
            table = db.open_table(TABLE_NAME)
            rebuild = HASH_COLUMN not in [f.name for f in table.schema]  # the old table: rebuilt once (D11, EMB-6)
            columns = ["id"] if rebuild else ["id", HASH_COLUMN]
            arrow = table.to_arrow().select(columns)
            ids = arrow.column("id").to_pylist()
            existing = dict(zip(ids, [None] * len(ids) if rebuild else arrow.column(HASH_COLUMN).to_pylist(), strict=True))
        todo = [r for r in rows.values() if existing.get(r[0].id) != r[2]]
        gone = [i for i in existing if i not in rows]

        schema = None
        if todo or rebuild:
            vectors = embedder([(PASSAGE_PREFIX + r[1]).strip() for r in todo]) if todo else []
            now = stamp(self._corpus.now())
            schema = pa.schema([pa.field("id", pa.string()), pa.field("source", pa.string()), pa.field("title", pa.string()),
                                pa.field("tags", pa.list_(pa.string())), pa.field("concepts", pa.list_(pa.string())),
                                pa.field("metadata_text", pa.string()),
                                pa.field("vector", pa.list_(pa.float32(), DIMENSIONS)),
                                pa.field("updated_at", pa.string()), pa.field(HASH_COLUMN, pa.string())])
            records = [{"id": e.id, "source": e.source, "title": e.title or "", "tags": list(e.tags or ()),
                        "concepts": list(e.concepts or ()), "metadata_text": text, "vector": [float(x) for x in vector],
                        "updated_at": now, HASH_COLUMN: digest}
                       for (e, text, digest), vector in zip(todo, vectors, strict=True)]
            data = pa.Table.from_pylist(records, schema=schema)
            if rebuild or table is None:
                table = db.create_table(TABLE_NAME, data=data, mode="overwrite")
            else:
                table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        if gone and not rebuild and table is not None:
            table.delete(f"id IN ({', '.join(_sql_quote(i) for i in gone)})")

        if table is not None:
            _ensure_indexes(table, TABLE_NAME, bool(todo or rebuild or gone))
            _write_meta(db, pa, self._dir, stamp(self._corpus.now()), generated_at=stamp(self._corpus.now()),
                        entry_count=len(rows))
        return EmbedResult(len(rows), len(todo), len(gone))

    def embed_chunks(self, chunks: Mapping[tuple[str, str], Sequence[Chunk]], embedder: Embedder | None = None) -> ChunkEmbedResult:
        """Replace the chunk rows of each given (source, path); other files' rows stay. Unchanged chunks keep their vectors."""
        lancedb, pa = self._require(fastembed=embedder is None)
        embedder = resolve_embedder(embedder)
        if not any(chunks.values()) and not self._dir.is_dir():
            return ChunkEmbedResult(len(chunks), 0, 0, 0)
        db = lancedb.connect(str(self._dir))
        index = self._corpus.index.load()
        now = stamp(self._corpus.now())

        table = db.open_table(CHUNKS_TABLE) if CHUNKS_TABLE in db.list_tables().tables else None
        old: dict[str, dict] = {}
        if table is not None:
            wanted = " OR ".join(f"(source = {_sql_quote(s)} AND path = {_sql_quote(p)})" for s, p in chunks)
            if wanted:
                old = {r["id"]: r for r in table.search().where(wanted).limit(None).to_arrow().to_pylist()}

        given: dict[str, tuple] = {}
        for (source, path), items in chunks.items():
            entry = index.find(source, path)
            for c in items:
                text = f"{c.heading_context} | {c.text}" if c.heading_context else c.text
                given[f"{source}:{path}#{c.index}"] = (source, path, c, entry.id if entry else None, text,
                                                       hashlib.sha256(text.encode("utf-8")).hexdigest())
        gone = [i for i in old if i not in given]

        def same(cid: str, row: dict) -> bool:
            source, path, c, parent, _, digest = given[cid]
            return (row["text_hash"], row["parent"], row["line_start"], row["line_end"], row["overlap_previous"],
                    row["heading_context"]) == (digest, parent, c.line_start, c.line_end, c.overlap_previous, c.heading_context)

        write = [i for i in given if i not in old or not same(i, old[i])]
        fresh = [i for i in write if i not in old or old[i]["text_hash"] != given[i][5]]
        vectors = list(embedder([given[i][4] for i in fresh])) if fresh else []
        new_vectors = dict(zip(fresh, vectors, strict=True))
        if write:
            schema = pa.schema([pa.field("id", pa.string()), pa.field("parent", pa.string()), pa.field("source", pa.string()),
                                pa.field("path", pa.string()), pa.field("chunk_index", pa.int64()),
                                pa.field("chunk_text", pa.string()), pa.field("heading_context", pa.string()),
                                pa.field("line_start", pa.int64()), pa.field("line_end", pa.int64()),
                                pa.field("overlap_previous", pa.int64()),
                                pa.field("vector", pa.list_(pa.float32(), DIMENSIONS)),
                                pa.field("updated_at", pa.string()), pa.field(HASH_COLUMN, pa.string())])
            records = []
            for cid in write:
                source, path, c, parent, _, digest = given[cid]
                vector = new_vectors[cid] if cid in new_vectors else old[cid]["vector"]
                records.append({"id": cid, "parent": parent, "source": source, "path": path, "chunk_index": c.index,
                                "chunk_text": c.text, "heading_context": c.heading_context, "line_start": c.line_start,
                                "line_end": c.line_end, "overlap_previous": c.overlap_previous,
                                "vector": [float(x) for x in vector], "updated_at": now, HASH_COLUMN: digest})
            data = pa.Table.from_pylist(records, schema=schema)
            if table is None:
                table = db.create_table(CHUNKS_TABLE, data=data)
            else:
                table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        if gone and table is not None:
            table.delete(f"id IN ({', '.join(_sql_quote(i) for i in gone)})")

        if table is not None:
            _ensure_indexes(table, CHUNKS_TABLE, bool(write or gone))
            _write_meta(db, pa, self._dir, now, chunk_count=table.count_rows())
        return ChunkEmbedResult(len(chunks), len(given), len(fresh), len(gone))

    def meta(self) -> EmbeddingsMeta | None:
        if not self._dir.is_dir():
            return None
        lancedb, _ = self._require(fastembed=False)
        values = _read_meta(lancedb.connect(str(self._dir)), self._dir)
        if not all(values.get(k) for k in ("model", "dimensions", "generated_at")):
            return None
        counts = {k: int(values[k]) if values.get(k) is not None else None for k in ("entry_count", "chunk_count")}
        return EmbeddingsMeta(values["model"], int(values["dimensions"]),
                              parse_timestamp(values["generated_at"], LANCE_DIR, "_meta.generated_at"), **counts)
