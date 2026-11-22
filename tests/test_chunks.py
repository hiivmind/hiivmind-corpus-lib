import pytest

from hiivmind_corpus_lib.chunks import Chunk, Strategy, chunks

R = lambda cs: [(c.line_start, c.line_end) for c in cs]
words = lambda t: len(t.split())


def test_empty_and_blank_text_have_no_chunks():  # ports test_chunk.py::test_empty_file_returns_empty
    assert chunks("", Strategy.MARKDOWN) == () and chunks("   ", Strategy.PARAGRAPH) == ()


def test_a_small_text_is_one_chunk():  # ports test_small_file_single_chunk
    text = "Just a small file.\nWith two lines."
    assert chunks(text, Strategy.MARKDOWN) == (Chunk(0, text, 1, 2, 0, None),)


def test_one_chunk_up_to_one_and_a_half_times_the_target():  # CHK-1
    assert R(chunks("\n".join(["word"] * 15), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=0, count=words)) == [(1, 15)]
    assert R(chunks("\n".join(["word"] * 16), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=0, count=words)) == [(1, 10), (11, 16)]


@pytest.mark.parametrize("strategy, lines, expected", [
    (Strategy.MARKDOWN, 1350, 1), (Strategy.MARKDOWN, 1351, 2), (Strategy.TRANSCRIPT, 1350, 1), (Strategy.TRANSCRIPT, 1351, 2),
    (Strategy.PARAGRAPH, 1350, 1), (Strategy.PARAGRAPH, 1351, 2), (Strategy.CODE, 900, 1), (Strategy.CODE, 901, 2)])
def test_default_target_is_900_tokens_and_600_for_code(strategy, lines, expected):  # CHK-1
    got = chunks("\n".join(["x"] * lines), strategy, count=words)
    assert (len(got) == 1) == (expected == 1)


@pytest.mark.parametrize("strategy, first_end, overlap", [(Strategy.MARKDOWN, 900, 100), (Strategy.CODE, 600, 50)])
def test_default_overlap_is_100_tokens_and_50_for_code(strategy, first_end, overlap):  # CHK-1
    got = chunks("\n".join(["x"] * 2000), strategy, count=words)
    assert got[0].line_end == first_end and got[1].overlap_previous == overlap


MARKDOWN = "\n".join(["# Introduction", "First paragraph of intro.", "Second paragraph of intro.", "", "## Getting Started",
                      "Content for getting started section.", "More content here with details.", "", "## Advanced Usage",
                      "Advanced content goes here.", "Even more advanced content."])
TRANSCRIPT = "\n".join(["Alice: Hello everyone, let's get started with the meeting.", "Alice: First item on the agenda is the Q3 review.", "",
                        "Bob: Thanks Alice. The numbers look good this quarter.", "Bob: Revenue is up 15% compared to last quarter.", "",
                        "Charlie: I have some concerns about the infrastructure costs.", "Charlie: We need to discuss the cloud spending."])
TIMESTAMPS = "\n".join(["[00:00:00] Meeting started", "Discussion about project timeline.", "More discussion here.", "",
                        "[00:15:00] Moving to next topic", "Budget review discussion.", "More budget details.", "",
                        "[00:30:00] Action items", "List of things to do."])
CODE = "\n".join(["def hello():", "    print('hello')", "    print('world')", "", "def goodbye():", "    print('goodbye')",
                  "    print('world')", "", "class MyClass:", "    def method(self):", "        pass"])


def test_markdown_splits_at_a_heading():  # CHK-1; ports test_chunk.py::TestMarkdownStrategy::test_splits_on_headings (ranges computed from the rules of Step 3)
    got = chunks(MARKDOWN, Strategy.MARKDOWN, target_tokens=20, overlap_tokens=0)
    assert R(got) == [(1, 4), (5, 8), (9, 11)] and [c.index for c in got] == [0, 1, 2]
    assert got[1].text.startswith("## Getting Started") and got[1].heading_context is None


def test_a_hash_line_in_a_fence_is_not_a_markdown_boundary():  # CMP-5 (one heading parser)
    real = ["x"] * 6 + ["# h"] + ["x"] * 9
    fenced = ["x"] * 5 + ["```", "# h", "```"] + ["x"] * 8
    assert R(chunks("\n".join(real), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=0, count=words)) == [(1, 6), (7, 15), (16, 16)]   # the heading starts the second chunk
    got = chunks("\n".join(fenced), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=0, count=words)
    assert R(got) == [(1, 9), (10, 16)] and 7 not in [c.line_start for c in got]                                                          # a fenced # line is no boundary


