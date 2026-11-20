"""The sources capability (spec 7.5, SRC-9..17, E4): locate, freshness, apply_update, drop_missing."""

import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from support import FIXED, open_corpus

from hiivmind_corpus.config import Build, Config, IndexInfo, Render
from hiivmind_corpus.errors import NoSuchSource
from hiivmind_corpus.graph import Graph
from hiivmind_corpus.index import Entry, Index, IndexMeta
from hiivmind_corpus.schema import NULL
from hiivmind_corpus.sources import (
    SOURCE_KINDS,
    Change,
    Changes,
    DropResult,
    Freshness,
    Head,
    Listing,
    Location,
    ManifestHash,
    Snapshot,
    SourceStatus,
    Unobserved,
    UpdateResult,
)

OLD = datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
RIGHT = "5eaa000000000000000000000000000000000000"
NEW = "43d7572" + "0" * 33


def put_index(corpus, entries, meta=IndexMeta(generated_at=OLD)):
    corpus.path.joinpath("index.yaml").write_text(Index(meta=meta, entries=tuple(entries)).dumps(), encoding="utf-8")


def put_config(corpus, **changes):
    config = replace(corpus.config.load(), **changes)
    corpus.path.joinpath("config.yaml").write_text(config.dumps(), encoding="utf-8")
    return config


def fresh(id, source="polars", **fields) -> Entry:
    return Entry(**{"id": id, "source": source, "path": id.split(":", 1)[1], "title": id, "summary": "kept",
                    "tags": ("t",), "keywords": ("k",), "concepts": ("c",), "category": "guide", "stale": False,
                    "stale_since": NULL, "last_indexed": OLD, **fields})


def entries(corpus):
    return {e.id: e for e in corpus.index.load().entries}


def snapshot(corpus):
    return {p.name: p.read_bytes() for p in corpus.path.iterdir() if p.is_file()}


def changes(*items, outside=0):
    return Changes(tuple(Change(s, p) for s, p in items), outside)


@pytest.fixture
def corpus(tmp_path):
    corpus = open_corpus(tmp_path)
    put_index(corpus, [fresh("polars:user-guide/a.md"), fresh("polars:gone.md"), fresh("polars:keep.md")])
    return corpus


# --- locate, kinds, freshness ----------------------------------------------------------------------------------------

def test_locate(corpus):
    entry = fresh("polars:a.md")
    assert corpus.sources.locate(entry) == Location(corpus.path / ".source/polars/docs/source/a.md", None)
    assert corpus.sources.locate(replace(entry, source="nope")) == Location(None, None)
    assert corpus.sources.locate(replace(entry, source="")) == Location(None, None)


def test_kinds(corpus):
    assert corpus.sources.kinds == ("git", "generated-docs", "obsidian", "self", "local", "web", "llms-txt")


def test_freshness_examples(corpus):
    assert corpus.sources.freshness({"polars": Head(RIGHT)}) == (
        SourceStatus(id="polars", type="git", freshness="current", error=None),)
    assert corpus.sources.freshness({"polars": Head(NEW)})[0].freshness == Freshness.BEHIND
    failed = corpus.sources.freshness({"polars": Unobserved("git ls-remote failed")})
    assert failed == (SourceStatus("polars", "git", Freshness.UNKNOWN, "source `polars`: git ls-remote failed"),)
    missing = corpus.sources.freshness({})
    assert missing == (SourceStatus("polars", "git", Freshness.UNKNOWN,
                                    "source `polars`: no observation of its upstream was handed in"),)


def test_freshness_of_an_unrecognised_source_and_config_order(corpus):
    raw = corpus.path.joinpath("config.yaml").read_text()
    corpus.path.joinpath("config.yaml").write_text(raw.replace("index:\n", "  - id: at\n    type: github\nindex:\n", 1))
    statuses = corpus.sources.freshness({"polars": Head(RIGHT)})
    assert [s.id for s in statuses] == ["polars", "at"]
    assert statuses[1] == SourceStatus("at", "github", Freshness.UNKNOWN, "source type `github` is not a known kind")


