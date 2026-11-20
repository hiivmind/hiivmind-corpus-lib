"""`index.yaml`: the entries of a corpus, one `Entry` per file or section."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import schema
from .errors import InvalidFile
from .schema import NULL, Null, _found
from .yamlio import dump_yaml, load_yaml

if TYPE_CHECKING:
    from .corpus import Corpus

FILE = "index.yaml"
Extra = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class Heading:
    anchor: str | None = None
    title: str | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Entry:
    id: str
    source: str
    path: str | None = None
    title: str | None = None
    summary: str | None = None
    tags: tuple[str, ...] | None = None
    keywords: tuple[str, ...] | None = None
    concepts: tuple[str, ...] | None = None
    category: str | None = None
    content_type: str | None = None
    size: str | None = None
    grep_hint: str | Null | None = field(default=None, metadata={"nullable": True})
    headings: tuple[Heading, ...] | None = None
    links_to: tuple[str, ...] | None = None
    links_from: tuple[str, ...] | None = None
    frontmatter: dict[str, Any] | None = None
    stale: bool | None = None
    stale_since: datetime | Null | None = field(default=None, metadata={"nullable": True})
    last_indexed: datetime | Null | None = field(default=None, metadata={"nullable": True})
    section: str | None = None
    tier: str | None = None
    parent: str | None = None
    anchor: str | None = None
    heading_level: int | None = None
    line_range: tuple[int, ...] | None = None
    extra: Extra = ()

    @property
    def rel_path(self) -> str:
        """`path`, or the id without its `<source>:` prefix."""
        if self.path:
            return self.path
        prefix = f"{self.source}:"
        return self.id[len(prefix):] if self.id.startswith(prefix) else self.id


@dataclass(frozen=True)
class IndexMeta:
    generated_at: datetime | None = None
    entry_count: int | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Index:
    meta: IndexMeta | None = None
    entries: tuple[Entry, ...] = ()
    extra: Extra = ()

    @classmethod
    def loads(cls, text: str) -> Index:
        data = load_yaml(text, FILE)
        if not isinstance(data, dict):
            raise InvalidFile(FILE, "", f"the file must be a mapping, found {_found(data)}")
        index = schema.read(cls, data, FILE)
        seen: dict[str, int] = {}
        for n, entry in enumerate(index.entries):
            if entry.id in seen:
                raise InvalidFile(FILE, f"entries[{n}].id",
                                  f"duplicate id `{entry.id}` (also entries[{seen[entry.id]}])")
            seen[entry.id] = n
        return index

    def dumps(self) -> str:
        index = self
        if self.meta is not None:
            index = replace(self, meta=replace(self.meta, entry_count=len(self.entries)))
        return dump_yaml(schema.mapping(index))

    def find(self, source: str, rel_path: str) -> Entry | None:
        for entry in self.entries:
            if entry.source == source and entry.rel_path == rel_path:
                return entry
        return None


class IndexCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def load(self) -> Index:
        return Index.loads((self._corpus.path / FILE).read_text(encoding="utf-8"))
