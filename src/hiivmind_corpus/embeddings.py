"""`corpus.embeddings`: the Lance table of entry vectors, its status, lag and incremental embed (spec 7.10).

`fastembed`, `lancedb` and `pyarrow` are imported only when an operation needs them (PKG-8).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ExtraMissing, NoModel
from .schema import parse_timestamp, stamp

if TYPE_CHECKING:
    from .corpus import Corpus

MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIMENSIONS = 384
TABLE_NAME = "embeddings"
META_TABLE = "_meta"
PASSAGE_PREFIX = "passage: "
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


def _cache_dir() -> Path:
    given = os.environ.get("FASTEMBED_CACHE_PATH")
    return Path(given) if given else Path(tempfile.gettempdir()) / "fastembed_cache"


def _model_cached() -> bool:
    """Whether fastembed's cache holds the model. Creates nothing: fastembed's own lookup would create the directory."""
    try:
        repos = [p for p in _cache_dir().iterdir() if p.name.lower() == MODEL_REPO_DIR]
    except OSError:
        return False
    return any(any((repo / "snapshots").glob(f"*/{MODEL_FILE}")) for repo in repos)


def _text_of(entry) -> str:
    return f"{entry.title or ''} | {entry.summary or ''} | {', '.join(entry.tags or ())} | {', '.join(entry.concepts or ())}"


def _sql_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _default_embedder() -> Embedder:
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name=MODEL_NAME, local_files_only=True)
    return lambda texts: [vector.tolist() for vector in model.embed(list(texts))]


class EmbeddingsCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    @property
    def _dir(self) -> Path:
        return self._corpus.path / LANCE_DIR

    def _require(self, *, model: bool):
        try:
            import lancedb
            import pyarrow

            if model:
                import fastembed  # noqa: F401
        except ImportError as exc:
            raise ExtraMissing(f"the embeddings extra is not installed: {EXTRA_HINT}") from exc
        return lancedb, pyarrow

    def status(self) -> EmbeddingsState:
        if not self._dir.is_dir():
            return EmbeddingsState.ABSENT
        try:
            self._require(model=False)
        except ExtraMissing:
            return EmbeddingsState.NOT_INSTALLED
        return EmbeddingsState.READY if _model_cached() else EmbeddingsState.NO_MODEL

    def lag(self) -> int | None:
        """Entries indexed after the table was generated; `None` when there is no table or no `_meta`."""
        if not self._dir.is_dir():
            return None
        lancedb, _ = self._require(model=False)
        db = lancedb.connect(str(self._dir))
        if not META_TABLE in db.list_tables().tables:
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
        lancedb, pa = self._require(model=embedder is None)
        if embedder is None:
            if not _model_cached():
                raise NoModel(f"the model {MODEL_NAME} is not in the fastembed cache {_cache_dir()}; nothing was downloaded")
            embedder = _default_embedder()
        entries = self._corpus.index.load().entries
        db = lancedb.connect(str(self._dir)) if entries or self._dir.is_dir() else None
        if db is None:
            return EmbedResult(0, 0, 0)

        rows = {}
        for entry in entries:
            text = _text_of(entry)
            rows[entry.id] = (entry, text.strip(), hashlib.sha256((PASSAGE_PREFIX + text).strip().encode("utf-8")).hexdigest())

        existing: dict[str, str] = {}
        table = None
        if TABLE_NAME in db.list_tables().tables:
            table = db.open_table(TABLE_NAME)
            if HASH_COLUMN in [f.name for f in table.schema]:
                arrow = table.to_arrow().select(["id", HASH_COLUMN])
                existing = dict(zip(arrow.column("id").to_pylist(), arrow.column(HASH_COLUMN).to_pylist(), strict=True))
            else:
                table = None  # the old table: rebuilt once, every entry embedded (D11, EMB-6)
        todo = [r for r in rows.values() if existing.get(r[0].id) != r[2]]
        gone = [i for i in existing if i not in rows]

        if todo:
            vectors = embedder([(PASSAGE_PREFIX + r[1]).strip() for r in todo])
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
            if table is None:
                table = db.create_table(TABLE_NAME, data=data, mode="overwrite")
            else:
                table.merge_insert("id").when_matched_update_all().when_not_matched_insert_all().execute(data)
        if gone and table is not None:
            table.delete(f"id IN ({', '.join(_sql_quote(i) for i in gone)})")

        if table is not None:
            meta = {"model": MODEL_NAME, "dimensions": str(DIMENSIONS), "generated_at": stamp(self._corpus.now()),
                    "entry_count": str(len(rows))}
            fields = pa.schema([pa.field("key", pa.string()), pa.field("value", pa.string())])
            data = pa.Table.from_pylist([{"key": k, "value": v} for k, v in meta.items()], schema=fields)
            db.create_table(META_TABLE, data=data, mode="overwrite")
        return EmbedResult(len(rows), len(todo), len(gone))
