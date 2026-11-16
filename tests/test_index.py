"""`stale_files`, `apply_scan` and `drop_missing`: finding the stale entries, merging the scans into `index.yaml`, and removing the entries whose files are gone."""

import difflib
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from corpus_fixture import RENDER_INDEX
from hiivmind_corpus.index import apply_scan, drop_missing, load_index, stale_files, write_entries

CLONE = Path("/home/nathanielramm/git/hiivmind/hiivmind-corpus-data")
INDEX = "hiivmind-corpus-polars/index.yaml"
POLARS = CLONE / INDEX


def scanned(path: str, summary: str) -> dict:
    """A complete scan result for one file: `path` and the nine fields."""
    return {
        "path": path, "title": f"{path} rescanned", "summary": summary, "tags": ["rescanned"], "keywords": ["new"],
        "category": "guide", "content_type": "markdown", "size": "large", "grep_hint": "grep -n '^## ' FILE",
        "headings": [{"anchor": "intro", "title": "Intro"}],
    }


SCANNED_A = scanned("a.md", "A, rescanned.")
SCANNED_UNASKED = scanned("z.md", "Z, which no batch asked for.")


def test_stale_files_groups_by_source_and_skips_sections_under_a_stale_parent(corpus_stale):
    corpus_stale.add_entry({"id": "docs:a.md#intro", "tier": "section", "parent": "docs:a.md", "stale": True})
    assert stale_files(corpus_stale.path) == {"by_source": {"docs": ["a.md", "b.md"]}, "entry_ids": ["docs:a.md", "docs:b.md"]}


def test_a_stale_entry_without_path_takes_it_from_its_id(corpus_stale):
    corpus_stale.add_entry({"id": "docs:guide/c.md", "source": "docs", "stale": True})
    corpus_stale.add_entry({"id": "other:x/y.md", "stale": True})   # no `source` either: the id's prefix names it
    found = stale_files(corpus_stale.path)
    assert found["by_source"] == {"docs": ["a.md", "b.md", "guide/c.md"], "other": ["x/y.md"]}
    assert found["entry_ids"] == ["docs:a.md", "docs:b.md", "docs:guide/c.md", "other:x/y.md"]


def test_apply_replaces_the_scanned_fields_and_preserves_the_rest(corpus_stale):
    before = corpus_stale.entry("docs:a.md")
    r = apply_scan([{"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": None}], corpus_stale.path)
    after = corpus_stale.entry("docs:a.md")
    assert r["enriched"] == ["docs:a.md"] and after["summary"] == "A, rescanned." and after["stale"] is False
    assert (after["id"], after["links_to"], after["concepts"]) == (before["id"], before["links_to"], before["concepts"])
    assert (after["source"], after["path"], after["links_from"], after["frontmatter"]) == (
        before["source"], before["path"], before["links_from"], before["frontmatter"]
    )
    for field in ("title", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings"):
        assert after[field] == SCANNED_A[field]
    assert after["stale_since"] is None and after["last_indexed"] > before["last_indexed"]


def test_an_entry_not_asked_for_is_ignored_and_a_missing_one_is_skipped(corpus_stale):   # Review Focus 5
    r = apply_scan([{"source": "docs", "files": ["a.md", "b.md"], "entries": [SCANNED_A, SCANNED_UNASKED], "error": None}], corpus_stale.path)
    assert r["enriched"] == ["docs:a.md"] and r["skipped"] == [{"id": "docs:b.md", "reason": "no scan returned for it (file unreadable or not in the source)"}]
    assert corpus_stale.entry("docs:b.md")["stale"] is True
    assert [e["id"] for e in yaml.safe_load((corpus_stale.path / "index.yaml").read_text())["entries"] if e["id"].endswith("z.md")] == []


def test_a_failed_scan_skips_its_whole_batch_with_the_reason(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["a.md", "b.md"], "entries": [], "error": "no_exit"}], corpus_stale.path)
    assert r == {"enriched": [], "skipped": [{"id": "docs:a.md", "reason": "no_exit"}, {"id": "docs:b.md", "reason": "no_exit"}]}
    assert corpus_stale.entry("docs:a.md")["stale"] is True


