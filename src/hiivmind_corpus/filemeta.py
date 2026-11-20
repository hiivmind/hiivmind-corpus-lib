"""File metadata and heading slugs (spec §7.9)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .index import Heading

LARGE_FILE_LINES = 1000

_CONTENT_TYPES = {
    ".md": "markdown", ".mdx": "markdown", ".yaml": "yaml", ".yml": "yaml",
    ".json": "json", ".rst": "rst",
}
_ATX = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")


@dataclass(frozen=True)
class FileMetadata:
    content_type: str
    lines: int
    size: str
    grep_hint: str | None
    headings: tuple[Heading, ...]


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _headings(lines: list[str]) -> tuple[Heading, ...]:
    found: list[Heading] = []
    fenced = False
    for line in lines:
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced:
            continue
        match = _ATX.match(line)
        if match and match.group(1):
            title = match.group(1)
            found.append(Heading(slug(title), title))
    return tuple(found)


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
        headings=_headings(lines) if content_type == "markdown" else (),
    )
