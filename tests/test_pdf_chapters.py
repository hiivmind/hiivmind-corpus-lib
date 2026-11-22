from hiivmind_corpus_lib.pdf import Chapter, TocEntry, chapters_from_outline


def test_chapters_from_outline():                              # ports test_detect_chapters_from_toc_entries
    entries = [TocEntry(1, "Introduction", 0), TocEntry(1, "Getting Started", 15), TocEntry(1, "Advanced Topics", 42)]
    chapters = chapters_from_outline(entries, page_count=60)
    assert chapters == (Chapter(1, "Introduction", 0, 15), Chapter(2, "Getting Started", 15, 42), Chapter(3, "Advanced Topics", 42, 60))

def test_chapters_from_outline_filters_level():                # ports test_detect_chapters_from_toc_entries_filters_level
    entries = [TocEntry(1, "Part 1", 0), TocEntry(2, "Chapter 1.1", 0), TocEntry(2, "Chapter 1.2", 10), TocEntry(1, "Part 2", 20)]
    assert [c.title for c in chapters_from_outline(entries, page_count=40, level=1)] == ["Part 1", "Part 2"]
    assert chapters_from_outline(entries, page_count=40, level=2) == (Chapter(1, "Chapter 1.1", 0, 10), Chapter(2, "Chapter 1.2", 10, 40))

def test_chapters_from_outline_without_entries_at_the_level_is_empty():   # plugin: empty list
    assert chapters_from_outline([TocEntry(2, "Only", 0)], page_count=5, level=1) == ()
    assert chapters_from_outline([], page_count=5) == ()


# --- PyMuPDF-backed chapters ---
import pytest
from hiivmind_corpus_lib.pdf import Manifest, chapters, chapters_by_font, split
from pdf_support import make_pdf
from support import needs

BODY = ("body text", "helv", 11, 200)

@needs("pymupdf")
def test_chapters_from_the_outline(tmp_path):                        # ports detect_chapters (TOC branch)
    path = make_pdf(tmp_path / "b.pdf", [[BODY]] * 5, toc=[(1, "One", 1), (2, "Sub", 2), (1, "Two", 4)])
    assert chapters(path) == (Chapter(1, "One", 0, 3), Chapter(2, "Two", 3, 5))
    assert chapters(path, level=2) == (Chapter(1, "Sub", 1, 5),)

@needs("pymupdf")
def test_chapters_fall_back_to_chapter_lines_without_an_outline(tmp_path):     # ports _detect_chapters_by_text
    pages = [[("Chapter 1 Basics", "hebo", 20, 80), BODY], [BODY], [("CHAPTER IV Limits", "hebo", 20, 80)], [BODY]]
    assert chapters(make_pdf(tmp_path / "b.pdf", pages)) == (Chapter(1, "Chapter 1 Basics", 0, 2), Chapter(2, "CHAPTER IV Limits", 2, 4))

@needs("pymupdf")
def test_chapter_line_title_is_cut_to_sixty_characters(tmp_path):
    line = "Chapter 2 " + "x" * 70
    path = make_pdf(tmp_path / "b.pdf", [[(line, "helv", 9, 80)]])
    assert chapters(path)[0].title == line[:60]

@needs("pymupdf")
def test_chapters_fall_back_when_the_level_has_no_entries(tmp_path):  # plugin: no entries at the level -> text detection
    path = make_pdf(tmp_path / "b.pdf", [[("Chapter 1 Basics", "hebo", 20, 80)], [BODY]], toc=[(1, "Only", 1)])
    assert chapters(path, level=2) == (Chapter(1, "Chapter 1 Basics", 0, 2),)

@needs("pymupdf")
def test_chapters_none_found_is_empty(tmp_path):
    assert chapters(make_pdf(tmp_path / "b.pdf", [[BODY]])) == ()

@needs("pymupdf")
def test_split_of_no_chapters_is_no_files_and_an_empty_manifest(tmp_path):   # Review Focus 5
    path = make_pdf(tmp_path / "b.pdf", [[BODY]])
    assert split(path, chapters(path)) == ((), Manifest("b.pdf", ()))

@needs("pymupdf")
def test_chapters_by_font_takes_the_first_matching_span_in_the_top_150pt(tmp_path):
    big = lambda t: (t, "hebo", 24, 100)
    pages = [[big("Alpha"), ("Alpha again", "hebo", 24, 130)], [BODY], [big("Beta")], [("Footnote", "hebo", 24, 700)]]
    result = chapters_by_font(make_pdf(tmp_path / "b.pdf", pages), "bold", 20)
    assert result == (Chapter(1, "Alpha", 0, 2), Chapter(2, "Beta", 2, 4))      # substring, case-insensitive; page 3 is below 150 pt

@needs("pymupdf")
def test_chapters_by_font_respects_minimum_size(tmp_path):
    path = make_pdf(tmp_path / "b.pdf", [[("Small", "hebo", 12, 100)]])
    assert chapters_by_font(path, "Helvetica-Bold", 20) == ()
