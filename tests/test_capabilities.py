"""Status, scripts and documents through the package: the freshness and refresh-needed checks, the embeddings, the
previews, and `reference`."""

import json
from datetime import date, timedelta

import pytest

import hiivmind_corpus.refresh as refresh
from hiivmind_corpus.reference import reference
from hiivmind_corpus.refresh import embeddings_lag, embeddings_status, refresh_needed, source_freshness, verify_previews
from hiivmind_corpus.run import SCRIPTS, run_script


def test_a_current_corpus_needs_no_refresh_and_one_behind_does(corpus):
    assert refresh_needed(corpus.path) is True
    corpus.set_last_sha(corpus.upstream_head)
    assert refresh_needed(corpus.path) is False


def test_stale_entries_alone_need_a_refresh(corpus_stale):
    corpus_stale.set_last_sha(corpus_stale.upstream_head)
    assert refresh_needed(corpus_stale.path) is True


def test_unknown_freshness_needs_a_refresh(corpus):
    corpus.set_last_sha(corpus.upstream_head)
    corpus.add_source({"id": "site", "type": "web"})
    assert refresh_needed(corpus.path) is True


def test_a_status_that_raises_needs_a_refresh(corpus):
    corpus.set_last_sha(corpus.upstream_head)
    corpus.break_lance_dir()   # lance_meta.py fails on it, and corpus_status raises
    assert refresh_needed(corpus.path) is True


def test_the_lag_alone_needs_a_refresh(corpus):
    corpus.set_last_sha(corpus.upstream_head)
    corpus.make_lance((date.today() - timedelta(days=400)).isoformat() + "T00:00:00Z")   # before every entry's last_indexed
    assert embeddings_lag(corpus.path) == 3
    assert refresh_needed(corpus.path) is True


def test_no_embeddings_is_no_lag(corpus):
    assert embeddings_lag(corpus.path) is None


def test_source_freshness_gives_each_source_with_its_error(corpus):
    corpus.add_source({"id": "site", "type": "web"})
    corpus.add_source({"id": "gone", "type": "git", "repo_url": "/nowhere", "last_commit_sha": "x"})
    found = source_freshness(corpus.path)
    assert found[0] == {"id": "docs", "type": "git", "freshness": "behind", "error": None}
    assert found[1] == {"id": "site", "type": "web", "freshness": "unknown", "error": "source type `web` is not handled by this instance yet"}
    assert found[2]["freshness"] == "unknown" and "/nowhere" in found[2]["error"]


def test_embeddings_status_is_absent_without_a_lance_directory(corpus):
    assert embeddings_status(corpus.path) == "absent"


def test_embeddings_status_is_what_detect_prints(corpus, monkeypatch):
    (corpus.path / "index-embeddings.lance").mkdir()
    monkeypatch.setattr(refresh, "run_script", lambda name, *args, **kw: type("Done", (), {"stdout": "  odd words\n", "returncode": 0})())
    assert embeddings_status(corpus.path) == "odd words"


def test_verify_previews_gives_the_script_s_json(corpus_stale):
    [preview] = verify_previews(corpus_stale.path, ["docs:a.md"])
    assert preview["entry_id"] == "docs:a.md" and "Changed." in preview["content_preview"]


def test_reference_returns_a_section_and_names_the_ones_there_are():
    text = reference("graph", "Schema Definition")
    assert text.startswith("### Schema Definition") and "concepts:" in text and "## " not in text.splitlines()[-1]
    assert reference("sources/git").startswith("# ")
    with pytest.raises(KeyError, match="Schema Definition"):
        reference("graph", "No such section")
    with pytest.raises(FileNotFoundError, match="sources/git"):
        reference("no-such-document")


def test_a_heading_inside_a_code_block_is_not_a_section():
    with pytest.raises(KeyError):
        reference("graph", "Concepts: knowledge graph nodes")   # a `#` comment in the schema's YAML


def test_run_script_runs_detect_from_the_package():
    done = run_script("detect.py")
    assert SCRIPTS.name == "scripts" and done.returncode == 0 and done.stdout.strip() in ("ready", "no-model", "not-installed")