# --- apply_update ----------------------------------------------------------------------------------------------------

def test_apply_update_example(corpus):
    before = snapshot(corpus)
    result = corpus.sources.apply_update(
        "polars", changes(("M", "user-guide/a.md"), ("A", "new.md"), ("D", "gone.md")), Head(NEW))
    assert result == UpdateResult(files_changed=3, added=1, modified=1, removed=1, removed_ids=("polars:gone.md",),
                                  stale_entries=("polars:user-guide/a.md", "polars:new.md"), excluded=(),
                                  outside_docs_root=0)
    found = entries(corpus)
    assert "polars:gone.md" not in found
    assert found["polars:user-guide/a.md"] == replace(fresh("polars:user-guide/a.md"), stale=True, stale_since=FIXED)
    new = found["polars:new.md"]
    assert (new.summary, new.category, new.stale, new.stale_since) == ("Pending re-scan", "unknown", True, FIXED)
    assert (new.tags, new.keywords, new.concepts, new.section, new.path) == ((), (), (), None, "new.md")
    old = Config.loads(before["config.yaml"].decode())
    now = corpus.config.load()
    assert now == replace(old, sources=(replace(old.sources[0], last_commit_sha=NEW, last_indexed_at=FIXED),),
                          index=replace(old.index, last_updated_at=FIXED))
    assert corpus.index.load().meta.generated_at == FIXED
    page = corpus.path.joinpath("index.md").read_text()
    assert "polars:new.md" in page and "polars:gone.md" not in page


def test_a_call_that_changes_nothing_writes_nothing(corpus):
    corpus.sources.apply_update("polars", Changes(), Head(NEW))
    before = snapshot(corpus)
    stamps = {n: os.stat(corpus.path / n).st_mtime_ns for n in before}
    result = corpus.sources.apply_update("polars", Changes(), Head(NEW))
    assert result == UpdateResult(0, 0, 0, 0, (), (), (), 0)
    assert snapshot(corpus) == before
    assert {n: os.stat(corpus.path / n).st_mtime_ns for n in before} == stamps


@pytest.mark.parametrize("raw,observation", [
    ({"type": "git", "repo_url": "https://x/y", "last_commit_sha": "1"}, Head("2")),
    ({"type": "generated-docs", "source_repo": {"url": "u", "last_commit_sha": "1"}}, Head("2")),
    ({"type": "obsidian", "repo_url": "https://x/y", "last_commit_sha": "1"}, Head("2")),
    ({"type": "obsidian", "vault_path": "/v"}, Snapshot({"a.md": FIXED})),
    ({"type": "self", "docs_root": "docs"}, Unobserved("none")),
    ({"type": "local"}, Snapshot({"a.md": FIXED})),
    ({"type": "web", "cache_dir": ".cache/w", "urls": []}, Snapshot({"a.md": FIXED})),
    ({"type": "llms-txt", "manifest": {"url": "u", "last_hash": "1"}}, ManifestHash("2")),
])
def test_apply_update_through_each_kind(corpus, raw, observation):
    source = SOURCE_KINDS[raw["type"]].parse({"id": "polars", **raw})
    config = put_config(corpus, sources=(source,))
    corpus.sources.apply_update("polars", Changes(), observation)
    expected = SOURCE_KINDS[source.type].recorded(source, observation, FIXED)
    assert corpus.config.load().sources == (expected,)
    assert expected != source
    assert corpus.config.load().index.last_updated_at == FIXED
    assert corpus.config.load() == replace(config, sources=(expected,), index=replace(config.index, last_updated_at=FIXED))


