"""Split Markdown text into sections by heading."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from hiivmind_corpus_lib.markdown import headings, slug
from hiivmind_corpus_lib.tokens import count_tokens

Count = Callable[[str], int]

_PREVIEW_CHARS = 200


@dataclass(frozen=True)
class Section:
    title: str
    level: int
    line_start: int  # 1-based, inclusive
    line_end: int  # 1-based, inclusive
    tokens: int
    anchor: str
    preview: str


def sections(
    text: str,
    *,
    min_level: int = 2,
    max_level: int = 4,
    min_tokens: int = 200,
    count: Count = count_tokens,
) -> tuple[Section, ...]:
    lines = text.split("\n")
    last = len(lines)
    while last > 0 and not lines[last - 1].strip():
        last -= 1
    selected = [h for h in headings(text) if min_level <= h.level <= max_level and h.line <= last]
    if not selected:
        return ()

    def body(start: int, end: int) -> str:
        return "\n".join(lines[start - 1 : end])

    result: list[Section] = []
    for i, h in enumerate(selected):
        end = selected[i + 1].line - 1 if i + 1 < len(selected) else last
        own = count(body(h.line, end))
        if min_tokens > 0 and own < min_tokens and result:
            prev = result[-1]
            merged = body(prev.line_start, end)
            result[-1] = Section(prev.title, prev.level, prev.line_start, end,
                                 count(merged), prev.anchor, merged[:_PREVIEW_CHARS])
        else:
            content = body(h.line, end)
            result.append(Section(h.title, h.level, h.line, end, own, slug(h.title), content[:_PREVIEW_CHARS]))
    return tuple(result)
