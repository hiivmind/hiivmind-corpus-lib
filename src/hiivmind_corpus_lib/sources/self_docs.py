"""The `self` kind: documentation in the repository that holds the corpus."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Location, Observation, Source, normalise_docs_root


@dataclass(frozen=True)
class SelfSource(Source):
    type = "self"
    id: str
    docs_root: str | None = None
    last_commit_sha: str | None = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


class SelfKind:
    type = "self"

    def parse(self, raw: Mapping, where: str = "source") -> SelfSource:
        return schema.read(SelfSource, raw, CONFIG_FILE, where)

    def dump(self, source: SelfSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: SelfSource, corpus, rel_path: str) -> Location:
        root = normalise_docs_root(source.docs_root)
        base = corpus.repo_root
        return Location(file=(base if root == "." else base / root) / rel_path)

    def freshness(self, source: SelfSource, observation: Observation | None, now: datetime) -> Freshness:
        return Freshness.MANUAL

    def recorded(self, source: SelfSource, observation: Observation | None, now: datetime) -> SelfSource:
        return replace(source, last_indexed_at=now)
