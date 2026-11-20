"""The `obsidian` kind: a vault, either in a git repository or in a local directory."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from ..errors import InvalidFile
from .types import (
    CONFIG_FILE,
    Freshness,
    Head,
    Location,
    Observation,
    Source,
    normalise_docs_root,
    snapshot_freshness,
)


@dataclass(frozen=True)
class ObsidianSource(Source):
    type = "obsidian"
    id: str
    repo_url: str | None = None
    branch: str | None = None
    docs_root: str | None = None
    last_commit_sha: str | None = None
    vault_path: str | None = None
    include_patterns: tuple[str, ...] | None = None
    exclude_patterns: tuple[str, ...] | None = None
    last_indexed_at: datetime | None = None
    extraction: Any = None
    extra: tuple[tuple[str, Any], ...] = ()


class ObsidianKind:
    type = "obsidian"

    def parse(self, raw: Mapping, where: str = "source") -> ObsidianSource:
        source = schema.read(ObsidianSource, raw, CONFIG_FILE, where)
        if (source.repo_url is None) == (source.vault_path is None):
            found = "both" if source.repo_url is not None else "neither"
            raise InvalidFile(CONFIG_FILE, where,
                              f"`{where}` must have exactly one of `repo_url` and `vault_path`, found {found}")
        return source

    def dump(self, source: ObsidianSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: ObsidianSource, corpus, rel_path: str) -> Location:
        if source.vault_path is not None:
            return Location(file=corpus.path / source.vault_path / rel_path)
        root = normalise_docs_root(source.docs_root)
        base = corpus.path / ".source" / source.id
        return Location(file=(base if root == "." else base / root) / rel_path)

    def freshness(self, source: ObsidianSource, observation: Observation | None, now: datetime) -> Freshness:
        if source.vault_path is not None:
            return snapshot_freshness(observation, source.last_indexed_at)
        if not isinstance(observation, Head):
            return Freshness.UNKNOWN
        return Freshness.CURRENT if observation.sha == source.last_commit_sha else Freshness.BEHIND

    def recorded(self, source: ObsidianSource, observation: Observation | None, now: datetime) -> ObsidianSource:
        if source.repo_url is not None and isinstance(observation, Head):
            return replace(source, last_commit_sha=observation.sha, last_indexed_at=now)
        return replace(source, last_indexed_at=now)
