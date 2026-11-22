"""Frozen result types of the pdf package."""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class TocEntry:
    level: int
    title: str
    page: int


@dataclass(frozen=True)
class Box:
    x0: float
    top: float
    x1: float
    bottom: float


@dataclass(frozen=True)
class TextBlock:
    text: str
    font: str
    size: float
    bold: bool
    italic: bool
    monospace: bool
    box: Box
    page: int


@dataclass(frozen=True)
class FontInfo:
    font: str
    size: float
    characters: int
    pages: tuple[int, ...]


@dataclass(frozen=True)
class Chapter:
    index: int
    title: str
    start_page: int
    end_page: int

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page

    @property
    def page_range(self) -> str:
        return f"{self.start_page + 1}-{self.end_page}"


@dataclass(frozen=True)
class ChapterPdf:
    chapter: Chapter
    file_name: str
    data: bytes


@dataclass(frozen=True)
class Manifest:
    source: str
    chapters: tuple[tuple[Chapter, str], ...]

    def to_json(self) -> str:
        return json.dumps({"source": self.source, "chapters": [
            {"index": c.index, "title": c.title, "file": file, "pages": c.page_range}
            for c, file in self.chapters]}, indent=2)


@dataclass(frozen=True)
class CrossRef:
    """A reference found in text: the matched `text`, its `kind`, the `display_text` and the 1-based `page`."""
    text: str
    kind: str
    display_text: str
    page: int | None
