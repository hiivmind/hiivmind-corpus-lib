from datetime import UTC, datetime
from pathlib import Path

import pytest

from hiivmind_corpus.errors import InvalidFile
from hiivmind_corpus.sources import (
    Freshness,
    Head,
    Location,
    ManifestHash,
    Snapshot,
    Unobserved,
)
from hiivmind_corpus.sources.generated_docs import GeneratedDocsKind
from hiivmind_corpus.sources.obsidian import ObsidianKind
from hiivmind_corpus.sources.self_docs import SelfKind
from support import FIXED, StubCorpus

CORPUS = StubCorpus(Path("/c/corpus"), Path("/repo"))
EARLY = datetime(2026, 11, 1, tzinfo=UTC)
LATE = datetime(2026, 11, 25, tzinfo=UTC)

GEN = GeneratedDocsKind()
GEN_RAW = {
    "id": "airtable",
    "type": "generated-docs",
    "source_repo": {"url": "https://github.com/e/d", "branch": "main", "docs_root": "docs",
                    "last_commit_sha": "5eaa"},
    "web_output": {"base_url": "https://docs.example/", "sitemap_url": "https://docs.example/s.xml"},
    "cache": {"enabled": True, "dir": ".cache/web/airtable"},
    "last_indexed_at": "2026-11-19T10:00:00Z",
    "endpoints": [{"name": "api"}],
}


def test_generated_docs_keeps_extra_and_absent_stays_absent():
    s = GEN.parse(GEN_RAW)
    assert s.extra == (("endpoints", [{"name": "api"}]),)
    assert s.web_output.discovered_urls is None
    assert "discovered_urls" not in GEN.dump(s)["web_output"]
    assert list(GEN.dump(s)) == list(GEN_RAW)
    s2 = GEN.parse({**GEN_RAW, "web_output": {"base_url": "x", "discovered_urls": []}})
    assert GEN.dump(s2)["web_output"]["discovered_urls"] == []


def test_generated_docs_locate_with_cache():
    s = GEN.parse(GEN_RAW)
    assert GEN.locate(s, CORPUS, "a.md") == Location(
        file=CORPUS.path / ".cache/web/airtable/a.md", url="https://docs.example/a.md")


def test_generated_docs_locate_cache_off():
    raw = {**GEN_RAW, "cache": {"enabled": False, "dir": ".cache/x"}}
    assert GEN.locate(GEN.parse(raw), CORPUS, "a.md") == Location(None, "https://docs.example/a.md")
    raw = {k: v for k, v in GEN_RAW.items() if k != "cache"}
    assert GEN.locate(GEN.parse(raw), CORPUS, "a.md").file is None


def test_generated_docs_freshness():
    s = GEN.parse(GEN_RAW)
    assert GEN.freshness(s, Head("5eaa"), FIXED) is Freshness.CURRENT
    assert GEN.freshness(s, Head("43d7"), FIXED) is Freshness.BEHIND
    assert GEN.freshness(s, None, FIXED) is Freshness.UNKNOWN
    assert GEN.freshness(s, Unobserved("x"), FIXED) is Freshness.UNKNOWN
    bare = GEN.parse({k: v for k, v in GEN_RAW.items() if k != "source_repo"})
    assert GEN.freshness(bare, Head("43d7"), FIXED) is Freshness.MANUAL
    assert GEN.freshness(bare, None, FIXED) is Freshness.MANUAL


def test_generated_docs_recorded():
    s = GEN.parse(GEN_RAW)
    r = GEN.recorded(s, Head("43d7"), FIXED)
    assert r.source_repo.last_commit_sha == "43d7" and r.source_repo.branch == "main"
    assert r.last_indexed_at == FIXED
    assert s.source_repo.last_commit_sha == "5eaa"
    o = GEN.recorded(s, ManifestHash("ab"), FIXED)
    assert o.source_repo.last_commit_sha == "5eaa" and o.last_indexed_at == FIXED
    bare = GEN.parse({k: v for k, v in GEN_RAW.items() if k != "source_repo"})
    assert GEN.recorded(bare, Head("43d7"), FIXED).source_repo is None


OBS = ObsidianKind()
OBS_GIT = {"id": "v", "type": "obsidian", "repo_url": "https://github.com/e/v", "branch": "main",
           "docs_root": "notes", "last_commit_sha": "5eaa", "include_patterns": ["**/*.md"],
           "exclude_patterns": [], "last_indexed_at": "2026-11-19T10:00:00Z", "extraction": {"a": 1},
           "owner": "e"}
