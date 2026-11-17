"""`migrate_index`: a v1 corpus (`index.md` and `index-*.md`) to v2 (`index.yaml`), as the plugin's `migrate` Phases 1, 2, 3
(resolution only) and 5 do it, as code. Each entry is written stale, with its v1 title and summary: the `scan` node writes
the rest of its metadata from the file.

The ids are checked against the original files by an extraction that does not use the parser (`v1_ids`). A lost id or a
render failure puts back every file the migration wrote or overwrote, then raises `MigrationError`.
"""

import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from hiivmind_corpus.refresh import _block, _set

RENDER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "render-index.sh"
DEFAULT_EXTENSIONS = (".md", ".mdx")
TIMEOUT = 120   # seconds for the render

BULLET = re.compile(r"^\s*- \*\*(?P<title>.+?)\*\*(?: \((?P<date>\d{4}-\d{2}-\d{2})\))? `(?P<id>[^`]+)` (?P<rest>.*)$")
REST = re.compile(r"^(?:⚡ GREP )?- (?P<summary>.*)$")   # `- summary`, or flyio's bare `⚡ GREP - summary`
STALE = " ⏳ STALE"
TRAILING_HINT = re.compile(r"\s*⚡ GREP - `(?P<hint>[^`]*)`$")
TOKEN = re.compile(r"`([^`\n]+)`")
DETAILED = re.compile(r"\s+[-–—]\s+Detailed Index\s*$")


class MigrationError(RuntimeError):
    """The migration refused, or failed and put every file back."""


def _slug(text: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


def _cells(line: str) -> list[str] | None:
    """The cells of a markdown table row, stripped; None for any other line, and for a separator row."""
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1):
        return None
    cells = [cell.strip() for cell in stripped[1:-1].split("|")]
    return None if all(re.fullmatch(r":?-+:?", cell) for cell in cells) else cells


def _cell_path(cell: str, extensions: tuple[str, ...]) -> str | None:
    """The path of a cell that is one backticked path ending in an included extension."""
    found = re.fullmatch(r"`([^`]+)`", cell)
    return found.group(1) if found and found.group(1).endswith(extensions) else None


def _id_of(token: str, source_ids: list[str]) -> tuple[str, str] | None:
    """`(source, path)` of a `<source>:<path>` token whose source is one of `source_ids`."""
    source, colon, path = token.partition(":")
    return (source, path) if colon and path and source in source_ids else None


def parse_v1_line(line: str, source_ids: list[str], extensions: tuple[str, ...]) -> dict | None:
    """The entry a v1 line names, `{"id", "source", "path", "title", "summary", "grep_hint", "stale"}`; None for any other line.

    A bullet: `- **<title>**`, an optional `(<date>)`, the backticked `<source>:<path>`, then `- <summary>`, with the optional
    markers ` ⚡ GREP - `<hint>`` and ` ⏳ STALE` after it, or a bare `⚡ GREP` before the `-` (no hint). A table row, only in a
    corpus with one source: exactly one cell is a backticked path ending in an included extension; the title is the first
    cell without its backticks, the summary the last cell."""
    bullet = BULLET.match(line.rstrip("\n"))
    if bullet:
        named, rest = _id_of(bullet.group("id"), source_ids), REST.match(bullet.group("rest"))
        if not named or not rest:
            return None
        summary, stale = rest.group("summary").rstrip(), False
        if summary.endswith(STALE.strip()):
            summary, stale = summary[: -len(STALE.strip())].rstrip(), True
        hint = TRAILING_HINT.search(summary)
        if hint:
            summary = summary[: hint.start()].rstrip()
        source, path = named
        return {
            "id": f"{source}:{path}", "source": source, "path": path, "title": bullet.group("title").strip(),
            "summary": summary, "grep_hint": hint.group("hint") if hint else None, "stale": stale,
        }
    cells = _cells(line)
    if cells is None or len(source_ids) != 1:
        return None
    paths = [path for cell in cells if (path := _cell_path(cell, extensions))]
    if len(paths) != 1:
        return None
    named = _id_of(paths[0], source_ids)
    source, path = named or (source_ids[0], paths[0])
    return {
        "id": f"{source}:{path}", "source": source, "path": path, "title": cells[0].replace("`", "").strip(),
        "summary": cells[-1], "grep_hint": None, "stale": False,
    }


