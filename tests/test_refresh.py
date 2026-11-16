"""The index capabilities of the refresh path: readiness, the batches to scan, a source's update, the merge of the scans,
the concept and summary setters, and `meta`."""

import difflib
import re
import subprocess

import yaml

from hiivmind_corpus.index import load_index
from hiivmind_corpus.refresh import (
    BATCH, apply_source_update, corpus_ready, merge_scans, set_concepts, set_summary, stale_batches, stale_entries,
)

NOW = "2026-11-16T02:00:00Z"


def scanned(path: str) -> dict:
    return {
        "path": path, "title": f"{path} rescanned", "summary": f"{path}, rescanned.", "tags": ["rescanned"], "keywords": ["new"],
        "category": "guide", "content_type": "markdown", "size": "standard", "grep_hint": None, "headings": [],
    }


def changed_lines(before: str, after: str) -> list[str]:
    return [d for d in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0) if d[0] in "+-" and d[:3] not in ("+++", "---")]


def blocks(text: str) -> dict[str, str]:
    """`index.yaml`'s entry blocks by id, and its head under `"head"`."""
    head, *rest = re.split(r"(?m)^(?=- id: )", text)
    return {"head": head, **{part.splitlines()[0].removeprefix("- id: "): part for part in rest}}


# --- corpus_ready -----------------------------------------------------------------------------------------------------

def test_a_built_v2_corpus_is_ready(corpus):
    assert corpus_ready(corpus.path) is True


def test_a_placeholder_or_a_v1_index_or_no_source_is_not_ready(corpus):
    index_md, index_yaml, config = (corpus.path / name for name in ("index.md", "index.yaml", "config.yaml"))
    text = index_md.read_text()
    index_md.write_text("# Index\n\nRun hiivmind-corpus-build to build it.\n")
    assert corpus_ready(corpus.path) is False
    index_md.write_text(text)
    kept = index_yaml.read_text()
    index_yaml.unlink()
    assert corpus_ready(corpus.path) is False
    index_yaml.write_text(kept)
    data = yaml.safe_load(config.read_text())
    data["sources"] = []
    config.write_text(yaml.safe_dump(data))
    assert corpus_ready(corpus.path) is False
    config.unlink()
    assert corpus_ready(corpus.path) is False


# --- stale_batches ----------------------------------------------------------------------------------------------------

def test_stale_batches_are_at_most_thirty_files_of_one_source(corpus_many):
    batches = stale_batches(corpus_many.path)
    assert BATCH == 30 and [len(b["files"]) for b in batches] == [30, 30, 2] and {b["source"] for b in batches} == {"docs"}
    assert [f for b in batches for f in b["files"]][:4] == ["a.md", "b.md", "c.md", "m01.md"]


def test_nothing_stale_is_no_batch(corpus):
    assert stale_batches(corpus.path) == []


# --- apply_source_update ----------------------------------------------------------------------------------------------

def test_an_update_marks_m_stale_adds_a_and_removes_d(corpus_checked_out):
    c = corpus_checked_out
    (c.path / "graph.yaml").write_text("schema_version: 1\nconcepts:\n  concept:\n    entries:\n      - docs:c.md\n      - docs:a.md\n")
    before = (c.path / "index.yaml").read_text()
    r = apply_source_update(c.path, "docs", c.first_sha, c.upstream_head, NOW)
    assert {k: r[k] for k in ("added", "modified", "removed")} == {"added": 1, "modified": 1, "removed": 1}
    assert r["removed_ids"] == ["docs:c.md"] and r["excluded"] == []
    assert r["files_changed"] == 3 and r["stale_entries"] == ["docs:a.md", "docs:d.md"]   # the diff's lines; the ids marked stale, in its order
    assert yaml.safe_load((c.path / "graph.yaml").read_text())["concepts"]["concept"]["entries"] == ["docs:a.md"]
    config = yaml.safe_load((c.path / "config.yaml").read_text())
    assert config["sources"][0]["last_commit_sha"] == c.upstream_head
    a, d = c.entry("docs:a.md"), c.entry("docs:d.md")
    assert (a["stale"], a["stale_since"], a["summary"]) == (True, NOW, "The file a.md.")
    assert (d["stale"], d["stale_since"], d["summary"], d["category"], d["path"], d["source"]) == (True, NOW, "Pending re-scan", "unknown", "d.md", "docs")
    assert (d["tags"], d["keywords"], d["concepts"], d["section"]) == ([], [], [], None)
    after = (c.path / "index.yaml").read_text()
    old, new = blocks(before), blocks(after)
    assert set(new) == {"head", "docs:a.md", "docs:b.md", "docs:d.md"} and new["docs:b.md"] == old["docs:b.md"]
    assert changed_lines(old["head"], new["head"]) == ["-  generated_at: '2026-01-01T00:00:00Z'", f"+  generated_at: '{NOW}'"]   # 3 entries still
    assert load_index(c.path / "index.yaml")["meta"] == {"corpus": "test", "source": "docs", "generated_at": NOW, "entry_count": 3}


