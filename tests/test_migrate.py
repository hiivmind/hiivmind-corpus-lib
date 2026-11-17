"""`migrate_index`: a v1 corpus (`index.md`, `index-*.md`) to stale v2 entries, rendered by the package's `render-index.sh`,
with the ids checked against the original files by an extraction that does not use the parser (design §4.4)."""

import shutil

import pytest
import yaml

import hiivmind_corpus.migrate as migrate
from corpus_fixture import RENDER_INDEX
from hiivmind_corpus.migrate import MigrationError, migrate_index, parse_v1_line

NOW = "2026-11-17T00:00:00Z"
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
def test_parse_v1_line_reads_the_forms_found(line, expected):        # example 7b, CJW-9, CJW-10
    found = parse_v1_line(line, ["docs"], EXTENSIONS)
    assert found == (expected and {**expected, "source": "docs"})


def entries(corpus) -> dict[str, dict]:
    return {e["id"]: e for e in yaml.safe_load((corpus.path / "index.yaml").read_text())["entries"]}


def config(corpus) -> dict:
    return yaml.safe_load((corpus.path / "config.yaml").read_text())


def lost_id_file(corpus, path: str, id: str) -> None:
    """A committed corpus file outside the index that names `id`."""
    corpus.write(path, f"# Notes\n\nSee `{id}`.\n")
    corpus._save("test: a file that names an id")


def test_a_bullet_corpus_migrates_to_stale_v2_entries(corpus_v1_bullets):
    result = migrate_index(corpus_v1_bullets.path, NOW)
    assert result == {"migrated": 2, "migrate_skipped": [], "strategy": "single", "sections": []}
    found = entries(corpus_v1_bullets)
    assert {id: (e["title"], e["summary"]) for id, e in found.items()} == {
        "docs:a.md": ("Alpha", "The file a.md, in v1."), "docs:b.md": ("Beta", "The file b.md, in v1."),   # CJW-8
    }
    assert all(e["stale"] is True and e["stale_since"] == NOW and e["category"] == "unknown" for e in found.values())
    assert found["docs:a.md"]["tags"] == ["basics"]
    assert (corpus_v1_bullets.path / "render-index.sh").read_bytes() == migrate.RENDER_TEMPLATE.read_bytes()
    rendered = (corpus_v1_bullets.path / "index.md").read_text()
    assert "Generated from `index.yaml`" in rendered and "- **Alpha** `docs:a.md` - The file a.md, in v1. ⏳ STALE" in rendered
    assert config(corpus_v1_bullets)["render"] == {"strategy": "single"} and config(corpus_v1_bullets)["index"]["last_updated_at"] == NOW


def test_a_tiered_corpus_records_its_sections(corpus_v1_tiered):
    result = migrate_index(corpus_v1_tiered.path, NOW)
    assert result["strategy"] == "tiered" and result["sections"] == ["guide"] and result["migrated"] == 2
    assert config(corpus_v1_tiered)["render"] == {
        "strategy": "tiered",
        "sections": [{"id": "guide", "title": "Guide", "description": "The guide to the test documents."}],
        "quick_reference": ["docs:a.md"],
    }
    assert entries(corpus_v1_tiered)["docs:b.md"]["grep_hint"] == HINT
    assert "docs:b.md" in (corpus_v1_tiered.path / "index-guide.md").read_text()


def test_a_quick_reference_duplicate_keeps_the_sub_index_line(corpus_v1_tiered):   # Review Focus 3
    migrate_index(corpus_v1_tiered.path, NOW)
    [a] = [e for e in yaml.safe_load((corpus_v1_tiered.path / "index.yaml").read_text())["entries"] if e["id"] == "docs:a.md"]
    assert a["section"] == "guide" and a["summary"] == "The file a.md, in v1."


def test_a_table_corpus_migrates(corpus_v1_table):                     # CJW-10
    result = migrate_index(corpus_v1_table.path, NOW)
    assert result["migrated"] == 2
    assert {id: (e["title"], e["summary"]) for id, e in entries(corpus_v1_table).items()} == {
        "docs:a.md": ("Alpha", "The file a.md, in v1."), "docs:b.md": ("Beta", "The file b.md, with `code` in v1."),
    }


def test_a_missing_file_is_skipped_with_its_reason(corpus_v1_bullets):
    corpus_v1_bullets.write("index.md", (corpus_v1_bullets.path / "index.md").read_text() + "- **Zed** `docs:z.md` - Gone.\n")
    corpus_v1_bullets._save("test: an entry whose file is missing")
    result = migrate_index(corpus_v1_bullets.path, NOW)
    assert result["migrate_skipped"] == [{"id": "docs:z.md", "reason": "file-missing"}] and result["migrated"] == 2
    assert "docs:z.md" not in entries(corpus_v1_bullets)