def _ids_in(text: str, source_ids: list[str], extensions: tuple[str, ...], *, tables: bool) -> set[str]:
    """Every backticked `<source>:<path>` of `text`; with `tables` and one source, also every backticked path ending in an
    included extension that is a whole table cell. Uses no part of the parser's patterns."""
    found = {f"{named[0]}:{named[1]}" for token in TOKEN.findall(text) if (named := _id_of(token, source_ids))}
    if tables and len(source_ids) == 1:
        for line in text.splitlines():
            for cell in _cells(line) or []:
                path = _cell_path(cell, extensions)
                if path and not _id_of(path, source_ids):
                    found.add(f"{source_ids[0]}:{path}")
    return found


def _markdown_files(corpus: Path) -> list[Path]:
    """Each `.md` file of the corpus, outside `.source/` and `.git/`."""
    return sorted(p for p in corpus.rglob("*.md") if p.is_file() and not {".source", ".git"} & set(p.relative_to(corpus).parts))


def v1_ids(corpus: Path, source_ids: list[str], extensions: tuple[str, ...]) -> set[str]:
    """The ids in every `.md` file of the corpus outside `.source/`: the check `migrate_index` makes against its render. A
    table cell counts only in the index files (`index.md`, `index-*.md`): elsewhere a table of paths lists the corpus's own
    files (better-auth's and flyio's `CLAUDE.md`), and nothing an index entry could be."""
    corpus = Path(corpus)
    return set().union(*(
        _ids_in(f.read_text(), source_ids, extensions, tables=f.parent == corpus and (f.name == "index.md" or f.name.startswith("index-")))
        for f in _markdown_files(corpus)
    ))


def _extensions(config: dict) -> tuple[str, ...]:
    """The suffix after the last `*` of each include pattern (`**/*.mdx` gives `.mdx`)."""
    patterns = (config.get("settings") or {}).get("include_patterns") or []
    found = tuple(dict.fromkeys(p.rsplit("*", 1)[-1] for p in patterns if "*" in p and p.rsplit("*", 1)[-1]))
    return found or DEFAULT_EXTENSIONS


def _blocks_by_heading(text: str) -> list[tuple[str, list[str]]]:
    """`(## heading, its lines)` for each `## ` block of `text`; the lines before the first heading under `""`."""
    blocks: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        if line.startswith("## "):
            blocks.append((line[3:].strip(), []))
        else:
            blocks[-1][1].append(line)
    return blocks


def _sections(corpus: Path, main: str, subs: list[Path]) -> list[dict]:
    """The section definitions, in the order the main index links to them: `id` (the file's slug), `title` (the sub-index's
    h1 without " - Detailed Index", or the main index's heading), `description` (the italic line of that heading, or "")."""
    slugs = [f.stem.removeprefix("index-") for f in subs]
    order = {slug: main.find(f"index-{slug}.md") for slug in slugs}
    slugs.sort(key=lambda s: (order[s] < 0, order[s], s))
    sections = []
    for slug in slugs:
        linking = [(h, lines) for h, lines in _blocks_by_heading(main) if h and any(f"index-{slug}.md" in line for line in lines)]
        heading, lines = linking[-1] if linking else ("", [])
        h1 = next((l[2:].strip() for l in (corpus / f"index-{slug}.md").read_text().splitlines() if l.startswith("# ")), "")
        italic = next((l.strip()[1:-1] for l in lines if re.fullmatch(r"\*[^*].*[^*]\*", l.strip())), "")
        sections.append({"id": slug, "title": DETAILED.sub("", h1) or heading or slug, "description": italic})
    return sections


