"""The `local` kind: files placed in the corpus directory by hand."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Location, Observation, Source, snapshot_freshness


@dataclass(frozen=True)
class LocalSource(Source):
    type = "local"
    id: str
    path: str | None = None
    files: Any = None
    description: str | None = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


class LocalKind:
    type = "local"

    def parse(self, raw: Mapping, where: str = "source") -> LocalSource:
        return schema.read(LocalSource, raw, CONFIG_FILE, where)

    def dump(self, source: LocalSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: LocalSource, corpus, rel_path: str) -> Location:
        base = corpus.path / (source.path or f"uploads/{source.id}")
        return Location(file=base / rel_path)

    def freshness(self, source: LocalSource, observation: Observation | None, now: datetime) -> Freshness:
        return snapshot_freshness(observation, source.last_indexed_at)

    def recorded(self, source: LocalSource, observation: Observation | None, now: datetime) -> LocalSource:
        return replace(source, last_indexed_at=now)
