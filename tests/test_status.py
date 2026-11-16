"""`corpus_status`: the freshness pre-check, and the seam for source kinds."""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import hiivmind_corpus
from hiivmind_corpus.sources import SOURCE_KINDS, kind_of
from hiivmind_corpus.sources.git import GitSource
from hiivmind_corpus.status import corpus_status

SCRIPTS = Path(hiivmind_corpus.__file__).parent / "scripts"


def test_a_corpus_behind_its_upstream_needs_a_refresh(corpus):
    s = corpus_status(corpus.path, SCRIPTS)
    assert s["corpus"] == "test" and s["index_format"] == "v2"
    assert s["sources"] == [{"id": "docs", "type": "git", "freshness": "behind"}] and s["refresh_needed"] is True
    assert s["errors"] == []


def test_an_up_to_date_corpus_does_not(corpus):
    corpus.set_last_sha(corpus.upstream_head)
    s = corpus_status(corpus.path, SCRIPTS)
    assert s["sources"] == [{"id": "docs", "type": "git", "freshness": "current"}]
    assert s["refresh_needed"] is False and s["stale_entries"] == 0 and s["embeddings_lag"] is None


def test_stale_entries_alone_need_a_refresh(corpus_stale):
    corpus_stale.set_last_sha(corpus_stale.upstream_head)
    s = corpus_status(corpus_stale.path, SCRIPTS)
    assert s["refresh_needed"] is True and s["stale_entries"] == 2
    assert s["sources"][0]["freshness"] == "current"


def test_an_unreachable_upstream_is_unknown_and_is_reported(corpus):
    corpus.set_repo_url("/nowhere")
    s = corpus_status(corpus.path, SCRIPTS)
    assert s["sources"][0]["freshness"] == "unknown" and s["errors"] and s["refresh_needed"] is False


def test_an_upstream_that_times_out_is_unknown_and_is_reported(corpus, tmp_path, monkeypatch):
    import os, shutil, sys
    import hiivmind_corpus.sources.git
    slow = tmp_path / "slow-bin"
    slow.mkdir()
    (slow / "git").write_text(
        f"#!{sys.executable}\nimport os, sys, time\nif 'ls-remote' in sys.argv:\n    time.sleep(30)\n"
        f"os.execv('{shutil.which('git')}', ['git', *sys.argv[1:]])\n"
    )
    (slow / "git").chmod(0o755)
    monkeypatch.setenv("PATH", f"{slow}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(hiivmind_corpus.sources.git, "TIMEOUT", 1)
    s = corpus_status(corpus.path, SCRIPTS)
    assert s["sources"][0]["freshness"] == "unknown" and any("did not finish in 1 s" in e for e in s["errors"])


def test_a_branch_the_upstream_does_not_have_is_unknown_and_is_reported(corpus):
    corpus.add_source({"id": "other", "type": "git", "repo_url": str(corpus.upstream), "branch": "no-such-branch", "last_commit_sha": "x"})
    s = corpus_status(corpus.path, SCRIPTS)
    assert {"id": "other", "type": "git", "freshness": "unknown"} in s["sources"]
    assert any("no-such-branch" in e for e in s["errors"])


def test_a_kind_this_instance_does_not_handle_is_reported(corpus):
    corpus.add_source({"id": "site", "type": "web"})
    s = corpus_status(corpus.path, SCRIPTS)
    assert {"id": "site", "type": "web", "freshness": "unknown"} in s["sources"]
    assert "source type `web` is not handled by this instance yet" in s["errors"]


def test_nothing_is_changed(corpus):
    corpus_status(corpus.path, SCRIPTS)
    assert corpus.git("status", "--porcelain") == ""
    assert not (corpus.path / ".source").exists()


def test_the_seam_knows_git_only(corpus):
    assert set(SOURCE_KINDS) == {"git"} and isinstance(SOURCE_KINDS["git"], GitSource)
    assert kind_of({"id": "docs", "type": "git"}) is SOURCE_KINDS["git"]
    assert kind_of({"id": "site", "type": "web"}) is None and kind_of({"id": "x"}) is None


def test_a_missing_config_names_the_file(corpus):
    (corpus.path / "config.yaml").unlink()
    with pytest.raises(FileNotFoundError, match="config.yaml"):
        corpus_status(corpus.path, SCRIPTS)


def test_the_index_format_is_read_from_the_files(corpus):
    (corpus.path / "index.yaml").unlink()
    assert corpus_status(corpus.path, SCRIPTS)["index_format"] == "v1"
    (corpus.path / "index.md").unlink()
    assert corpus_status(corpus.path, SCRIPTS)["index_format"] == "none"


def test_a_v1_index_counts_its_stale_markers(corpus):
    (corpus.path / "index.yaml").unlink()
    (corpus.path / "index.md").write_text("- [A](a.md) \u23f3 STALE\n- [B](b.md)\n- [C](c.md) \u23f3 STALE\n")
    (corpus.path / "index-extra.md").write_text("- [D](d.md) \u23f3 STALE\n")
    assert corpus_status(corpus.path, SCRIPTS)["stale_entries"] == 3


# --- the embedding lag ------------------------------------------------------------------------------------------------

def _fake_scripts(tmp_path, stdout: str, exit_code: int = 0) -> Path:
    """A scripts directory whose `lance_meta.py` prints `stdout` and exits `exit_code`."""
    scripts = tmp_path / "fake-scripts"
    scripts.mkdir(parents=True)
    (scripts / "lance_meta.py").write_text(
        f"import sys\nprint({stdout!r})\nprint('stand-in failed', file=sys.stderr)\nsys.exit({exit_code})\n"
    )
    return scripts


def test_the_lag_counts_entries_indexed_after_the_embeddings(corpus, tmp_path, monkeypatch):
    stamp = lambda days: (date.today() + timedelta(days=days)).isoformat() + "T00:00:00Z"
    scripts = _fake_scripts(tmp_path, json.dumps({"generated_at": stamp(-3)}))
    (corpus.path / "index-embeddings.lance").mkdir()
    monkeypatch.chdir(tmp_path)   # the lookup does not depend on the working directory
    assert corpus_status(corpus.path, scripts)["embeddings_lag"] == 0
    for name, days in (("new1.md", -2), ("new2.md", 0), ("old.md", -4)):
        entry = {"id": f"docs:{name}", "source": "docs", "path": name, "stale": False, "last_indexed": stamp(days)}
        corpus.add_entry(entry)
    assert corpus_status(corpus.path, scripts)["embeddings_lag"] == 2


def test_no_meta_table_means_no_lag_figure(corpus, tmp_path, monkeypatch):
    scripts = _fake_scripts(tmp_path, "", exit_code=2)
    (corpus.path / "index-embeddings.lance").mkdir()
    assert corpus_status(corpus.path, scripts)["embeddings_lag"] is None


def test_any_other_failure_of_lance_meta_raises_naming_the_script(corpus, tmp_path, monkeypatch):
    scripts = _fake_scripts(tmp_path, "", exit_code=1)
    (corpus.path / "index-embeddings.lance").mkdir()
    with pytest.raises(RuntimeError, match="lance_meta.py"):
        corpus_status(corpus.path, scripts)


def test_the_real_script_gives_none_for_an_empty_lance_directory(corpus):
    (corpus.path / "index-embeddings.lance").mkdir()
    assert corpus_status(corpus.path, SCRIPTS)["embeddings_lag"] is None


def test_the_real_script_failing_on_an_unreadable_directory_raises(corpus):
    corpus.break_lance_dir()
    with pytest.raises(RuntimeError, match="lance_meta.py"):
        corpus_status(corpus.path, SCRIPTS)
