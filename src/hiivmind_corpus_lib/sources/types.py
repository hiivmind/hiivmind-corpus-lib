"""Source facts and the source-kind protocol: what every kind shares."""

import posixpath
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, ClassVar, Protocol, TypeVar

from ..errors import InvalidChanges
from ..schema import mapping

CONFIG_FILE = "config.yaml"


class Freshness(StrEnum):
    CURRENT = "current"
    BEHIND = "behind"
    UNKNOWN = "unknown"
    MANUAL = "manual"


@dataclass(frozen=True)
class Head:
    sha: str


@dataclass(frozen=True)
class ManifestHash:
    sha256: str


@dataclass(frozen=True)
class Snapshot:
    stamps: Mapping[str, datetime]


@dataclass(frozen=True)
class Unobserved:
    reason: str


Observation = Head | ManifestHash | Snapshot | Unobserved


@dataclass(frozen=True)
class Location:
    file: Path | None = None
    url: str | None = None


@dataclass(frozen=True)
class SourceStatus:
    id: str
    type: str | None
    freshness: Freshness
    error: str | None = None


@dataclass(frozen=True)
class Change:
    status: str
    path: str


@dataclass(frozen=True)
class Changes:
    items: tuple[Change, ...] = ()
    outside_docs_root: int = 0


def normalise_docs_root(value: str | None) -> str:
    """Empty, absent, `.` and `./` are the repository root (`.`); `docs/` is `docs`."""
    return posixpath.normpath(value) if value else "."


def _inside(path: str, root: str) -> str | None:
    if root == ".":
        return path
    prefix = root + "/"
    return path[len(prefix):] if path.startswith(prefix) else None


@dataclass(frozen=True)
class Listing:
    head: str
    paths: frozenset[str] = frozenset()
    outside_docs_root: int = 0

    @classmethod
    def of(cls, head: str, paths: Iterable[str], docs_root: str | None) -> "Listing":
        root = normalise_docs_root(docs_root)
        kept: set[str] = set()
        outside = 0
        for path in paths:
            rel = _inside(path, root)
            if rel is None:
                outside += 1
            else:
                kept.add(rel)
        return cls(head, frozenset(kept), outside)


def parse_name_status(text: str, docs_root: str | None) -> Changes:
    """Parse `git diff --name-status -z` output; paths outside `docs_root` are counted, not kept."""
    fields = text.split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 2:
        raise InvalidChanges(f"a path is missing after status {fields[-1]}")
    root = normalise_docs_root(docs_root)
    items: list[Change] = []
    outside = 0
    for status, path in zip(fields[0::2], fields[1::2]):
        rel = _inside(path, root)
        if rel is None:
            outside += 1
        else:
            items.append(Change(status, rel))
    return Changes(tuple(items), outside)


class Source:
    """Base of a kind's frozen source dataclass: `id`, `extra`, and the class attribute `type`."""

    type: ClassVar[str]
    reserved: ClassVar[tuple[str, ...]] = ("type",)
    id: str
    extra: tuple[tuple[str, Any], ...]

    def dump_mapping(self) -> dict[str, Any]:
        body = mapping(self)
        out: dict[str, Any] = {"id": body.pop("id"), "type": self.type}
        out.update(body)
        return out


@dataclass(frozen=True)
class UnrecognisedSource:
    id: str
    type: str | None
    raw: Mapping[str, Any]


S = TypeVar("S", bound=Source)


class SourceKind(Protocol[S]):
    """One kind of source; `S` is the `Source` subclass it parses and reads."""

    type: str

    def parse(self, raw: Mapping, where: str = "source") -> S: ...
    def dump(self, source: S) -> dict: ...
    def locate(self, source: S, corpus: Any, rel_path: str) -> Location: ...
    def freshness(self, source: S, observation: Observation | None, now: datetime) -> Freshness: ...
    def recorded(self, source: S, observation: Observation | None, now: datetime) -> S: ...


# Filled by the kinds' package (`sources/__init__.py`); insertion order is `Corpus.sources.kinds`.
# Keyed by `Source.type`, so each kind meets only sources of its own subclass: the pairing is by key, not by type.
SOURCE_KINDS: dict[str, SourceKind[Any]] = {}


def kind_of(source: Source | UnrecognisedSource) -> SourceKind[Any] | None:
    if isinstance(source, Source):
        return SOURCE_KINDS.get(source.type)
    return None


def join_url(base: str, path: str) -> str:
    """`base` and `path` joined by exactly one slash."""
    return base.rstrip("/") + "/" + path.lstrip("/")


def snapshot_freshness(observation: Observation | None, since: datetime | None) -> Freshness:
    """Kinds that watch a listing: no observation `manual`; a `Snapshot` newer than `since` `behind`."""
    if observation is None:
        return Freshness.MANUAL
    if not isinstance(observation, Snapshot):
        return Freshness.UNKNOWN
    if since is None or (observation.stamps and max(observation.stamps.values()) > since):
        return Freshness.BEHIND
    return Freshness.CURRENT