def _parse(corpus: Path, source_ids: list[str], extensions: tuple[str, ...]) -> tuple[list[dict], list[str], list[dict]]:
    """The entries of the v1 files (a duplicate id keeps its sub-index line), the Quick Reference ids, the sections."""
    main = (corpus / "index.md").read_text()
    subs = sorted(corpus.glob("index-*.md"))
    sections = _sections(corpus, main, subs)
    files = [(corpus / "index.md", None)] + [(corpus / f"index-{s['id']}.md", s["id"]) for s in sections]
    found: dict[str, dict] = {}
    quick: list[str] = []
    for file, section in files:
        heading = ""
        for line in (main if section is None else file.read_text()).splitlines():
            if line.startswith("## "):
                heading = line[3:].strip()
                continue
            entry = parse_v1_line(line, source_ids, extensions)
            if not entry:
                continue
            if section is None and heading.lower() == "quick reference" and entry["id"] not in quick:
                quick.append(entry["id"])
            if entry["id"] in found and (section is None or found[entry["id"]]["section"] is not None):
                continue   # the first line of a file wins; a sub-index line replaces a main-index one
            found[entry["id"]] = {**entry, "section": section, "heading": heading}
    return list(found.values()), quick, sections


def _v2_entry(parsed: dict, now: str) -> dict:
    """A stale v2 entry with the v1 title, summary and hint. `size` is `standard` until a scan says otherwise: the renderer
    reads its fields as tab-separated values, where an empty one would shift the rest."""
    entry = {
        "id": parsed["id"], "source": parsed["source"], "path": parsed["path"], "title": parsed["title"],
        "summary": parsed["summary"], "tags": [_slug(parsed["heading"])] if _slug(parsed["heading"]) else [], "keywords": [],
        "concepts": [], "category": "unknown", "content_type": "markdown" if parsed["path"].endswith((".md", ".mdx")) else "text",
        "size": "standard", "grep_hint": parsed["grep_hint"],
    }
    if parsed["section"]:
        entry["section"] = parsed["section"]
    return entry | {
        "headings": [], "links_to": [], "links_from": [], "frontmatter": {}, "stale": True, "stale_since": now, "last_indexed": None,
    }


def _config_text(text: str, render: dict, now: str) -> str:
    """`config.yaml` with its `render:` block replaced and `index.last_updated_at` set; the other lines as they were."""
    lines = text.splitlines(keepends=True)
    old = _block(lines, "render")
    del lines[old.start : old.stop]
    if _block(lines, "index"):
        _set(lines, _block(lines, "index"), "last_updated_at", now)
    else:
        lines.append(f'index:\n  last_updated_at: "{now}"\n')
    if lines and not lines[-1].endswith("\n"):
        lines[-1] += "\n"
    return "".join(lines) + "\n" + yaml.safe_dump({"render": render}, sort_keys=False, allow_unicode=True, width=10**9)


def _snapshot(corpus: Path) -> dict[Path, tuple[bytes, int] | None]:
    """Each file the migration writes or overwrites, as it is now: `(bytes, mode)`, or None when it does not exist."""
    files = [corpus / name for name in ("index.yaml", "config.yaml", "render-index.sh", "index.md")] + sorted(corpus.glob("index-*.md"))
    return {f: (f.read_bytes(), f.stat().st_mode) if f.is_file() else None for f in files}


def _restore(corpus: Path, snapshot: dict[Path, tuple[bytes, int] | None]) -> None:
    """Put back every file of `snapshot`, and remove each sub-index the render made."""
    for f in corpus.glob("index-*.md"):
        if f not in snapshot:
            f.unlink()
    for f, kept in snapshot.items():
        if kept is None:
            f.unlink(missing_ok=True)
        else:
            f.write_bytes(kept[0])
            os.chmod(f, kept[1])