def test_a_batch_with_an_error_enriches_nothing_even_if_it_carries_entries(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": "interrupted"}], corpus_stale.path)
    assert r == {"enriched": [], "skipped": [{"id": "docs:a.md", "reason": "interrupted"}]}
    assert corpus_stale.entry("docs:a.md")["summary"] == "The file a.md."


def test_batches_are_merged_each_on_its_own(corpus_stale):
    r = apply_scan([
        {"source": "docs", "files": ["a.md"], "entries": [SCANNED_A], "error": None},
        {"source": "docs", "files": ["b.md"], "entries": [], "error": "invalid_output"},
    ], corpus_stale.path)
    assert r == {"enriched": ["docs:a.md"], "skipped": [{"id": "docs:b.md", "reason": "invalid_output"}]}


def test_a_file_the_index_has_no_entry_for_is_skipped(corpus_stale):
    r = apply_scan([{"source": "docs", "files": ["z.md"], "entries": [SCANNED_UNASKED], "error": None}], corpus_stale.path)
    assert r == {"enriched": [], "skipped": [{"id": "docs:z.md", "reason": "no entry in the index"}]}


def test_an_entry_without_path_is_found_by_id_and_given_its_path(corpus_stale):                 # R11
    corpus_stale.add_entry({"id": "docs:guide/c.md", "source": "docs", "title": "C", "summary": "Old.", "tags": ["old"], "stale": True})
    r = apply_scan([{"source": "docs", "files": ["guide/c.md"], "entries": [scanned("guide/c.md", "C, rescanned.")], "error": None}], corpus_stale.path)
    after = corpus_stale.entry("docs:guide/c.md")
    assert r["enriched"] == ["docs:guide/c.md"] and after["path"] == "guide/c.md" and after["summary"] == "C, rescanned."
    assert after["stale"] is False and after["stale_since"] is None and after["id"] == "docs:guide/c.md"


def test_nothing_enriched_leaves_the_index_file_alone(corpus_stale):
    index = corpus_stale.path / "index.yaml"
    before = index.stat().st_mtime_ns, index.read_bytes()
    apply_scan([{"source": "docs", "files": ["a.md"], "entries": [], "error": "no_exit"}], corpus_stale.path)
    assert (index.stat().st_mtime_ns, index.read_bytes()) == before


def polars_on_main(tmp_path: Path) -> Path | None:
    """The Polars index as `origin/main` of the owner's corpus clone has it, copied into `tmp_path`; read only."""
    shown = subprocess.run(["git", "-C", str(CLONE), "show", f"origin/main:{INDEX}"], capture_output=True, text=True)
    if shown.returncode:
        return None
    copy = tmp_path / "main" / "index.yaml"
    copy.parent.mkdir()
    copy.write_text(shown.stdout)
    return copy


def polars_working_copy(tmp_path: Path) -> Path | None:
    if not POLARS.is_file():
        return None
    copy = tmp_path / "working" / "index.yaml"
    copy.parent.mkdir()
    shutil.copy(POLARS, copy)
    return copy


def either_polars(tmp_path: Path, which: str) -> Path:
    copy = (polars_on_main if which == "main" else polars_working_copy)(tmp_path)
    if copy is None:
        pytest.skip(f"the {which} version of the Polars index is not on this machine")
    return copy


@pytest.mark.parametrize("which", ["main", "working"])
def test_an_unchanged_polars_index_is_written_back_byte_identical(tmp_path, which):               # R12
    copy = either_polars(tmp_path, which)
    before = copy.read_bytes()
    write_entries(copy, {})
    assert copy.read_bytes() == before
    r = apply_scan([{"source": "polars", "files": ["index.md"], "entries": [], "error": "no_exit"}], copy.parent)
    assert r["enriched"] == [] and copy.read_bytes() == before


@pytest.mark.parametrize("which", ["main", "working"])
def test_merging_into_the_polars_index_changes_only_the_scanned_entry(tmp_path, which):
    copy = either_polars(tmp_path, which)
    before_text = copy.read_text()
    before = load_index(copy)
    r = apply_scan([{"source": "polars", "files": ["index.md"], "entries": [scanned("index.md", "Rescanned.")], "error": None}], copy.parent)
    after = load_index(copy)
    assert r == {"enriched": ["polars:index.md"], "skipped": []}
    assert after["meta"] == before["meta"] and after["entries"][1:] == before["entries"][1:]
    assert after["entries"][0]["path"] == "index.md" and after["entries"][0]["summary"] == "Rescanned."
    changed = [d for d in difflib.unified_diff(before_text.splitlines(), copy.read_text().splitlines(), lineterm="", n=0) if d[0] in "+-" and d[:3] not in ("+++", "---")]
    assert 0 < len(changed) < 40, f"{len(changed)} lines changed"


def test_an_updated_entry_is_written_in_the_layout_of_the_file(tmp_path):
    copy = either_polars(tmp_path, "main")
    apply_scan([{"source": "polars", "files": ["index.md"], "entries": [scanned("index.md", "Rescanned.")], "error": None}], copy.parent)
    lines = copy.read_text().splitlines()
    first = lines.index("  - id: polars:index.md")
    assert lines[first + 1] == "    source: polars" and "      - rescanned" in lines[first : first + 40]   # indented sequences, entries two in
    assert any(line.startswith("    summary: Rescanned.") for line in lines[first : first + 40])


# --- drop_missing: the entries whose files git says are gone from the source -------------------------------------------

def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "-C", str(cwd), *args],
        capture_output=True, text=True, check=True,
    )
    return r.stdout.strip()


