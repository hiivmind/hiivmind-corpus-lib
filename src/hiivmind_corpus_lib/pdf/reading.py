"""Reading a PDF with PyMuPDF: outline, pages, text blocks, fonts, tables."""

import re
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path

from ..errors import InvalidFile
from ._lib import _document, _require
from .types import Box, FontInfo, TextBlock, TocEntry

_BOLD, _ITALIC, _MONOSPACE = 16, 2, 8


def outline(path: Path) -> tuple[TocEntry, ...]:
    with _document(path) as doc:
        return tuple(TocEntry(level, title, page - 1) for level, title, page in doc.get_toc())


def page_count(path: Path) -> int:
    with _document(path) as doc:
        return len(doc)


def _check_page(path: Path, doc, page: int) -> None:
    n = len(doc)
    if not 0 <= page < n:
        raise InvalidFile(str(path), "page", f"page {page} is out of range (the file has {n} page{'s' if n != 1 else ''})")


def _blocks_of(page) -> tuple[TextBlock, ...]:
    pymupdf = _require()
    found = []
    for block in page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"].strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span["bbox"]
                flags = span["flags"]
                found.append(TextBlock(text, span["font"], round(span["size"], 1), bool(flags & _BOLD),
                                       bool(flags & _ITALIC), bool(flags & _MONOSPACE), Box(x0, y0, x1, y1), page.number))
    return tuple(found)


def text_blocks(path: Path, page: int) -> tuple[TextBlock, ...]:
    with _document(path) as doc:
        _check_page(path, doc, page)
        return _blocks_of(doc[page])


def strip_headers_footers(blocks: Sequence[TextBlock], page_height: float, *, header_zone: float = 50,
                          footer_zone: float = 40, header_pattern: str | None = None) -> tuple[TextBlock, ...]:
    def goes(b: TextBlock) -> bool:
        if b.box.top >= page_height - footer_zone:
            return True
        return b.box.top <= header_zone and (header_pattern is None or re.search(header_pattern, b.text) is not None)
    return tuple(b for b in blocks if not goes(b))


def fonts(path: Path) -> tuple[FontInfo, ...]:
    characters: dict[tuple[str, float], int] = defaultdict(int)
    pages: dict[tuple[str, float], set[int]] = defaultdict(set)
    with _document(path) as doc:
        for page in doc:
            for b in _blocks_of(page):
                characters[b.font, b.size] += len(b.text)
                pages[b.font, b.size].add(b.page)
    ordered = sorted(characters, key=lambda k: (-characters[k], k[0]))
    return tuple(FontInfo(f, s, characters[f, s], tuple(sorted(pages[f, s]))) for f, s in ordered)


def tables(path: Path, page: int) -> tuple[tuple[tuple[str, ...], ...], ...]:
    with _document(path) as doc:
        _check_page(path, doc, page)
        return tuple(tuple(tuple("" if cell is None else cell for cell in row) for row in t.extract())
                     for t in doc[page].find_tables().tables)
