"""File metadata and heading slugs (spec §7.9)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .index import Heading
from .markdown import headings as _markdown_headings, slug

LARGE_FILE_LINES = 1000

_CONTENT_TYPES = {
    ".md": "markdown", ".mdx": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".rst": "rst",
}


@dataclass(frozen=True)
class FileMetadata:
    content_type: str
    lines: int
    size: str
    grep_hint: str | None
    headings: tuple[Heading, ...]


def file_metadata(path: Path) -> FileMetadata:
    text = Path(path).read_bytes().decode("utf-8", errors="replace")
    lines = text.splitlines()
    content_type = _CONTENT_TYPES.get(Path(path).suffix.lower(), "text")
    large = len(lines) > LARGE_FILE_LINES
    return FileMetadata(
        content_type=content_type,
        lines=len(lines),
        size="large" if large else "standard",
        grep_hint='grep -n "^## " FILE' if large and content_type == "markdown" else None,
        headings=tuple(Heading(slug(h.title), h.title) for h in _markdown_headings(text)) if content_type == "markdown" else (),
    )