def _checkout(corpus) -> Path:
    return corpus.path / ".source" / "docs"


def _settle(corpus, status: str = "updated") -> list[dict]:
    """Commit what the worktree of the checkout holds, as the head the corpus has indexed (`last_commit_sha`): the state after
    a refresh that went well. What the refresh reported for the source: `[{"id": "docs", "status": status}]`."""
    _git(_checkout(corpus), "add", "-A")
    _git(_checkout(corpus), "commit", "-q", "--allow-empty", "-m", "test")
    corpus.set_last_sha(_git(_checkout(corpus), "rev-parse", "HEAD"))
    return [{"id": "docs", "status": status}]


def _only_live_entries(corpus) -> None:
    """The index without `docs:c.md`, which upstream deleted: every entry left has its file at the head."""
    corpus._edit("index.yaml", lambda d: d["entries"].__delitem__(2), "test: no c.md")


def _blocks(text: str) -> list[str]:
    """`index.yaml` as its head and then one string for each entry, each ending at its last line."""
    return re.split(r"(?m)^(?=- id: )", text)


def test_an_entry_whose_file_is_gone_is_removed_and_nothing_else_changes(corpus_stale):
    index = corpus_stale.path / "index.yaml"
    (_checkout(corpus_stale) / "docs" / "a.md").unlink()   # the first of three entries; c.md is not in the checkout either
    sources = _settle(corpus_stale)
    before = index.read_text()
    assert drop_missing(sources, corpus_stale.path) == {"removed": ["docs:a.md", "docs:c.md"]}
    head, a, b, c = _blocks(before)
    assert a.startswith("- id: docs:a.md") and b.startswith("- id: docs:b.md") and c.startswith("- id: docs:c.md")
    assert index.read_text() == head.replace("entry_count: 3", "entry_count: 1") + b
    assert [e["id"] for e in load_index(index)["entries"]] == ["docs:b.md"]


def test_index_md_is_rendered_again_when_something_went(corpus_stale):
    index_md = corpus_stale.path / "index.md"
    assert "`docs:c.md`" in index_md.read_text()
    drop_missing(_settle(corpus_stale), corpus_stale.path)
    text = index_md.read_text()
    assert "`docs:c.md`" not in text and "`docs:a.md`" in text and "Entries: 2 " in text