def test_a_path_the_build_skips_is_excluded(corpus_checked_out):
    c = corpus_checked_out
    (c.upstream / "docs" / "changelog").mkdir()
    (c.upstream / "docs" / "changelog" / "v2.md").write_text("# v2\n")
    subprocess.run(["git", "-C", str(c.upstream), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(c.upstream), "commit", "-q", "-m", "changelog"], check=True)
    head = subprocess.run(["git", "-C", str(c.upstream), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(c.path / ".source" / "docs"), "pull", "-q"], check=True)
    config = yaml.safe_load((c.path / "config.yaml").read_text())
    config["build"] = {"skip_sections": ["changelog"]}
    (c.path / "config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    r = apply_source_update(c.path, "docs", c.first_sha, head, NOW)
    assert r["excluded"] == ["changelog/v2.md"] and r["added"] == 1
    assert "docs:changelog/v2.md" not in [e["id"] for e in load_index(c.path / "index.yaml")["entries"]]


def test_the_config_diff_is_only_the_three_values(corpus_checked_out):
    c = corpus_checked_out
    before = (c.path / "config.yaml").read_text()
    apply_source_update(c.path, "docs", c.first_sha, c.upstream_head, NOW)
    assert sorted(changed_lines(before, (c.path / "config.yaml").read_text())) == sorted([
        f"-  last_commit_sha: {c.first_sha}", "-  last_indexed_at: '2026-01-01T00:00:00Z'", "-  last_updated_at: '2026-01-01T00:00:00Z'",
        f"+  last_commit_sha: {c.upstream_head}", f"+  last_indexed_at: '{NOW}'", f"+  last_updated_at: '{NOW}'",
    ])


def test_a_file_name_git_would_quote_is_read_as_it_is(corpus_checked_out):          # final review 3
    c = corpus_checked_out
    upstream = lambda *args: subprocess.run(["git", "-C", str(c.upstream), *args], capture_output=True, text=True, check=True).stdout.strip()
    (c.upstream / "docs" / "é.md").write_text("# é\n")
    upstream("add", "-A"); upstream("commit", "-q", "-m", "é")
    base = upstream("rev-parse", "HEAD")
    (c.upstream / "docs" / "é.md").write_text("# é, changed\n")
    (c.upstream / "docs" / "ü.md").write_text("# ü\n")
    upstream("add", "-A"); upstream("commit", "-q", "-m", "é changed, ü added")
    head = upstream("rev-parse", "HEAD")
    subprocess.run(["git", "-C", str(c.path / ".source" / "docs"), "pull", "-q"], check=True)
    c.add_entry({"id": "docs:é.md", "source": "docs", "path": "é.md", "stale": False})
    r = apply_source_update(c.path, "docs", base, head, NOW)
    assert (r["modified"], r["added"], r["stale_entries"]) == (1, 1, ["docs:é.md", "docs:ü.md"])
    assert c.entry("docs:ü.md")["path"] == "ü.md" and c.entry("docs:é.md")["stale"] is True


def test_a_failed_diff_raises_with_what_git_said(corpus_checked_out):
    c = corpus_checked_out
    try:
        apply_source_update(c.path, "docs", "0" * 40, c.upstream_head, NOW)
    except RuntimeError as e:
        assert "git" in str(e) and "0000000" in str(e)
    else:
        raise AssertionError("no error")


# --- merge_scans ------------------------------------------------------------------------------------------------------

def test_merge_pairs_done_scans_around_a_failed_batch(corpus_many):                # Review Focus 4
    first, middle, last = stale_batches(corpus_many.path)
    scans = [{"entries": [scanned(f) for f in first["files"]]}, {"entries": [scanned(f) for f in last["files"]]}]
    failures = [{"item": middle, "outcome": "failed", "reason": "no_exit"}]
    r = merge_scans(corpus_many.path, scans, failures, NOW)
    assert r["enriched"] == [f"docs:{f}" for f in first["files"] + last["files"]]
    assert r["skipped"] == [{"id": f"docs:{f}", "reason": "no_exit"} for f in middle["files"]]
    assert corpus_many.entry("docs:m58.md")["summary"] == "m58.md, rescanned." and corpus_many.entry("docs:m28.md")["stale"] is True


def test_merge_with_every_batch_failed_skips_every_entry(corpus_many):
    batches = stale_batches(corpus_many.path)
    failures = [{"item": b, "outcome": "invalid_output", "reason": None} for b in batches]
    r = merge_scans(corpus_many.path, [], failures, NOW)
    assert r["enriched"] == [] and len(r["skipped"]) == 62 and {s["reason"] for s in r["skipped"]} == {"invalid_output"}


def test_a_merge_with_no_source_update_sets_meta(corpus_stale):
    merge_scans(corpus_stale.path, [{"entries": [scanned("a.md"), scanned("b.md")]}], [], NOW)
    assert load_index(corpus_stale.path / "index.yaml")["meta"]["generated_at"] == NOW


# --- the setters ------------------------------------------------------------------------------------------------------

def test_set_concepts_and_set_summary_change_only_that_field(corpus):
    index = corpus.path / "index.yaml"
    before = index.read_text()
    assert set_concepts(corpus.path, {"docs:a.md": ["lazy", "concept"], "docs:nowhere.md": ["x"]}, NOW) == {"assigned": 1}
    assert set_summary(corpus.path, "docs:b.md", "B, verified.", NOW) == {"ok": True}
    old, new = blocks(before), blocks(index.read_text())
    assert new["docs:c.md"] == old["docs:c.md"]
    assert changed_lines(old["docs:a.md"], new["docs:a.md"]) == ["+  - lazy"]   # before `- concept`, which stays
    assert changed_lines(old["docs:b.md"], new["docs:b.md"]) == ["-  summary: The file b.md.", "+  summary: B, verified."]
    assert load_index(index)["meta"]["generated_at"] == NOW


def test_stale_entries_lists_the_ids_still_stale(corpus_stale):
    assert stale_entries(corpus_stale.path) == ["docs:a.md", "docs:b.md"]
