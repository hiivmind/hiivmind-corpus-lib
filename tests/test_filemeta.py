import pytest

from hiivmind_corpus_lib.filemeta import LARGE_FILE_LINES, file_metadata, slug
from hiivmind_corpus_lib.index import Heading


def _write(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


@pytest.mark.parametrize("name,kind", [
    ("a.md", "markdown"), ("a.mdx", "markdown"), ("a.yaml", "yaml"), ("a.yml", "yaml"),
    ("a.json", "json"), ("a.rst", "rst"), ("a.txt", "text"), ("a", "text"), ("A.MD", "markdown"),
])
def test_content_type_by_suffix(tmp_path, name, kind):
    assert file_metadata(_write(tmp_path, name, "x\n")).content_type == kind


def test_size_is_large_above_1000_lines(tmp_path):
    assert LARGE_FILE_LINES == 1000
    std = file_metadata(_write(tmp_path, "s.md", "x\n" * 1000))
    big = file_metadata(_write(tmp_path, "b.md", "x\n" * 1001))
    assert (std.lines, std.size, std.grep_hint) == (1000, "standard", None)
    assert (big.lines, big.size) == (1001, "large")
    assert big.grep_hint == 'grep -n "^## " FILE'
    assert file_metadata(_write(tmp_path, "b.yaml", "x\n" * 1001)).grep_hint is None


def test_headings_are_atx_outside_fenced_code(tmp_path):
    text = (
        "# Title\n## Arithmetic Operations\n```\n# not a heading\n```\n"
        "~~~\n# nor this\n~~~\n### Closed ###\n"
    )
    meta = file_metadata(_write(tmp_path, "h.md", text))
    assert meta.headings == (
        Heading("title", "Title"),
        Heading("arithmetic-operations", "Arithmetic Operations"),
        Heading("closed", "Closed"),
    )


def test_undecodable_bytes_are_replaced(tmp_path):
    p = tmp_path / "b.md"
    p.write_bytes(b"# Caf\xe9\n")
    assert file_metadata(p).headings[0].title == "Caf\ufffd"


def test_a_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        file_metadata(tmp_path / "missing.md")


def test_slug():
    assert slug("Window Functions & `over()`") == "window-functions-over"
    assert slug("  --  ") == ""
