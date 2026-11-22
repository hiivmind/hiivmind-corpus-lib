"""`corpus.content`: navigation, large files, sections and chunks over a source's files on disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import chunks as _chunks
from . import sections as _sections
from .errors import InvalidFile
from .markdown import headings
from .navigation import Coverage, Navigation, markdown_files, navigation_of
from .sources import kind_of

if TYPE_CHECKING:
    from .chunks import Chunk, Strategy
    from .corpus import Corpus
    from .sections import Section

_NO_NAVIGATION = Navigation(False, None, None, (), Coverage(0, 0, 0, 0, 0.0))


@dataclass(frozen=True)
class LargeFile:
    path: str
    tokens: int
    lines: int
    headings: int
    deepest_heading: int | None


class ContentCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def _root(self, source_id: str) -> Path | None:
        """The source's root directory on disk; None for a URL-only source or an unknown kind."""
        config = self._corpus.config.load()
        source = config.source(source_id)
        kind = kind_of(source)
        return None if kind is None else kind.locate(source, self._corpus, "").file

    def navigation(self, source_id: str) -> Navigation:
        """The navigation of the source's files; an empty one when they are not on disk."""
        root = self._root(source_id)
        return _NO_NAVIGATION if root is None else navigation_of(root)

    def large_files(self, source_id: str, max_tokens: int = 15000) -> tuple[LargeFile, ...]:
        """Markdown files above `max_tokens`, by path; unreadable files are skipped, undecodable bytes replaced."""
        root = self._root(source_id)
        if root is None:
            return ()
        found = []
        for rel in markdown_files(root):
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            tokens = self._corpus.tokens.count(text)
            if tokens <= max_tokens:
                continue
            levels = [h.level for h in headings(text)]
            found.append(LargeFile(rel, tokens, len(text.splitlines()), len(levels), max(levels, default=None)))
        return tuple(found)

    def _text(self, source_id: str, path: str) -> str:
        root = self._root(source_id)
        refusal = InvalidFile(path, "", f"not a file of {source_id} on disk")
        if root is None:
            raise refusal
        try:
            base = root.resolve()
            target = (base / path).resolve()
            if not target.is_relative_to(base) or not target.is_file():
                raise refusal
            return target.read_text(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            raise refusal from None

    def sections(self, source_id: str, path: str, **options: Any) -> tuple[Section, ...]:
        options.setdefault("count", self._corpus.tokens.count)
        return _sections.sections(self._text(source_id, path), **options)

    def chunks(self, source_id: str, path: str, strategy: Strategy, **options: Any) -> tuple[Chunk, ...]:
        options.setdefault("count", self._corpus.tokens.count)
        return _chunks.chunks(self._text(source_id, path), strategy, **options)