def test_transcript_splits_on_speaker_turns():  # CHK-1; ports test_splits_on_speaker_turns
    assert R(chunks(TRANSCRIPT, Strategy.TRANSCRIPT, target_tokens=20, overlap_tokens=0)) == [(1, 1), (2, 3), (4, 4), (5, 6), (7, 8)]


def test_transcript_splits_on_timestamps():  # CHK-1; ports test_splits_on_timestamps
    assert R(chunks(TIMESTAMPS, Strategy.TRANSCRIPT, target_tokens=20, overlap_tokens=0)) == [(1, 4), (5, 8), (9, 10)]


def test_code_splits_on_definitions():  # CHK-1; ports test_splits_on_function_definitions
    assert R(chunks(CODE, Strategy.CODE, target_tokens=10, overlap_tokens=0)) == [(1, 4), (5, 8), (9, 11)]


def test_paragraph_strategy_splits_where_the_target_is_filled():  # CHK-1; ports test_splits_on_double_newlines + test_line_ranges_are_contiguous
    text = "\n".join(f"Line {i}" for i in range(50))                # 3 tokens a line: 7 lines fill 20
    assert R(chunks(text, Strategy.PARAGRAPH, target_tokens=20, overlap_tokens=0)) == [(7 * i + 1, 7 * i + 7) for i in range(7)] + [(50, 50)]


def test_overlap_is_the_lines_shared_with_the_chunk_before():  # CHK-1; ports test_overlap_produces_shared_content
    lines = []
    for i in range(5):
        lines += [f"## Section {i}"] + [f"Content line {i}-{j}." for j in range(10)] + [""]
    got = chunks("\n".join(lines), Strategy.MARKDOWN, target_tokens=30, overlap_tokens=10)
    assert R(got) == [(1, 12), (9, 24), (21, 36), (33, 48), (45, 60)] and (got[1].line_start, got[1].overlap_previous) == (9, 4)
    assert got[0].overlap_previous == 0
    assert all(b.overlap_previous == max(0, a.line_end - b.line_start + 1) for a, b in zip(got, got[1:]))
    assert R(chunks("\n".join(lines), Strategy.MARKDOWN, target_tokens=30, overlap_tokens=0)) == [(1, 12), (13, 24), (25, 36), (37, 48), (49, 60)]


def test_among_equally_scored_boundaries_the_nearest_the_target_wins_and_a_tie_the_earlier():   # CHK-1 (the plugin took the earliest)
    def first_chunk(*blanks):
        lines = ["x"] * 20
        for i in blanks:
            lines[i] = ""
        return R(chunks("\n".join(lines), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=0, count=words))[0]

    assert first_chunk(5, 10) == (1, 11)      # the target is line 10 (index 9): the blank at index 10 is 1 away, the one at index 5 is 4
    assert first_chunk(7, 11) == (1, 8)       # both 2 away: the earlier


@pytest.mark.parametrize("overlap, first", [(5, [(1, 10), (6, 20), (16, 30)]), (50, [(1, 10), (2, 20), (3, 30)]),
                                            (200, [(1, 10), (2, 20), (3, 30)])])
def test_no_chunk_lies_inside_the_one_before(overlap, first):      # CHK-1 (the plugin could emit one); the walk never reaches the previous first line
    got = chunks("\n".join(["x"] * 100), Strategy.MARKDOWN, target_tokens=10, overlap_tokens=overlap, count=words)
    assert len(got) == 10 and R(got)[:3] == first
    assert all(b.line_end > a.line_end and b.line_start > a.line_start for a, b in zip(got, got[1:]))


@pytest.mark.parametrize("strategy", [Strategy.MARKDOWN, Strategy.TRANSCRIPT, Strategy.CODE, Strategy.PARAGRAPH, Strategy.HEADINGS])
def test_lines_are_one_based_inclusive_and_cover_every_non_empty_line(strategy):  # CHK-2; ports test_line_ranges_cover_entire_file
    text = {Strategy.MARKDOWN: MARKDOWN, Strategy.TRANSCRIPT: TRANSCRIPT, Strategy.CODE: CODE,
            Strategy.PARAGRAPH: "\n".join(f"Line {i}" for i in range(50)),
            Strategy.HEADINGS: "Intro.\n\n" + MARKDOWN}[strategy]
    lines = text.split("\n")
    got = chunks(text, strategy, target_tokens=20, overlap_tokens=5)
    assert got[0].line_start == 1 and all(1 <= c.line_start <= c.line_end <= len(lines) for c in got)
    assert all(c.text == "\n".join(lines[c.line_start - 1:c.line_end]) for c in got)
    covered = {n for c in got for n in range(c.line_start, c.line_end + 1)}
    assert {n for n, line in enumerate(lines, 1) if line.strip()} <= covered


