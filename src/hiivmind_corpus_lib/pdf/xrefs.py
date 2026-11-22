"""Cross-references in text and their resolution to chapter files."""

import re
from collections.abc import Sequence

from .emit import safe_file_name
from .types import Chapter, CrossRef


def cross_references(text: str, patterns: Sequence[tuple[str, str]]) -> tuple[CrossRef, ...]:
    """Group layouts: chapter_reference (number, display, page); any other kind (display, page)."""
    refs = []
    for pattern, kind in patterns:
        for match in re.finditer(pattern, text):
            groups = match.groups()
            if kind == "chapter_reference" and len(groups) >= 3:
                refs.append(CrossRef(match.group(0), kind, groups[1].rstrip(",").strip(), int(groups[2])))
            elif kind != "chapter_reference" and len(groups) >= 2:
                refs.append(CrossRef(match.group(0), kind, groups[0], int(groups[1])))
    return tuple(refs)


def resolve(ref: CrossRef, chapters: Sequence[Chapter], file_name: str = "{index:02d}_{title}") -> str | None:
    if ref.page is None:
        return None
    for chapter in chapters:
        if chapter.start_page <= ref.page - 1 < chapter.end_page:
            return file_name.format(index=chapter.index, title=safe_file_name(chapter.title))
    return None
