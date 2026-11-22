"""The v1 parser: a v1 corpus's `index.md` and `index-*.md` read into entries (spec 7.11). Moved with its behaviour from
the old `migrate.py`; the ids are also read by an extraction that does not use the parser (`v1_ids`)."""

import re
from pathlib import Path

from ..config import Config

DEFAULT_EXTENSIONS = (".md", ".mdx")

BULLET = re.compile(r"^\s*- \*\*(?P<title>.+?)\*\*(?: \((?P<date>\d{4}-\d{2}-\d{2})\))? `(?P<id>[^`]+)` (?P<rest>.*)$")
REST = re.compile(r"^(?:⚡ GREP )?- (?P<summary>.*)$")   # `- summary`, or flyio's bare `⚡ GREP - summary`
STALE = " ⏳ STALE"
TRAILING_HINT = re.compile(r"\s*⚡ GREP - `(?P<hint>[^`]*)`$")
TOKEN = re.compile(r"`([^`\n]+)`")
DETAILED = re.compile(r"\s+[-–—]\s+Detailed Index\s*$")


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
    paths = [found for cell in cells if (found := _cell_path(cell, extensions))]
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


def _sub_indexes(corpus: Path) -> list[Path]:
    """The sub-index files, `index-<section>.md` at the corpus root: the names `render-index.sh`, the process that writes
    the index files, gives them. The v1 corpora this migrates use the same names."""
    return sorted(Path(corpus).glob("index-*.md"))


def _index_files(corpus: Path) -> list[Path]:
    """The index files as `render-index.sh` writes them: `index.md`, then each sub-index (`_sub_indexes`)."""
    return [Path(corpus) / "index.md", *_sub_indexes(corpus)]


def _markdown_files(corpus: Path) -> list[Path]:
    """Each `.md` file of the corpus, outside `.source/` and `.git/`."""
    return sorted(p for p in corpus.rglob("*.md") if p.is_file() and not {".source", ".git"} & set(p.relative_to(corpus).parts))


def v1_ids(corpus: Path, source_ids: list[str], extensions: tuple[str, ...]) -> set[str]:
    """The ids in every `.md` file of the corpus outside `.source/`: the check `migrate_index` makes against its render. A
    table cell counts only in the index files (`_index_files`): elsewhere a table of paths lists the corpus's own files
    (better-auth's and flyio's `CLAUDE.md`), and nothing an index entry could be."""
    corpus = Path(corpus)
    indexes = set(_index_files(corpus))
    return set().union(*(_ids_in(f.read_text(), source_ids, extensions, tables=f in indexes) for f in _markdown_files(corpus)))


def _extensions(config: Config) -> tuple[str, ...]:
    """The suffix after the last `*` of each include pattern (`**/*.mdx` gives `.mdx`)."""
    patterns = (config.settings.include_patterns if config.settings else None) or ()
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
        h1 = next((text[2:].strip() for text in (corpus / f"index-{slug}.md").read_text().splitlines() if text.startswith("# ")), "")
        italic = next((text.strip()[1:-1] for text in lines if re.fullmatch(r"\*[^*].*[^*]\*", text.strip())), "")
        sections.append({"id": slug, "title": DETAILED.sub("", h1) or heading or slug, "description": italic})
    return sections


def _parse(corpus: Path, source_ids: list[str], extensions: tuple[str, ...]) -> tuple[list[dict], list[str], list[dict]]:
    """The entries of the v1 files (a duplicate id keeps its sub-index line), the Quick Reference ids, the sections."""
    main = (corpus / "index.md").read_text()
    subs = _sub_indexes(corpus)
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
