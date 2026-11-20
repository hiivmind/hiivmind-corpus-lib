"""`corpus.migration`: a v1 corpus to v2 over the package's own writer and renderer (spec 7.11, MIG-1..3, E9, E10)."""

import os
from dataclasses import replace
from pathlib import Path

import pytest

from hiivmind_corpus import files
from hiivmind_corpus.config import Config
from hiivmind_corpus.corpus import Corpus
from hiivmind_corpus.errors import MigrationRefused, Refusal, WriteFailed
from hiivmind_corpus.index import Index, Skip
from hiivmind_corpus.migration import MigrationResult
from hiivmind_corpus.migration.v1 import parse_v1_line
from hiivmind_corpus.schema import NULL
from support import FIXED, GOLDEN
from v1_fixtures import build_v1

EXTENSIONS = (".md", ".mdx")
HINT = 'grep -n "^## " FILE'


@pytest.mark.parametrize("line, expected", [
    (   # flyio: a bare GREP before the summary gives the summary and no hint
        "- **fly deploy** `docs:flyctl/cmd/fly_deploy.md` ⚡ GREP - Deploy your application",
        {"id": "docs:flyctl/cmd/fly_deploy.md", "path": "flyctl/cmd/fly_deploy.md", "title": "fly deploy",
         "summary": "Deploy your application", "grep_hint": None, "stale": False},
    ),
    (   # atproto: a date after the title
        "- **Call for Developers** (2023-08-03) `docs:blog/call-for-developers/en.mdx` - Invitation for developers…",
        {"id": "docs:blog/call-for-developers/en.mdx", "path": "blog/call-for-developers/en.mdx", "title": "Call for Developers",
         "summary": "Invitation for developers…", "grep_hint": None, "stale": False},
    ),
    (   # htmx: a table row with one backticked path
        "| `hx-get` | `attributes/hx-get.md` | Issues a GET request to the specified URL |",
        {"id": "docs:attributes/hx-get.md", "path": "attributes/hx-get.md", "title": "hx-get",
         "summary": "Issues a GET request to the specified URL", "grep_hint": None, "stale": False},
    ),
    (   # atproto's glossary: no cell is a path with an included extension
        "| Account | … | `specs/account` |",
        None,
    ),
    (   # the renderer's own markers: a trailing hint
        f"- **Big** `docs:big.md` - A big file. ⚡ GREP - `{HINT}`",
        {"id": "docs:big.md", "path": "big.md", "title": "Big", "summary": "A big file.", "grep_hint": HINT, "stale": False},
    ),
    (
        "- **Old** `docs:old.md` - An old file. ⏳ STALE",
        {"id": "docs:old.md", "path": "old.md", "title": "Old", "summary": "An old file.", "grep_hint": None, "stale": True},
    ),
    (
        f"- **Big** `docs:big.md` - A big file. ⚡ GREP - `{HINT}` ⏳ STALE",
        {"id": "docs:big.md", "path": "big.md", "title": "Big", "summary": "A big file.", "grep_hint": HINT, "stale": True},
    ),
])
def test_parse_v1_line_reads_the_forms_found(line, expected):
    found = parse_v1_line(line, ["docs"], EXTENSIONS)
    assert found == (expected and {**expected, "source": "docs"})


def open_v1(tmp_path, layout="bullets") -> Corpus:
    return Corpus.open(build_v1(tmp_path / "corpus", layout), clock=lambda: FIXED)


def tree(corpus: Corpus) -> dict[str, tuple[bytes, int]]:
    return {p.relative_to(corpus.path).as_posix(): (p.read_bytes(), p.stat().st_mode)
            for p in sorted(corpus.path.rglob("*")) if p.is_file()}


def refused(corpus: Corpus, reason: Refusal, message: str) -> None:
    before = tree(corpus)
    with pytest.raises(MigrationRefused) as caught:
        corpus.migration.migrate()
    assert caught.value.code == "migration-refused" and caught.value.reason == reason
    assert str(caught.value) == message
    assert tree(corpus) == before


@pytest.mark.parametrize("layout, strategy, sections", [
    ("bullets", "single", ()), ("tiered", "tiered", ("guide",)), ("table", "single", ()),
])
def test_each_v1_fixture_migrates_to_its_golden(tmp_path, layout, strategy, sections):
    corpus = open_v1(tmp_path, layout)
    result = corpus.migration.migrate()
    assert result == MigrationResult(migrated=2, skipped=(), strategy=strategy, sections=sections)
    golden = GOLDEN / "migrated" / layout
    written = {p.name for p in corpus.path.iterdir() if p.is_file() and p.name.startswith(("index", "config"))}
    assert written == {p.name for p in golden.iterdir()}
    for path in sorted(golden.iterdir()):
        assert (corpus.path / path.name).read_text(encoding="utf-8") == path.read_text(encoding="utf-8"), path.name
    assert not (corpus.path / "render-index.sh").exists()
    config, index = corpus.config.load(), corpus.index.load()
    assert config.render.strategy == strategy and config.index.last_updated_at == FIXED
    if strategy == "tiered":
        assert "strategy: tiered" in (corpus.path / "config.yaml").read_text(encoding="utf-8")
    assert len(index.entries) == 2
    for entry in index.entries:
        assert entry.stale is True and entry.stale_since == FIXED and entry.last_indexed is NULL
        assert entry.size == "standard" and entry.category == "unknown"
    assert {e.id: (e.title, e.summary) for e in index.entries}["docs:a.md"][0] == "Alpha"


