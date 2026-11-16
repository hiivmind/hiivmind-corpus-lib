"""Preparing the base branch before a refresh. Every git command runs in the fixture clone."""

import pytest

from hiivmind_corpus.repo import RepoError, repo_prepare


def test_a_dirty_tree_stops_before_anything_changes(corpus):                       # Review Focus 1
    corpus.write("stray.txt", "x")
    with pytest.raises(RepoError, match="dirty"):
        repo_prepare(corpus.settings)
    assert corpus.git("branch", "--show-current") == "main"


def test_a_clean_tree_on_a_feature_branch_returns_to_the_base_branch(corpus):
    corpus.git("checkout", "-b", "elsewhere")
    result = repo_prepare(corpus.settings)
    assert result == {"main_advanced": False, "stale_branches": []}
    assert corpus.git("branch", "--show-current") == "main"


def test_prepare_reports_whether_main_advanced(corpus):
    other = corpus.next_dir("other")
    corpus.git("clone", "-q", str(corpus.origin), str(other))
    corpus.git("-C", str(other), "config", "user.name", "Test")
    corpus.git("-C", str(other), "config", "user.email", "test@example.com")
    (other / "new.txt").write_text("x")
    corpus.git("-C", str(other), "add", "new.txt")
    corpus.git("-C", str(other), "commit", "-q", "-m", "elsewhere")
    corpus.git("-C", str(other), "push", "-q", "origin", "main")
    assert repo_prepare(corpus.settings)["main_advanced"] is True
    assert repo_prepare(corpus.settings)["main_advanced"] is False


def test_a_local_base_branch_ahead_of_origin_stops_the_run(corpus):
    corpus.write("local.txt", "unpushed\n")
    corpus.git("add", "-A")
    corpus.git("commit", "-q", "-m", "local only")
    with pytest.raises(RepoError, match=r"main has 1 commit\(s\) that origin/main does not"):
        repo_prepare(corpus.settings)
