"""`corpus.previews`: the first words of each entry's text, with a token estimate (spec 7.8, PRV-1/2)."""

import math
from dataclasses import replace

import pytest

from hiivmind_corpus_lib.previews import Preview
from hiivmind_corpus_lib.store import save
from support import open_corpus, write_tree


@pytest.fixture
def corpus(tmp_path):
    return open_corpus(tmp_path)


def _source_root(corpus):
    return corpus.sources.locate(corpus.index.load().entries[0]).file.parent


def _put(corpus, name, text):
    path = corpus.sources.locate(corpus.index.load().find("polars", name)).file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_a_preview_of_a_long_file_is_384_words_and_500_tokens(corpus):
    words = [f"w{n}" for n in range(1000)]
    _put(corpus, "a.md", "\n\n".join(words))
    entry = corpus.index.load().find("polars", "a.md")
    [preview] = corpus.previews.of(["polars:a.md"], token_limit=500)
    assert preview == Preview(entry_id="polars:a.md", title=entry.title, summary=entry.summary, source_path="a.md",
                              content_preview=" ".join(words[:384]), estimated_tokens=500)
    assert preview.estimated_tokens == math.ceil(384 * 1.3)
    _put(corpus, "b.md", "a short\n\ntext")
    [short] = corpus.previews.of(["polars:b.md"])
    assert short.content_preview == "a short\n\ntext" and short.estimated_tokens == math.ceil(3 * 1.3)


def test_an_entry_whose_file_cannot_be_read_has_no_preview(corpus):
    index = corpus.index.load()
    for name in ("a.md", "b.md"):
        corpus.sources.locate(index.find("polars", name)).file.unlink(missing_ok=True)
    previews = corpus.previews.of(["polars:b.md", "polars:a.md"])
    assert [p.entry_id for p in previews] == [e.id for e in index.entries if e.id in {"polars:a.md", "polars:b.md"}]
    assert all(p.content_preview is None and p.estimated_tokens == 0 for p in previews)


def test_section_entries_are_skipped_unknown_ids_left_out_and_index_order_kept(corpus):
    index = corpus.index.load()
    section = replace(index.entries[0], id="polars:a.md#s", tier="section", parent="polars:a.md")
    save(corpus, index=replace(index, entries=(*index.entries, section)))
    for name in ("a.md", "b.md"):
        _put(corpus, name, "text")
    previews = corpus.previews.of(["polars:b.md", "nope", "polars:a.md#s", "polars:a.md"])
    assert [p.entry_id for p in previews] == ["polars:a.md", "polars:b.md"]


def _with_web(tmp_path, source):
    import yaml

    corpus = open_corpus(tmp_path)
    data = yaml.safe_load((corpus.path / "config.yaml").read_text(encoding="utf-8"))
    data["sources"].append(source)
    (corpus.path / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    index = corpus.index.load()
    entry = replace(index.entries[0], id="web:x.md", source="web", path="x.md", title="X", summary="Sx")
    save(corpus, index=replace(index, entries=(*index.entries, entry)))
    return corpus, entry


def test_an_entry_that_locates_to_a_url_takes_the_text_it_is_given(tmp_path):
    corpus, entry = _with_web(tmp_path, {"id": "web", "type": "web", "fetch_mode": "live", "base_url": "https://example.com/"})
    location = corpus.sources.locate(entry)
    assert location.file is None and location.url
    [bare] = corpus.previews.of(["web:x.md"])
    assert bare.content_preview is None and bare.estimated_tokens == 0
    [given] = corpus.previews.of(["web:x.md"], texts={"web:x.md": "fetched words here"})
    assert given.content_preview == "fetched words here" and given.estimated_tokens == math.ceil(3 * 1.3)


def test_an_entry_with_file_and_url_reads_the_file_and_falls_back_to_the_text(tmp_path):
    corpus, entry = _with_web(tmp_path, {"id": "web", "type": "web", "cache_dir": "cache/web",
                                         "urls": [{"url": "https://example.com/x", "cached_file": "x.md"}]})
    location = corpus.sources.locate(entry)
    assert location.file is not None and location.url
    texts = {"web:x.md": "fetched"}
    [fallback] = corpus.previews.of(["web:x.md"], texts=texts)
    assert fallback.content_preview == "fetched"
    write_tree(corpus.path, {"cache/web/x.md": "on disk"})
    [read] = corpus.previews.of(["web:x.md"], texts=texts)
    assert read.content_preview == "on disk"
