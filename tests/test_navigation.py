import pytest

from hiivmind_corpus_lib.navigation import Coverage, NavFormat, NavItem as N, Navigation, markdown_files, navigation_of
from support import write_tree


def _nav(tmp_path, files):
    write_tree(tmp_path, files)
    return navigation_of(tmp_path)


def test_flat_mkdocs_nav(tmp_path):  # NAV-1; ports test_detect_nav.py::TestParseMkdocsNav::test_simple_flat_nav, TestDetectNav::test_mkdocs_detected
    nav = _nav(tmp_path, {"mkdocs.yml": "site_name: T\nnav:\n  - Home: index.md\n  - Getting Started: getting-started.md\n  - API Reference: api.md\n",
                          "index.md": "#", "getting-started.md": "#", "api.md": "#"})
    assert (nav.found, nav.nav_file, nav.format) == (True, "mkdocs.yml", NavFormat.MKDOCS)
    assert nav.hierarchy == (N("Home", "index.md", 0, ()), N("Getting Started", "getting-started.md", 0, ()), N("API Reference", "api.md", 0, ()))


def test_nested_mkdocs_nav(tmp_path):  # ports test_nested_nav
    nav = _nav(tmp_path, {"mkdocs.yml": "nav:\n  - Home: index.md\n  - Guide:\n    - Install: guide/install.md\n    - Usage: guide/usage.md\n"})
    assert nav.hierarchy == (N("Home", "index.md", 0, ()),
                             N("Guide", None, 0, (N("Install", "guide/install.md", 1, ()), N("Usage", "guide/usage.md", 1, ()))))


def test_a_bare_string_item_is_its_own_title_and_path(tmp_path):
    assert _nav(tmp_path, {"mkdocs.yml": "nav:\n  - index.md\n"}).hierarchy == (N("index.md", "index.md", 0, ()),)


def test_missing_files_are_still_in_the_hierarchy_and_counted(tmp_path):  # NAV-3; ports test_missing_files_still_parsed
    nav = _nav(tmp_path, {"mkdocs.yml": "nav:\n  - Exists: exists.md\n  - Missing: missing.md\n", "exists.md": "# Exists"})
    assert len(nav.hierarchy) == 2 and nav.coverage == Coverage(2, 1, 1, 1, 100.0)


def test_coverage_is_resolved_over_all_markdown_files(tmp_path):  # NAV-3; ports test_coverage_calculation
    nav = _nav(tmp_path, {"mkdocs.yml": "nav:\n  - Home: index.md\n  - Missing: missing.md\n", "index.md": "# Home", "extra.md": "# Extra"})
    assert nav.coverage == Coverage(2, 1, 1, 2, 50.0)


def test_coverage_counts_mdx_and_nested_files_and_rounds_to_one_decimal(tmp_path):  # NAV-3
    nav = _nav(tmp_path, {"mkdocs.yml": "nav:\n  - Home: index.md\n", "index.md": "#", "docs/a.mdx": "#", "docs/deep/b.md": "#", "notes.txt": "x"})
    assert nav.coverage == Coverage(1, 1, 0, 3, 33.3)


def test_flat_sidebar(tmp_path):  # NAV-1; ports test_sidebar_fallback, TestParseSidebarMd::test_flat_sidebar
    nav = _nav(tmp_path, {"_sidebar.md": "- [Home](index.md)\n- [Guide](guide.md)\n- [API](api.md)\n", "index.md": "#"})
    assert (nav.found, nav.nav_file, nav.format) == (True, "_sidebar.md", NavFormat.SIDEBAR)
    assert nav.hierarchy == (N("Home", "index.md", 0, ()), N("Guide", "guide.md", 0, ()), N("API", "api.md", 0, ()))


def test_nested_sidebar_nests_by_indentation(tmp_path):  # ports test_nested_sidebar, test_summary_md_detected
    nav = _nav(tmp_path, {"SUMMARY.md": "- [Introduction](intro.md)\n  - [Install](install.md)\n  - [Config](config.md)\n- [Advanced](advanced.md)\n"})
    assert (nav.nav_file, nav.format) == ("SUMMARY.md", NavFormat.SUMMARY)
    assert nav.hierarchy == (N("Introduction", "intro.md", 0, (N("Install", "install.md", 1, ()), N("Config", "config.md", 1, ()))),
                             N("Advanced", "advanced.md", 0, ()))


def test_src_summary_md_is_found_and_a_draft_link_is_a_group(tmp_path):
    nav = _nav(tmp_path, {"src/SUMMARY.md": "- [Intro](intro.md)\n- [Draft]()\n"})
    assert nav.nav_file == "src/SUMMARY.md" and nav.hierarchy[1] == N("Draft", None, 0, ())


def test_markdown_navigation_targets_are_relative_to_the_navigation_file(tmp_path):
    nav = _nav(tmp_path, {"src/SUMMARY.md": "- [Intro](intro.md)\n", "src/intro.md": "#"})
    assert nav.hierarchy == (N("Intro", "src/intro.md", 0, ()),)       # root-relative, like every other format
    assert nav.coverage == Coverage(1, 1, 0, 2, 50.0)                  # resolved: src/intro.md exists


def test_no_navigation_file(tmp_path):  # NAV-1; ports test_no_nav_file
    assert _nav(tmp_path, {"readme.md": "# Hello"}) == Navigation(False, None, None, (), Coverage(0, 0, 0, 1, 0.0))