def test_a_missing_file_is_skipped(tmp_path):
    corpus = open_v1(tmp_path)
    text = (corpus.path / "index.md").read_text(encoding="utf-8") + "- **Zed** `docs:z.md` - Gone.\n"
    (corpus.path / "index.md").write_text(text, encoding="utf-8")
    result = corpus.migration.migrate()
    assert result.migrated == 2
    assert result.skipped == (Skip(id="docs:z.md", code="file-missing", reason="file-missing"),)
    assert "docs:z.md" not in {e.id for e in corpus.index.load().entries}


def test_a_quick_reference_duplicate_keeps_the_sub_index_line(tmp_path):
    corpus = open_v1(tmp_path, "tiered")
    corpus.migration.migrate()
    [a] = [e for e in corpus.index.load().entries if e.id == "docs:a.md"]
    assert a.section == "guide" and a.summary == "The file a.md, in v1."
    assert corpus.config.load().render.quick_reference == ("docs:a.md",)


def test_a_table_corpus_migrates(tmp_path):
    corpus = open_v1(tmp_path, "table")
    assert corpus.migration.migrate().migrated == 2
    assert {e.id: (e.title, e.summary) for e in corpus.index.load().entries} == {
        "docs:a.md": ("Alpha", "The file a.md, in v1."), "docs:b.md": ("Beta", "The file b.md, with `code` in v1."),
    }


def test_a_v2_corpus_is_refused(tmp_path):
    corpus = open_v1(tmp_path)
    (corpus.path / "index.yaml").write_text("entries: []\n", encoding="utf-8")
    refused(corpus, Refusal.ALREADY_V2, "index.yaml exists — nothing to migrate")


def test_no_v1_index_is_refused(tmp_path):
    corpus = open_v1(tmp_path)
    (corpus.path / "index.md").unlink()
    refused(corpus, Refusal.NO_V1_INDEX, "no v1 index found")


def test_no_entries_is_refused(tmp_path):
    corpus = open_v1(tmp_path)
    (corpus.path / "index.md").write_text("# Nothing here\n", encoding="utf-8")
    refused(corpus, Refusal.NO_ENTRIES, "no entries parsed")


def note(corpus: Corpus, path: str, text: str) -> None:
    target = corpus.path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_an_id_the_parser_does_not_read_is_lost(tmp_path):
    corpus = open_v1(tmp_path)
    note(corpus, "sections/extra.md", "# Notes\n\nSee `docs:c.md`.\n")
    refused(corpus, Refusal.IDS_LOST, "ids lost in migration: docs:c.md")


def test_the_lost_ids_are_listed_ten_and_a_count(tmp_path):
    corpus = open_v1(tmp_path)
    note(corpus, "extra.md", "".join(f"`docs:q{n:02d}.md`\n" for n in range(13)))
    ids = ", ".join(f"docs:q{n:02d}.md" for n in range(10))
    refused(corpus, Refusal.IDS_LOST, f"ids lost in migration: {ids}, … and 3 more")


def test_an_id_in_another_md_file_that_is_migrated_is_not_lost(tmp_path):
    corpus = open_v1(tmp_path)
    note(corpus, "skills/x/SKILL.md", "See `docs:a.md`.\n")
    assert corpus.migration.migrate().migrated == 2


def test_a_table_path_outside_the_index_files_is_not_an_id(tmp_path):
    corpus = open_v1(tmp_path)
    note(corpus, "CLAUDE.md", "| File | Purpose |\n|---|---|\n| `data/index.md` | The index |\n")
    assert corpus.migration.migrate().migrated == 2


def test_a_table_path_in_an_index_file_the_parser_does_not_read_is_lost(tmp_path):
    corpus = open_v1(tmp_path)
    (corpus.path / "index.md").write_text(
        (corpus.path / "index.md").read_text(encoding="utf-8") + "\n| `c.md` | `b.md` | two paths |\n", encoding="utf-8")
    refused(corpus, Refusal.IDS_LOST, "ids lost in migration: docs:c.md")


def test_a_write_failure_leaves_every_file_as_it_was(tmp_path, monkeypatch):
    corpus = open_v1(tmp_path, "tiered")
    os.chmod(corpus.path / "config.yaml", 0o444)
    before = tree(corpus)
    real, calls = os.replace, []

    def replace(src, dst, *a, **k):
        calls.append(dst)
        if len(calls) == 3:
            raise OSError("disk full")
        return real(src, dst, *a, **k)

    monkeypatch.setattr(files.os, "replace", replace)
    with pytest.raises(WriteFailed) as caught:
        corpus.migration.migrate()
    assert caught.value.unrestored == ()
    assert tree(corpus) == before and not (corpus.path / "index.yaml").exists()
