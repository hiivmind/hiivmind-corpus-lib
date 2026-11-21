"""The `llms-txt` kind: a site's `llms.txt` manifest and the pages it lists."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Location, ManifestHash, Observation, Source, join_url


@dataclass(frozen=True)
class Manifest:
    url: str | None = None
    last_hash: str | None = None
    last_fetched_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Urls:
    base_url: str | None = None
    suffix: str | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class LlmsCache:
    enabled: bool | None = None
    dir: str | None = None
    strategy: str | None = None
    sections: Any = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class LlmsTxtSource(Source):
    type = "llms-txt"
    id: str
    manifest: Manifest | None = None
    urls: Urls | None = None
    cache: LlmsCache | None = None
    structure: Any = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


class LlmsTxtKind:
    type = "llms-txt"

    def parse(self, raw: Mapping, where: str = "source") -> LlmsTxtSource:
        return schema.read(LlmsTxtSource, raw, CONFIG_FILE, where)

    def dump(self, source: LlmsTxtSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: LlmsTxtSource, corpus, rel_path: str) -> Location:
        cache = source.cache
        file = corpus.path / cache.dir / rel_path if cache and cache.enabled and cache.dir else None
        urls = source.urls
        url = None
        if urls and urls.base_url:
            suffix = urls.suffix or ""
            url = join_url(urls.base_url, rel_path if rel_path.endswith(suffix) else rel_path + suffix)
        return Location(file=file, url=url)

    def freshness(self, source: LlmsTxtSource, observation: Observation | None, now: datetime) -> Freshness:
        if not isinstance(observation, ManifestHash):
            return Freshness.UNKNOWN
        last = source.manifest.last_hash if source.manifest else None
        return Freshness.CURRENT if observation.sha256 == last else Freshness.BEHIND

    def recorded(self, source: LlmsTxtSource, observation: Observation | None, now: datetime) -> LlmsTxtSource:
        if isinstance(observation, ManifestHash):
            manifest = replace(source.manifest or Manifest(), last_hash=observation.sha256, last_fetched_at=now)
            return replace(source, manifest=manifest, last_indexed_at=now)
        return replace(source, last_indexed_at=now)
