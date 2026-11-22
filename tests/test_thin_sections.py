import pytest
from support import FIXED, open_corpus
from test_index_ops import put_index

from hiivmind_corpus_lib import store
from hiivmind_corpus_lib.index import Entry, Index, IndexMeta, Merge, ThinResult
from hiivmind_corpus_lib.thinning import thin

# 320 words = 416 tokens (the plugin's `* 30` is 78 tokens, under the 100 threshold, so it never exercised "stays")
BIG = "Method documentation content here " * 80


def sec(id, parent, level, line_range, summary="Short", keywords=(), source=None):
    return Entry(id=id, source=source or id.split(":")[0], tier="section", parent=parent, heading_level=level,
                 line_range=line_range, summary=summary, keywords=keywords, title=id)


def file(id, summary="API docs", keywords=None):
    return Entry(id=id, source=id.split(":")[0], tier="file", summary=summary, keywords=keywords, title=id)


def ix(*entries):
    return Index(meta=IndexMeta(), entries=entries)


def test_small_section_merges_into_its_nearest_earlier_sibling():
    index = ix(file("src:api.md"), sec("src:api.md#methods", "src:api.md", 2, (10, 50), BIG, ("methods",)),
               sec("src:api.md#params", "src:api.md", 2, (51, 55), "Short", ("params",)))
    thinned, result = thin(index, min_tokens=100)
    methods = next(e for e in thinned.entries if e.id == "src:api.md#methods")
    assert [e.id for e in thinned.entries] == ["src:api.md", "src:api.md#methods"]
    assert methods.keywords == ("methods", "params") and methods.line_range == (10, 55)
    assert methods.summary == BIG.strip() + " Short"
    assert result == ThinResult(2, 1, (Merge("src:api.md#params", "src:api.md#methods"),))


def test_with_no_earlier_sibling_it_merges_into_its_parent():
    index = ix(file("src:api.md", keywords=("api",)), sec("src:api.md#tiny", "src:api.md", 2, (10, 12), "Short", ("tiny",)))
    thinned, result = thin(index, min_tokens=100)
    parent = thinned.entries[0]
    assert parent.keywords == ("api", "tiny") and parent.summary == "API docs Short" and parent.line_range is None
    assert result.merges == (Merge("src:api.md#tiny", "src:api.md"),)


def test_the_nearest_earlier_sibling_wins_not_the_first():
    index = ix(file("src:a.md"), sec("src:a.md#s1", "src:a.md", 2, (1, 10), BIG), sec("src:a.md#s2", "src:a.md", 2, (11, 20), BIG),
               sec("src:a.md#s3", "src:a.md", 2, (21, 25)))
    assert thin(index, min_tokens=100)[1].merges == (Merge("src:a.md#s3", "src:a.md#s2"),)


def test_the_first_section_goes_to_the_parent_not_the_next_sibling():
    index = ix(file("src:a.md"), sec("src:a.md#s1", "src:a.md", 2, (1, 3)), sec("src:a.md#s2", "src:a.md", 2, (4, 40), BIG))
    assert thin(index, min_tokens=100)[1].merges == (Merge("src:a.md#s1", "src:a.md"),)


def test_a_section_over_min_tokens_stays_counting_summary_and_keywords():
    index = ix(file("src:a.md"), sec("src:a.md#s", "src:a.md", 2, (1, 3), "Short", ("k1", "k2")))
    assert thin(index, min_tokens=3)[1].merges == ()
    assert len(thin(index, min_tokens=5)[1].merges) == 1


def test_the_injected_counter_decides_the_size():
    index = ix(file("src:a.md"), sec("src:a.md#s", "src:a.md", 2, (1, 3), "Short"))
    assert thin(index, min_tokens=100, count=lambda text: 100)[1].merges == ()


def test_never_merges_across_sources():
    index = ix(file("src1:a.md"), sec("src1:a.md#small", "src1:a.md", 2, (1, 3)),
               file("src2:b.md", "B docs " * 30), sec("src2:b.md#big", "src2:b.md", 2, (1, 50), "Big section " * 80))
    thinned, result = thin(index, min_tokens=100)
    assert result.merges == (Merge("src1:a.md#small", "src1:a.md"),)
    assert next(e for e in thinned.entries if e.id == "src2:b.md").summary == "B docs " * 30


def test_a_section_whose_parent_is_in_another_source_stays():
    index = ix(file("src2:b.md"), sec("src1:a.md#orphan", "src2:b.md", 2, (1, 3), source="src1"))
    assert thin(index, min_tokens=100)[1].merges == ()


