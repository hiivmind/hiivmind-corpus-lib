"""`corpus.search`: vector, hybrid and reranked search over the entries and chunks tables (spec 7.11, design §10)."""

from __future__ import annotations

import importlib.util
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from . import embeddings as emb
from .embeddings import CHUNKS_TABLE, FTS_COLUMN, MODEL_NAME, QUERY_PREFIX, TABLE_NAME, Embedder
from .errors import ExtraMissing, ModelMismatch, NoEmbeddings, NoModel, NoTextIndex

if TYPE_CHECKING:
    from .corpus import Corpus

RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"
RERANK_REPO_DIR = "models--xenova--ms-marco-minilm-l-6-v2"
RERANK_FILE = "onnx/model.onnx"

Reranker = Callable[[str, Sequence[str]], Sequence[float]]


class Mode(StrEnum):
    VECTOR = "vector"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class Hit:
    id: str
    score: float
    fields: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", MappingProxyType(dict(self.fields)))


def _reranker_cached() -> bool:
    try:
        repos = [p for p in emb._cache_dir().iterdir() if p.name.lower() == RERANK_REPO_DIR]
    except OSError:
        return False
    return any(next((repo / "snapshots").glob(f"*/{RERANK_FILE}"), None) is not None for repo in repos)


def _default_reranker() -> Reranker:
    """The cached cross-encoder; never downloads."""
    if not _reranker_cached():
        raise NoModel(f"the model {RERANK_MODEL} is not in the fastembed cache {emb._cache_dir()}; nothing was downloaded")
    if importlib.util.find_spec("fastembed") is None:
        raise ExtraMissing(f"the embeddings extra is not installed: {emb.EXTRA_HINT}")
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    model = TextCrossEncoder(model_name=RERANK_MODEL, local_files_only=True)
    return lambda query, texts: list(model.rerank(query, list(texts)))


class SearchCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def entries(self, query: str, *, top_k: int = 10, where: str | None = None, columns: Sequence[str] = (),
                mode: Mode = Mode.VECTOR, rerank: bool = False, embedder: Embedder | None = None,
                reranker: Reranker | None = None) -> tuple[Hit, ...]:
        return self._search(TABLE_NAME, query, top_k, where, columns, mode, rerank, embedder, reranker)

    def chunks(self, query: str, *, top_k: int = 10, where: str | None = None, columns: Sequence[str] = (),
               mode: Mode = Mode.VECTOR, rerank: bool = False, embedder: Embedder | None = None,
               reranker: Reranker | None = None) -> tuple[Hit, ...]:
        return self._search(CHUNKS_TABLE, query, top_k, where, columns, mode, rerank, embedder, reranker)

    def _search(self, table_name, query, top_k, where, columns, mode, rerank, embedder, reranker) -> tuple[Hit, ...]:
        corpus = self._corpus
        info = corpus.config.load().corpus
        name = (info.name if info else None) or corpus.path.name  # the identifier, not the display name
        chunked = table_name == CHUNKS_TABLE
        text_column = FTS_COLUMN[table_name]
        no_table = (f"search: {name} has no chunk embeddings; run embed_chunks first." if chunked
                    else f"search: {name} has no embeddings; run embed first.")
        directory = emb.lance_dir(corpus)
        if not directory.is_dir():
            raise NoEmbeddings(no_table)
        lancedb, _ = emb.require_lance(fastembed=embedder is None)
        db = lancedb.connect(str(directory))
        if table_name not in db.list_tables().tables:
            raise NoEmbeddings(no_table)
        meta = corpus.embeddings.meta()
        if meta is not None and meta.model != MODEL_NAME:
            raise ModelMismatch(f"search: the embeddings were built with {meta.model}, not {MODEL_NAME}; run embed again.")
        table = db.open_table(table_name)
        hybrid = mode == Mode.HYBRID
        if hybrid and "FTS" not in [i.index_type for i in table.list_indices()]:
            label = "chunk embeddings" if chunked else "embeddings"
            raise NoTextIndex(f"search: {name}'s {label} have no text index; run embed again.")
        if rerank and reranker is None:
            reranker = _default_reranker()
        vector = emb.resolve_embedder(embedder)([QUERY_PREFIX + query])[0]

        if hybrid:
            from lancedb.rerankers import RRFReranker

            builder = (table.search(query_type="hybrid").vector(vector).text(query).metric("cosine")
                       .rerank(RRFReranker()).limit(top_k))
        else:
            builder = table.search(vector, vector_column_name="vector").metric("cosine").limit(top_k)
        if where:
            builder = builder.where(where)
        result = builder.to_arrow()

        score_column = "_relevance_score" if hybrid else "_distance"
        present = set(result.column_names)
        ids = result.column("id").to_pylist()
        raw = result.column(score_column).to_pylist()
        scores = [round(max(0.0, s), 4) if hybrid else round(max(0.0, 1.0 - s), 4) for s in raw]
        texts = result.column(text_column).to_pylist() if rerank else []
        base = ("parent", "line_start", "line_end") if chunked else ()
        wanted = [*base, *(c for c in columns if c in present and c not in base)]
        rows = []
        for i, hit_id in enumerate(ids):
            fields = {c: result.column(c)[i].as_py() for c in wanted}
            rows.append((hit_id, scores[i], fields))
        if rerank:
            rescored = [round(float(s), 4) for s in reranker(query, texts)]
            rows = sorted(((h, s, f) for (h, _, f), s in zip(rows, rescored, strict=True)), key=lambda r: -r[1])
        return tuple(Hit(h, s, f) for h, s, f in rows)