def test_ids_the_parser_does_not_read_fail_the_migration_and_write_nothing(corpus_v1_bullets):   # CJW-4, example 7
    lost_id_file(corpus_v1_bullets, "sections/extra.md", "docs:c.md")
    with pytest.raises(MigrationError, match=r"^ids lost in migration: docs:c\.md$"):
        migrate_index(corpus_v1_bullets.path, NOW)
    assert corpus_v1_bullets.git("status", "--porcelain") == "" and not (corpus_v1_bullets.path / "index.yaml").exists()


def test_an_id_in_another_md_file_fails_the_migration_and_writes_nothing(corpus_v1_bullets):    # Review Focus 1
    lost_id_file(corpus_v1_bullets, "skills/x/SKILL.md", "docs:q.md")
    with pytest.raises(MigrationError, match="docs:q.md"):
        migrate_index(corpus_v1_bullets.path, NOW)
    assert corpus_v1_bullets.git("status", "--porcelain") == ""


def test_an_id_in_another_md_file_that_is_migrated_is_not_lost(corpus_v1_bullets):
    lost_id_file(corpus_v1_bullets, "skills/x/SKILL.md", "docs:a.md")
    assert migrate_index(corpus_v1_bullets.path, NOW)["migrated"] == 2


def test_a_table_path_outside_the_index_files_is_not_an_id(corpus_v1_bullets):   # better-auth's and flyio's CLAUDE.md
    corpus_v1_bullets.write("CLAUDE.md", "| File | Purpose |\n|---|---|\n| `data/index.md` | The index |\n")
    corpus_v1_bullets._save("test: a CLAUDE.md with a table of files")
    assert migrate_index(corpus_v1_bullets.path, NOW)["migrated"] == 2


def test_a_table_path_in_an_index_file_the_parser_does_not_read_is_lost(corpus_v1_bullets):
    corpus_v1_bullets.write("index.md", (corpus_v1_bullets.path / "index.md").read_text() + "\n| `c.md` | `b.md` | two paths |\n")
    corpus_v1_bullets._save("test: a table row with two paths, which the parser does not read")
    with pytest.raises(MigrationError, match=r"^ids lost in migration: docs:c\.md$"):
        migrate_index(corpus_v1_bullets.path, NOW)


def test_a_render_failure_restores_every_file(corpus_v1_tiered, monkeypatch, tmp_path):        # CJW-5, example 7c
    failing = tmp_path / "failing-render.sh"
    failing.write_text('#!/usr/bin/env bash\necho half > index.md\necho half > index-guide.md\necho "no yq here" >&2\nexit 1\n')
    monkeypatch.setattr(migrate, "RENDER_TEMPLATE", failing)
    before = {name: (corpus_v1_tiered.path / name).read_text() for name in ("index.md", "index-guide.md", "config.yaml")}
    with pytest.raises(MigrationError, match="^render-index.sh failed: no yq here"):
        migrate_index(corpus_v1_tiered.path, NOW)
    assert corpus_v1_tiered.git("status", "--porcelain") == ""
    assert {name: (corpus_v1_tiered.path / name).read_text() for name in before} == before


def test_a_failed_migration_restores_the_corpus_own_render_script(corpus_v1_bullets):           # Review Focus 2
    shutil.copy(RENDER_INDEX, corpus_v1_bullets.path / "render-index.sh")
    lost_id_file(corpus_v1_bullets, "sections/extra.md", "docs:c.md")
    with pytest.raises(MigrationError):
        migrate_index(corpus_v1_bullets.path, NOW)
    assert (corpus_v1_bullets.path / "render-index.sh").read_bytes() == RENDER_INDEX.read_bytes()
    assert corpus_v1_bullets.git("status", "--porcelain") == ""


def test_a_v2_corpus_is_refused(corpus):
    with pytest.raises(MigrationError, match="^index.yaml exists — nothing to migrate$"):
        migrate_index(corpus.path, NOW)


def test_a_failure_before_the_render_runs_restores_every_file(corpus_v1_bullets, monkeypatch, tmp_path):   # final review 1
    monkeypatch.setattr(migrate, "RENDER_TEMPLATE", tmp_path / "no-such-render-index.sh")   # the copy raises
    with pytest.raises(FileNotFoundError):
        migrate_index(corpus_v1_bullets.path, NOW)
    assert corpus_v1_bullets.git("status", "--porcelain") == "" and not (corpus_v1_bullets.path / "index.yaml").exists()
