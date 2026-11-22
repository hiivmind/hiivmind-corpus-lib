"""Index operations over one atomic save (spec 7.3, IDX-1..10, PKG-9..11)."""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from support import FIXED, open_corpus

from hiivmind_corpus_lib import store
from hiivmind_corpus_lib.config import Config
from hiivmind_corpus_lib.errors import NoSuchEntry, WriteFailed
from hiivmind_corpus_lib.index import AssignResult, Entry, Index, IndexMeta, MergeResult, ScanBatch, SetResult, Skip
from hiivmind_corpus_lib.schema import NULL

DOCS = ".source/polars/docs/source"
OLD = FIXED.replace(year=2026, month=11, day=19, hour=10)


def stale_entry(id: str, source: str = "polars", **fields) -> Entry:
    path = id.split(":", 1)[1]
    return Entry(**{"id": id, "source": source, "path": path, "title": path, "summary": "old", "stale": True,
                    "stale_since": OLD, "links_to": ("polars:z.md",), "concepts": ("c",),
                    "frontmatter": {"k": "v"}, **fields})


def write_files(corpus, names, body="# Heading One\n\ntext\n"):
    root = corpus.path / DOCS
    root.mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / name).write_text(body, encoding="utf-8")


def put_index(corpus, entries, meta=IndexMeta(generated_at=OLD)):
    corpus.path.joinpath("index.yaml").write_text(Index(meta=meta, entries=tuple(entries)).dumps(), encoding="utf-8")


def scanned(path, **fields):
    return {"path": path, "title": f"T {path}", "summary": f"S {path}", "tags": ["t"], "keywords": ["k"],
            "category": "guide", **fields}


def entry_of(corpus, id):
    return next(e for e in corpus.index.load().entries if e.id == id)


@pytest.fixture
def many(tmp_path):
    corpus = open_corpus(tmp_path)
    config = corpus.config.load()
    git = config.sources[0]
    entries = [stale_entry(f"polars:a{n:02}.md") for n in range(40)]
    entries += [stale_entry(f"polars:sec{n}.md", tier="section", parent="polars:a00.md") for n in range(3)]
    entries += [stale_entry(f"other:b{n:02}.md", source="other") for n in range(22)]
    entries.append(replace(stale_entry("polars:fresh.md"), stale=False))
    put_index(corpus, entries)
    return corpus


# --- batches and ids -------------------------------------------------------------------------------------------------

def test_stale_batches_are_at_most_size_files_of_one_source_in_index_order(many):
    batches = many.index.stale_batches(size=30)
    assert [(b.source, len(b.files)) for b in batches] == [("polars", 30), ("polars", 10), ("other", 22)]
    assert batches[0] == ScanBatch("polars", tuple(f"a{n:02}.md" for n in range(30)))
    assert all(not f.startswith("sec") for b in batches for f in b.files)
    assert [len(b.files) for b in many.index.stale_batches(size=30)] == [30, 10, 22]


def test_nothing_stale_is_no_batch(tmp_path):
    corpus = open_corpus(tmp_path)
    assert corpus.index.stale_batches() == ()


def test_stale_ids_lists_the_stale_file_entries(many):
    ids = many.index.stale_ids()
    assert len(ids) == 62 and ids[0] == "polars:a00.md" and "polars:sec0.md" not in ids and "polars:fresh.md" not in ids


# --- setters ---------------------------------------------------------------------------------------------------------

def test_set_summary(tmp_path):
    corpus = open_corpus(tmp_path)
    assert corpus.index.set_summary("polars:a.md", "Verified.") == SetResult(ok=True)
    index = corpus.index.load()
    assert index.meta.generated_at == FIXED
    assert entry_of(corpus, "polars:a.md").summary == "Verified."
    assert "Verified." in (corpus.path / "index.md").read_text(encoding="utf-8")
    assert "Generated: 2026-11-20T09:00:00Z" in (corpus.path / "index.md").read_text(encoding="utf-8")