def test_nothing_removed_leaves_index_md_and_index_yaml_alone(corpus_stale):
    _only_live_entries(corpus_stale)
    sources = _settle(corpus_stale)
    index, index_md = corpus_stale.path / "index.yaml", corpus_stale.path / "index.md"
    before = (index.read_bytes(), index_md.stat().st_mtime_ns, index_md.read_bytes())
    assert drop_missing(sources, corpus_stale.path) == {"removed": []}
    assert (index.read_bytes(), index_md.stat().st_mtime_ns, index_md.read_bytes()) == before


def test_removing_every_entry_leaves_an_empty_list(corpus_stale):
    corpus_stale._edit("index.yaml", lambda d: d["entries"].__delitem__(1), "test: no b.md")   # b.md is in the source, not in the index
    (_checkout(corpus_stale) / "docs" / "a.md").unlink()
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:a.md", "docs:c.md"]}
    text = (corpus_stale.path / "index.yaml").read_text()
    assert "entries: []\n" in text and load_index(corpus_stale.path / "index.yaml")["entries"] == []
    assert load_index(corpus_stale.path / "index.yaml")["meta"]["entry_count"] == 0
    assert "Entries: 0 " in (corpus_stale.path / "index.md").read_text()


def test_only_the_ids_removed_from_the_file_are_returned(corpus_stale):
    index = corpus_stale.path / "index.yaml"
    (_checkout(corpus_stale) / "docs" / "a.md").unlink()
    text = index.read_text().replace("- id: docs:c.md", "# a comment the entries stop at\n- id: docs:c.md")   # what follows it is not an entry block
    index.write_text(text)
    corpus_stale._save("test: a comment")
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:a.md"]}
    assert "- id: docs:c.md" in index.read_text()


def test_a_source_that_is_not_checked_out_removes_nothing(corpus):   # the refresh failed or never cloned it
    index = corpus.path / "index.yaml"
    before = index.read_bytes()
    assert not (corpus.path / ".source").exists()
    assert drop_missing([{"id": "docs", "status": "updated"}], corpus.path) == {"removed": []}
    assert index.read_bytes() == before


def _sparse_without_docs(corpus) -> None:
    """A clone that is a git repository at the head, as `git clone --sparse` leaves it when `sparse-checkout set docs` has not run:
    only the root of the tree is there."""
    shutil.rmtree(_checkout(corpus))
    _git(corpus.path, "clone", "-q", "--filter=blob:none", "--sparse", "--depth=50", "--branch", "main", str(corpus.upstream), str(_checkout(corpus)))
    assert not (_checkout(corpus) / "docs" / "a.md").exists()


def _empty_directory(corpus) -> None:
    shutil.rmtree(_checkout(corpus))
    _checkout(corpus).mkdir()


def _no_git_directory(corpus) -> None:
    shutil.rmtree(_checkout(corpus) / ".git")


def _behind(corpus) -> None:
    """A checkout one commit behind the head the corpus believes it has: `docs/d.md`, an entry's file, is not in it yet."""
    _git(_checkout(corpus), "checkout", "-q", corpus.first_sha)
    corpus.add_entry({"id": "docs:d.md", "source": "docs", "path": "d.md", "stale": False})


@pytest.mark.parametrize("damage", [_sparse_without_docs, _empty_directory, _no_git_directory, _behind])
def test_a_checkout_that_is_not_the_head_the_index_describes_removes_nothing(corpus_stale, damage):
    _only_live_entries(corpus_stale)
    corpus_stale.set_last_sha(corpus_stale.upstream_head)
    damage(corpus_stale)
    index = corpus_stale.path / "index.yaml"
    before = index.read_bytes()
    assert drop_missing([{"id": "docs", "status": "updated"}], corpus_stale.path) == {"removed": []}
    assert index.read_bytes() == before


