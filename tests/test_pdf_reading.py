import pytest
from hiivmind_corpus_lib.errors import InvalidFile
from hiivmind_corpus_lib.pdf import Box, FontInfo, TextBlock, TocEntry, fonts, outline, page_count, strip_headers_footers, tables, text_blocks
from pdf_support import make_pdf, make_table_pdf
from support import needs

BODY = ("body text", "helv", 11, 200)
CODE = ("code x=1", "cour", 10, 250)
ITALIC = ("ital", "heit", 10, 300)
TITLE = ("Chapter 1 Title", "hebo", 24, 100)


@needs("pymupdf")
def test_outline_is_zero_based(tmp_path):
    path = make_pdf(tmp_path / "b.pdf", [[BODY]] * 4, toc=[(1, "One", 1), (1, "Two", 3), (2, "Sub", 3)])
    assert outline(path) == (TocEntry(1, "One", 0), TocEntry(1, "Two", 2), TocEntry(2, "Sub", 2))

@needs("pymupdf")
def test_outline_without_bookmarks_is_empty(tmp_path):
    assert outline(make_pdf(tmp_path / "b.pdf", [[BODY]])) == ()

@needs("pymupdf")
def test_page_count(tmp_path):
    assert page_count(make_pdf(tmp_path / "b.pdf", [[BODY]] * 3)) == 3

@needs("pymupdf")
def test_text_blocks_carry_font_size_flags_box_and_page(tmp_path):   # ports test_extract_text_blocks_returns_list, test_text_block_bold_detection
    path = make_pdf(tmp_path / "b.pdf", [[TITLE, BODY, CODE, ITALIC]])
    by_text = {b.text: b for b in text_blocks(path, 0)}
    title = by_text["Chapter 1 Title"]
    assert (title.font, title.size, title.bold, title.italic, title.monospace, title.page) == ("Helvetica-Bold", 24.0, True, False, False, 0)
    assert isinstance(title.box, Box) and 70 < title.box.top < 80 and title.box.x0 == 72.0
    assert (by_text["body text"].bold, by_text["body text"].size) == (False, 11.0)
    assert by_text["code x=1"].monospace is True
    assert by_text["ital"].italic is True

@needs("pymupdf")
def test_text_blocks_of_a_page_without_text_is_empty(tmp_path):
    assert text_blocks(make_pdf(tmp_path / "b.pdf", [[]]), 0) == ()

@needs("pymupdf")
def test_text_blocks_page_out_of_range(tmp_path):                    # design §10
    path = make_pdf(tmp_path / "b.pdf", [[BODY]])
    with pytest.raises(InvalidFile, match=r"page 3 is out of range \(the file has 1 page\)"):
        text_blocks(path, 3)

@needs("pymupdf")
def test_tables_reads_a_drawn_grid_as_rows(tmp_path):                # design §7.8: Page.find_tables()
    path = make_table_pdf(tmp_path / "t.pdf", [["Name", "Type"], ["SYSDATE", "Readonly"], ["SYSERR", ""]])
    assert tables(path, 0) == ((("Name", "Type"), ("SYSDATE", "Readonly"), ("SYSERR", "")),)   # an empty cell is "", not None

@needs("pymupdf")
def test_a_page_without_a_table_has_no_tables(tmp_path):
    assert tables(make_pdf(tmp_path / "b.pdf", [[BODY]]), 0) == ()

@needs("pymupdf")
def test_tables_page_out_of_range(tmp_path):                         # the same rule as text_blocks
    path = make_table_pdf(tmp_path / "t.pdf", [["a", "b"], ["c", "d"]])
    with pytest.raises(InvalidFile, match=r"page 2 is out of range \(the file has 1 page\)"):
        tables(path, 2)

@needs("pymupdf")
def test_fonts_profile_by_font_and_size(tmp_path):                   # ports test_analyze_fonts_returns_font_map
    path = make_pdf(tmp_path / "b.pdf", [[BODY, CODE], [BODY]])
    assert fonts(path) == (FontInfo("Helvetica", 11.0, 18, (0, 1)), FontInfo("Courier", 10.0, 8, (0,)))   # by characters, descending

def _block(text, top, *, size=8.0):
    return TextBlock(text, "Arial", size, False, False, False, Box(0, top, 500, top + 10), 0)

def test_strip_headers_footers():                                    # ports test_strip_headers_footers
    blocks = (_block("Chapter 3 / Macro Variables", 10), _block("Body text here", 100, size=12.0), _block("42", 780))
    result = strip_headers_footers(blocks, 800, header_pattern=r"Chapter \d+", header_zone=50, footer_zone=40)
    assert [b.text for b in result] == ["Body text here"]

def test_strip_headers_footers_pattern_keeps_other_text_in_the_header_zone():   # plugin behaviour, untested there
    blocks = (_block("Chapter 3 / Macro Variables", 10), _block("A real title", 20))
    assert [b.text for b in strip_headers_footers(blocks, 800, header_pattern=r"Chapter \d+")] == ["A real title"]

def test_strip_headers_footers_zone_only_and_defaults():             # §7.8: header zone 50 pt, footer zone 40 pt
    blocks = (_block("top", 50), _block("just inside", 51), _block("bottom", 760), _block("just above", 759))
    assert [b.text for b in strip_headers_footers(blocks, 800)] == ["just inside", "just above"]
