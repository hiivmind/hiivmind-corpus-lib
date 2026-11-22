import subprocess, sys
import pytest
from hiivmind_corpus_lib.errors import ExtraMissing, InvalidFile
from hiivmind_corpus_lib.pdf import Chapter, chapters, chapters_by_font, fonts, outline, page_count, split, tables, text_blocks
from pdf_support import make_png
from support import needs

CALLS = {
    "outline": lambda p: outline(p), "page_count": lambda p: page_count(p), "text_blocks": lambda p: text_blocks(p, 0),
    "fonts": lambda p: fonts(p), "chapters": lambda p: chapters(p), "chapters_by_font": lambda p: chapters_by_font(p, "Bold", 20),
    "split": lambda p: split(p, (Chapter(1, "One", 0, 1),)), "tables": lambda p: tables(p, 0),
}


@pytest.mark.parametrize("name", CALLS)
def test_every_pdf_call_without_the_extra_names_the_extra(name, tmp_path, monkeypatch):
    path = tmp_path / "b.pdf"                                        # never opened: the extra is checked first
    monkeypatch.setitem(sys.modules, "pymupdf", None)                # `import pymupdf` now raises ImportError
    with pytest.raises(ExtraMissing, match=r"pdf extra is not installed: install hiivmind-corpus-lib\[pdf\]") as raised:
        CALLS[name](path)
    assert raised.value.code == "extra-missing"


@needs("pymupdf")
@pytest.mark.parametrize("name", CALLS)
@pytest.mark.parametrize("kind", ["text", "empty", "png"])
def test_every_pdf_call_on_an_unreadable_file_is_invalid_file(name, kind, tmp_path):   # design §10
    path = tmp_path / "bad.pdf"
    if kind == "png":
        make_png(path)                                               # PyMuPDF opens it, but Document.is_pdf is False
    else:
        path.write_bytes(b"not a pdf" if kind == "text" else b"")
    with pytest.raises(InvalidFile) as raised:
        CALLS[name](path)
    assert raised.value.code == "invalid-file" and str(path) in str(raised.value) and "not a readable PDF" in str(raised.value)


@needs("pymupdf")
@pytest.mark.parametrize("name", CALLS)
def test_every_pdf_call_on_a_missing_file_is_invalid_file(name, tmp_path):
    with pytest.raises(InvalidFile, match="missing.pdf: not a readable PDF"):
        CALLS[name](tmp_path / "missing.pdf")


def test_importing_the_package_and_calling_pure_helpers_does_not_import_pymupdf():     # PDF-2, CMP-3
    code = ("import sys, hiivmind_corpus_lib, hiivmind_corpus_lib.pdf as pdf\n"
            "pdf.layout_table([['a'], ['b']]); pdf.chapters_from_outline([], 1); pdf.strip_headers_footers((), 800)\n"
            "assert 'pymupdf' not in sys.modules, 'pymupdf was imported'")
    subprocess.run([sys.executable, "-c", code], check=True)
