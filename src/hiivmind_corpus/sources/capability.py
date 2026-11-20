"""`corpus.sources`: locate, freshness, apply_update, drop_missing (spec 7.5)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING

from ..errors import NoSuchSource
from ..index import Entry, Index, IndexMeta
from .types import (
    SOURCE_KINDS,
    Changes,
    Freshness,
    Listing,
    Location,
    Observation,
    SourceStatus,
    Unobserved,
    UnrecognisedSource,
    kind_of,
)

if TYPE_CHECKING:
    from ..config import Config
    from ..corpus import Corpus

PENDING = "Pending re-scan"


@dataclass(frozen=True)
class UpdateResult:
    files_changed: int
    added: int
    modified: int
    removed: int
    removed_ids: tuple[str, ...]
    stale_entries: tuple[str, ...]
    excluded: tuple[str, ...]
    outside_docs_root: int


@dataclass(frozen=True)
class DropResult:
    removed_ids: tuple[str, ...]
    skipped: str | None
    outside_docs_root: int


def _skipped(path: str, sections: tuple[str, ...]) -> bool:
    """A skip section matches the directory components of the path (a section may span several)."""
    parts = path.split("/")[:-1]
    for section in sections:
        wanted = [p for p in section.strip("/").split("/") if p]
        width = len(wanted)
        if width and any(parts[i:i + width] == wanted for i in range(len(parts) - width + 1)):
            return True
    return False


def _children(entries: tuple[Entry, ...], parent: str) -> list[Entry]:
    return [e for e in entries if e.tier == "section" and e.parent == parent]


class SourcesCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    @property
    def kinds(self) -> tuple[str, ...]:
        return tuple(SOURCE_KINDS)

    def locate(self, entry: Entry) -> Location:
        from . import locate_entry

        return locate_entry(self._corpus, self._corpus.config.load(), entry)

    def freshness(self, observations: Mapping[str, Observation]) -> tuple[SourceStatus, ...]:
        now = self._corpus.now()
        out = []
        for source in self._corpus.config.load().sources:
            kind = kind_of(source)
            if kind is None:
                out.append(SourceStatus(source.id, source.type, Freshness.UNKNOWN,
                                        f"source type `{source.type}` is not a known kind"))
                continue
            observation = observations.get(source.id)
            state = kind.freshness(source, observation, now)
            error = None
            if state == Freshness.UNKNOWN:
                reason = observation.reason if isinstance(observation, Unobserved) else "no observation of its upstream was handed in"
                error = f"source `{source.id}`: {reason}"
            out.append(SourceStatus(source.id, source.type, state, error))
        return tuple(out)

    def _source(self, config: Config, source_id: str):
        source = next((s for s in config.sources if s.id == source_id), None)
        if source is None:
            raise NoSuchSource(f"config.yaml has no source `{source_id}`")
        return source

    def _save(self, config: Config | None, before: Index, after: Index, gone: set[str]) -> None:
        """One save of what changed; the graph only when it exists and cleaning changed it."""
        from .. import store

        graph = None
        if gone and self._corpus.graph.exists():
            loaded = self._corpus.graph._load()
            cleaned = loaded.without_entries(gone)
            graph = cleaned if cleaned != loaded else None
        index = None
        if after != before:
            now = self._corpus.now()
            index = replace(after, meta=replace(after.meta or IndexMeta(), generated_at=now))
        elif after.meta is None:
            index = replace(after, meta=IndexMeta(generated_at=self._corpus.now()))
        if config is not None or index is not None or graph is not None:
            store.save(self._corpus, config=config, index=index, graph=graph)

    def apply_update(self, source_id: str, changes: Changes, observation: Observation) -> UpdateResult:
        from ..config import IndexInfo

        corpus = self._corpus
        config = corpus.config.load()
        source = self._source(config, source_id)
        now = corpus.now()
        before = corpus.index.load()
        entries = list(before.entries)
        by_section = config.build is not None and config.build.organization == "by-source" \
            and config.render.strategy == "tiered"
        skip = tuple(config.build.skip_sections or ()) if config.build else ()
        added: list[str] = []
        modified: list[str] = []
        removed: list[str] = []
        excluded: list[str] = []
        stale_ids: list[str] = []
        gone: set[str] = set()
        for change in changes.items:
            current = tuple(entries)
            entry = next((e for e in current if e.source == source_id and e.tier != "section"
                          and e.rel_path == change.path), None)
            if change.status == "D":
                if entry is not None:
                    drop = {entry.id} | {c.id for c in _children(current, entry.id)}
                    entries = [e for e in entries if e.id not in drop]
                    gone |= drop
                    removed.append(entry.id)
            elif change.status == "A" and entry is None:
                if _skipped(change.path, skip):
                    excluded.append(change.path)
                    continue
                entry_id = f"{source_id}:{change.path}"
                entries.append(Entry(
                    id=entry_id, source=source_id, path=change.path, stale=True, stale_since=now,
                    category="unknown", summary=PENDING, section=source_id if by_section else None,
                    tags=(), keywords=(), concepts=()))
                added.append(entry_id)
                stale_ids.append(entry_id)
            elif entry is not None and change.status != "D" and entry.id not in added:
                stale = {entry.id} | {c.id for c in _children(current, entry.id)}
                entries = [replace(e, stale=True, stale_since=now) if e.id in stale else e for e in entries]
                if entry.id not in modified:
                    modified.append(entry.id)
                    stale_ids.append(entry.id)
        kind = kind_of(source)
        recorded = kind.recorded(source, observation, now) if kind is not None else source
        updated = replace(
            config,
            sources=tuple(recorded if s.id == source_id else s for s in config.sources),
            index=replace(config.index or IndexInfo(), last_updated_at=now))
        after = replace(before, entries=tuple(entries))
        self._save(updated if updated != config else None, before, after, gone)
        return UpdateResult(
            files_changed=len(changes.items), added=len(added), modified=len(modified), removed=len(removed),
            removed_ids=tuple(removed), stale_entries=tuple(stale_ids), excluded=tuple(excluded),
            outside_docs_root=changes.outside_docs_root)

    def drop_missing(self, source_id: str, listing: Listing) -> DropResult:
        corpus = self._corpus
        config = corpus.config.load()
        source = self._source(config, source_id)
        outside = listing.outside_docs_root
        if not listing.paths:
            return DropResult((), "empty-listing", outside)
        kind = kind_of(source)
        if kind is not None and kind.freshness(source, _head(listing), corpus.now()) == Freshness.BEHIND:
            return DropResult((), "head-mismatch", outside)
        before = corpus.index.load()
        removed = [e for e in before.entries
                   if e.source == source_id and e.tier != "section" and e.rel_path not in listing.paths]
        if not removed:
            return DropResult((), None, outside)
        gone = {e.id for e in removed} | {c.id for e in removed for c in _children(before.entries, e.id)}
        after = replace(before, entries=tuple(e for e in before.entries if e.id not in gone))
        self._save(None, before, after, gone)
        return DropResult(tuple(e.id for e in removed), None, outside)


def _head(listing: Listing):
    from .types import Head

    return Head(listing.head)
