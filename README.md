# hiivmind-corpus-lib

The `hiivmind_corpus` Python package (distribution `hiivmind-corpus-lib`). It reads and writes a corpus directory: `config.yaml`, `index.yaml`, `graph.yaml` and the rendered `index*.md` files. One `Corpus` object is opened on the directory, and each capability is an attribute of it. Capabilities take data and return data.

**The package runs no command.** It does not call `git`, `gh` or any other program, and it does not touch the network. Nodes run `git` and `gh` and hand the facts in: a commit sha (`Head`), command output (`parse_name_status`, `Listing.of`), a fetched manifest hash, a snapshot of modification times. The package turns those facts into changes on disk.

## Development

```bash
uv sync                      # base dependency: pyyaml; dev group: pytest, lancedb, pyarrow
uv run pytest -q             # no network, no git, no model
uv sync --extra embeddings   # the embeddings extra (fastembed, lancedb, pyarrow)
```

Python 3.12 or later. Run one pytest process at a time.

## Using it

Results are frozen dataclasses, enums and tuples. Failures are `CorpusError` subclasses with a stable `.code`. The clock is given at open time, and every stamp is `YYYY-MM-DDTHH:MM:SSZ` from it.

```python
from datetime import UTC, datetime
from hiivmind_corpus import Corpus, Head, Listing, parse_name_status

corpus = Corpus.open("~/corpora/hiivmind-corpus-polars",
                     clock=lambda: datetime(2026, 11, 20, 9, 0, tzinfo=UTC))
corpus.name       # "polars": config corpus.display_name, else corpus.name, else the directory name
corpus.ready()    # config has a source, index.yaml exists, index.md is not the build's placeholder
```

`repo_root` (default: two directories above the corpus) is where a `self` source's files live.

### config and index

```python
cfg = corpus.config.load()
cfg.sources[0]            # GitSource(id="polars", repo_url="https://github.com/pola-rs/polars", branch="main", ...)
cfg.render.strategy       # "single" when the block is absent
Config.loads(text).dumps() == text      # for canonical text

idx = corpus.index.load()               # Index(meta=IndexMeta(...), entries=(Entry(...), ...))
idx.find("polars", "user-guide/a.md")   # the Entry with that (source, rel_path), or None
corpus.index.stale_batches(size=30)     # (ScanBatch(source="polars", files=(...)), ...)
corpus.index.stale_ids()                # ("polars:a.md", ...)
corpus.index.set_summary("polars:a.md", "...")                 # SetResult(ok=True)
corpus.index.set_concepts({"polars:a.md": ["expressions"]})    # AssignResult(assigned=("polars:a.md",))
corpus.index.merge_scans(scans, failures)   # MergeResult(enriched=(...), skipped=(Skip(id, code, reason), ...))
```

`merge_scans` takes `path`, `title`, `summary`, `tags`, `keywords` and `category` from each scan and fills `content_type`, `size`, `grep_hint` and `headings` from the file `sources.locate` names. Skip codes: `batch-failed`, `not-indexed`, `no-scan`, `file-unreadable`. A call that changes nothing writes nothing.

### graph

```python
report = corpus.graph.validate()   # GraphReport(concepts=19, relationships=24, issues=(Issue(severity, rule, detail), ...), valid=True)
corpus.graph.exists()
corpus.graph.remove_entries({"polars:gone.md"})
```

A malformed graph is `InvalidFile` on load. One that loads but breaks a rule is an `Issue`.

### sources

Seven kinds: `corpus.sources.kinds` is `("git", "generated-docs", "obsidian", "self", "local", "web", "llms-txt")`. A source whose `type` no kind owns loads as `UnrecognisedSource` and is written back as found. Every kind's source class (`GitSource` and the others) and `UnrecognisedSource` import from `hiivmind_corpus.sources`.

```python
corpus.sources.locate(entry)                     # Location(file=Path(...), url=None)
corpus.sources.freshness({"polars": Head("5eaa...")})
# (SourceStatus(id="polars", type="git", freshness="current", error=None),)

changes = parse_name_status("M\0docs/source/a.md\0A\0docs/source/new.md\0D\0README.md\0", docs_root="docs/source")
# Changes(items=(Change("M", "a.md"), Change("A", "new.md")), outside_docs_root=1)
corpus.sources.apply_update("polars", changes, Head("43d7572..."))
# UpdateResult(files_changed=2, added=1, modified=1, removed=0, removed_ids=(), stale_entries=(...), excluded=(), outside_docs_root=1)

listing = Listing.of("43d7572...", paths_from_git_ls_tree, docs_root="docs/source")
corpus.sources.drop_missing("polars", listing)
# DropResult(removed_ids=("polars:old.md",), skipped=None, outside_docs_root=0)
# a listing of another commit: DropResult(removed_ids=(), skipped="head-mismatch", ...)
```

