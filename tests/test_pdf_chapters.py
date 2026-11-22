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
