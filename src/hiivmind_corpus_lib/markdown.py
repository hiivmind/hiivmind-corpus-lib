"""The one Markdown heading parser, link extractor and heading slug."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import unquote

from markdown_it import MarkdownIt
from markdown_it.token import Token

_MD = MarkdownIt("commonmark")


@dataclass(frozen=True)
class HeadingLine:
    level: int
    title: str
    line: int  # 1-based


@dataclass(frozen=True)
class Link:
    title: str
    target: str | None
    depth: int


def slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _parse(text: str) -> list[Token]:
    return _MD.parse(text.removeprefix("\ufeff"))


def headings(text: str) -> tuple[HeadingLine, ...]:
    tokens = _parse(text)
    found: list[HeadingLine] = []
    for i, token in enumerate(tokens):
        if token.type == "heading_open" and token.map:
            title = tokens[i + 1].content
            if title:
                found.append(HeadingLine(int(token.tag[1]), title, token.map[0] + 1))
    return tuple(found)


def links(text: str) -> tuple[Link, ...]:
    found: list[Link] = []
    nesting = 0
    for token in _parse(text):
        if token.type in ("bullet_list_open", "ordered_list_open"):
            nesting += 1
        elif token.type in ("bullet_list_close", "ordered_list_close"):
            nesting -= 1
        elif token.type == "inline" and nesting > 0:
            target: str | None = None
            parts: list[str] | None = None
            for child in token.children or ():
                if child.type == "link_open":
                    target = unquote(str(child.attrGet("href") or "")) or None
                    parts = []
                elif child.type == "link_close" and parts is not None:
                    found.append(Link("".join(parts), target, nesting - 1))
                    parts = None
                elif parts is not None and child.type in ("text", "code_inline"):
                    parts.append(child.content)
    return tuple(found)