def test_a_section_within_the_target_is_one_chunk_with_its_heading_context():  # CHK-1; ports test_chunk_headings.py::test_sections_within_target_are_single_chunks
    text = "## Section One\n\nShort content.\n\n## Section Two\n\nAnother short section.\n"
    got = chunks(text, Strategy.HEADINGS, target_tokens=100, overlap_tokens=10)
    assert got == (Chunk(0, "## Section One\n\nShort content.\n", 1, 4, 0, "Section One"),
                   Chunk(1, "## Section Two\n\nAnother short section.", 5, 7, 0, "Section Two"))


def test_heading_context_is_the_ancestor_titles():  # CHK-1 (design §7.4 example)
    text = "## Install\nSteps.\n### From PyPI\npip install.\n## Usage\nRun.\n"
    assert [c.heading_context for c in chunks(text, Strategy.HEADINGS)] == ["Install", "Install > From PyPI", "Usage"]
    text = "# Title\nIntro.\n## Install\nSteps.\n#### Deep\nx\n"
    assert [c.heading_context for c in chunks(text, Strategy.HEADINGS)] == ["Title", "Title > Install", "Title > Install > Deep"]


def test_text_before_the_first_heading_is_a_chunk_without_context():  # CHK-2
    got = chunks("Intro line.\n\n## A\nBody.\n", Strategy.HEADINGS)
    assert [(c.line_start, c.line_end, c.heading_context) for c in got] == [(1, 2, None), (3, 4, "A")]


def test_a_large_section_splits_and_keeps_its_context_and_overlap():  # CHK-1; ports test_large_sections_split_at_paragraphs + test_overlap_on_paragraph_splits
    text = "## Big Section\n\n" + "".join(f"Paragraph {i}. " * 20 + "\n\n" for i in range(20))
    got = chunks(text, Strategy.HEADINGS, target_tokens=50, overlap_tokens=10)
    assert len(got) > 1 and {c.heading_context for c in got} == {"Big Section"}
    assert (got[0].line_start, got[0].line_end, got[1].overlap_previous) == (1, 2, 1)


def test_no_overlap_at_a_heading_boundary():  # CHK-1; ports test_no_overlap_at_heading_boundaries
    got = chunks("## First\n\nContent one.\n\n## Second\n\nContent two.\n", Strategy.HEADINGS, target_tokens=100, overlap_tokens=10)
    assert got[1].overlap_previous == 0


def test_headings_without_headings_split_like_markdown_with_no_context():  # ports test_no_headings_falls_back
    text = "Just plain text.\n" * 50
    got = chunks(text, Strategy.HEADINGS, target_tokens=20, overlap_tokens=5)
    assert R(got) == R(chunks(text, Strategy.MARKDOWN, target_tokens=20, overlap_tokens=5))
    assert (len(got), R(got)[:2], got[1].overlap_previous) == (10, [(1, 5), (4, 10)], 2)
    assert {c.heading_context for c in got} == {None}


def test_crlf_text_chunks_on_the_same_lines():  # Review Focus 3
    text = "## A\nline\n\n## B\nline\n" * 30
    assert R(chunks(text.replace("\n", "\r\n"), Strategy.MARKDOWN, target_tokens=40)) == R(chunks(text, Strategy.MARKDOWN, target_tokens=40))


def test_the_count_is_injected():  # CMP-5
    assert len(chunks("a\nb\nc", Strategy.MARKDOWN, target_tokens=1, overlap_tokens=0, count=lambda t: 100)) > 1


def test_paragraph_strategy_splits_at_a_blank_line_rather_than_a_text_line():  # CHK-1 (a blank scores 50, a text line 10)
    lines = ["x"] * 20
    lines[8] = ""                       # the target (10 words) is filled at index 9; the blank is the best boundary within the window
    got = chunks("\n".join(lines), Strategy.PARAGRAPH, target_tokens=10, overlap_tokens=0, count=words)
    assert R(got)[0] == (1, 9)


def test_a_range_of_blank_lines_is_not_a_chunk():  # CHK-2 (the text's blank lines 6-7 fall between chunks; every non-empty line is still covered)
    text = "# H\n- i\n- i\n- i\n\n\n\nx\n- i"
    got = chunks(text, Strategy.MARKDOWN, target_tokens=3, overlap_tokens=0, count=words)
    assert R(got) == [(1, 5), (8, 9)] and all(c.text.strip() for c in got)
