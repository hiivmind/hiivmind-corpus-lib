"""The one place a PDF is opened: PyMuPDF is imported here, inside the call (P-5)."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ..errors import ExtraMissing, InvalidFile

EXTRA_HINT = "install hiivmind-corpus-lib[pdf]"


def _require():
    try:
        import pymupdf
    except ImportError as exc:
        raise ExtraMissing(f"the pdf extra is not installed: {EXTRA_HINT}") from exc
    return pymupdf


@contextmanager
def _document(path: Path) -> Iterator:
    pymupdf = _require()
    try:
        doc = pymupdf.open(str(path))
    except (pymupdf.FileDataError, pymupdf.FileNotFoundError) as exc:
        raise InvalidFile(str(path), "", "not a readable PDF") from exc
    try:
        if not doc.is_pdf:
            raise InvalidFile(str(path), "", "not a readable PDF")
        yield doc
    finally:
        doc.close()
