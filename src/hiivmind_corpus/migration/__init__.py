"""`corpus.migration`: a v1 corpus (`index.md`, `index-*.md`) to v2 over the package's own writer and renderer (spec 7.11)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..config import Config, Render, RenderSection
from ..errors import MigrationRefused, Refusal
from ..filemeta import slug
from ..index import FILE as INDEX_FILE
from ..index import Entry, Index, IndexMeta, Skip
from ..render import render_texts
from ..schema import NULL
from .v1 import _extensions, _ids_in, _parse, v1_ids

if TYPE_CHECKING:
    from ..corpus import Corpus

V1_INDEX = "index.md"
FILE_MISSING = "file-missing"
SHOWN = 10


@dataclass(frozen=True)
class MigrationResult:
    migrated: int
    skipped: tuple[Skip, ...]
    strategy: str
    sections: tuple[str, ...]


def _lost(ids: list[str]) -> str:
    more = f", … and {len(ids) - SHOWN} more" if len(ids) > SHOWN else ""
    return f"ids lost in migration: {', '.join(ids[:SHOWN])}{more}"


def _entry(parsed: dict, now) -> Entry:
    """A stale entry with the v1 title, summary and hint; `size` is `standard` until a scan says otherwise."""
    tag = slug(parsed["heading"])
    return Entry(
        id=parsed["id"], source=parsed["source"], path=parsed["path"], title=parsed["title"], summary=parsed["summary"],
        tags=(tag,) if tag else (), keywords=(), concepts=(), category="unknown",
        content_type="markdown" if parsed["path"].endswith((".md", ".mdx")) else "text", size="standard",
        grep_hint=parsed["grep_hint"] if parsed["grep_hint"] is not None else NULL, headings=(), links_to=(),
        links_from=(), frontmatter={}, stale=True, stale_since=now, last_indexed=NULL, section=parsed["section"])


class MigrationCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def migrate(self) -> MigrationResult:
        from dataclasses import replace

        from .. import store

        corpus = self._corpus
        path = corpus.path
        if (path / INDEX_FILE).exists():
            raise MigrationRefused(Refusal.ALREADY_V2, "index.yaml exists — nothing to migrate")
        if not (path / V1_INDEX).is_file():
            raise MigrationRefused(Refusal.NO_V1_INDEX, "no v1 index found")
        config = corpus.config.load()
        source_ids = [s.id for s in config.sources]
        extensions = _extensions(config)
        parsed, quick, sections = _parse(path, source_ids, extensions)
        if not parsed:
            raise MigrationRefused(Refusal.NO_ENTRIES, "no entries parsed")

        now = corpus.now()
        kept: list[Entry] = []
        skipped: list[Skip] = []
        for item in parsed:
            entry = _entry(item, now)
            located = corpus.sources.locate(entry).file
            if located is not None and located.is_file():
                kept.append(entry)
            else:
                skipped.append(Skip(entry.id, FILE_MISSING, FILE_MISSING))

        strategy = "tiered" if sections else "single"
        render = Render(
            strategy=strategy,
            sections=tuple(RenderSection(s["id"], s["title"], s["description"] or None) for s in sections),
            quick_reference=tuple(quick))
        info = config.index
        from ..config import IndexInfo
        config = replace(config, render=render, index=replace(info or IndexInfo(), last_updated_at=now))
        index = Index(meta=IndexMeta(generated_at=now), entries=tuple(kept))

        rendered: set[str] = set()
        for text in render_texts(config, index, corpus.name_in(config)).values():
            rendered |= _ids_in(text, source_ids, extensions, tables=True)
        lost = sorted(v1_ids(path, source_ids, extensions) - rendered - {s.id for s in skipped})
        if lost:
            raise MigrationRefused(Refusal.IDS_LOST, _lost(lost))

        store.save(corpus, config=config, index=index)
        return MigrationResult(len(kept), tuple(skipped), strategy, tuple(s["id"] for s in sections))
