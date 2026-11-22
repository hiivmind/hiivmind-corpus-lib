from hiivmind_corpus_lib.markdown import HeadingLine, Link, headings, links, slug


def test_headings_have_level_title_and_one_based_line():
    text = "# Title\n\nIntro.\n\n## Install\n\n###### Deep\n"
    assert headings(text) == (HeadingLine(1, "Title", 1), HeadingLine(2, "Install", 5), HeadingLine(6, "Deep", 7))


def test_a_closed_atx_heading_loses_its_closing_hashes_and_keeps_its_markup():
    assert headings("### Closed ###\n## Window Functions & `over()`\n") == (
        HeadingLine(3, "Closed", 1), HeadingLine(2, "Window Functions & `over()`", 2))


def test_an_empty_heading_is_not_a_heading():
    assert headings("#\n## Real\n") == (HeadingLine(2, "Real", 2),)


def test_a_heading_inside_a_backtick_fence_is_not_one():  # SEC-1; ports test_split_by_headings.py::test_skips_code_block_headings
    text = "## Real\nx\n\n```markdown\n## Fake\n```\n\n## Another\ny\n"
    assert [h.title for h in headings(text)] == ["Real", "Another"]


def test_a_heading_inside_a_tilde_fence_or_indented_code_is_not_one():  # SEC-1
    text = "## One\n\n~~~\n# nor this\n~~~\n\n    ## nor this\n\n## Two\n"
    assert [h.title for h in headings(text)] == ["One", "Two"]


def test_a_longer_fence_is_closed_only_by_a_fence_as_long():  # SEC-1 (the old toggle closed at the first ```)
    text = "````\n```\n# inside\n```\n````\n# Out\n"
    assert headings(text) == (HeadingLine(1, "Out", 6),)


def test_crlf_text_keeps_its_line_numbers():
    assert headings("## A\r\nx\r\n## B\r\n") == (HeadingLine(2, "A", 1), HeadingLine(2, "B", 3))


def test_a_bom_and_a_last_line_heading():  # Review Focus 3
    assert headings("\ufeff# Title\nx\n## End") == (HeadingLine(1, "Title", 1), HeadingLine(2, "End", 3))


def test_links_of_a_flat_list():  # ports test_detect_nav.py::TestParseSidebarMd::test_flat_sidebar
    assert links("- [Home](index.md)\n- [Guide](guide.md)\n- [API](api.md)\n") == (
        Link("Home", "index.md", 0), Link("Guide", "guide.md", 0), Link("API", "api.md", 0))


def test_links_nest_by_list_depth():  # ports test_nested_sidebar
    text = "- [Introduction](intro.md)\n  - [Install](install.md)\n  - [Config](config.md)\n- [Advanced](advanced.md)\n"
    assert links(text) == (Link("Introduction", "intro.md", 0), Link("Install", "install.md", 1),
                           Link("Config", "config.md", 1), Link("Advanced", "advanced.md", 0))


def test_links_only_come_from_lists_and_an_empty_target_is_none():
    text = "[Outside](out.md)\n\n- [Draft]()\n- [In](in.md)\n1. [Numbered](n.md)\n"
    assert links(text) == (Link("Draft", None, 0), Link("In", "in.md", 0), Link("Numbered", "n.md", 0))


def test_link_title_is_plain_text_and_target_is_unescaped():
    assert links("- [The `DataFrame` type](<my file.md>)\n") == (Link("The DataFrame type", "my file.md", 0),)


def test_every_link_of_a_list_item_is_returned():
    assert links("- [A](a.md) and [B](b.md)\n") == (Link("A", "a.md", 0), Link("B", "b.md", 0))


def test_a_leading_bom_does_not_hide_the_first_list():  # Review Focus 3
    assert links("\ufeff- [A](a.md)\n") == (Link("A", "a.md", 0),)


def test_slug():  # moved from test_filemeta.py
    assert slug("Window Functions & `over()`") == "window-functions-over"
    assert slug("  --  ") == ""


def test_filemeta_re_exports_the_one_slug():  # CMP-5
    from hiivmind_corpus_lib import filemeta, markdown

    assert filemeta.slug is markdown.slug
