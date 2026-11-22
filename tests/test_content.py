from types import SimpleNamespace

import pytest
import yaml

from hiivmind_corpus_lib.chunks import Strategy, chunks
from hiivmind_corpus_lib.content import LargeFile
from hiivmind_corpus_lib.errors import InvalidFile, NoSuchSource
from hiivmind_corpus_lib.navigation import Coverage, Navigation, navigation_of
from hiivmind_corpus_lib.sections import sections
from support import open_corpus, write_tree


@pytest.fixture
def corpus(tmp_path):
    return open_corpus(tmp_path)


def root(corpus):
    return corpus.sources.locate(corpus.index.load().find("polars", "a.md")).file.parent


def put(corpus, files):
    return write_tree(root(corpus), files)


def test_navigation_reads_the_sources_files(corpus):  # NAV-1; ports test_detect_nav.py::TestDetectNav::test_mkdocs_detected
    put(corpus, {"mkdocs.yml": "site_name: Test\nnav:\n  - Home: index.md\n  - About: about.md\n", "index.md": "# Home", "about.md": "# About"})
    assert corpus.content.navigation("polars") == navigation_of(root(corpus))
    assert corpus.content.navigation("polars").nav_file == "mkdocs.yml"


def test_a_source_whose_files_are_not_on_disk_has_no_navigation_and_no_large_files(corpus):
    assert corpus.content.navigation("polars") == Navigation(False, None, None, (), Coverage(0, 0, 0, 0, 0.0))
    assert corpus.content.large_files("polars") == ()


