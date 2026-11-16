"""The capabilities the refresh nodes call: readiness, the batches to scan, a source's update, the merge of the scans, the
concept and summary setters, and `meta`.

Each edits `index.yaml` with the layout-keeping writer of `index.py`, and `config.yaml` line by line: a node never edits
either file by text (CRP-4). A function that writes takes `now`, the time it records.
"""

import posixpath
import re
import subprocess
from pathlib import Path, PurePosixPath

import yaml

from hiivmind_corpus.index import _graph_without, _renderer, _split, _without, apply_scan, load_index, stale_files, write_entries

BATCH = 30   # files in one scan run
PLACEHOLDER = "Run hiivmind-corpus-build"   # what the build's placeholder index.md says
TIMEOUT = 120   # seconds for one git command


def corpus_ready(corpus: Path) -> bool:
    """True when `config.yaml` has a source, `index.yaml` exists, and `index.md` is not the build's placeholder."""
    corpus = Path(corpus)
    config_file = corpus / "config.yaml"
    if not config_file.is_file():
        return False
    config = yaml.safe_load(config_file.read_text()) or {}
    index_md = corpus / "index.md"
    placeholder = index_md.is_file() and PLACEHOLDER in index_md.read_text()
    return bool(config.get("sources")) and (corpus / "index.yaml").is_file() and not placeholder


def stale_batches(corpus: Path) -> list[dict]:
    """The stale files to scan, as batches of at most `BATCH` files of one source: `[{"source", "files"}]`, in the order of
    `stale_files`; `[]` when nothing is stale."""
    by_source = stale_files(corpus)["by_source"]
    return [{"source": source, "files": files[i : i + BATCH]} for source, files in by_source.items() for i in range(0, len(files), BATCH)]


def stale_entries(corpus: Path) -> list[str]:
    """The ids of the file entries still stale."""
    return stale_files(corpus)["entry_ids"]


# --- writing single lines -----------------------------------------------------------------------------------------------

def _styled(old: str, new: str) -> str:
    """`new` quoted as `old` was."""
    return f"{old[0]}{new}{old[0]}" if old[:1] in ("'", '"') else new


def _block(lines: list[str], key: str) -> range:
    """The lines of the top-level key `key:` (its own line first), a mapping or a list at any indent; empty when the file has none."""
    start = next((i for i, line in enumerate(lines) if re.match(rf"^{re.escape(key)}:\s*$", line)), None)
    if start is None:
        return range(0)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i][0].isspace() and not lines[i].startswith("- ")), len(lines))
    return range(start, end)


def _set(lines: list[str], block: range, key: str, value: str) -> None:
    """Set `key` on its line in `block`, keeping the quotes its old value had. A block without the key gets it after its
    first line, at the indent of the line after that."""
    for i in block:
        found = re.match(rf"^(\s*(?:- )?){re.escape(key)}:[ \t]*(.*?)(\r?\n?)$", lines[i])
        if found:
            lines[i] = f"{found.group(1)}{key}: {_styled(found.group(2), value)}{found.group(3) or chr(10)}"
            return
    first = block.start
    indent = re.match(r"^(\s*)", lines[first + 1]).group(1) if first + 1 < block.stop else "  "
    lines.insert(first + 1, f"{indent}{key}: {value}\n")


def set_meta(corpus: Path, now: str) -> None:
    """Set `meta.generated_at` to `now` and `meta.entry_count` to the number of entries in `index.yaml`; only those lines change."""
    index_file = Path(corpus) / "index.yaml"
    text = index_file.read_text()
    _, blocks, _ = _split(text)
    lines = text.splitlines(keepends=True)
    _set(lines, _block(lines, "meta"), "generated_at", now)
    _set(lines, _block(lines, "meta"), "entry_count", str(len(blocks)))
    index_file.write_text("".join(lines))


