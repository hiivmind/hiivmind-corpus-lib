"""`stale_files`, `apply_scan` and `drop_missing`: which files of the index are stale, the merge of the scans of them into
`index.yaml`, and the removal of the entries whose files are gone from the source.

`apply_scan` is `enrich-headless` Phase 2's merge as code. It is the only writer of `index.yaml` while the scans, which run
at the same time and change nothing, are going on.
"""

import posixpath
import re
import subprocess
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPLACED = ("title", "summary", "tags", "keywords", "category", "content_type", "size", "grep_hint", "headings")
NOT_RETURNED = "no scan returned for it (file unreadable or not in the source)"
NOT_INDEXED = "no entry in the index"


def load_index(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


ENTRY_START = re.compile(r"^( *)- ")


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _split(text: str) -> tuple[list[str], list[list[str]], list[str]]:
    """The lines of an index file as `(head, entry blocks, tail)`: `head` runs to the first entry, `tail` starts at the first
    line after the entries that is not one of them. Entries are the items of the `entries:` list, at whatever indent it has."""
    lines = text.splitlines(keepends=True)
    after = next((i + 1 for i, line in enumerate(lines) if line.rstrip() == "entries:"), len(lines))
    first = next((i for i in range(after, len(lines)) if ENTRY_START.match(lines[i])), len(lines))
    base = _indent(lines[first]) if first < len(lines) else 0
    blocks: list[list[str]] = []
    end = len(lines)
    for i in range(first, len(lines)):
        line = lines[i]
        if ENTRY_START.match(line) and _indent(line) == base:
            blocks.append([line])
        elif line.strip() and _indent(line) <= base:
            end = i
            break
        else:
            blocks[-1].append(line)
    return lines[:first], blocks, lines[end:]


def _renderer(blocks: list[list[str]]):
    """A function that writes one entry in the layout the file has: its indent, whether a list under a key is indented, and
    whether long text is wrapped (at 80, as PyYAML does) or left on one line."""
    base = _indent(blocks[0][0]) if blocks else 0
    lines = [line for block in blocks for line in block]
    nested = any(
        prev.rstrip().endswith(":") and line.lstrip().startswith("- ") and _indent(line) > _indent(prev)
        for prev, line in zip(lines, lines[1:])
    )
    width = 4096 if any(len(line) > 120 for line in lines) else 80

    class Dumper(yaml.SafeDumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False if nested else indentless)

    def render(entry: dict) -> list[str]:
        dumped = yaml.dump([entry], Dumper=Dumper, sort_keys=False, allow_unicode=True, width=width)
        return textwrap.indent(dumped, " " * base).splitlines(keepends=True)

    return render


def write_entries(path: Path, changed: dict[str, dict]) -> None:
    """Rewrite the entries of the index file at `path` whose id is in `changed`, and nothing else: every other line, and the
    layout (indent, list style, line wrapping) the file has, stay as they are. No entry changed leaves the file untouched."""
    if not changed:
        return
    text = path.read_text()
    head, blocks, tail = _split(text)
    render = _renderer(blocks)
    out = list(head)
    for block in blocks:
        entry = yaml.safe_load("".join(block))[0]
        out += render(changed[entry["id"]]) if entry["id"] in changed else block
    path.write_text("".join(out + tail))


def _without(text: str, ids: set[str]) -> tuple[str, list[str]]:
    """The index file `text` without the entries whose id is in `ids`, and the ids it did remove: only the lines of those
    entries go, and `meta.entry_count` becomes the number left. An emptied list stays `entries: []`. Nothing removed: `text` as it is."""
    head, blocks, tail = _split(text)
    kept, removed = [], []
    for block in blocks:
        id = yaml.safe_load("".join(block))[0]["id"]
        if id in ids:
            removed.append(id)
        else:
            kept.append(block)
    if not removed:
        return text, []
    head = [re.sub(r"^( +entry_count: *)\d+", rf"\g<1>{len(kept)}", line, count=1) for line in head]
    if not kept:   # `entries:` with nothing under it would be null
        last = max(i for i, line in enumerate(head) if line.rstrip() == "entries:")
        head[last] = head[last].replace("entries:", "entries: []")
    return "".join(head + [line for block in kept for line in block] + tail), removed


def _source_of(entry: dict) -> str:
    return entry.get("source") or str(entry["id"]).partition(":")[0]


def _path_of(entry: dict) -> str:
    """The entry's `path`, or, when it has none (most of Polars's), its id without the `<source>:` prefix."""
    return entry.get("path") or str(entry["id"]).removeprefix(f"{_source_of(entry)}:")


def stale_files(corpus: Path) -> dict:
    """The file entries of the index marked stale: `by_source` (source id to relative paths) and `entry_ids`.

    A section entry (`tier: section`) is not a file to scan: its parent file is re-scanned when stale, and a section keeps
    its line range until the next build, as `enrich-headless` does.
    """
    entries = load_index(Path(corpus) / "index.yaml").get("entries") or []
    by_source: dict[str, list[str]] = {}
    ids: list[str] = []
    for entry in entries:
        if entry.get("stale") is True and entry.get("tier") != "section":
            by_source.setdefault(_source_of(entry), []).append(_path_of(entry))
            ids.append(entry["id"])
    return {"by_source": by_source, "entry_ids": ids}


def apply_scan(scans: list, corpus: Path) -> dict:
    """Merge the scans into `index.yaml`.

    `scans` has one item for each scan run, done or not: `{"source": str, "files": [str], "entries": [dict], "error": str | None}`.
    For each file of a batch: its entry is skipped with the batch's `error` as the reason if there is one; else updated from the
    scanned entry whose `path` is that file; else skipped with the reason `no scan returned for it (file unreadable or not in
    the source)`. A scanned entry for a file the batch did not ask for is ignored. An updated entry takes the nine scanned fields and keeps `id`, `source`, `links_to`,
    `links_from`, `frontmatter` and `concepts`; `path` is set; `stale` is false, `stale_since` null, `last_indexed` now.

    Returns `enriched` (entry ids) and `skipped` (`id`, `reason`).
    """
    index_file = Path(corpus) / "index.yaml"
    index = load_index(index_file)
    by_id = {entry["id"]: entry for entry in index.get("entries") or []}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    enriched: list[str] = []
    skipped: list[dict] = []
    for batch in scans:
        returned = {e.get("path"): e for e in reversed(batch.get("entries") or [])}   # the first of a file's entries wins
        for file in batch.get("files") or []:
            id = f"{batch['source']}:{file}"
            entry = by_id.get(id)
            if batch.get("error"):
                skipped.append({"id": id, "reason": batch["error"]})
            elif entry is None:
                skipped.append({"id": id, "reason": NOT_INDEXED})
            elif file not in returned:
                skipped.append({"id": id, "reason": NOT_RETURNED})
            else:
                for field in REPLACED:
                    entry[field] = returned[file].get(field)
                entry["path"] = file
                entry["stale"], entry["stale_since"], entry["last_indexed"] = False, None, now
                enriched.append(id)
    write_entries(index_file, {id: by_id[id] for id in enriched})
    return {"enriched": enriched, "skipped": skipped}


def _scalar(text: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None


def _gone(item, ids: set[str]) -> bool:
    return isinstance(item, str) and item in ids


def _graph_without(text: str, ids: set[str]) -> str:
    """`graph.yaml`'s `text` without `ids` in the `entries` lists of its concepts (schema version 1; version 2 has no such
    list), line by line: nothing else changes. A list emptied stays a list (`[]`). A file without such a list, or without those
    ids in it, comes back as it is."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        match = re.match(r"^( +)entries:[ \t]*(.*?)(\r?\n?)$", line)
        if not match:
            out.append(line)
            i += 1
            continue
        indent, rest, newline = match.groups()
        if rest.startswith("["):   # `entries: [a, b]`
            items = _scalar(rest)
            if isinstance(items, list) and any(_gone(item, ids) for item in items):
                tokens = [t.strip() for t in rest[1:rest.rindex("]")].split(",")]   # the items as written, quotes and all
                if len(tokens) != len(items):   # a comma inside an item: write the list again
                    tokens = [yaml.safe_dump(item, default_flow_style=True, width=10**9).strip() for item in items]
                kept = [t for t, item in zip(tokens, items) if not _gone(item, ids)]
                out.append(f"{indent}entries: [{', '.join(kept)}]{newline}")
            else:
                out.append(line)
            i += 1
            continue
        header = len(out)
        out.append(line)   # `entries:` and a block list, indented or not, under it
        i += 1
        listed = dropped = 0
        while i < len(lines):
            item = re.match(r"^( *)- (.*?)\s*$", lines[i])
            if item is None and lines[i].strip():
                break
            if item is not None and len(item.group(1)) < len(indent):
                break
            if item is not None:
                listed += 1
            if item is not None and _gone(_scalar(re.sub(r"\s+#.*$", "", item.group(2))), ids):
                dropped += 1
            else:
                out.append(lines[i])
            i += 1
        if listed and dropped == listed:   # all gone: `entries:` alone would be null
            out[header] = f"{indent}entries: []{newline}"
    return "".join(out)


def _checked_out(corpus: Path, source: dict, status: str | None) -> set[str] | None:
    """The files of the source, as git says the checkout has them at `HEAD`, under its `docs_root`; `None` when that cannot be
    trusted. It can when `status` is what the refresh reported for the source (`updated` or `current`), `.source/<id>/.git` exists
    and `HEAD` is the `last_commit_sha` of `config.yaml` in full. The worktree is not looked at: a sparse or partial one has
    fewer files than the commit."""
    checkout = corpus / ".source" / str(source["id"])
    sha = source.get("last_commit_sha")
    if status not in ("updated", "current") or not isinstance(sha, str) or not (checkout / ".git").exists():
        return None
    docs_root = posixpath.normpath(str(source.get("docs_root") or "."))
    listing = ["ls-tree", "-r", "-z", "--name-only", "HEAD"] + ([] if docs_root == "." else ["--", docs_root])
    try:
        head, files = (
            subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=120)
            for args in (["rev-parse", "HEAD"], listing)
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if head.returncode or files.returncode or head.stdout.strip() != sha or not files.stdout:   # no files: a docs_root that is not there
        return None
    return set(files.stdout.split("\0")) - {""}


def drop_missing(sources: list, corpus: Path) -> dict:
    """Remove the entries whose file is gone from its git source: `{"removed": [entry ids]}`.

    `sources` is what the refresh reported, `{"id": str, "status": str}` for each source (`[]` when the refresh did not end
    `done`). For each file entry (not `tier: section`) of a `git` source of `config.yaml` that `_checked_out` trusts, the file is
    `<docs_root>/<path>` (`docs_root` `.` or absent: none; `path` as `stale_files` takes it); when git does not list it at `HEAD` of the
    checkout, the entry goes from `index.yaml`, and its id from the `entries` lists of `graph.yaml`, if it has any. When anything
    went, `meta.entry_count` follows and `index.md` is rendered again (`render-index.sh`). A source that fails any check loses nothing.
    """
    corpus = Path(corpus)
    config = yaml.safe_load((corpus / "config.yaml").read_text()) or {}
    reported = {s.get("id"): s.get("status") for s in sources or [] if isinstance(s, dict)}
    git = {s["id"]: s for s in config.get("sources") or [] if s.get("type") == "git"}
    files = {id: _checked_out(corpus, source, reported.get(id)) for id, source in git.items()}
    index_file = corpus / "index.yaml"
    gone = set()
    for entry in load_index(index_file).get("entries") or []:
        listed = files.get(_source_of(entry))
        if listed is not None and entry.get("tier") != "section":
            docs_root = git[_source_of(entry)].get("docs_root") or "."
            if posixpath.normpath(posixpath.join(str(docs_root), _path_of(entry))) not in listed:
                gone.add(entry["id"])
    text, removed = _without(index_file.read_text(), gone)
    if not removed:
        return {"removed": []}
    graph_file = corpus / "graph.yaml"
    graph = _graph_without(graph_file.read_text(), set(removed)) if graph_file.is_file() else None
    if graph is not None and graph != graph_file.read_text():   # graph.yaml first: a failure leaves index.yaml whole
        graph_file.write_text(graph)
    index_file.write_text(text)
    done = subprocess.run(["bash", "./render-index.sh", "index.yaml"], cwd=corpus, capture_output=True, text=True, timeout=120)
    if done.returncode:
        raise RuntimeError(f"render-index.sh failed after the removal of {len(removed)} entries: {done.stderr.strip() or done.stdout.strip()}")
    return {"removed": removed}
