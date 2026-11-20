"""`corpus.status`: the freshness pre-check (spec 7.6, STA-1..5, CFG-2, CFG-3)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from .embeddings import EXTRA_HINT
from .errors import ExtraMissing
from .sources.types import Freshness, Observation, SourceStatus

if TYPE_CHECKING:
    from .corpus import Corpus


class IndexFormat(StrEnum):
    V2 = "v2"
    V1 = "v1"
    NONE = "none"


@dataclass(frozen=True)
class Status:
    corpus: str
    index_format: IndexFormat
    sources: tuple[SourceStatus, ...]
    stale_entries: int | None
    embeddings_lag: int | None
    refresh_needed: bool
    errors: tuple[str, ...]


class StatusCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def index_format(self) -> IndexFormat:
        if (self._corpus.path / "index.yaml").is_file():
            return IndexFormat.V2
        if (self._corpus.path / "index.md").is_file():
            return IndexFormat.V1
        return IndexFormat.NONE


    def embeddings_lag(self) -> int | None:
        """The lag, `None` when there is nothing to compare or the extra is missing."""
        try:
            return self._corpus.embeddings.lag()
        except ExtraMissing:
            return None

    def report(self, observations: Mapping[str, Observation] = {}) -> Status:
        corpus = self._corpus
        sources = corpus.sources.freshness(observations)
        errors = [s.error for s in sources if s.error]
        fmt = self.index_format()
        stale: int | None
        if fmt == IndexFormat.V1:
            stale = None
        elif fmt == IndexFormat.V2:
            stale = sum(1 for e in corpus.index.load().entries if e.stale is True)
        else:
            stale = 0
        lag = None
        try:
            lag = corpus.embeddings.lag()
        except ExtraMissing:
            errors.append(f"embeddings lag not computed: {EXTRA_HINT}")
        needed = (any(s.freshness in (Freshness.BEHIND, Freshness.UNKNOWN) for s in sources)
                  or (stale or 0) > 0 or lag not in (0, None))
        return Status(corpus=corpus.name, index_format=fmt, sources=sources, stale_entries=stale,
                      embeddings_lag=lag, refresh_needed=needed, errors=tuple(errors))