def _source_item(lines: list[str], source: str) -> range:
    """The lines of the item of `sources:` whose `id` is `source`."""
    within = _block(lines, "sources")
    items = [i for i in within if re.match(r"^\s*- ", lines[i])]
    base = min((len(lines[i]) - len(lines[i].lstrip()) for i in items), default=0)
    starts = [i for i in items if len(lines[i]) - len(lines[i].lstrip()) == base]
    for n, start in enumerate(starts):
        item = range(start, starts[n + 1] if n + 1 < len(starts) else within.stop)
        if any(re.match(rf"^\s*(?:- )?id:\s*['\"]?{re.escape(source)}['\"]?\s*$", lines[i]) for i in item):
            return item
    raise KeyError(f"config.yaml has no source `{source}`")


def _appended(text: str, new: list[dict]) -> str:
    """The index file `text` with the entries `new` after its last entry, in the layout the file has."""
    if not new:
        return text
    head, blocks, tail = _split(text)
    rendered = [line for entry in new for line in _renderer(blocks)(entry)]
    if blocks:
        return "".join(head + [line for block in blocks for line in block] + rendered + tail)
    lines = text.splitlines(keepends=True)   # `entries: []`, or `entries:` with nothing under it
    at = next(i for i, line in enumerate(lines) if re.match(r"^entries:\s*(\[\s*\])?\s*$", line))
    lines[at] = "entries:\n"
    return "".join(lines[: at + 1] + rendered + lines[at + 1 :])


# --- a source's update ------------------------------------------------------------------------------------------------