def test_a_root_that_is_not_a_directory_is_not_found(tmp_path):  # ports TestDetectNavCLI::test_cli_nonexistent_dir
    assert navigation_of(tmp_path / "nope") == Navigation(False, None, None, (), Coverage(0, 0, 0, 0, 0.0))


def test_the_first_file_in_order_that_yields_entries_wins(tmp_path):  # NAV-1
    both = {"_sidebar.md": "- [S](s.md)\n", "SUMMARY.md": "- [M](m.md)\n"}
    assert _nav(tmp_path / "a", {"mkdocs.yml": "site_name: T\n", **both}).nav_file == "_sidebar.md"      # no nav key: falls through
    assert _nav(tmp_path / "b", {"mkdocs.yml": "nav:\n  - A: a.md\n", "mkdocs.yaml": "nav:\n  - B: b.md\n"}).hierarchy[0].title == "A"
    assert _nav(tmp_path / "c", {"mkdocs.yml": "nav: []\n", **both}).nav_file == "_sidebar.md"            # empty nav: falls through
    assert _nav(tmp_path / "d", {"SUMMARY.md": "- [M](m.md)\n", "src/SUMMARY.md": "- [N](n.md)\n"}).nav_file == "SUMMARY.md"


def test_a_jupyter_book_toc(tmp_path):  # NAV-2
    nav = _nav(tmp_path, {"_toc.yml": "format: jb-book\nroot: intro\nchapters:\n  - file: guide\n    sections:\n      - file: guide/install\n  - file: api.md\n    title: API\n",
                          "intro.md": "#", "guide.md": "#", "guide/install.md": "#", "api.md": "#"})
    assert (nav.nav_file, nav.format) == ("_toc.yml", NavFormat.JUPYTER_BOOK)
    assert nav.hierarchy == (N("intro", "intro.md", 0, ()),
                             N("guide", "guide.md", 0, (N("install", "guide/install.md", 1, ()),)),
                             N("API", "api.md", 0, ()))
    assert nav.coverage == Coverage(4, 4, 0, 4, 100.0)


def test_jupyter_book_parts_are_groups_and_a_missing_extensionless_file_resolves_to_md(tmp_path):  # NAV-2
    nav = _nav(tmp_path, {"_toc.yml": "parts:\n  - caption: Basics\n    chapters:\n      - file: a\n      - file: gone\n", "a.md": "#"})
    assert nav.hierarchy == (N("Basics", None, 0, (N("a", "a.md", 1, ()), N("gone", "gone.md", 1, ()))),)
    assert nav.coverage.files_missing == 1


def test_a_toc_yml_with_mkdocs_nav_keys_is_not_read_as_mkdocs(tmp_path):  # NAV-2
    nav = _nav(tmp_path, {"_toc.yml": "nav:\n  - Home: index.md\n", "index.md": "#"})
    assert nav == Navigation(False, None, None, (), Coverage(0, 0, 0, 1, 0.0))


def test_mkdocs_python_tags_do_not_stop_the_nav_being_read(tmp_path):
    text = ("markdown_extensions:\n  - pymdownx.emoji:\n      emoji_index: !!python/name:material.extensions.emoji.twemoji\n"
            "nav:\n  - Home: index.md\n")
    assert len(_nav(tmp_path, {"mkdocs.yml": text}).hierarchy) == 1


def test_a_navigation_file_that_is_not_yaml_yields_no_entries_and_the_next_one_is_read(tmp_path):  # NAV-1; no new error (design §10)
    nav = _nav(tmp_path, {"mkdocs.yml": "nav: [unclosed\n", "_sidebar.md": "- [S](s.md)\n"})
    assert nav.nav_file == "_sidebar.md"
    assert _nav(tmp_path / "only", {"mkdocs.yml": "nav: [unclosed\n"}).found is False


def test_markdown_files_are_md_and_mdx_sorted(tmp_path):  # NAV-3, LRG-1 (the shared rule)
    write_tree(tmp_path, {"b.md": "#", "a.mdx": "#", "docs/c.md": "#", "x.txt": "x"})
    assert markdown_files(tmp_path) == ("a.mdx", "b.md", "docs/c.md")


def test_a_latin1_navigation_file_does_not_raise(tmp_path):
    (tmp_path / "mkdocs.yml").write_bytes("nav:\n  - Caf\xe9: cafe.md\n".encode("latin-1"))
    assert [n.path for n in navigation_of(tmp_path).hierarchy] == ["cafe.md"]
    (tmp_path / "mkdocs.yml").unlink()
    (tmp_path / "_sidebar.md").write_bytes("- [Caf\xe9](cafe.md)\n".encode("latin-1"))
    assert navigation_of(tmp_path).hierarchy


def test_external_links_are_kept_and_anchored_links_count_as_their_file(tmp_path):
    nav = _nav(tmp_path / "a", {"src/SUMMARY.md": "- [Intro](intro.md#start)\n- [Site](https://example.com/a/b)\n- [Gone](gone.md)\n",
                                "src/intro.md": "#"})
    assert [n.path for n in nav.hierarchy] == ["src/intro.md#start", "https://example.com/a/b", "src/gone.md"]
    assert nav.coverage == Coverage(2, 1, 1, 2, 50.0)
    nav = _nav(tmp_path / "b", {"mkdocs.yml": "nav:\n  - Home: index.md\n  - GitHub: https://github.com/x\n", "index.md": "#"})
    assert nav.coverage == Coverage(1, 1, 0, 1, 100.0)