OBS_LOCAL = {"id": "v", "type": "obsidian", "vault_path": "/home/me/vault",
             "last_indexed_at": "2026-11-19T10:00:00Z"}


def test_obsidian_round_trip_keeps_empty_list_and_absent():
    s = OBS.parse(OBS_GIT)
    assert s.exclude_patterns == ()
    assert list(OBS.dump(s)) == list(OBS_GIT)
    local = OBS.parse(OBS_LOCAL)
    assert local.include_patterns is None and local.exclude_patterns is None
    assert list(OBS.dump(local)) == list(OBS_LOCAL)


def test_obsidian_git_backed_behaves_as_git():
    s = OBS.parse(OBS_GIT)
    assert OBS.locate(s, CORPUS, "a.md").file == CORPUS.path / ".source/v/notes/a.md"
    assert OBS.freshness(s, Head("5eaa"), FIXED) is Freshness.CURRENT
    assert OBS.freshness(s, Head("43d7"), FIXED) is Freshness.BEHIND
    assert OBS.freshness(s, None, FIXED) is Freshness.UNKNOWN
    r = OBS.recorded(s, Head("43d7"), FIXED)
    assert (r.last_commit_sha, r.last_indexed_at) == ("43d7", FIXED)


def test_obsidian_local_locate():
    s = OBS.parse(OBS_LOCAL)
    assert OBS.locate(s, CORPUS, "a.md") == Location(Path("/home/me/vault/a.md"), None)
    rel = OBS.parse({**OBS_LOCAL, "vault_path": "vault"})
    assert OBS.locate(rel, CORPUS, "a.md").file == CORPUS.path / "vault/a.md"


def test_obsidian_local_freshness():
    s = OBS.parse(OBS_LOCAL)
    assert OBS.freshness(s, None, FIXED) is Freshness.MANUAL
    assert OBS.freshness(s, Snapshot({"a.md": LATE, "b.md": EARLY}), FIXED) is Freshness.BEHIND
    assert OBS.freshness(s, Snapshot({"a.md": EARLY}), FIXED) is Freshness.CURRENT
    never = OBS.parse({k: v for k, v in OBS_LOCAL.items() if k != "last_indexed_at"})
    assert OBS.freshness(never, Snapshot({"a.md": EARLY}), FIXED) is Freshness.BEHIND


def test_obsidian_local_recorded_sets_only_last_indexed_at():
    s = OBS.parse(OBS_LOCAL)
    r = OBS.recorded(s, Snapshot({"a.md": LATE}), FIXED)
    assert r.last_indexed_at == FIXED and r.vault_path == s.vault_path
    assert r.last_commit_sha is None


@pytest.mark.parametrize("raw", [
    {"id": "v", "type": "obsidian", "repo_url": "https://x", "vault_path": "/v"},
    {"id": "v", "type": "obsidian"},
], ids=["both", "neither"])
def test_obsidian_with_both_or_neither_of_repo_url_and_vault_path_is_invalid_file(raw):
    with pytest.raises(InvalidFile) as e:
        OBS.parse(raw, where="sources[0]")
    assert e.value.where == "sources[0]"


SELF = SelfKind()
SELF_RAW = {"id": "self", "type": "self", "docs_root": "docs", "last_commit_sha": "5eaa",
            "last_indexed_at": "2026-11-19T10:00:00Z", "note": "x"}


def test_self_locate_and_round_trip():
    s = SELF.parse(SELF_RAW)
    assert list(SELF.dump(s)) == list(SELF_RAW)
    assert SELF.locate(s, CORPUS, "a.md") == Location(Path("/repo/docs/a.md"), None)
    root = SELF.parse({"id": "self", "type": "self"})
    assert SELF.locate(root, CORPUS, "a.md").file == Path("/repo/a.md")


def test_self_freshness_is_manual():
    s = SELF.parse(SELF_RAW)
    for obs in (Head("5eaa"), None, Snapshot({"a": LATE})):
        assert SELF.freshness(s, obs, FIXED) is Freshness.MANUAL


def test_self_recorded_sets_only_last_indexed_at():
    s = SELF.parse(SELF_RAW)
    r = SELF.recorded(s, Head("43d7"), FIXED)
    assert r.last_indexed_at == FIXED and r.last_commit_sha == "5eaa"
