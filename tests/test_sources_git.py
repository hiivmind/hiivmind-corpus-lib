from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hiivmind_corpus_lib.errors import InvalidFile
from hiivmind_corpus_lib.sources import (
    SOURCE_KINDS,
    Freshness,
    GitKind,
    GitSource,
    Head,
    Location,
    ManifestHash,
    Unobserved,
    kind_of,
)
from support import FIXED, StubCorpus

RAW = {
    "id": "polars",
    "type": "git",
    "repo_url": "https://github.com/pola-rs/polars",
    "branch": "main",
    "docs_root": "docs/source",
    "last_commit_sha": "5eaa",
    "last_indexed_at": "2026-11-19T10:00:00Z",
    "repo_owner": "pola-rs",
}
KIND = GitKind()
CORPUS = StubCorpus(Path("/c/corpus"), Path("/c"))


def test_registered():
    assert isinstance(SOURCE_KINDS["git"], GitKind)
    assert list(SOURCE_KINDS)[0] == "git"
    s = KIND.parse(RAW)
    assert kind_of(s) is SOURCE_KINDS["git"]


def test_parse_then_dump_keeps_order_and_extra():
    s = KIND.parse(RAW)
    assert s.extra == (("repo_owner", "pola-rs"),)
    assert s.last_indexed_at == datetime(2026, 11, 19, 10, tzinfo=UTC)
    assert list(KIND.dump(s)) == list(RAW)
    assert list(s.dump_mapping()) == list(RAW)


def test_absent_branch_stays_absent():
    raw = {k: v for k, v in RAW.items() if k != "branch"}
    s = KIND.parse(raw)
    assert s.branch is None
    assert "branch" not in KIND.dump(s)


def test_invalid_repo_url_names_the_place():
    with pytest.raises(InvalidFile) as e:
        KIND.parse({**RAW, "repo_url": 5}, where="sources[0]")
    assert e.value.where == "sources[0].repo_url"


@pytest.mark.parametrize("root", [".", "", None])
def test_locate_at_the_root(root):
    s = KIND.parse({**RAW, "docs_root": root} if root is not None else {k: v for k, v in RAW.items() if k != "docs_root"})
    assert KIND.locate(s, CORPUS, "a.md") == Location(CORPUS.path / ".source/polars/a.md", None)


def test_locate_under_docs_root():
    assert KIND.locate(KIND.parse(RAW), CORPUS, "a.md").file == CORPUS.path / ".source/polars/docs/source/a.md"


def test_freshness():
    s = KIND.parse(RAW)
    assert KIND.freshness(s, Head("5eaa"), FIXED) is Freshness.CURRENT
    assert KIND.freshness(s, Head("43d7"), FIXED) is Freshness.BEHIND
    for other in (None, Unobserved("x"), ManifestHash("ab")):
        assert KIND.freshness(s, other, FIXED) is Freshness.UNKNOWN


def test_recorded():
    s = KIND.parse(RAW)
    r = KIND.recorded(s, Head("43d7"), FIXED)
    assert (r.last_commit_sha, r.last_indexed_at) == ("43d7", FIXED)
    assert s.last_commit_sha == "5eaa"
    u = KIND.recorded(s, Unobserved("x"), FIXED)
    assert (u.last_commit_sha, u.last_indexed_at) == ("5eaa", FIXED)
    assert KIND.recorded(s, ManifestHash("ab"), FIXED).last_commit_sha == "5eaa"
    with pytest.raises(FrozenInstanceError):
        s.branch = "x"


def test_freshness_is_a_string_enum():
    assert Freshness.CURRENT == "current" and Freshness.MANUAL == "manual"