Observations handed in by nodes: `Head(sha)` for `git`, `generated-docs` and git-backed `obsidian`; `ManifestHash(sha256)` for `llms-txt`; `Snapshot(stamps)` for `web`, `local` and local `obsidian`; `Unobserved(reason)` for any kind whose observation failed. A path outside `docs_root` is dropped and counted in `outside_docs_root`.

### status, render, previews

```python
corpus.status.report({"polars": Head("5eaa...")})
# Status(corpus="polars", index_format="v2", sources=(...), stale_entries=0, embeddings_lag=None, refresh_needed=False, errors=())
corpus.status.report({})            # the source is "unknown" with a reason in `errors`; nothing is raised
corpus.status.embeddings_lag()      # an int, or None when there is no embeddings table
corpus.status.index_format()        # "v2", "v1" or "none"

corpus.render.texts()               # {"index.md": "...", "index-guide.md": "..."}  (pure)
corpus.render.write()               # RenderResult(written=(...), removed=(...))

corpus.previews.of(["polars:a.md"], token_limit=500)
# (Preview(entry_id=..., title=..., summary=..., source_path=..., content_preview=..., estimated_tokens=...),)
# content_preview is None when the file cannot be read; pass texts={"web:x": fetched} for a URL-only entry
```

### file metadata

```python
from pathlib import Path
from hiivmind_corpus import file_metadata, slug
file_metadata(Path("expressions.md"))   # FileMetadata(content_type="markdown", lines=1203, size="large", grep_hint=..., headings=(Heading(...), ...))
slug("Window Functions & `over()`")     # "window-functions-over"
```

### migration

```python
corpus.migration.migrate()
# MigrationResult(migrated=148, skipped=(Skip(...),), strategy="tiered", sections=(...))
```

The writes are one atomic set with rollback.

## Errors

| Error | `.code` | Raised when |
|---|---|---|
| `NotACorpus` | `not-a-corpus` | `Corpus.open` finds no `config.yaml` |
| `InvalidFile` | `invalid-file` | a file does not fit its schema, or has a duplicate entry id; carries `file` and `where` (`entries[3].tags`); an `obsidian` source with both or neither of `repo_url` and `vault_path` |
| `NoSuchSource` | `unknown-source` | an operation names a source `config.yaml` lacks |
| `NoSuchEntry` | `unknown-entry` | `set_summary` names an entry the index lacks |
| `InvalidChanges` | `invalid-changes` | `parse_name_status` is given a truncated listing |
| `NoModel` | `no-model` | `embeddings.embed()` and the model is not cached; nothing was downloaded |
| `ExtraMissing` | `extra-missing` | `embed()` or `lag()` without the extra: install `hiivmind-corpus-lib[embeddings]` |
| `MigrationRefused` | `migration-refused` | `migrate()`; `.reason` is a `Refusal`: `ALREADY_V2`, `NO_V1_INDEX`, `NO_ENTRIES` or `IDS_LOST` |
| `WriteFailed` | `write-failed` | a multi-file write failed midway; names the files restored and those not |

All derive from `CorpusError`. Not errors: `status.report` with no observation for a source, a source of an unrecognised kind, an entry with no `path`, a `drop_missing` listing of another commit.

## The embeddings extra

`uv sync --extra embeddings` installs `fastembed`, `lancedb` (0.23.0 or later) and `pyarrow`. They are imported only when an embeddings operation runs; `import hiivmind_corpus` imports none of them.

```python
corpus.embeddings.status()   # "absent" | "not-installed" | "no-model" | "ready"
corpus.embeddings.lag()      # an int, or None without an embeddings table
corpus.embeddings.embed()    # EmbedResult(total=79, embedded=26, removed=33)
```

`embed` never downloads a model: without the cached model it raises `NoModel`, without the extra `ExtraMissing`. Tests pass an embedding function as `embed(embedder)`.

## Canonical formats

`config.yaml`, `index.yaml` and `graph.yaml` each load into a validated value (`Config.loads`, `Index.loads`, `Graph.loads`) and are written only from one (`dumps`). The rule: `loads` then `dumps` of canonical text returns the same bytes, and a second pass over drifted text changes nothing.

- Block style, two-space indent, no line folding, one trailing newline.
- Known keys in schema order, then unknown keys in the order found; unknown keys survive.
- Collections keep their order. Absent stays absent. A nullable field (`stale_since`, `grep_hint`, `last_indexed`) keeps an explicit `null`; any other `null` reads as absent.
- Timestamps are quoted `YYYY-MM-DDTHH:MM:SSZ`.
- Loading is tolerant of a number or boolean in a list of strings, then strict: anything else off-schema is `InvalidFile`.

Consequences of the canonical form:

- **C1.** `config.yaml` is written canonically; its comments are not kept.
- **C2.** The first time a tool writes a published `index.yaml`, its formatting changes: one large diff, then stable.
- **C3.** Published `index.md` files change where an entry had no category (`## Null` becomes `## Unknown`).

The goldens in `tests/golden/` and the drift fixtures in `tests/drift/` pin all of this.
