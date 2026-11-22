import dataclasses, json
import pytest
from hiivmind_corpus_lib.pdf import Box, Chapter, ChapterPdf, CrossRef, FontInfo, Manifest, TextBlock, TocEntry


def test_chapter_page_count_and_range():                       # ports test_chapter_boundary_dataclass
    chapter = Chapter(index=1, title="Introduction", start_page=0, end_page=15)
    assert chapter.page_count == 15
    assert chapter.page_range == "1-15"


def test_toc_entry_and_font_info_hold_their_values():          # ports test_toc_entry_dataclass, test_font_info_dataclass
    assert TocEntry(level=1, title="Chapter 1", page=0).level == 1
    info = FontInfo(font="Arial", size=12.0, characters=5, pages=(0, 2))
    assert (info.font, info.characters, info.pages) == ("Arial", 5, (0, 2))


@pytest.mark.parametrize("value", [
    Box(0, 1, 2, 3), TocEntry(1, "a", 0), Chapter(1, "a", 0, 1), CrossRef("page 1", "see_reference", "Intro", 1),
    FontInfo("Arial", 12.0, 1, (0,)), ChapterPdf(Chapter(1, "a", 0, 1), "01_a.pdf", b""),
    TextBlock("t", "Arial", 12.0, False, False, False, Box(0, 1, 2, 3), 0),
    Manifest("book.pdf", ()),
])
def test_every_result_is_frozen(value):                        # P-3
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, dataclasses.fields(value)[0].name, None)


def test_manifest_to_json_is_the_plugins_manifest_shape():     # ports split_pdf.split_pdf's manifest.json
    manifest = Manifest("book.pdf", ((Chapter(1, "One", 0, 2), "01_One.pdf"), (Chapter(2, "Two", 2, 4), "02_Two.pdf")))
    assert json.loads(manifest.to_json()) == {"source": "book.pdf", "chapters": [
        {"index": 1, "title": "One", "file": "01_One.pdf", "pages": "1-2"},
        {"index": 2, "title": "Two", "file": "02_Two.pdf", "pages": "3-4"}]}
    assert manifest.to_json() == json.dumps(json.loads(manifest.to_json()), indent=2)
