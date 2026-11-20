"""The three v1 corpus layouts (flyio's bare GREP, atproto's dates, htmx's table), built with files only."""

from pathlib import Path

V1_INDEXES = {
    "bullets": {
        "index.md": (
            "# Test Documentation Corpus\n\n> Two files.\n\n---\n\n## Basics\n\n"
            "- **Alpha** `docs:a.md` - The file a.md, in v1.\n"
            "- **Beta** (2023-06-08) `docs:b.md` ⚡ GREP - The file b.md, in v1.\n"
        ),
    },
    "tiered": {
        "index.md": (
            "# Test Documentation Corpus\n\n---\n\n## Quick Reference\n\n### Start here\n"
            "- **Alpha** `docs:a.md` - Alpha, in short.\n\n---\n\n"
            "## The Guide\n*The guide to the test documents.*\n\n→ See [index-guide.md](index-guide.md)\n"
        ),
        "index-guide.md": (
            "# Guide - Detailed Index\n\n> Back to [main index](index.md)\n\n---\n\n## Basics\n\n"
            "- **Alpha** `docs:a.md` - The file a.md, in v1.\n"
            "  Keywords: `alpha`\n"
            "- **Beta** `docs:b.md` - The file b.md, in v1. ⚡ GREP - `grep -n \"^## \" FILE` ⏳ STALE\n"
        ),
    },
    "table": {
        "index.md": (
            "# Test Documentation Index\n\n## Files\n\n| Topic | File | Description |\n|-------|------|-------------|\n"
            "| `Alpha` | `a.md` | The file a.md, in v1. |\n| Beta | `b.md` | The file b.md, with `code` in v1. |\n\n"
            "## Glossary\n\n| Term | Description | Spec |\n|------|-------------|------|\n| **PDS** | A server | `specs/account` |\n"
        ),
    },
}

CONFIG = """\
schema_version: 2
corpus:
  name: test
  display_name: Test
  created_at: "2026-01-01T00:00:00Z"
  keywords: [test]
sources:
  - id: docs
    type: git
    repo_url: https://example.invalid/docs.git
    branch: main
    last_commit_sha: 5eaa000000000000000000000000000000000000
    last_indexed_at: "2026-01-01T00:00:00Z"
index:
  format: markdown
  last_updated_at: "2026-01-01T00:00:00Z"
settings:
  include_patterns: ["**/*.md"]
  exclude_patterns: ["**/_*.md"]
"""


def build_v1(root: Path, layout: str) -> Path:
    """A v1 corpus directory: config.yaml, the layout's index files, and `.source/docs/{a,b,c}.md`."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.yaml").write_text(CONFIG, encoding="utf-8")
    for name, text in V1_INDEXES[layout].items():
        (root / name).write_text(text, encoding="utf-8")
    source = root / ".source" / "docs"
    source.mkdir(parents=True)
    for name in ("a.md", "b.md", "c.md"):
        (source / name).write_text(f"# {name}\n\nFirst version of {name}.\n", encoding="utf-8")
    return root
