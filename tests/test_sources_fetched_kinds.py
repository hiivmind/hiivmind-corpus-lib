from datetime import UTC, datetime, timedelta
from pathlib import Path

from hiivmind_corpus.sources import (
    SOURCE_KINDS,
    Freshness,
    Head,
    Location,
    ManifestHash,
    Snapshot,
    Unobserved,
)
from hiivmind_corpus.sources.llms_txt import LlmsTxtKind
from hiivmind_corpus.sources.local import LocalKind
from hiivmind_corpus.sources.web import WebKind
from support import FIXED, StubCorpus

CORPUS = StubCorpus(Path("/c/corpus"), Path("/repo"))
EARLY = datetime(2026, 11, 1, tzinfo=UTC)
LATE = datetime(2026, 11, 25, tzinfo=UTC)


def test_the_seven_kinds_in_order():
    assert list(SOURCE_KINDS) == ["git", "generated-docs", "obsidian", "self", "local", "web", "llms-txt"]


LOCAL = LocalKind()
LOCAL_RAW = {"id": "notes", "type": "local", "path": "uploads/notes/", "files": ["a.md"],
             "description": "Notes", "last_indexed_at": "2026-11-19T10:00:00Z", "owner": "me"}


def test_local_round_trip():
    s = LOCAL.parse(LOCAL_RAW)
    assert list(LOCAL.dump(s)) == list(LOCAL_RAW)
    bare = LOCAL.parse({"id": "notes", "type": "local"})
    assert LOCAL.dump(bare) == {"id": "notes", "type": "local"}


def test_local_locate():
    assert LOCAL.locate(LOCAL.parse(LOCAL_RAW), CORPUS, "a.md").file == CORPUS.path / "uploads/notes/a.md"
    bare = LOCAL.parse({"id": "notes", "type": "local"})
    assert LOCAL.locate(bare, CORPUS, "a.md") == Location(CORPUS.path / "uploads/notes/a.md", None)


def test_local_freshness():
    s = LOCAL.parse(LOCAL_RAW)
    assert LOCAL.freshness(s, None, FIXED) is Freshness.MANUAL
    assert LOCAL.freshness(s, Snapshot({"a.md": LATE}), FIXED) is Freshness.BEHIND
    assert LOCAL.freshness(s, Snapshot({"a.md": EARLY}), FIXED) is Freshness.CURRENT
    assert LOCAL.freshness(s, Unobserved("x"), FIXED) is Freshness.UNKNOWN


def test_local_recorded():
    s = LOCAL.parse(LOCAL_RAW)
    assert LOCAL.recorded(s, Snapshot({"a.md": LATE}), FIXED).last_indexed_at == FIXED
    assert LOCAL.recorded(s, None, FIXED).files == ["a.md"]


WEB = WebKind()
FETCHED = "2026-11-10T08:00:00Z"
CACHED = {"id": "fastmail-dev", "type": "web", "cache_dir": ".cache/web/fastmail-dev",
          "urls": [{"url": "https://jmap.io/crash-course.html", "cached_file": "crash-course.md",
                    "fetched_at": FETCHED, "content_hash": "abc"},
                   {"url": "https://jmap.io/spec.html", "cached_file": "spec.md",
                    "fetched_at": "2026-11-12T08:00:00Z"}],
          "last_fetched_at": "2026-11-12T08:00:00Z", "content_hash": "0a"}
LIVE = {"id": "airtable", "type": "web", "fetch_mode": "live",
        "base_url": "https://airtable.com/developers/web/api/", "discovered_urls": []}
OLDEST = datetime(2026, 11, 10, 8, tzinfo=UTC)


def test_web_round_trip_keeps_extras_and_empty_list():
    s = WEB.parse(CACHED)
    assert s.urls[0].extra == (("content_hash", "abc"),)
    assert s.extra == (("content_hash", "0a"),)
    assert list(WEB.dump(s)) == list(CACHED)
    live = WEB.parse(LIVE)
    assert live.urls is None and live.discovered_urls == []
    assert WEB.dump(live)["discovered_urls"] == [] and "urls" not in WEB.dump(live)


def test_web_locate_cached():
    assert WEB.locate(WEB.parse(CACHED), CORPUS, "crash-course.md") == Location(
        file=CORPUS.path / ".cache/web/fastmail-dev/crash-course.md",
        url="https://jmap.io/crash-course.html")
    assert WEB.locate(WEB.parse(CACHED), CORPUS, "other.md").url is None


def test_web_locate_live():
    assert WEB.locate(WEB.parse(LIVE), CORPUS, "introduction") == Location(
        None, "https://airtable.com/developers/web/api/introduction")


