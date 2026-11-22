"""`index.yaml`: the entries of a corpus, one `Entry` per file or section."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import schema
from .errors import InvalidFile, NoSuchEntry
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


def duplicate_id(entry_id: str, n: int, also: int) -> InvalidFile:
    """E3: entries[n] repeats the id of entries[also]."""
    return InvalidFile(FILE, f"entries[{n}].id", f"duplicate id `{entry_id}` (also entries[{also}])")


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
                raise duplicate_id(entry.id, n, seen[entry.id])
            seen[entry.id] = n
        return index

    def dumps(self) -> str:
        index = self
        if self.meta is not None:
            index = replace(self, meta=replace(self.meta, entry_count=len(self.entries)))
        return dump_yaml(schema.mapping(index))

    def find(self, source: str, rel_path: str) -> Entry | None:
        """The file entry at (source, rel_path); a section shares the pair and is never returned."""
        for entry in self.entries:
            if entry.source == source and entry.tier != "section" and entry.rel_path == rel_path:
                return entry
        return None


@dataclass(frozen=True)
class ScanBatch:
    source: str
    files: tuple[str, ...]


@dataclass(frozen=True)
class Skip:
    id: str
    code: str
    reason: str


@dataclass(frozen=True)
class MergeResult:
    enriched: tuple[str, ...]
    skipped: tuple[Skip, ...]


@dataclass(frozen=True)
class SetResult:
    ok: bool


@dataclass(frozen=True)
class AssignResult:
    assigned: tuple[str, ...]


@dataclass(frozen=True)
class Merge:
    removed: str
    into: str


@dataclass(frozen=True)
class ThinResult:
    sections_before: int
    sections_after: int
    merges: tuple[Merge, ...]


NOT_INDEXED = "no entry in the index"
NO_SCAN = "no scan returned for it (file unreadable or not in the source)"
UNREADABLE = "the file cannot be read or the entry names no file"


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _texts(value: Any) -> tuple[str, ...] | None:
    return tuple(str(v) for v in value) if isinstance(value, (list, tuple)) else None


def _batch_of(item: Any) -> tuple[str, tuple[str, ...]]:
    if isinstance(item, ScanBatch):
        return item.source, item.files
    return str(item.get("source")), tuple(item.get("files") or ())


class IndexCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def load(self) -> Index:
        return Index.loads((self._corpus.path / FILE).read_text(encoding="utf-8"))

    def stale_batches(self, size: int = 30) -> tuple[ScanBatch, ...]:
        by_source: dict[str, list[str]] = {}
        for entry in self.load().entries:
            if entry.stale is True and entry.tier != "section":
                by_source.setdefault(entry.source, []).append(entry.rel_path)
        return tuple(ScanBatch(source, tuple(files[i:i + size]))
                     for source, files in by_source.items() for i in range(0, len(files), size))

    def stale_ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.load().entries if e.stale is True and e.tier != "section")

    def _save(self, index: Index) -> None:
        from . import store

        meta = replace(index.meta or IndexMeta(), generated_at=self._corpus.now())
        store.save(self._corpus, index=replace(index, meta=meta))

    def _set(self, values: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
        """Set `field_name` of each entry named in `values`; the ids found. Saved only when an entry changed."""
        index = self.load()
        found: list[str] = []
        changed = False
        entries = []
        for entry in index.entries:
            if entry.id in values:
                found.append(entry.id)
                updated = replace(entry, **{field_name: values[entry.id]})
                changed = changed or updated != entry
                entry = updated
            entries.append(entry)
        if changed:
            self._save(replace(index, entries=tuple(entries)))
        return tuple(found)

    def set_summary(self, entry_id: str, summary: str) -> SetResult:
        if not self._set({entry_id: summary}, "summary"):
            raise NoSuchEntry(f"index.yaml has no entry `{entry_id}`")
        return SetResult(ok=True)

    def set_concepts(self, assignments: Mapping[str, Sequence[str]]) -> AssignResult:
        values = {entry_id: tuple(concepts) for entry_id, concepts in assignments.items()}
        return AssignResult(assigned=self._set(values, "concepts"))

    def merge_scans(self, scans: Sequence[Mapping], failures: Sequence[Mapping]) -> MergeResult:
        from .filemeta import file_metadata
        from .sources import locate_entry

        index = self.load()
        failed = {_batch_of(f.get("item") or {}) for f in failures}
        batches = [b for b in self.stale_batches() if (b.source, b.files) not in failed]
        work: list[tuple[str, tuple[str, ...], dict[str, Mapping], str | None]] = []
        for batch, scan in zip(batches, scans):
            returned: dict[str, Mapping] = {}
            for scanned in scan.get("entries") or ():
                if isinstance(scanned, Mapping) and isinstance(scanned.get("path"), str):
                    returned.setdefault(scanned["path"], scanned)   # the first entry of a file wins
            work.append((batch.source, batch.files, returned, None))
        for failure in failures:
            source, files = _batch_of(failure.get("item") or {})
            work.append((source, files, {}, str(failure.get("reason") or failure.get("outcome"))))

        config = self._corpus.config.load()
        now = self._corpus.now()
        done: dict[str, Entry] = {}
        skipped: list[Skip] = []
        for source, files, returned, error in work:
            for file in files:
                entry = index.find(source, file)
                entry_id = entry.id if entry else f"{source}:{file}"
                if entry is None:
                    skipped.append(Skip(entry_id, "not-indexed", NOT_INDEXED))
                elif error is not None:
                    skipped.append(Skip(entry_id, "batch-failed", error))
                elif file not in returned:
                    skipped.append(Skip(entry_id, "no-scan", NO_SCAN))
                else:
                    location = locate_entry(self._corpus, config, entry)
                    try:
                        if location.file is None:
                            raise OSError(UNREADABLE)
                        meta = file_metadata(Path(location.file))
                    except OSError:
                        skipped.append(Skip(entry_id, "file-unreadable", UNREADABLE))
                        continue
                    scan = returned[file]
                    done[entry_id] = replace(
                        entry, path=file, title=_text(scan.get("title")), summary=_text(scan.get("summary")),
                        tags=_texts(scan.get("tags")), keywords=_texts(scan.get("keywords")),
                        category=_text(scan.get("category")), content_type=meta.content_type, size=meta.size,
                        grep_hint=meta.grep_hint if meta.grep_hint is not None else NULL, headings=meta.headings,
                        stale=False, stale_since=NULL, last_indexed=now)
        if done:
            current = tuple(
                done.get(e.id, replace(e, stale=False, stale_since=NULL)
                         if e.tier == "section" and e.parent in done else e)
                for e in index.entries)
            self._save(replace(index, entries=current))
        return MergeResult(enriched=tuple(done), skipped=tuple(skipped))

    def thin_sections(self, min_tokens: int = 300, *, dry_run: bool = False) -> ThinResult:
        from .thinning import thin

        thinned, result = thin(self.load(), min_tokens)
        if result.merges and not dry_run:
            self._save(thinned)
        return result