def _diff(corpus: Path, source: str, docs_root: str, old_sha: str, new_sha: str) -> list[tuple[str, str]]:
    """`(status, path under the docs root)` for each line of the clone's diff, in its order."""
    command = ["git", "-C", str(corpus / ".source" / source), "diff", "--name-status", "--no-renames", f"{old_sha}..{new_sha}"]
    if docs_root != ".":
        command += ["--", docs_root]
    done = subprocess.run(command, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    if done.returncode:
        why = " ".join((done.stderr or done.stdout).split()) or "no message"
        raise RuntimeError(f"{' '.join(command)} exited {done.returncode}: {why}")
    changes = []
    for line in done.stdout.splitlines():
        status, _, path = line.partition("\t")
        changes.append((status[:1], path if docs_root == "." else path.removeprefix(f"{docs_root}/")))
    return changes


def apply_source_update(corpus: Path, source: str, old_sha: str, new_sha: str, now: str) -> dict:
    """Apply the diff `old_sha..new_sha` of the source's clone (`.source/<source>`, under its `docs_root`) to the index, as
    `index-updating.md` "v2 format" says, and record the source's new commit in `config.yaml`.

    `M`, or `A` of an entry the index has: the entry is marked stale (`stale_since` now) and nothing else of it changes. `A`:
    an entry `Pending re-scan` is added after the last one, unless a directory of its path is in `build.skip_sections`
    (then it is listed in `excluded`); its `section` is the source when `build.organization` is `by-source` and
    `render.strategy` is `tiered`. `D`: the entry goes from `index.yaml` and its id from the entry lists of `graph.yaml`.
    Then `meta` is set, and the source's `last_commit_sha` (`new_sha`) and `last_indexed_at`, and `index.last_updated_at`.

    Returns `added`, `modified`, `removed` (counts), `removed_ids` and `excluded` (paths). A git failure raises `RuntimeError`
    with git's message, and nothing is changed.
    """
    corpus = Path(corpus)
    config_file, index_file, graph_file = corpus / "config.yaml", corpus / "index.yaml", corpus / "graph.yaml"
    config = yaml.safe_load(config_file.read_text()) or {}
    found = [s for s in config.get("sources") or [] if s.get("id") == source]
    if not found:
        raise KeyError(f"config.yaml has no source `{source}`")
    docs_root = posixpath.normpath(str(found[0].get("docs_root") or "."))
    changes = _diff(corpus, source, docs_root, old_sha, new_sha)

    build, render = config.get("build") or {}, config.get("render") or {}
    skipped = {str(s) for s in build.get("skip_sections") or []}
    section = source if build.get("organization") == "by-source" and render.get("strategy") == "tiered" else None
    by_id = {e["id"]: e for e in load_index(index_file).get("entries") or []}
    stale: dict[str, dict] = {}
    added: list[dict] = []
    gone: set[str] = set()
    excluded: list[str] = []
    for status, path in changes:
        id = f"{source}:{path}"
        if status in ("M", "A") and id in by_id:
            stale[id] = {**by_id[id], "stale": True, "stale_since": now}
        elif status == "A" and any(part in skipped for part in PurePosixPath(path).parts[:-1]):
            excluded.append(path)
        elif status == "A" and id not in {e["id"] for e in added}:
            added.append({
                "id": id, "source": source, "path": path, "stale": True, "stale_since": now, "category": "unknown",
                "summary": "Pending re-scan", "section": section, "tags": [], "keywords": [], "concepts": [],
            })
        elif status == "D" and id in by_id:
            gone.add(id)

    write_entries(index_file, stale)
    text, removed = _without(index_file.read_text(), gone)
    if removed and graph_file.is_file():   # graph.yaml first: a failure leaves index.yaml whole
        graph = _graph_without(graph_file.read_text(), set(removed))
        if graph != graph_file.read_text():
            graph_file.write_text(graph)
    index_file.write_text(_appended(text, added))
    set_meta(corpus, now)

    lines = config_file.read_text().splitlines(keepends=True)
    _set(lines, _source_item(lines, source), "last_commit_sha", new_sha)
    _set(lines, _source_item(lines, source), "last_indexed_at", now)
    if _block(lines, "index"):
        _set(lines, _block(lines, "index"), "last_updated_at", now)
    config_file.write_text("".join(lines))
    return {"added": len(added), "modified": len(stale), "removed": len(removed), "removed_ids": removed, "excluded": excluded}


# --- the merge of the scans, and the setters ----------------------------------------------------------------------------

def merge_scans(corpus: Path, scans: list[dict], failures: list[dict], now: str) -> dict:
    """Merge a fan-out's scans into `index.yaml` with `apply_scan`.

    `scans` are the outputs of the scan runs that ended `done`, in item order, without their items; `failures` are
    `{item, outcome, reason}` for the others. The batches are `stale_batches()` again (nothing wrote the index since the
    fan-out listed them) without the failed items, paired with `scans` in order; a failed batch's entries are skipped with
    its reason, or its outcome. `meta` is set when an entry was enriched. Returns `apply_scan`'s `enriched` and `skipped`.
    """
    failed = [f.get("item") for f in failures]
    batches = [b for b in stale_batches(corpus) if b not in failed]
    merged = [{**batch, "entries": scan.get("entries") or [], "error": None} for batch, scan in zip(batches, scans)]
    merged += [{**f["item"], "entries": [], "error": f.get("reason") or f.get("outcome")} for f in failures]
    result = apply_scan(merged, corpus)
    if result["enriched"]:
        set_meta(corpus, now)
    return result


def _set_field(corpus: Path, values: dict[str, object], field: str, now: str) -> list[str]:
    """Set `field` of each entry named in `values`; the ids it found. `meta` is set when one was."""
    index_file = Path(corpus) / "index.yaml"
    by_id = {e["id"]: e for e in load_index(index_file).get("entries") or []}
    changed = {id: {**by_id[id], field: value} for id, value in values.items() if id in by_id}
    write_entries(index_file, changed)
    if changed:
        set_meta(corpus, now)
    return list(changed)


def set_concepts(corpus: Path, assignments: dict[str, list[str]], now: str) -> dict:
    """Set the `concepts` of each entry in `assignments` (`{entry id: [concept ids]}`); an id the index has not is left out.
    Returns `{"assigned": <entries changed>}`."""
    return {"assigned": len(_set_field(corpus, {id: list(c) for id, c in assignments.items()}, "concepts", now))}


def set_summary(corpus: Path, entry_id: str, summary: str, now: str) -> dict:
    """Set the `summary` of one entry. An id the index has not raises `KeyError`."""
    if not _set_field(corpus, {entry_id: summary}, "summary", now):
        raise KeyError(f"index.yaml has no entry `{entry_id}`")
    return {"ok": True}
