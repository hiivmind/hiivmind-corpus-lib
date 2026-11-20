"""`Entry` and `Index`: values, E2, E3, nullable markers (spec 7.3, 8, 11)."""

import dataclasses
from datetime import UTC, datetime

import pytest

from hiivmind_corpus.errors import InvalidFile
from hiivmind_corpus.schema import NULL
from hiivmind_corpus.index import Entry, Heading, Index, IndexMeta

from support import golden, open_corpus


def test_the_enriched_entry_loads_with_null_markers():            # CAN-13
    index = Index.loads(golden("index/single.yaml"))
    enriched, pending, big = index.entries
    assert enriched.stale_since is NULL and enriched.grep_hint is NULL
    assert enriched.last_indexed == datetime(2026, 11, 20, 9, 0, tzinfo=UTC)
    assert enriched.stale is False
    assert enriched.headings == (Heading(anchor="expressions", title="Expressions"),)
    assert pending.title is None and pending.last_indexed is None and pending.stale is True
    assert pending.stale_since == datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    assert big.grep_hint == "grep -n '^## ' big.md" and big.stale_since is None
    assert index.meta == IndexMeta(generated_at=datetime(2026, 11, 20, 9, 0, tzinfo=UTC), entry_count=3)


def test_the_tiered_golden_loads_sections():
    index = Index.loads(golden("index/tiered.yaml"))
    section = index.entries[1]
    assert (section.tier, section.parent, section.anchor, section.heading_level) == ("section", "docs:guide.md", "install", 2)
    assert section.line_range == (10, 42)
    assert index.entries[0].section == "guide"


def test_find_is_by_source_and_rel_path_and_ids_are_never_rebuilt():
    index = Index(entries=(
        Entry(id="midjourney:x", source="midjourney", path="docs/x.md"),
        Entry(id="polars:a.md", source="polars")))
    assert index.find("midjourney", "docs/x.md").id == "midjourney:x"
    assert index.find("polars", "a.md").id == "polars:a.md"
    assert index.find("midjourney", "x") is None
    assert index.find("other", "docs/x.md") is None


def test_rel_path_is_path_or_the_id_without_its_source_prefix():
    assert Entry(id="polars:user-guide/a.md", source="polars").rel_path == "user-guide/a.md"
    assert Entry(id="polars:user-guide/a.md", source="polars", path="p.md").rel_path == "p.md"
    assert Entry(id="a:b:c.md", source="a").rel_path == "b:c.md"
    assert Entry(id="odd", source="polars").rel_path == "odd"


def _entries(n, mutate=None):
    lines = ["entries:"]
    for i in range(n):
        lines += [f"  - id: polars:{i}.md", "    source: polars"]
        if mutate:
            lines += mutate(i)
    return "\n".join(lines) + "\n"


def test_an_entry_with_tags_5_names_the_place():                   # E2
    text = _entries(5, lambda i: ["    tags: 5"] if i == 3 else [])
    with pytest.raises(InvalidFile) as e:
        Index.loads(text)
    assert (e.value.code, e.value.file, e.value.where) == ("invalid-file", "index.yaml", "entries[3].tags")


def test_two_entries_with_one_id_is_invalid_file():                # E3
    ids = ["polars:a.md" if i in (3, 7) else f"polars:{i}.md" for i in range(9)]
    text = "entries:\n" + "".join(f"  - id: {x}\n    source: polars\n" for x in ids)
    with pytest.raises(InvalidFile) as e:
        Index.loads(text)
    assert e.value.where == "entries[7].id"
    assert "duplicate id `polars:a.md` (also entries[3])" in str(e.value)


def test_an_entry_needs_id_and_source():
    with pytest.raises(InvalidFile) as e:
        Index.loads("entries:\n  - id: a\n")
    assert e.value.where == "entries[0].source"


def test_dumps_derives_entry_count():
    text = golden("index/single.yaml").replace("entry_count: 3", "entry_count: 9")
    assert "entry_count: 3" in Index.loads(text).dumps()


def test_dumps_adds_no_meta_when_there_is_none():
    assert "meta" not in Index.loads(_entries(2)).dumps()


def test_drift_shapes_read_as_absent_and_strings():
    from support import GOLDEN
    root = GOLDEN.parent / "drift"
    no_path = Index.loads((root / "index-no-path.yaml").read_text())
    assert no_path.entries[0].path is None and no_path.entries[0].rel_path == "user-guide/a.md"
    assert Index.loads((root / "index-no-meta.yaml").read_text()).meta is None
    nulled = Index.loads((root / "index-headings-null.yaml").read_text()).entries[0]
    assert nulled.headings is None and nulled.tags is None and "headings" not in Index(entries=(nulled,)).dumps()
    assert Index.loads((root / "index-integer-keywords.yaml").read_text()).entries[0].keywords == ("pixels", "2048", "true")
    extra = Index.loads((root / "index-meta-corpus.yaml").read_text())
    assert dict(extra.meta.extra) == {"corpus": "polars", "source": "polars"} and dict(extra.extra)["stats"]["files"] == 1


def test_every_timestamp_form_reads_as_utc():
    from support import GOLDEN
    index = Index.loads((GOLDEN.parent / "drift" / "index-timestamps.yaml").read_text())
    a, b, c, d = index.entries
    assert a.last_indexed == datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    assert a.stale_since == datetime(2026, 11, 18, tzinfo=UTC)
    assert b.last_indexed == datetime(2026, 11, 19, 10, 0, tzinfo=UTC)
    assert c.last_indexed.microsecond == 123456 and c.stale_since is NULL
    assert d.last_indexed is NULL and d.stale_since == datetime(2026, 11, 18, 10, 0, tzinfo=UTC)
    out = index.dumps()
    assert 'last_indexed: "2026-11-19T10:00:00Z"' in out and "stale_since: null" in out


def test_the_corpus_loads_its_index(tmp_path):
    index = open_corpus(tmp_path).index.load()
    assert [e.id for e in index.entries] == ["polars:a.md", "polars:b.md", "polars:c.md"]
    assert dataclasses.is_dataclass(index) and index.meta.entry_count == 3