def test_web_freshness_without_observation():
    s = WEB.parse(CACHED)
    assert WEB.freshness(s, None, OLDEST + timedelta(days=7)) is Freshness.CURRENT
    assert WEB.freshness(s, None, OLDEST + timedelta(days=7, seconds=1)) is Freshness.BEHIND
    only_last = WEB.parse({k: v for k, v in CACHED.items() if k != "urls"})
    assert WEB.freshness(only_last, None, datetime(2026, 11, 20, 8, tzinfo=UTC)) is Freshness.BEHIND
    assert WEB.freshness(only_last, None, datetime(2026, 11, 19, 8, tzinfo=UTC)) is Freshness.CURRENT
    none = WEB.parse({"id": "w", "type": "web"})
    assert WEB.freshness(none, None, FIXED) is Freshness.UNKNOWN
    assert WEB.freshness(WEB.parse(LIVE), None, FIXED) is Freshness.MANUAL


def test_web_freshness_with_snapshot():
    s = WEB.parse(CACHED)
    assert WEB.freshness(s, Snapshot({"a": OLDEST + timedelta(seconds=1)}), FIXED) is Freshness.BEHIND
    assert WEB.freshness(s, Snapshot({"a": OLDEST}), FIXED) is Freshness.CURRENT
    none = WEB.parse({"id": "w", "type": "web"})
    assert WEB.freshness(none, Snapshot({"a": LATE}), FIXED) is Freshness.UNKNOWN
    assert WEB.freshness(s, Head("x"), FIXED) is Freshness.UNKNOWN
    assert WEB.freshness(s, Unobserved("x"), FIXED) is Freshness.UNKNOWN


def test_web_recorded():
    r = WEB.recorded(WEB.parse(CACHED), None, FIXED)
    assert r.last_indexed_at == FIXED and r.last_fetched_at == FIXED
    assert r.urls[0].fetched_at == OLDEST


LLMS = LlmsTxtKind()
LLMS_RAW = {"id": "llms", "type": "llms-txt",
            "manifest": {"url": "https://d.example/llms.txt", "last_hash": "h1",
                         "last_fetched_at": "2026-11-19T10:00:00Z"},
            "urls": {"base_url": "https://d.example/", "suffix": ".md"},
            "cache": {"enabled": True, "dir": ".cache/llms", "strategy": "full", "sections": ["guide"]},
            "structure": {"guide": ["a"]}, "last_indexed_at": "2026-11-19T10:00:00Z", "generator": "x"}


def test_llms_round_trip():
    s = LLMS.parse(LLMS_RAW)
    assert list(LLMS.dump(s)) == list(LLMS_RAW)
    assert s.cache.sections == ["guide"]


def test_llms_locate():
    s = LLMS.parse(LLMS_RAW)
    assert LLMS.locate(s, CORPUS, "a.md") == Location(CORPUS.path / ".cache/llms/a.md", "https://d.example/a.md")
    assert LLMS.locate(s, CORPUS, "a").url == "https://d.example/a.md"
    off = LLMS.parse({**LLMS_RAW, "cache": {"enabled": False, "dir": ".cache/llms"}})
    assert LLMS.locate(off, CORPUS, "a.md") == Location(None, "https://d.example/a.md")


def test_llms_freshness():
    s = LLMS.parse(LLMS_RAW)
    assert LLMS.freshness(s, ManifestHash("h1"), FIXED) is Freshness.CURRENT
    assert LLMS.freshness(s, ManifestHash("h2"), FIXED) is Freshness.BEHIND
    for other in (None, Unobserved("x"), Head("h1")):
        assert LLMS.freshness(s, other, FIXED) is Freshness.UNKNOWN


def test_llms_recorded():
    s = LLMS.parse(LLMS_RAW)
    r = LLMS.recorded(s, ManifestHash("h2"), FIXED)
    assert (r.manifest.last_hash, r.manifest.last_fetched_at, r.last_indexed_at) == ("h2", FIXED, FIXED)
    assert r.manifest.url == "https://d.example/llms.txt"
    assert s.manifest.last_hash == "h1"
    o = LLMS.recorded(s, Unobserved("x"), FIXED)
    assert o.manifest.last_hash == "h1" and o.last_indexed_at == FIXED


def test_web_recorded_fetch_time_only_for_snapshot_or_no_observation():
    s = WEB.parse(CACHED)
    before = s.last_fetched_at
    for obs in (None, Snapshot({"a": LATE})):
        assert WEB.recorded(s, obs, FIXED).last_fetched_at == FIXED
    for obs in (Head("x"), ManifestHash("x"), Unobserved("x")):
        r = WEB.recorded(s, obs, FIXED)
        assert r.last_fetched_at == before and r.last_indexed_at == FIXED
