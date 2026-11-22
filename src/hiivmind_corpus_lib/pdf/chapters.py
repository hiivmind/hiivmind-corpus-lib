"""Chapter detection."""

import re
from collections.abc import Sequence
from pathlib import Path

from ._lib import _document
from .reading import _blocks_of, outline
from .types import Chapter, TocEntry

_CHAPTER_LINE = re.compile(r"^Chapter\s+(\d+|[IVXLC]+)", re.IGNORECASE)


def _chain(starts: Sequence[tuple[str, int]], page_count: int) -> tuple[Chapter, ...]:
    """Chapters from (title, start page) pairs: each ends where the next starts, the last at the page count."""
    return tuple(Chapter(i, title, page, starts[i][1] if i < len(starts) else page_count)
                 for i, (title, page) in enumerate(starts, start=1))


def chapters_from_outline(entries: Sequence[TocEntry], page_count: int, level: int = 1) -> tuple[Chapter, ...]:
    return _chain([(e.title, e.page) for e in entries if e.level == level], page_count)


def chapters(path: Path, level: int = 1) -> tuple[Chapter, ...]:
    with _document(path) as doc:
        n = len(doc)
        from_outline = chapters_from_outline([TocEntry(lv, t, p - 1) for lv, t, p in doc.get_toc()], n, level)
        if from_outline:
            return from_outline
        starts = []
        for number, page in enumerate(doc):
            for line in page.get_text().split("\n")[:10]:
                if _CHAPTER_LINE.match(line):
                    starts.append((line.strip()[:60], number))
                    break
        return _chain(starts, n)


def chapters_by_font(path: Path, font: str, min_size: float) -> tuple[Chapter, ...]:
    wanted = font.lower()
    with _document(path) as doc:
        starts = []
        for page in doc:
            for b in _blocks_of(page):
                if b.box.top <= 150 and b.size >= min_size and wanted in b.font.lower():
                    starts.append((b.text, page.number))
                    break
        return _chain(starts, len(doc))