def _lost(ids: list[str]) -> str:
    more = f", … and {len(ids) - 10} more" if len(ids) > 10 else ""
    return f"ids lost in migration: {', '.join(ids[:10])}{more}"


def migrate_index(corpus: Path, now: str) -> dict:
    """Migrate the corpus's v1 index to `index.yaml`, every entry stale, and render it with the package's `render-index.sh`.

    Returns `{"migrated": <entries>, "migrate_skipped": [{"id", "reason"}], "strategy": "single" | "tiered", "sections": [ids]}`.
    Raises `MigrationError` when `index.yaml` exists, when there is no `index.md`, when no entry parses, and, after putting
    every file back, when an id of the original files is neither rendered nor skipped, or when the render fails."""
    corpus = Path(corpus)
    if (corpus / "index.yaml").exists():
        raise MigrationError("index.yaml exists — nothing to migrate")
    if not (corpus / "index.md").is_file():
        raise MigrationError("no v1 index found")
    config_text = (corpus / "config.yaml").read_text()
    config = yaml.safe_load(config_text) or {}
    sources = {s["id"]: s for s in config.get("sources") or []}
    source_ids, extensions = list(sources), _extensions(config)

    parsed, quick, sections = _parse(corpus, source_ids, extensions)
    if not parsed:
        raise MigrationError("no entries parsed")
    kept, skipped = [], []
    for entry in parsed:
        docs_root = sources[entry["source"]].get("docs_root") or ""
        if (corpus / ".source" / entry["source"] / docs_root / entry["path"]).is_file():
            kept.append(entry)
        else:
            skipped.append({"id": entry["id"], "reason": "file-missing"})
    original = v1_ids(corpus, source_ids, extensions)

    strategy = "tiered" if sections else "single"
    render: dict = {"strategy": strategy}
    if sections:
        render["sections"] = sections
    if quick:
        render["quick_reference"] = quick
    entries = [_v2_entry(e, now) for e in kept]
    index = {"meta": {"generated_at": now, "entry_count": len(entries)}, "entries": entries}

    snapshot = _snapshot(corpus)
    try:
        rendered = _write_and_render(corpus, index, _config_text(config_text, render, now), source_ids, extensions)
    except BaseException:
        _restore(corpus, snapshot)   # nothing is left half applied, whatever went wrong (P18)
        raise
    lost = sorted(original - rendered - {s["id"] for s in skipped})
    if lost:
        _restore(corpus, snapshot)
        raise MigrationError(_lost(lost))
    return {"migrated": len(entries), "migrate_skipped": skipped, "strategy": strategy, "sections": [s["id"] for s in sections]}


def _write_and_render(corpus: Path, index: dict, config_text: str, source_ids: list[str], extensions: tuple[str, ...]) -> set[str]:
    """Write `index.yaml` and `config.yaml`, copy the package's `render-index.sh` and render; the ids in the rendered files.
    A render that fails or does not finish raises `MigrationError`."""
    (corpus / "index.yaml").write_text(yaml.safe_dump(index, sort_keys=False, allow_unicode=True))
    (corpus / "config.yaml").write_text(config_text)
    shutil.copy(RENDER_TEMPLATE, corpus / "render-index.sh")
    try:
        done = subprocess.run(["bash", "./render-index.sh", "index.yaml"], cwd=corpus, capture_output=True, text=True, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise MigrationError(f"render-index.sh failed: no result after {TIMEOUT} seconds") from None
    if done.returncode:
        raise MigrationError(f"render-index.sh failed: {done.stderr.strip() or done.stdout.strip() or f'exit {done.returncode}'}")
    rendered: set[str] = set()
    for f in [corpus / "index.md", *sorted(corpus.glob("index-*.md"))]:
        rendered |= _ids_in(f.read_text(), source_ids, extensions, tables=True)
    return rendered
