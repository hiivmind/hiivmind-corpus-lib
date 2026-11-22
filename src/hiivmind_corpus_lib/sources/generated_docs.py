"""The `generated-docs` kind: documentation generated from a repository and published as a website."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Head, Location, Observation, Source, join_url


@dataclass(frozen=True)
class SourceRepo:
    url: str | None = None
    branch: str | None = None
    docs_root: str | None = None
    last_commit_sha: str | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class WebOutput:
    base_url: str | None = None
    sitemap_url: str | None = None
    discovered_urls: Any = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Cache:
    enabled: bool | None = None
    dir: str | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class GeneratedDocsSource(Source):
    type = "generated-docs"
    id: str
    source_repo: SourceRepo | None = None
    web_output: WebOutput | None = None
    cache: Cache | None = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


class GeneratedDocsKind:
    type = "generated-docs"

    def parse(self, raw: Mapping, where: str = "source") -> GeneratedDocsSource:
        return schema.read(GeneratedDocsSource, raw, CONFIG_FILE, where)

    def dump(self, source: GeneratedDocsSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: GeneratedDocsSource, corpus, rel_path: str) -> Location:
        cache = source.cache
        file = corpus.path / cache.dir / rel_path if cache and cache.enabled and cache.dir else None
        base = source.web_output.base_url if source.web_output else None
        return Location(file=file, url=join_url(base, rel_path) if base else None)

    def freshness(self, source: GeneratedDocsSource, observation: Observation | None, now: datetime) -> Freshness:
        if source.source_repo is None:
            return Freshness.MANUAL
        if not isinstance(observation, Head):
            return Freshness.UNKNOWN
        return Freshness.CURRENT if observation.sha == source.source_repo.last_commit_sha else Freshness.BEHIND

    def recorded(self, source: GeneratedDocsSource, observation: Observation | None,
                 now: datetime) -> GeneratedDocsSource:
        if isinstance(observation, Head) and source.source_repo is not None:
            repo = replace(source.source_repo, last_commit_sha=observation.sha)
            return replace(source, source_repo=repo, last_indexed_at=now)
        return replace(source, last_indexed_at=now)
