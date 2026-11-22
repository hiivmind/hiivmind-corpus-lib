import json
import pymupdf
import pytest
from hiivmind_corpus_lib.errors import InvalidFile
from hiivmind_corpus_lib.pdf import Chapter, ChapterPdf, Manifest, split
from pdf_support import make_pdf

PAGES = [[(f"page {n}", "helv", 11, 200)] for n in range(1, 5)]
CHAPTERS = (Chapter(1, "One", 0, 2), Chapter(2, "Two: Last!", 2, 4))


def _text(data):
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        return [page.get_text().strip() for page in doc]

def test_split_returns_each_chapter_as_bytes(tmp_path):              # ports split_pdf (file names, page ranges)
    path = make_pdf(tmp_path / "book.pdf", PAGES)
    files, manifest = split(path, CHAPTERS)
    assert [(f.chapter, f.file_name) for f in files] == [(CHAPTERS[0], "01_One.pdf"), (CHAPTERS[1], "02_Two_Last.pdf")]
    assert all(isinstance(f, ChapterPdf) and isinstance(f.data, bytes) for f in files)
    assert _text(files[0].data) == ["page 1", "page 2"]
    assert _text(files[1].data) == ["page 3", "page 4"]

def test_split_manifest(tmp_path):                                   # ports split_pdf (manifest.json shape)
    _, manifest = split(make_pdf(tmp_path / "book.pdf", PAGES), CHAPTERS)
    assert manifest == Manifest("book.pdf", ((CHAPTERS[0], "01_One.pdf"), (CHAPTERS[1], "02_Two_Last.pdf")))
    assert json.loads(manifest.to_json())["chapters"][1] == {"index": 2, "title": "Two: Last!", "file": "02_Two_Last.pdf", "pages": "3-4"}

def test_split_writes_nothing(tmp_path):                             # PDF-1
    path = make_pdf(tmp_path / "book.pdf", PAGES)
    before = {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")}
    split(path, CHAPTERS)
    assert {p: p.stat().st_mtime_ns for p in tmp_path.rglob("*")} == before

def test_split_names_use_two_digit_indexes_and_cut_long_titles(tmp_path):
    path = make_pdf(tmp_path / "book.pdf", PAGES)
    files, _ = split(path, (Chapter(12, "T" * 80, 0, 1),))
    assert files[0].file_name == "12_" + "T" * 50 + ".pdf"

def test_split_a_chapter_outside_the_file_is_invalid(tmp_path):      # design §10
    path = make_pdf(tmp_path / "book.pdf", PAGES)
    with pytest.raises(InvalidFile, match=r"chapter 3 \(pages 4-9\) is outside the file's 4 pages"):
        split(path, (Chapter(3, "Far", 3, 9),))