def test_a_path_the_build_skips_is_excluded(corpus):
    put_config(corpus, build=Build(skip_sections=("drafts",)))
    result = corpus.sources.apply_update("polars", changes(("A", "drafts/e.md"), ("A", "a/drafts/f.md")), Head(NEW))
    assert result.excluded == ("drafts/e.md", "a/drafts/f.md")
    assert (result.added, result.stale_entries, result.files_changed) == (0, (), 2)
    assert set(entries(corpus)) == {"polars:user-guide/a.md", "polars:gone.md", "polars:keep.md"}


@pytest.mark.parametrize("organization,strategy,section", [
    ("by-source", "tiered", "polars"), ("by-source", "single", None), ("by-topic", "tiered", None), (None, "tiered", None)])
def test_organization_by_source_in_a_tiered_corpus_sets_section(corpus, organization, strategy, section):
    put_config(corpus, build=Build(organization=organization), render=Render(strategy=strategy))
    corpus.sources.apply_update("polars", changes(("A", "new.md")), Head(NEW))
    assert entries(corpus)["polars:new.md"].section == section


def tiered(corpus):
    put_index(corpus, [fresh("docs:g.md", "docs"), fresh("docs:g.md#s1", "docs", path="g.md", tier="section", parent="docs:g.md"),
                       fresh("docs:g.md#s2", "docs", path="g.md", tier="section", parent="docs:g.md"),
                       fresh("docs:o.md", "docs")])


def test_tiered_children(tmp_path):
    corpus = open_corpus(tmp_path)
    config = corpus.config.load()
    put_config(corpus, sources=(replace(config.sources[0], id="docs"),))
    tiered(corpus)
    gone = corpus.sources.apply_update("docs", changes(("D", "g.md")), Head(NEW))
    assert gone.removed == 1 and gone.removed_ids == ("docs:g.md",)
    assert set(entries(corpus)) == {"docs:o.md"}

    tiered(corpus)
    modified = corpus.sources.apply_update("docs", changes(("M", "g.md")), Head(NEW))
    assert modified.modified == 1 and modified.stale_entries == ("docs:g.md",)
    found = entries(corpus)
    assert [found[i].stale for i in ("docs:g.md", "docs:g.md#s1", "docs:g.md#s2", "docs:o.md")] == [True, True, True, False]

    tiered(corpus)
    added = corpus.sources.apply_update("docs", changes(("A", "g.md")), Head(NEW))
    assert (added.added, added.modified, added.stale_entries) == (0, 1, ("docs:g.md",))
    assert entries(corpus)["docs:g.md#s1"].stale is True


def test_a_path_added_twice_adds_once_and_a_delete_of_an_unknown_path_counts_nothing(corpus):
    result = corpus.sources.apply_update(
        "polars", changes(("A", "n.md"), ("A", "n.md"), ("D", "never.md")), Head(NEW))
    assert (result.added, result.removed, result.removed_ids, result.stale_entries) == (1, 0, (), ("polars:n.md",))
    assert len([i for i in entries(corpus) if i == "polars:n.md"]) == 1


def test_outside_docs_root_is_carried(corpus):
    assert corpus.sources.apply_update("polars", changes(("M", "keep.md"), outside=4), Head(NEW)).outside_docs_root == 4


def graph_text(schema, ids=("polars:gone.md", "polars:keep.md")):
    entries = "".join(f"      - {i}\n" for i in ids)
    return (f"schema_version: {schema}\nconcepts:\n  c:\n    label: C\n    entries:\n{entries}    entry_count: {len(ids)}\n")


def test_the_graph_is_cleaned(corpus):
    path = corpus.path / "graph.yaml"
    path.write_text(graph_text(1))
    corpus.sources.apply_update("polars", changes(("D", "gone.md")), Head(NEW))
    assert Graph.loads(path.read_text()).concepts["c"].entries == ("polars:keep.md",)

    path.write_text(graph_text(2))
    os.utime(path, ns=(10**18, 10**18))
    put_index(corpus, [fresh("polars:gone.md")])
    corpus.sources.apply_update("polars", changes(("D", "gone.md")), Head(NEW))
    assert path.read_text() == graph_text(2) and path.stat().st_mtime_ns == 10**18


