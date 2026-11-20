"""`graph.yaml`: concepts, the relationships between them, and the six validation rules."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import schema
from .errors import InvalidFile
from .files import write_set
from .index import Index
from .schema import _found
from .yamlio import dump_yaml, load_yaml

if TYPE_CHECKING:
    from .corpus import Corpus

FILE = "graph.yaml"
INDEX_FILE = "index.yaml"
RELATIONSHIP_TYPES = ("includes", "depends-on", "see-also", "extends", "contrast-with")
ORIGINS = ("wikilink", "tag", "frontmatter", "manual")
Extra = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class Concept:
    label: str | None = None
    description: str | None = None
    tags: tuple[str, ...] | None = None
    entries: tuple[str, ...] | None = None
    entry_count: int | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Relationship:
    from_: str | None = field(default=None, metadata={"key": "from"})
    to: str | None = None
    type: str | None = None
    origin: str | None = None
    evidence: str | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class GraphMeta:
    generated_at: datetime | None = None
    concept_count: int | None = None
    relationship_count: int | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Issue:
    severity: str
    rule: str
    detail: str


@dataclass(frozen=True)
class GraphReport:
    concepts: int
    relationships: int
    issues: tuple[Issue, ...]
    valid: bool


@dataclass(frozen=True)
class Graph:
    schema_version: int | None = None
    concepts: dict[str, Concept] = field(default_factory=dict, metadata={"omit_default": True})
    relationships: tuple[Relationship, ...] = field(default=(), metadata={"omit_default": True})
    meta: GraphMeta | None = None
    extra: Extra = ()

    @classmethod
    def loads(cls, text: str) -> Graph:
        data = load_yaml(text, FILE)
        if not isinstance(data, dict):
            raise InvalidFile(FILE, "", f"the file must be a mapping, found {_found(data)}")
        return schema.read(cls, data, FILE)

    def dumps(self) -> str:
        return dump_yaml(schema.mapping(self))

    def without_entries(self, ids: set[str]) -> Graph:
        """Schema 1: the ids leave each concept's `entries` and `entry_count` follows. Else `self`."""
        if self.schema_version != 1:
            return self
        concepts = {}
        for cid, concept in self.concepts.items():
            if concept.entries is not None:
                kept = tuple(e for e in concept.entries if e not in ids)
                if kept != concept.entries:
                    count = len(kept) if concept.entry_count is not None else None
                    concept = replace(concept, entries=kept, entry_count=count)
            concepts[cid] = concept
        return replace(self, concepts=concepts)


class GraphCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def exists(self) -> bool:
        return (self._corpus.path / FILE).is_file()

    def _load(self) -> Graph:
        return Graph.loads((self._corpus.path / FILE).read_text(encoding="utf-8"))

    def validate(self) -> GraphReport:
        graph = self._load()
        index_file = self._corpus.path / INDEX_FILE
        entries = Index.loads(index_file.read_text(encoding="utf-8")).entries if index_file.is_file() else ()
        concepts, relationships = graph.concepts, graph.relationships
        issues: list[Issue] = []

        def issue(severity: str, rule: str, detail: str) -> None:
            issues.append(Issue(severity, rule, detail))

        # 1. schema
        if graph.schema_version != 2:
            issue("error", "schema", f"schema_version is {graph.schema_version!r}, not 2")
        for cid, concept in concepts.items():
            for name in ("label", "description"):
                if getattr(concept, name) is None:
                    issue("error", "schema", f"concept `{cid}` has no {name}")
        for n, rel in enumerate(relationships, 1):
            for name, value in (("from", rel.from_), ("to", rel.to), ("type", rel.type), ("origin", rel.origin)):
                if not value:
                    issue("error", "schema", f"relationship {n} has no {name}")
        meta = graph.meta or GraphMeta()
        for name in ("generated_at", "concept_count", "relationship_count"):
            if getattr(meta, name) is None:
                issue("error", "schema", f"meta has no {name}")

        # 2. dangling concept references
        named: set[str] = set()
        for entry in entries:
            for cid in entry.concepts or ():
                named.add(cid)
                if cid not in concepts:
                    issue("error", "dangling-concept",
                          f"entry {entry.id} names concept `{cid}`, which graph.yaml lacks")

        # 3. dangling relationships
        for n, rel in enumerate(relationships, 1):
            for end, verb in ((rel.from_, "comes from"), (rel.to, "goes to")):
                if end and end not in concepts:
                    issue("error", "dangling-relationship", f"relationship {n} {verb} `{end}`, which is not a concept")

        # 4. orphan concepts
        for cid in concepts:
            if cid not in named:
                issue("warning", "orphan-concept", f"concept `{cid}` is named by no entry")

        # 5 and 6. the vocabularies
        for n, rel in enumerate(relationships, 1):
            if rel.type and rel.type not in RELATIONSHIP_TYPES:
                issue("warning", "relationship-type", f"relationship {n} uses `{rel.type}`")
        for n, rel in enumerate(relationships, 1):
            if rel.origin and rel.origin not in ORIGINS:
                issue("warning", "origin", f"relationship {n} has origin `{rel.origin}`")

        return GraphReport(len(concepts), len(relationships), tuple(issues),
                           not any(i.severity == "error" for i in issues))

    def remove_entries(self, ids: Iterable[str]) -> None:
        if not self.exists():
            return
        graph = self._load()
        updated = graph.without_entries(set(ids))
        if updated == graph:
            return
        write_set(self._corpus.path, {FILE: updated.dumps()})