def test_a_sparse_clone_with_nothing_checked_out_does_not_hide_the_files_git_has(corpus_stale):
    """The worktree is not the evidence: the tree at HEAD is. The entry whose file upstream deleted still goes."""
    corpus_stale.set_last_sha(corpus_stale.upstream_head)
    _sparse_without_docs(corpus_stale)
    assert drop_missing([{"id": "docs", "status": "current"}], corpus_stale.path) == {"removed": ["docs:c.md"]}


@pytest.mark.parametrize("sha", ["short", "other"])
def test_head_must_be_the_whole_last_commit_sha_of_the_source(corpus_stale, sha):
    corpus_stale.set_last_sha(corpus_stale.upstream_head)
    corpus_stale.set_last_sha(corpus_stale.upstream_head[:7] if sha == "short" else corpus_stale.first_sha)
    assert drop_missing([{"id": "docs", "status": "updated"}], corpus_stale.path) == {"removed": []}


@pytest.mark.parametrize("reported", [
    [{"id": "docs", "status": "failed"}], [{"id": "docs", "status": "skipped-manual"}], [{"id": "docs"}], [{"id": "other", "status": "updated"}], [],
])
def test_a_source_the_refresh_did_not_update_or_find_current_removes_nothing(corpus_stale, reported):
    corpus_stale.set_last_sha(corpus_stale.upstream_head)   # everything else is in order: the checkout is at the head
    assert drop_missing(reported, corpus_stale.path) == {"removed": []}


def test_a_section_entry_is_never_removed(corpus_stale):
    corpus_stale.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md"})
    corpus_stale.add_entry({"id": "docs:gone.md#intro", "source": "docs", "tier": "section", "parent": "docs:gone.md"})
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:c.md", "docs:gone.md"]}
    assert [e["id"] for e in load_index(corpus_stale.path / "index.yaml")["entries"]] == ["docs:a.md", "docs:b.md", "docs:gone.md#intro"]


def test_the_file_is_found_from_the_path_or_else_the_id_under_the_docs_root(corpus_stale):
    docs = _checkout(corpus_stale) / "docs"
    (docs / "guide").mkdir()
    (docs / "guide" / "here.md").write_text("# here\n")
    corpus_stale.add_entry({"id": "docs:guide/here.md", "source": "docs"})                         # no path: the id gives it
    corpus_stale.add_entry({"id": "docs:guide/gone.md", "source": "docs"})
    corpus_stale.add_entry({"id": "docs:odd-id", "source": "docs", "path": "guide/here.md"})       # the path wins over the id
    corpus_stale.add_entry({"id": "other:a.md", "path": "a.md"})                                  # no source `other` in config.yaml
    assert drop_missing(_settle(corpus_stale), corpus_stale.path)["removed"] == ["docs:c.md", "docs:guide/gone.md"]


@pytest.mark.parametrize("docs_root", [".", None, "./docs/.."])
def test_a_docs_root_of_dot_or_none_means_the_root_of_the_checkout(corpus_stale, docs_root):
    config = yaml.safe_load((corpus_stale.path / "config.yaml").read_text())
    config["sources"][0].pop("docs_root")
    if docs_root:
        config["sources"][0]["docs_root"] = docs_root
    (corpus_stale.path / "config.yaml").write_text(yaml.safe_dump(config))
    checkout = _checkout(corpus_stale)
    shutil.rmtree(checkout / "docs")
    (checkout / "a.md").write_text("# a\n")   # at the root, where a document of this source is
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:b.md", "docs:c.md"]}   # b.md is not there; docs/b.md would not do


def test_only_files_under_the_docs_root_count(corpus_stale):
    (_checkout(corpus_stale) / "a.md").write_text("# a, at the root, outside docs/\n")
    shutil.rmtree(_checkout(corpus_stale) / "docs")
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": []}   # nothing under docs/ at all: the source is not trusted


