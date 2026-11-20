"""The `git` kind: a repository cloned under `.source/<id>`."""

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any

from .. import schema
from .types import CONFIG_FILE, Freshness, Head, Location, Observation, Source, normalise_docs_root


@dataclass(frozen=True)
class GitSource(Source):
    type = "git"
    id: str
    repo_url: str
    branch: str | None = None
    docs_root: str | None = None
    last_commit_sha: str | None = None
    last_indexed_at: datetime | None = None
    extra: tuple[tuple[str, Any], ...] = ()


class GitKind:
    type = "git"

    def parse(self, raw: Mapping, where: str = "source") -> GitSource:
        return schema.read(GitSource, raw, CONFIG_FILE, where)

    def dump(self, source: GitSource) -> dict:
        return source.dump_mapping()

    def locate(self, source: GitSource, corpus, rel_path: str) -> Location:
        root = normalise_docs_root(source.docs_root)
        base = corpus.path / ".source" / source.id
        return Location(file=(base if root == "." else base / root) / rel_path)

    def freshness(self, source: GitSource, observation: Observation | None, now: datetime) -> Freshness:
        if not isinstance(observation, Head):
            return Freshness.UNKNOWN
        return Freshness.CURRENT if observation.sha == source.last_commit_sha else Freshness.BEHIND

    def recorded(self, source: GitSource, observation: Observation | None, now: datetime) -> GitSource:
        if isinstance(observation, Head):
            return replace(source, last_commit_sha=observation.sha, last_indexed_at=now)
        return replace(source, last_indexed_at=now)
