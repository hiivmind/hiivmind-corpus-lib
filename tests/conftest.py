"""The corpus fixtures of the package's tests. One test uses one corpus fixture: they all build in `tmp_path`."""

from datetime import date

import pytest

from corpus_fixture import make_corpus

MANY = ["docs:a.md", "docs:b.md", "docs:c.md"] + [f"docs:m{i:02d}.md" for i in range(1, 60)]


def _make(monkeypatch, tmp_path, *, at_root=False, push=False, extra_files=0, stale=(), checkout=False):
    return make_corpus(monkeypatch, tmp_path, at_root=at_root, push=push, extra_files=extra_files, stale=stale, checkout=checkout)


@pytest.fixture
def corpus(monkeypatch, tmp_path):
    """The corpus in `hiivmind-corpus-test/`, `PUSH: false`."""
    return _make(monkeypatch, tmp_path)


@pytest.fixture
def corpus_at_root(monkeypatch, tmp_path):
    """`corpus` with the corpus at the clone's root."""
    return _make(monkeypatch, tmp_path, at_root=True)


@pytest.fixture
def corpus_stale(monkeypatch, tmp_path):
    """`corpus` with `docs:a.md` and `docs:b.md` stale and `.source/docs/` checked out."""
    return _make(monkeypatch, tmp_path, stale=("docs:a.md", "docs:b.md"), checkout=True)


@pytest.fixture
def corpus_many(monkeypatch, tmp_path):
    """62 entries in the index, all stale, and 61 files in the source (`c.md` is deleted there): three batches of at most 30."""
    return _make(monkeypatch, tmp_path, extra_files=59, stale=tuple(MANY), checkout=True)


@pytest.fixture
def today() -> str:
    """Today's date as the branch names write it."""
    return date.today().isoformat()
