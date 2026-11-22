"""Builds real PDFs with PyMuPDF for the pdf tests."""

from collections.abc import Sequence
from pathlib import Path


def make_pdf(path: Path, pages: Sequence[Sequence[tuple[str, str, float, float]]],
             toc: Sequence[tuple[int, str, int]] = ()) -> Path:
    import pymupdf
    doc = pymupdf.open()
    for items in pages:
        page = doc.new_page(width=595, height=842)
        for text, fontname, size, y in items:
            page.insert_text((72, y), text, fontsize=size, fontname=fontname)
    if toc:
        doc.set_toc([list(entry) for entry in toc])
    doc.save(str(path))
    doc.close()
    return path


def make_png(path: Path) -> Path:
    import pymupdf
    pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 4, 4)).save(str(path), output="png")
    return path


def make_table_pdf(path: Path, rows: Sequence[Sequence[str]]) -> Path:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    nrows, ncols = len(rows), len(rows[0])
    for r in range(nrows + 1):
        y = 100 + 26 * r
        page.draw_line((72, y), (72 + 120 * ncols, y), width=0.5)
    for c in range(ncols + 1):
        x = 72 + 120 * c
        page.draw_line((x, 100), (x, 100 + 26 * nrows), width=0.5)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            if cell:
                page.insert_text((72 + 120 * c + 6, 100 + 26 * r + 17), cell, fontsize=11, fontname="helv")
    doc.save(str(path))
    doc.close()
    return path