def test_set_summary_of_an_unknown_id_raises(tmp_path):
    corpus = open_corpus(tmp_path)
    before = (corpus.path / "index.yaml").read_bytes()
    with pytest.raises(NoSuchEntry) as err:
        corpus.index.set_summary("polars:nope.md", "x")
    assert err.value.code == "unknown-entry" and str(err.value) == "index.yaml has no entry `polars:nope.md`"
    assert (corpus.path / "index.yaml").read_bytes() == before


def test_set_concepts_changes_only_that_field_and_leaves_out_an_unknown_id(tmp_path):
    corpus = open_corpus(tmp_path)
    before = corpus.index.load()
    result = corpus.index.set_concepts({"polars:a.md": ["lazy"], "polars:nope.md": ["x"]})
    assert result == AssignResult(assigned=("polars:a.md",))
    after = corpus.index.load()
    assert entry_of(corpus, "polars:a.md") == replace(before.entries[0], concepts=("lazy",))
    assert after.entries[1:] == before.entries[1:]
    mtime = os.stat(corpus.path / "index.yaml").st_mtime_ns
    assert corpus.index.set_concepts({"polars:nope.md": ["x"]}) == AssignResult(assigned=())
    assert os.stat(corpus.path / "index.yaml").st_mtime_ns == mtime


# --- merge_scans -----------------------------------------------------------------------------------------------------

