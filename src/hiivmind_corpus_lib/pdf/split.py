"""Splitting a PDF into chapter PDFs, in memory."""

from collections.abc import Sequence
from pathlib import Path

from ..errors import InvalidFile
from ._lib import _document, _require
from .emit import safe_file_name
from .types import Chapter, ChapterPdf, Manifest


def split(path: Path, chapters: Sequence[Chapter]) -> tuple[tuple[ChapterPdf, ...], Manifest]:
    pymupdf = _require()
    with _document(path) as doc:
        n = len(doc)
        for c in chapters:
            if c.start_page < 0 or c.end_page <= c.start_page or c.end_page > n:
                raise InvalidFile(str(path), "chapters", f"chapter {c.index} (pages {c.page_range}) is outside the file's {n} pages")
        files = []
        for c in chapters:
            new = pymupdf.open()
            try:
                new.insert_pdf(doc, from_page=c.start_page, to_page=c.end_page - 1)
                data = new.tobytes()
            finally:
                new.close()
            files.append(ChapterPdf(c, f"{c.index:02d}_{safe_file_name(c.title)}.pdf", data))
    return tuple(files), Manifest(path.name, tuple((f.chapter, f.file_name) for f in files))
