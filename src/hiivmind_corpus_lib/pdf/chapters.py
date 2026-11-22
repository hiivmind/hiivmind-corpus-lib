"""Chapter detection."""

from collections.abc import Sequence

from .types import Chapter, TocEntry


def chapters_from_outline(entries: Sequence[TocEntry], page_count: int, level: int = 1) -> tuple[Chapter, ...]:
    chosen = [e for e in entries if e.level == level]
    return tuple(
        Chapter(i, e.title, e.page, chosen[i].page if i < len(chosen) else page_count)
        for i, e in enumerate(chosen, start=1))
