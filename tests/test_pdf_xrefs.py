from hiivmind_corpus_lib.pdf import Chapter, CrossRef, cross_references, resolve

CHAPTERS = (Chapter(1, "Intro", 0, 20), Chapter(2, "Scopes", 20, 60), Chapter(3, "Advanced", 60, 80))
CHAPTER_REF = (r'Chapter (\d+), ["\u201c](.+?)["\u201d],? on page (\d+)', "chapter_reference")
SECTION_REF = (r"see the ([A-Z][A-Za-z ]+?) section on page (\d+)", "section_reference")
SEE_REF = (r"\(see ([^)]+?), page (\d+)\)", "see_reference")


def test_find_cross_references():                              # ports test_pdf_utils.py::test_find_cross_references
    text = "See Chapter 5, \u201cScopes of Macro Variables,\u201d on page 57."
    refs = cross_references(text, [CHAPTER_REF])
    assert len(refs) == 1
    assert refs[0].display_text == "Scopes of Macro Variables"
    assert refs[0].page == 57
    assert refs[0] == CrossRef('Chapter 5, \u201cScopes of Macro Variables,\u201d on page 57', "chapter_reference",
                               "Scopes of Macro Variables", 57)

def test_each_group_layout_and_the_order_of_the_patterns():
    text = 'For details see the Macro Basics section on page 12 and (see Appendix A, page 80). Also Chapter 3, "Advanced Use" on page 61.'
    assert cross_references(text, [SEE_REF, SECTION_REF, CHAPTER_REF]) == (       # pattern order, then text order
        CrossRef("(see Appendix A, page 80)", "see_reference", "Appendix A", 80),
        CrossRef("see the Macro Basics section on page 12", "section_reference", "Macro Basics", 12),
        CrossRef('Chapter 3, "Advanced Use" on page 61', "chapter_reference", "Advanced Use", 61))

def test_cross_references_none_and_patterns_without_the_groups_of_their_layout():
    assert cross_references("nothing to see", [CHAPTER_REF]) == ()
    assert cross_references("Chapter 3 is long", [(r"Chapter \d+", "chapter_reference")]) == ()     # no groups: skipped

def test_resolve_cross_ref():                                  # ports test_pdf_utils.py::test_resolve_cross_ref
    ref = CrossRef("see page 57", "section_reference", "Scopes", 57)
    result = resolve(ref, CHAPTERS, file_name="{index:02d}_{title}")
    assert result is not None
    assert "Scopes" in result
    assert result == "02_Scopes"

def test_resolve_finds_the_chapter_holding_the_one_based_page():
    page = lambda n: CrossRef("p", "see_reference", "d", n)
    assert [resolve(page(n), CHAPTERS) for n in (1, 20, 21, 60, 61, 80)] == [
        "01_Intro", "01_Intro", "02_Scopes", "02_Scopes", "03_Advanced", "03_Advanced"]
    assert [resolve(page(n), CHAPTERS) for n in (0, 81, None)] == [None, None, None]

def test_resolve_formats_the_file_name_with_the_safe_title():
    ref = CrossRef("p", "see_reference", "d", 57)
    assert resolve(ref, (Chapter(2, "Macro: Vars!", 20, 60),), file_name="{title}-{index}") == "Macro_Vars-2"
