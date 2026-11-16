"""Preparing the base branch before a refresh. Every git command runs in the fixture clone."""

import pytest

from hiivmind_corpus.repo import RepoError, prepare_base


def test_prepare_base_refuses_a_dirty_tree(corpus):
    corpus.write("stray.txt", "x")
    with pytest.raises(RepoError, match="dirty"):
        prepare_base(corpus.path, "main")
    assert corpus.git("branch", "--show-current") == "main"


def test_a_corpus_at_the_repository_root_is_prepared_the_same(corpus_at_root):
    corpus_at_root.git("checkout", "-b", "elsewhere")
    assert prepare_base(corpus_at_root.path, "main") is True and corpus_at_root.git("branch", "--show-current") == "main"


def test_a_clean_tree_on_a_feature_branch_returns_to_the_base_branch(corpus):
    corpus.git("checkout", "-b", "elsewhere")
    assert prepare_base(corpus.path, "main") is True
    assert corpus.git("branch", "--show-current") == "main"


def test_prepare_base_fast_forwards_to_origin(corpus):                          # Review Focus 3
    other = corpus.next_dir("other")
    corpus.git("clone", "-q", str(corpus.origin), str(other))
    corpus.git("-C", str(other), "config", "user.name", "Test")
    corpus.git("-C", str(other), "config", "user.email", "test@example.com")
    (other / "new.txt").write_text("x")
    corpus.git("-C", str(other), "add", "new.txt")
    corpus.git("-C", str(other), "commit", "-q", "-m", "elsewhere")
    corpus.git("-C", str(other), "push", "-q", "origin", "main")
    assert not (corpus.clone / "new.txt").exists()
    assert prepare_base(corpus.path, "main") is True
    assert (corpus.clone / "new.txt").read_text() == "x"


def test_prepare_base_refuses_a_base_ahead_of_origin(corpus):
    corpus.write("local.txt", "unpushed\n")
    corpus.git("add", "-A")
    corpus.git("commit", "-q", "-m", "local only")
    with pytest.raises(RepoError, match=r"main has 1 commit\(s\) that origin/main does not"):
        prepare_base(corpus.path, "main")