def test_apply_update_to_an_unknown_source_raises(corpus):
    with pytest.raises(NoSuchSource, match="config.yaml has no source `nope`") as error:
        corpus.sources.apply_update("nope", changes(("M", "a.md")), Head(NEW))
    assert error.value.code == "unknown-source"


def test_an_update_creates_the_index_block_when_the_config_has_none(corpus):
    put_config(corpus, index=None)
    corpus.sources.apply_update("polars", changes(("M", "keep.md")), Head(NEW))
    assert corpus.config.load().index == IndexInfo(last_updated_at=FIXED)


# --- drop_missing ----------------------------------------------------------------------------------------------------

def listing(*paths, head=RIGHT, outside=0):
    return Listing(head, frozenset(paths), outside)


def test_drop_missing(corpus):
    put_index(corpus, [fresh("polars:old.md"), fresh("polars:a.md"), fresh("polars:a.md#s", path="a.md", tier="section", parent="polars:a.md")])
    corpus.path.joinpath("graph.yaml").write_text(graph_text(1, ("polars:old.md", "polars:a.md")))
    result = corpus.sources.drop_missing("polars", listing("a.md", outside=2))
    assert result == DropResult(removed_ids=("polars:old.md",), skipped=None, outside_docs_root=2)
    assert set(entries(corpus)) == {"polars:a.md", "polars:a.md#s"}
    assert Graph.loads(corpus.path.joinpath("graph.yaml").read_text()).concepts["c"].entries == ("polars:a.md",)
    assert "polars:old.md" not in corpus.path.joinpath("index.md").read_text()
    assert corpus.index.load().meta.generated_at == FIXED


def test_drop_missing_can_remove_every_entry_and_a_section_goes_with_its_file(corpus):
    put_index(corpus, [fresh("polars:a.md"), fresh("polars:a.md#s", path="a.md", tier="section", parent="polars:a.md")])
    result = corpus.sources.drop_missing("polars", listing("other.md"))
    assert result.removed_ids == ("polars:a.md",)
    assert corpus.index.load().entries == ()


@pytest.mark.parametrize("head", [NEW, RIGHT[:7]])
def test_drop_missing_skips_a_listing_of_another_commit(corpus, head):
    before = snapshot(corpus)
    assert corpus.sources.drop_missing("polars", listing("keep.md", head=head)) == DropResult((), "head-mismatch", 0)
    assert snapshot(corpus) == before


def test_drop_missing_skips_an_empty_listing(corpus):
    before = snapshot(corpus)
    assert corpus.sources.drop_missing("polars", listing()).skipped == "empty-listing"
    assert snapshot(corpus) == before


def test_a_section_entry_is_never_removed_by_itself(corpus):
    put_index(corpus, [fresh("polars:a.md"), fresh("polars:a.md#s", path="zzz.md", tier="section", parent="polars:a.md")])
    result = corpus.sources.drop_missing("polars", listing("a.md"))
    assert result.removed_ids == () and len(corpus.index.load().entries) == 2


def test_nothing_removed_writes_nothing(corpus):
    before = snapshot(corpus)
    assert corpus.sources.drop_missing("polars", listing("user-guide/a.md", "gone.md", "keep.md")) == DropResult((), None, 0)
    assert snapshot(corpus) == before


def test_a_local_source_still_compares_paths(tmp_path):
    corpus = open_corpus(tmp_path)
    put_config(corpus, sources=(SOURCE_KINDS["local"].parse({"id": "polars", "type": "local"}),))
    result = corpus.sources.drop_missing("polars", listing("keep.md", head="anything"))
    assert result == DropResult(("polars:a.md", "polars:b.md", "polars:c.md"), None, 0)


def test_drop_missing_of_an_unknown_source_raises(corpus):
    with pytest.raises(NoSuchSource, match="config.yaml has no source `nope`"):
        corpus.sources.drop_missing("nope", listing("a.md"))