def test_a_live_web_source_gives_urls_only(corpus):  # design §6.3
    data = yaml.safe_load((corpus.path / "config.yaml").read_text(encoding="utf-8"))
    data["sources"].append({"id": "web", "type": "web", "fetch_mode": "live", "base_url": "https://example.com/"})
    (corpus.path / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    assert corpus.content.navigation("web").found is False and corpus.content.large_files("web") == ()
    with pytest.raises(InvalidFile, match=r"^docs/x\.md: not a file of web on disk$"):
        corpus.content.sections("web", "docs/x.md")
    with pytest.raises(InvalidFile, match=r"^docs/x\.md: not a file of web on disk$"):
        corpus.content.chunks("web", "docs/x.md", Strategy.MARKDOWN)


@pytest.mark.parametrize("call", [
    lambda c: c.content.navigation("nope"), lambda c: c.content.large_files("nope"),
    lambda c: c.content.sections("nope", "a.md"), lambda c: c.content.chunks("nope", "a.md", Strategy.MARKDOWN)])
def test_an_unknown_source_is_no_such_source(corpus, call):
    with pytest.raises(NoSuchSource, match="config.yaml has no source `nope`"):
        call(corpus)


def _with_headings():
    text = "# Large File\n\n"
    for i in range(20):
        text += f"## Section {i}\n\n" + f"Content for section {i}. " * 10 + "\n\n"
    return text


def test_large_files_lists_a_file_only_above_the_threshold(corpus):  # LRG-1; ports test_detect_large_files.py::test_detects_large_files, test_ignores_small_files, test_reports_heading_info, test_no_headings_detected
    put(corpus, {"small.md": "# Small\n\nJust a small file.\n", "large_with_headings.md": _with_headings(),
                 "large_plain.md": "Just a very long file.\n" * 100})
    assert corpus.content.large_files("polars", max_tokens=50) == (
        LargeFile("large_plain.md", 650, 100, 0, None), LargeFile("large_with_headings.md", 1122, 82, 21, 2))


def test_a_file_at_exactly_max_tokens_is_not_listed(corpus):  # LRG-1
    put(corpus, {"ten.md": " ".join(["w"] * 10)})                      # 13 tokens
    assert corpus.content.large_files("polars", max_tokens=13) == ()
    assert [f.path for f in corpus.content.large_files("polars", max_tokens=12)] == ["ten.md"]


def test_a_high_threshold_lists_nothing(corpus):  # ports test_high_threshold_finds_nothing, test_empty_dir
    put(corpus, {"large_with_headings.md": _with_headings()})
    assert corpus.content.large_files("polars", max_tokens=999999) == ()


def test_large_files_cover_mdx_and_subdirectories_sorted_by_path_and_skip_other_files(corpus):  # LRG-1, NAV-3
    words = " ".join(["w"] * 50)
    put(corpus, {"z.md": words, "a/b.mdx": words, "a.md": words, "notes.txt": words})
    assert [f.path for f in corpus.content.large_files("polars", max_tokens=50)] == ["a.md", "a/b.mdx", "z.md"]


def test_heading_statistics_come_from_the_parser_and_ignore_fenced_hashes(corpus):  # CMP-5, SEC-1
    put(corpus, {"f.md": "# A\n\n```\n# not\n```\n\n### B\n" + "word " * 100})
    [found] = corpus.content.large_files("polars", max_tokens=50)
    assert (found.headings, found.deepest_heading) == (2, 3)


def test_a_file_with_undecodable_bytes_is_read_with_replacement(corpus):
    root(corpus).mkdir(parents=True, exist_ok=True)
    (root(corpus) / "b.md").write_bytes(b"# Caf\xe9\n" + b"word " * 100)
    assert [(f.path, f.headings) for f in corpus.content.large_files("polars", max_tokens=50)] == [("b.md", 1)]


def test_the_corpus_counter_decides_the_tokens(corpus):  # CMP-5
    put(corpus, {"a.md": "## A\nx\n## B\ny\n"})
    corpus.tokens = SimpleNamespace(counter=lambda: lambda text: 999)
    assert corpus.content.large_files("polars", max_tokens=500)[0].tokens == 999
    assert all(s.tokens == 999 for s in corpus.content.sections("polars", "a.md", min_tokens=0))
    assert len(corpus.content.chunks("polars", "a.md", Strategy.MARKDOWN, target_tokens=1, overlap_tokens=0)) > 1


def test_detect_then_split(corpus):  # ports test_pipeline.py::test_detect_then_split, test_small_files_not_split
    api = "# API Reference\n\n"
    for i in range(15):
        api += f"## Method {i}\n\n" + f"Description of method {i}. " * 20 + "\n\n"
        api += f"### Parameters\n\nParam details for method {i}. " * 10 + "\n\n"
    put(corpus, {"api.md": api, "readme.md": "# README\n\nShort file.\n"})
    assert [f.path for f in corpus.content.large_files("polars", max_tokens=100)] == ["api.md"]
    got = corpus.content.sections("polars", "api.md", min_tokens=0)
    assert len(got) == 30 and got == sections(api, min_tokens=0, count=corpus.tokens.count)


def test_chunks_of_a_file_are_chunks_of_its_text(corpus):
    text = "## One\nShort.\n\n## Two\nAlso short.\n"
    put(corpus, {"a.md": text})
    assert corpus.content.chunks("polars", "a.md", Strategy.HEADINGS, target_tokens=100) == \
        chunks(text, Strategy.HEADINGS, target_tokens=100, count=corpus.tokens.count)


def test_a_path_that_is_not_a_file_on_disk_is_an_invalid_file(corpus):  # design §10
    put(corpus, {"docs/real.md": "## R\nx\n"})
    with pytest.raises(InvalidFile, match=r"^docs/missing\.md: not a file of polars on disk$") as caught:
        corpus.content.sections("polars", "docs/missing.md")
    assert (caught.value.file, caught.value.detail) == ("docs/missing.md", "not a file of polars on disk")
    with pytest.raises(InvalidFile, match="^docs: not a file of polars on disk$"):
        corpus.content.chunks("polars", "docs", Strategy.MARKDOWN)      # a directory


def test_a_path_that_leaves_the_source_root_is_the_same_invalid_file(corpus):
    (corpus.path / "config-secret.md").write_text("## S\nx\n", encoding="utf-8")
    with pytest.raises(InvalidFile, match=r"^\.\./\.\./\.\./\.\./config-secret\.md: not a file of polars on disk$"):
        corpus.content.sections("polars", "../../../../config-secret.md")


def test_a_path_with_a_nul_byte_is_the_same_invalid_file(corpus):
    put(corpus, {"a.md": "## A\nx\n"})
    with pytest.raises(InvalidFile, match="^a\x00b\\.md: not a file of polars on disk$"):
        corpus.content.sections("polars", "a\x00b.md")
    with pytest.raises(InvalidFile, match="^a\x00b\\.md: not a file of polars on disk$"):
        corpus.content.chunks("polars", "a\x00b.md", Strategy.MARKDOWN)


def test_a_non_utf8_file_and_an_unreadable_file_do_not_stop_large_files_or_navigation(corpus):  # Review Focus 4
    big = "## A\n" + "word " * 200
    put(corpus, {"latin1.md": "", "locked.md": big, "ok.md": big, "_sidebar.md": "- [Ok](ok.md)\n"})
    (corpus.content._root("polars") / "latin1.md").write_bytes(("## Café\n" + "mot " * 200).encode("latin-1"))
    locked = corpus.content._root("polars") / "locked.md"
    locked.chmod(0o000)
    try:
        assert [f.path for f in corpus.content.large_files("polars", max_tokens=100)] == ["latin1.md", "ok.md"]
        assert corpus.content.navigation("polars").coverage.total_markdown_files == 4     # every .md file counts; only large_files skips the unreadable one
    finally:
        locked.chmod(0o644)


def test_config_source_names_the_unknown_source(corpus):
    with pytest.raises(NoSuchSource, match="config.yaml has no source `nope`"):
        corpus.config.load().source("nope")
