from hiivmind_corpus_lib.sections import Section, sections


def test_basic_split():
    text = ("# Title\n\nIntro paragraph.\n\n## Section One\n\nContent for section one.\nMore content here.\n\n"
            "## Section Two\n\nContent for section two.\n")
    result = sections(text, min_tokens=0)
    assert [(s.title, s.level, s.line_start, s.line_end, s.tokens, s.anchor) for s in result] == [
        ("Section One", 2, 5, 9, 13, "section-one"), ("Section Two", 2, 10, 12, 10, "section-two")]


def test_line_ranges():
    result = sections("## First\nLine 2\nLine 3\n\n## Second\nLine 6\n", min_tokens=0)
    assert [(s.line_start, s.line_end) for s in result] == [(1, 4), (5, 6)]


def test_anchor_is_the_slug_of_the_title():
    result = sections("## Getting Started Guide\nContent.\n\n## API (v2) Reference!\nContent.\n", min_tokens=0)
    assert [s.anchor for s in result] == ["getting-started-guide", "api-v2-reference"]


def test_a_heading_in_any_code_block_is_not_a_section():
    text = "## Real\nx\n\n```markdown\n## Fake\n```\n\n~~~\n## Fake 2\n~~~\n\n    ## Fake 3\n\n## Another\ny\n"
    assert [s.title for s in sections(text, min_tokens=0)] == ["Real", "Another"]


def test_levels_outside_the_range_are_not_sections():
    text = "# H1\nc\n## H2\nc\n### H3\nc\n#### H4\nc\n##### H5\nc\n"
    assert [s.level for s in sections(text, min_level=2, max_level=3, min_tokens=0)] == [2, 3]


def test_a_small_section_merges_into_the_one_before_it():
    text = "## Big Section\n" + "Word " * 200 + "\n\n## Tiny\nOne line.\n\n## Another Big\n" + "Word " * 200 + "\n"
    result = sections(text, min_tokens=100)
    assert [(s.title, s.line_start, s.line_end, s.tokens) for s in result] == [
        ("Big Section", 1, 6, 270), ("Another Big", 7, 8, 264)]


def test_a_small_first_section_stays_and_the_next_small_one_merges_into_it():
    assert [(s.title, s.line_end) for s in sections("## A\nx\n## B\ny\n", min_tokens=100)] == [("A", 4)]
    text = "## Tiny\nx\n\n## Big\n" + "Word " * 200 + "\n"
    assert [s.title for s in sections(text, min_tokens=100)] == ["Tiny", "Big"]


def test_no_headings_is_no_sections():
    assert sections("Just a plain text file.\nWith no headings at all.\n", min_tokens=0) == ()
    assert sections("") == ()


def test_preview_is_the_first_200_characters():
    [s] = sections("## Section\nFirst line of content.\nSecond line.\n", min_tokens=0)
    assert s.preview == "## Section\nFirst line of content.\nSecond line."
    [long] = sections("## L\n" + "x" * 500 + "\n", min_tokens=0)
    assert long.preview == ("## L\n" + "x" * 500)[:200]


def test_contiguous_sections_leave_no_gap():
    text = "# API Reference\n\n"
    for i in range(15):
        text += f"## Method {i}\n\n" + f"Description of method {i}. " * 20 + "\n\n"
        text += f"### Parameters\n\nParam details for method {i}. " * 10 + "\n\n"
    result = sections(text, min_tokens=0)
    assert len(result) == 30 and result[0].line_start == 3
    assert all(a.line_end + 1 == b.line_start for a, b in zip(result, result[1:]))
    assert all(s.line_start <= s.line_end for s in result)


def test_the_count_is_injected_and_decides_merging():
    text = "## A\nx y\n## B\nz\n"
    assert [(s.title, s.tokens) for s in sections(text, min_tokens=5, count=lambda t: 1000)] == [("A", 1000), ("B", 1000)]
    assert [s.title for s in sections(text, min_tokens=5, count=lambda t: 1)] == ["A"]


def test_crlf_text_has_the_same_ranges():
    assert [(s.title, s.line_start, s.line_end) for s in sections("## A\r\nx\r\n## B\r\ny\r\n", min_tokens=0)] == [("A", 1, 2), ("B", 3, 4)]


def test_a_heading_on_the_last_line_is_a_one_line_section():
    assert [(s.title, s.line_start, s.line_end) for s in sections("## A\nx\n## B", min_tokens=0)] == [("A", 1, 2), ("B", 3, 3)]


def test_section_is_frozen():
    [s] = sections("## A\nx\n", min_tokens=0)
    assert isinstance(s, Section)
