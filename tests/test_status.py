"""`corpus.status`: the freshness pre-check (spec 7.6, STA-1..5, CFG-2, CFG-3)."""

import os
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from hiivmind_corpus import embeddings as emb
from hiivmind_corpus.sources.types import Freshness, Head, SourceStatus, Unobserved
from hiivmind_corpus.status import IndexFormat, Status
from hiivmind_corpus.store import save
from support import open_corpus

SHA = "5eaa000000000000000000000000000000000000"
LANCE = "index-embeddings.lance"


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    monkeypatch.setattr(emb, "find_spec", lambda name: object())  # fastembed is not a dev dependency
    return open_corpus(tmp_path)


def _stale(corpus, n=1, tier=None):
    index = corpus.index.load()
    entries = tuple(replace(e, stale=True, tier=tier) if i < n else e for i, e in enumerate(index.entries))
    save(corpus, index=replace(index, entries=entries))


def test_report_of_a_current_corpus(corpus):
    assert corpus.status.report({"polars": Head(SHA)}) == Status(
        corpus="Polars", index_format="v2", sources=(SourceStatus("polars", "git", "current", None),),
        stale_entries=0, embeddings_lag=None, refresh_needed=False, errors=())


def test_a_behind_source_needs_a_refresh(corpus):
    s = corpus.status.report({"polars": Head("b" * 40)})
    assert s.sources[0].freshness == Freshness.BEHIND and s.refresh_needed is True and s.errors == ()


def test_a_missing_observation_is_unknown_and_reported_not_raised(corpus):
    s = corpus.status.report({})
    assert s.sources[0].freshness == "unknown"
    assert s.errors == ("source `polars`: no observation of its upstream was handed in",)
    assert s.refresh_needed is True


def test_a_failed_observation_is_unknown_with_its_reason(corpus):
    s = corpus.status.report({"polars": Unobserved("timed out")})
    assert s.errors == ("source `polars`: timed out",) and s.refresh_needed is True


def test_a_stale_entry_alone_needs_a_refresh(corpus):
    _stale(corpus)
    s = corpus.status.report({"polars": Head(SHA)})
    assert s.stale_entries == 1 and s.refresh_needed is True


def test_stale_sections_are_counted(corpus):
    _stale(corpus, 2, tier="section")
    assert corpus.status.report({"polars": Head(SHA)}).stale_entries == 2


def test_a_manual_source_alone_does_not_need_a_refresh(tmp_path):
    d = tmp_path / "manual"
    d.mkdir()
    (d / "config.yaml").write_text(
        "schema_version: 2\ncorpus:\n  name: manual\nsources:\n  - id: self\n    type: self\n    docs_root: docs\n",
        encoding="utf-8")
    (d / "index.yaml").write_text("entries: []\n", encoding="utf-8")
    from hiivmind_corpus import Corpus
    s = Corpus.open(d).status.report({})
    assert s.sources[0].freshness == Freshness.MANUAL
    assert s.refresh_needed is False and s.errors == ()


def _lance(corpus, generated_at):
    import lancedb
    import pyarrow as pa

    db = lancedb.connect(str(corpus.path / LANCE))
    schema = pa.schema([pa.field("key", pa.string()), pa.field("value", pa.string())])
    db.create_table(emb.META_TABLE, data=pa.Table.from_pylist(
        [{"key": "generated_at", "value": generated_at}], schema=schema))


def test_only_a_lance_lag_needs_a_refresh(corpus):
    pytest.importorskip("lancedb")
    _lance(corpus, "2026-11-19T09:00:00Z")  # entries were indexed at 10:00
    s = corpus.status.report({"polars": Head(SHA)})
    assert s.embeddings_lag == 3 and s.refresh_needed is True and s.errors == ()
    assert corpus.status.embeddings_lag() == 3


def test_a_lag_of_zero_does_not(corpus):
    pytest.importorskip("lancedb")
    _lance(corpus, "2026-11-19T10:00:00Z")
    s = corpus.status.report({"polars": Head(SHA)})
    assert s.embeddings_lag == 0 and s.refresh_needed is False


def test_a_v1_corpus(corpus):
    (corpus.path / "index.yaml").unlink()
    (corpus.path / "index.md").write_text("- [A](a.md) \u23f3 STALE\n", encoding="utf-8")
    s = corpus.status.report({"polars": Head(SHA)})
    assert corpus.status.index_format() == "v1" and s.index_format == "v1" and s.stale_entries is None


def test_a_corpus_with_no_index_is_none_with_zero_stale(corpus):
    (corpus.path / "index.yaml").unlink()
    (corpus.path / "index.md").unlink()
    s = corpus.status.report({"polars": Head(SHA)})
    assert corpus.status.index_format() == IndexFormat.NONE and s.stale_entries == 0


def test_the_extra_missing_with_a_lance_directory_present(corpus, monkeypatch):
    monkeypatch.setattr(emb, "find_spec", lambda name: None)
    (corpus.path / LANCE).mkdir()
    s = corpus.status.report({"polars": Head(SHA)})
    assert s.embeddings_lag is None
    assert s.errors[-1] == "embeddings lag not computed: install hiivmind-corpus-lib[embeddings]"
    assert corpus.status.embeddings_lag() is None


def test_embeddings_lag_and_index_format_asked_alone(corpus):
    assert corpus.status.embeddings_lag() is None
    assert corpus.status.index_format() == "v2"


def test_report_fetches_nothing_and_changes_nothing(corpus):
    def mtimes():
        return {p: p.stat().st_mtime_ns for p in corpus.path.rglob("*")}

    before = mtimes()
    corpus.status.report({})
    assert mtimes() == before


def test_an_unrecognised_source_is_unknown_with_its_error(tmp_path):
    d = tmp_path / "odd"
    d.mkdir()
    (d / "config.yaml").write_text(
        "schema_version: 2\nsources:\n  - id: tickets\n    type: github\n    base: appXYZ\n", encoding="utf-8")
    (d / "index.yaml").write_text("entries: []\n", encoding="utf-8")
    from hiivmind_corpus import Corpus
    s = Corpus.open(d).status.report({})
    assert s.sources[0].freshness == "unknown" and s.sources[0].error in s.errors
    assert s.refresh_needed is True