def test_only_git_sources_are_looked_at(corpus_stale):
    config = yaml.safe_load((corpus_stale.path / "config.yaml").read_text())
    config["sources"].append({"id": "wiki", "type": "web", "url": "https://example.com"})
    (corpus_stale.path / "config.yaml").write_text(yaml.safe_dump(config))
    (corpus_stale.path / ".source" / "wiki").mkdir()
    corpus_stale.add_entry({"id": "wiki:page", "source": "wiki", "path": "page.md"})
    sources = _settle(corpus_stale) + [{"id": "wiki", "status": "updated"}]
    assert drop_missing(sources, corpus_stale.path) == {"removed": ["docs:c.md"]}
    assert corpus_stale.entry("wiki:page")["path"] == "page.md"


GRAPH_V1 = """schema_version: 1

concepts:
  first:
    label: "First"
    entries:
      - docs:a.md
      - "docs:c.md"
      - docs:b.md   # kept
      - {id: not-an-id}
    entry_count: 3

  second:
    label: "Second"
    entries: [docs:c.md, {k: v}, docs:a.md]
  third:
    label: "Third"
    entries:
    - docs:c.md
    tags: ["t"]
  fourth:
    entries: [docs:c.md]
"""


def test_the_removed_ids_leave_the_entry_lists_of_graph_yaml_and_nothing_else_does(corpus_stale):
    graph = corpus_stale.path / "graph.yaml"
    graph.write_text(GRAPH_V1)
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:c.md"]}
    expected = (
        GRAPH_V1.replace('      - "docs:c.md"\n', "").replace("[docs:c.md, {k: v}, docs:a.md]", "[{k: v}, docs:a.md]")
        .replace("    entries:\n    - docs:c.md\n", "    entries: []\n").replace("[docs:c.md]", "[]")
    )
    assert graph.read_text() == expected
    assert yaml.safe_load(expected)["concepts"]["third"]["entries"] == []


def test_a_graph_without_entry_lists_is_left_alone(corpus_stale):
    graph = corpus_stale.path / "graph.yaml"
    before = (graph.stat().st_mtime_ns, graph.read_bytes())
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:c.md"]}
    assert (graph.stat().st_mtime_ns, graph.read_bytes()) == before
    (corpus_stale.path / "graph.yaml").unlink()
    corpus_stale.add_entry({"id": "docs:gone.md", "source": "docs", "path": "gone.md"})
    assert drop_missing(_settle(corpus_stale), corpus_stale.path) == {"removed": ["docs:gone.md"]}   # and no graph.yaml at all is not an error


@pytest.mark.parametrize("which", ["main", "working"])
def test_dropping_from_the_polars_index_removes_only_the_lines_of_the_entry(tmp_path, which):
    copy = either_polars(tmp_path, which)
    corpus = copy.parent
    shutil.copy(CLONE / "hiivmind-corpus-polars" / "config.yaml", corpus / "config.yaml")
    config = yaml.safe_load((corpus / "config.yaml").read_text())
    source = next(s for s in config["sources"] if s["id"] == "polars")
    entries = load_index(copy)["entries"]
    kept = [e for e in entries if e["id"] != "polars:index.md" and e.get("tier") != "section"]
    checkout = corpus / ".source" / "polars"
    for entry in kept:
        target = checkout / source["docs_root"] / (entry.get("path") or entry["id"].removeprefix("polars:"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x")
    _git(checkout.parent, "init", "-q", str(checkout))
    _git(checkout, "add", "-A")
    _git(checkout, "commit", "-q", "-m", "test")
    source["last_commit_sha"] = _git(checkout, "rev-parse", "HEAD")
    (corpus / "config.yaml").write_text(yaml.safe_dump(config))
    shutil.copy(RENDER_INDEX, corpus / "render-index.sh")
    before = copy.read_text()
    assert drop_missing([{"id": "polars", "status": "updated"}], corpus) == {"removed": ["polars:index.md"]}
    parts = re.split(r"(?m)^(?= *- id: )", before)   # the head, then the entries, each ending at its last line
    [gone] = [i for i, part in enumerate(parts) if part.lstrip().startswith("- id: polars:index.md\n")]
    after = copy.read_text()
    count = f"entry_count: {len(entries) - 1}"
    assert after == re.sub(r"entry_count: \d+", count, "".join(parts[:gone] + parts[gone + 1:]), count=1)
