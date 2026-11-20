"""The `web` kind: pages fetched into a cache directory, or read live."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Location, Observation, Snapshot, Source, join_url

STALE_AFTER = timedelta(days=7)


@dataclass(frozen=True)
class WebUrl:
    url: str | None = None
    cached_file: str | None = None
    fetched_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class WebSource(Source):
    type = "web"
    id: str
    cache_dir: str | None = None
    urls: tuple[WebUrl, ...] | None = None
    fetch_mode: str | None = None
    base_url: str | None = None
    discovered_urls: Any = None
    pages: Any = None
    last_fetched_at: datetime | None = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


def _oldest_fetch(source: WebSource) -> datetime | None:
    stamps = [u.fetched_at for u in source.urls or () if u.fetched_at is not None]
    return min(stamps) if stamps else source.last_fetched_at


class WebKind:
    type = "web"

    def parse(self, raw: Mapping, where: str = "source") -> WebSource:
        return schema.read(WebSource, raw, CONFIG_FILE, where)

    def dump(self, source: WebSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: WebSource, corpus, rel_path: str) -> Location:
        if source.fetch_mode == "live":
            return Location(url=join_url(source.base_url, rel_path) if source.base_url else None)
        file = corpus.path / source.cache_dir / rel_path if source.cache_dir else None
        url = next((u.url for u in source.urls or () if u.cached_file == rel_path), None)
        return Location(file=file, url=url)

    def freshness(self, source: WebSource, observation: Observation | None, now: datetime) -> Freshness:
        if observation is None and source.fetch_mode == "live":
            return Freshness.MANUAL
        oldest = _oldest_fetch(source)
        if oldest is None:
            return Freshness.UNKNOWN
        if isinstance(observation, Snapshot):
            newest = max(observation.stamps.values(), default=None)
            return Freshness.BEHIND if newest is not None and newest > oldest else Freshness.CURRENT
        if observation is not None:
            return Freshness.UNKNOWN
        return Freshness.BEHIND if now - oldest > STALE_AFTER else Freshness.CURRENT

    def recorded(self, source: WebSource, observation: Observation | None, now: datetime) -> WebSource:
        return replace(source, last_indexed_at=now, last_fetched_at=now)