def test_a_section_with_children_never_merges():
    index = ix(file("src:api.md"), sec("src:api.md#parent", "src:api.md", 2, (10, 50)),
               sec("src:api.md#child", "src:api.md#parent", 3, (20, 50), "Child section " * 80))
    thinned, result = thin(index, min_tokens=100)
    assert "src:api.md#parent" in [e.id for e in thinned.entries] and result.merges == ()


def test_deepest_first_and_a_parent_stays_once_its_child_merged_into_it():
    index = ix(file("src:a.md"), sec("src:a.md#p", "src:a.md", 2, (1, 50), BIG),
               sec("src:a.md#c", "src:a.md#p", 3, (10, 12), "Short", ("c",)))
    thinned, result = thin(index, min_tokens=100)
    assert result.merges == (Merge("src:a.md#c", "src:a.md#p"),)
    assert [e.id for e in thinned.entries] == ["src:a.md", "src:a.md#p"]


def test_chain_merge_goes_to_the_surviving_sibling():
    index = ix(file("src:a.md", "A docs " * 80), sec("src:a.md#s1", "src:a.md", 2, (1, 50), "Big " * 80, ("s1",)),
               sec("src:a.md#s2", "src:a.md", 2, (51, 53), "Tiny", ("s2",)),
               sec("src:a.md#s3", "src:a.md", 2, (54, 56), "Also tiny", ("s3",)))
    thinned, result = thin(index, min_tokens=100)
    assert result.merges == (Merge("src:a.md#s2", "src:a.md#s1"), Merge("src:a.md#s3", "src:a.md#s1"))
    s1 = next(e for e in thinned.entries if e.id == "src:a.md#s1")
    assert s1.keywords == ("s1", "s2", "s3") and s1.line_range == (1, 56)


def test_keywords_deduplicate_keeping_first_occurrence():
    index = ix(file("src:a.md", keywords=("a", "b")), sec("src:a.md#s", "src:a.md", 2, (1, 2), "Short", ("b", "c", "c")))
    assert thin(index, min_tokens=100)[0].entries[0].keywords == ("a", "b", "c")


def test_no_sections_changes_nothing():
    index = ix(file("src:a.md"))
    assert thin(index, min_tokens=100) == (index, ThinResult(0, 0, ()))


def test_entries_are_not_mutated_and_the_input_index_is_unchanged():
    index = ix(file("src:a.md"), sec("src:a.md#s", "src:a.md", 2, (1, 3)))
    before = index
    thin(index, min_tokens=100)
    assert index == before and len(index.entries) == 2


@pytest.fixture
def corpus(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [file("polars:guide.md"),
                       sec("polars:guide.md#methods", "polars:guide.md", 2, (10, 50), BIG),
                       sec("polars:guide.md#params", "polars:guide.md", 2, (51, 55)),
                       sec("polars:guide.md#extra", "polars:guide.md", 2, (56, 60))])
    return corpus


def test_thin_sections_saves_through_store_save(corpus, monkeypatch):
    calls = []
    real = store.save
    monkeypatch.setattr(store, "save", lambda *a, **k: calls.append(k) or real(*a, **k))
    result = corpus.index.thin_sections(min_tokens=100)
    assert len(calls) == 1 and set(calls[0]) == {"index"}
    saved = corpus.index.load()
    assert [e.id for e in saved.entries] == ["polars:guide.md", "polars:guide.md#methods"]
    assert saved.meta.entry_count == 2 and saved.meta.generated_at == FIXED
    assert result == ThinResult(3, 1, (Merge("polars:guide.md#params", "polars:guide.md#methods"),
                                      Merge("polars:guide.md#extra", "polars:guide.md#methods")))


def test_dry_run_returns_the_same_result_and_writes_nothing(corpus, monkeypatch):
    before = {n: (corpus.path / n).read_bytes() for n in ("index.yaml", "index.md")}
    monkeypatch.setattr(store, "save", lambda *a, **k: pytest.fail("dry run wrote"))
    dry = corpus.index.thin_sections(min_tokens=100, dry_run=True)
    assert dry.sections_before == 3 and dry.sections_after == 1 and len(dry.merges) == 2
    assert {n: (corpus.path / n).read_bytes() for n in before} == before


def test_nothing_to_merge_writes_nothing(corpus, monkeypatch):
    monkeypatch.setattr(store, "save", lambda *a, **k: pytest.fail("wrote"))
    assert corpus.index.thin_sections(min_tokens=1).merges == ()


def test_default_min_tokens_is_300(corpus):
    assert corpus.index.thin_sections(dry_run=True).merges