def test_merge_scans_takes_six_fields_and_fills_four_from_the_file(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md", content_type="x", size="x", grep_hint="x")])
    write_files(corpus, ["a.md"], "# Alpha\n\n## Beta\n")
    scan = scanned("a.md", size="huge", links_to=["polars:q.md"], id="polars:other")
    result = corpus.index.merge_scans([{"entries": [scan]}], [])
    assert result == MergeResult(enriched=("polars:a.md",), skipped=())
    e = entry_of(corpus, "polars:a.md")
    assert (e.title, e.summary, e.tags, e.keywords, e.category) == ("T a.md", "S a.md", ("t",), ("k",), "guide")
    assert (e.content_type, e.size, e.grep_hint) == ("markdown", "standard", NULL)
    assert [h.title for h in e.headings] == ["Alpha", "Beta"]
    assert (e.id, e.source, e.links_to, e.links_from, e.concepts, e.frontmatter) == (
        "polars:a.md", "polars", ("polars:z.md",), None, ("c",), {"k": "v"})
    assert e.stale is False and e.stale_since is NULL and e.last_indexed == FIXED
    assert corpus.index.load().meta.generated_at == FIXED


def test_merge_pairs_done_scans_around_a_failed_batch(many):
    write_files(many, [f"a{n:02}.md" for n in range(40)])
    (many.path / ".source" / "other").mkdir(parents=True, exist_ok=True)
    first, middle, last = many.index.stale_batches()
    failures = [{"item": {"source": middle.source, "files": list(middle.files)}, "outcome": "failed", "reason": "no_exit"}]
    scans = [{"entries": [scanned(f) for f in first.files]}]
    # the last batch is of source `other`, whose files are absent: unreadable
    scans.append({"entries": [scanned(f) for f in last.files]})
    r = many.index.merge_scans(scans, failures)
    assert r.enriched == tuple(f"polars:{f}" for f in first.files)
    assert {s for s in r.skipped if s.code == "batch-failed"} == {Skip(f"polars:{f}", "batch-failed", "no_exit") for f in middle.files}
    assert {s.code for s in r.skipped if s.code != "batch-failed"} == {"file-unreadable"}
    assert entry_of(many, "polars:a35.md").stale is True and entry_of(many, "polars:a05.md").summary == "S a05.md"


def test_merge_with_every_batch_failed_skips_every_entry(many):
    failures = [{"item": {"source": b.source, "files": list(b.files)}, "outcome": "invalid_output", "reason": None}
                for b in many.index.stale_batches()]
    r = many.index.merge_scans([], failures)
    assert r.enriched == () and len(r.skipped) == 62
    assert {(s.code, s.reason) for s in r.skipped} == {("batch-failed", "invalid_output")}


def test_not_indexed_and_no_scan_and_unrequested_and_first_entry_wins(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md"), stale_entry("polars:b.md")])
    write_files(corpus, ["a.md", "b.md", "c.md"])
    # one batch of [a, b]; the scan returns a twice and c (not asked for); a failure for a file the index lacks
    first = scanned("a.md", title="first")
    second = scanned("a.md", title="second")
    r = corpus.index.merge_scans([{"entries": [first, second, scanned("c.md")]}],
                                 [{"item": {"source": "polars", "files": ["ghost.md"]}, "outcome": "failed", "reason": "x"}])
    assert r.enriched == ("polars:a.md",)
    assert Skip("polars:b.md", "no-scan", "no scan returned for it (file unreadable or not in the source)") in r.skipped
    assert entry_of(corpus, "polars:a.md").title == "first"
    assert entry_of(corpus, "polars:b.md").stale is True


def test_a_failed_batch_of_a_file_the_index_lacks_is_not_indexed(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md")])
    write_files(corpus, ["a.md"])
    r = corpus.index.merge_scans([{"entries": [scanned("a.md")]}], [
        {"item": {"source": "polars", "files": ["ghost.md"]}, "outcome": "failed", "reason": "x"}])
    assert r.enriched == ("polars:a.md",)
    assert r.skipped == (Skip("polars:ghost.md", "not-indexed", "no entry in the index"),)


def test_an_entry_without_path_is_found_by_rel_path_and_given_its_path(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [replace(stale_entry("polars:a.md"), path=None)])
    write_files(corpus, ["a.md"])
    assert corpus.index.stale_batches() == (ScanBatch("polars", ("a.md",)),)
    r = corpus.index.merge_scans([{"entries": [scanned("a.md")]}], [])
    assert r.enriched == ("polars:a.md",) and entry_of(corpus, "polars:a.md").path == "a.md"


def test_a_url_only_entry_is_skipped_file_unreadable_and_stays_stale(tmp_path):
    corpus = open_corpus(tmp_path)
    config = Config.loads((corpus.path / "config.yaml").read_text(encoding="utf-8"))
    web = Config.loads(
        "sources:\n  - id: live\n    type: web\n    fetch_mode: live\n    base_url: https://example.com/docs\n").sources[0]
    store.save(corpus, config=replace(config, sources=config.sources + (web,)))
    put_index(corpus, [stale_entry("live:x.md", source="live"), stale_entry("polars:gone.md")])
    r = corpus.index.merge_scans([{"entries": [scanned("x.md")]}, {"entries": [scanned("gone.md")]}], [])
    assert r.enriched == ()
    assert {(s.id, s.code) for s in r.skipped} == {("live:x.md", "file-unreadable"), ("polars:gone.md", "file-unreadable")}
    assert all(e.stale is True for e in corpus.index.load().entries)


def test_a_merge_writes_index_and_markdown_together_and_a_failure_restores_both(tmp_path, monkeypatch):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md")])
    store.save(corpus, index=corpus.index.load())
    write_files(corpus, ["a.md"])
    before = {n: (corpus.path / n).read_bytes() for n in ("index.yaml", "index.md")}
    from hiivmind_corpus_lib import files

    real, calls = os.replace, []

    def flaky(src, dst):
        calls.append(dst)
        if len(calls) == 2:
            raise OSError("disk full")
        return real(src, dst)

    monkeypatch.setattr(files.os, "replace", flaky)
    with pytest.raises(WriteFailed):
        corpus.index.merge_scans([{"entries": [scanned("a.md")]}], [])
    assert {n: (corpus.path / n).read_bytes() for n in before} == before


def test_nothing_enriched_writes_nothing(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md")])
    before = {n: os.stat(corpus.path / n).st_mtime_ns for n in ("index.yaml", "index.md", "config.yaml")}
    r = corpus.index.merge_scans([], [])
    assert r == MergeResult(enriched=(), skipped=())
    r = corpus.index.merge_scans([{"entries": []}], [])
    assert r.skipped[0].code == "no-scan"
    assert {n: os.stat(corpus.path / n).st_mtime_ns for n in before} == before


def test_an_index_without_meta_gains_it_on_write(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md", summary="x"), stale_entry("polars:b.md", stale=False)], meta=None)
    assert corpus.index.load().meta is None
    corpus.index.set_summary("polars:a.md", "new")
    meta = corpus.index.load().meta
    assert meta.generated_at == FIXED and meta.entry_count == 2


def test_every_stamp_comes_from_the_clock(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [stale_entry("polars:a.md"), stale_entry("polars:b.md")])
    write_files(corpus, ["a.md"])
    corpus.index.merge_scans([{"entries": [scanned("a.md")]}], [])
    corpus.index.set_summary("polars:b.md", "s")
    corpus.index.set_concepts({"polars:b.md": ["q"]})
    text = (corpus.path / "index.yaml").read_text(encoding="utf-8") + (corpus.path / "config.yaml").read_text(encoding="utf-8")
    import re

    stamps = set(re.findall(r'"(\d{4}-\d\d-\d\dT[\d:]+Z)"', text))
    assert "2026-11-20T09:00:00Z" in stamps
    index = corpus.index.load()
    assert index.meta.generated_at == FIXED
    assert entry_of(corpus, "polars:a.md").last_indexed == FIXED
    assert entry_of(corpus, "polars:b.md").stale_since == OLD  # unchanged: not rescanned


# --- store.save ------------------------------------------------------------------------------------------------------

def test_save_removes_stale_sub_indexes_when_tiered(tmp_path):
    corpus = open_corpus(tmp_path)
    (corpus.path / "index-old.md").write_text("x", encoding="utf-8")
    assert store.save(corpus, index=corpus.index.load()) == ()          # single strategy: nothing stale
    config = corpus.config.load()
    from hiivmind_corpus_lib.config import Render, RenderSection

    tiered = replace(config, render=Render(strategy="tiered", sections=(RenderSection(id="new"),)))
    changed = store.save(corpus, config=tiered)
    assert "index-old.md" in changed and "index-new.md" in changed and not (corpus.path / "index-old.md").exists()
    assert "config.yaml" in changed


def test_save_writes_a_removal_and_a_graph(tmp_path):
    corpus = open_corpus(tmp_path)
    (corpus.path / "extra.txt").write_text("x", encoding="utf-8")
    graph = Path(corpus.path / "graph.yaml").read_text(encoding="utf-8")
    from hiivmind_corpus_lib.graph import Graph

    changed = store.save(corpus, graph=Graph.loads(graph), removes=("extra.txt",))
    assert changed == ("extra.txt",) and not (corpus.path / "extra.txt").exists()


def test_save_gives_a_meta_less_index_its_meta(tmp_path):
    corpus = open_corpus(tmp_path)
    entries = corpus.index.load().entries
    store.save(corpus, index=Index(entries=entries))
    meta = corpus.index.load().meta
    assert meta is not None and meta.entry_count == len(entries) and meta.generated_at is None
    assert "Generated: unknown" in (corpus.path / "index.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("section_first", [True, False])
def test_merge_scan_lands_on_the_file_entry_never_a_section(tmp_path, section_first):
    corpus = open_corpus(tmp_path)
    section = stale_entry("polars:a.md#s", tier="section", parent="polars:a.md", path="a.md", title="Sec", summary="sec")
    parent = stale_entry("polars:a.md")
    put_index(corpus, [section, parent] if section_first else [parent, section])
    write_files(corpus, ["a.md"])
    assert corpus.index.merge_scans([{"entries": [scanned("a.md")]}], []).enriched == ("polars:a.md",)
    assert entry_of(corpus, "polars:a.md").summary == "S a.md"
    assert entry_of(corpus, "polars:a.md#s").summary == "sec" and entry_of(corpus, "polars:a.md#s").title == "Sec"
