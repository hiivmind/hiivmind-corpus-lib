# hiivmind-corpus-lib

The `hiivmind_corpus_lib` Python package (distribution `hiivmind-corpus-lib`). It reads and writes a corpus directory: `config.yaml`, `index.yaml`, `graph.yaml` and the rendered `index*.md` files. One `Corpus` object is opened on the directory, and each capability is an attribute of it. Capabilities take data and return data.

**The package runs no command.** It does not call `git`, `gh` or any other program, and it does not touch the network. Nodes run `git` and `gh` and hand the facts in: a commit sha (`Head`), command output (`parse_name_status`, `Listing.of`), a fetched manifest hash, a snapshot of modification times. The package turns those facts into changes on disk.

## Development

```bash
hatch run test_github:test    # the base install: tests that need an extra skip
hatch run test_extras:test    # every extra installed: the whole suite runs
hatch run ruff:check
hatch run mypy:check
```

Python 3.12 or later. No test touches the network, runs `git` or downloads a model. [TESTING.md](TESTING.md) has every environment and command; [hatch.toml](hatch.toml) owns them, [pyproject.toml](pyproject.toml) the package and its dependencies.

## Using it

Results are frozen dataclasses, enums and tuples. Failures are `CorpusError` subclasses with a stable `.code`. The clock is given at open time, and every stamp is `YYYY-MM-DDTHH:MM:SSZ` from it.

```python
from datetime import UTC, datetime
from hiivmind_corpus_lib import Corpus, Head, Listing, parse_name_status

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

Seven kinds: `corpus.sources.kinds` is `("git", "generated-docs", "obsidian", "self", "local", "web", "llms-txt")`. A source whose `type` no kind owns loads as `UnrecognisedSource` and is written back as found. Every kind's source class (`GitSource` and the others) and `UnrecognisedSource` import from `hiivmind_corpus_lib.sources`.

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
from hiivmind_corpus_lib import file_metadata, slug
file_metadata(Path("expressions.md"))   # FileMetadata(content_type="markdown", lines=1203, size="large", grep_hint=..., headings=(Heading(...), ...))
slug("Window Functions & `over()`")     # "window-functions-over"
```

### migration

```python
corpus.migration.migrate()
# MigrationResult(migrated=148, skipped=(Skip(...),), strategy="tiered", sections=(...))
```

The writes are one atomic set with rollback.

### tokens and markdown

```python
from hiivmind_corpus_lib import count_tokens, headings, links
corpus.tokens.count("some text")      # an int: the cached embedding tokenizer if there is one, else ceil(words * 1.3)
corpus.tokens.method                  # TokenMethod.WORDS or TokenMethod.TOKENIZER
count_tokens("some text")             # 3 (the word estimate; pass a `Tokenizer` as the second argument to use one)
headings("# A\n\n## B\n")             # (HeadingLine(level=1, title="A", line=1), HeadingLine(level=2, title="B", line=3))
links("- [Intro](intro.md)\n")        # (Link(title="Intro", target="intro.md", depth=0),)
```

### sections and chunks

```python
from hiivmind_corpus_lib import Strategy, chunks, sections
sections(text, min_level=2, max_level=4, min_tokens=200)
# (Section(title="Joins", level=2, line_start=40, line_end=96, tokens=410, anchor="joins", preview="..."), ...)
chunks(text, Strategy.MARKDOWN, target_tokens=900, overlap_tokens=100)
# (Chunk(index=0, text="...", line_start=1, line_end=58, overlap_previous=0, heading_context="Joins"), ...)
```

`Strategy` is `MARKDOWN`, `TRANSCRIPT`, `CODE`, `PARAGRAPH` or `HEADINGS`. Both functions are pure; each takes a `count=` function.

### navigation and content

```python
nav = corpus.content.navigation("polars")   # reads mkdocs.yml, _sidebar.md, SUMMARY.md or _toc.yml of the source
# Navigation(found=True, nav_file="mkdocs.yml", format=NavFormat.MKDOCS, hierarchy=(NavItem(...), ...),
#            coverage=Coverage(nav_entries=40, files_resolved=38, files_missing=2, total_markdown_files=61, percent=...))
corpus.content.large_files("polars", max_tokens=15000)
# (LargeFile(path="user-guide/expressions.md", tokens=21000, lines=1203, headings=48, deepest_heading=4), ...)
corpus.content.sections("polars", "user-guide/expressions.md")             # (Section(...), ...)
corpus.content.chunks("polars", "user-guide/expressions.md", Strategy.MARKDOWN)   # (Chunk(...), ...)
```

`navigation_of(root)` does the same for a directory.

### thinning

```python
corpus.index.thin_sections(min_tokens=300, dry_run=True)
# ThinResult(sections_before=92, sections_after=71, merges=(Merge(removed="polars:a.md#x", into="polars:a.md#y"), ...))
```

A section entry whose summary and keywords are under `min_tokens` merges into a neighbour. `dry_run=True` writes nothing.

### search

```python
corpus.embeddings.embed_chunks({("polars", "a.md"): corpus.content.chunks("polars", "a.md", Strategy.MARKDOWN)})
# ChunkEmbedResult(files=1, total=12, embedded=12, removed=0)
corpus.embeddings.meta()    # EmbeddingsMeta(model=..., dimensions=384, generated_at=..., entry_count=79, chunk_count=12)
corpus.search.entries("lazy evaluation", top_k=5, mode=Mode.HYBRID, rerank=True)
# (Hit(id="polars:a.md", score=0.83, fields={...}), ...)
corpus.search.chunks("lazy evaluation")
```

`Mode` is `VECTOR` (default) or `HYBRID`. Tests pass `embedder=` and `reranker=`. Like `embed`, search never downloads a model.

### pdf

```python
from hiivmind_corpus_lib.pdf import TocEntry, chapters_from_outline
outline = (TocEntry(level=1, title="Introduction", page=0), TocEntry(level=2, title="Why", page=1),
           TocEntry(level=1, title="Basics", page=4))
chapters_from_outline(outline, page_count=9)
# (Chapter(index=1, title='Introduction', start_page=0, end_page=4), Chapter(index=2, title='Basics', start_page=4, end_page=9))
```

`pdf.outline(path)` returns the `TocEntry` tuple of a PDF file (pages are 0-based), and `pdf.chapters(path)` the chapters straight from it.

`hiivmind_corpus_lib.pdf` holds the pure PDF helpers: result types, Markdown emitters, table row clean-up, TeX math decoding, cross-references and chapter splitting. PyMuPDF is imported only inside the calls that read a PDF.

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
| `NoEmbeddings` | `no-embeddings` | `search` finds no table for the corpus (or its chunks): run `embed` first |
| `ModelMismatch` | `model-mismatch` | `search` on embeddings built with another model than the query's |
| `NoTextIndex` | `no-text-index` | hybrid `search` on a table without a text index: run `embed` again |

All derive from `CorpusError`. Not errors: `status.report` with no observation for a source, a source of an unrecognised kind, an entry with no `path`, a `drop_missing` listing of another commit.

## The embeddings extra

The `embeddings` extra (`hiivmind-corpus-lib[embeddings]`) installs `fastembed`, `lancedb` (0.23.0 or later) and `pyarrow`. They are imported only when an embeddings operation runs; `import hiivmind_corpus_lib` imports none of them.

```python
corpus.embeddings.status()   # "absent" | "not-installed" | "no-model" | "ready"
corpus.embeddings.lag()      # an int, or None without an embeddings table
corpus.embeddings.embed()    # EmbedResult(total=79, embedded=26, removed=33)
```

`embed` never downloads a model: without the cached model it raises `NoModel`, without the extra `ExtraMissing`. Tests pass an embedding function as `embed(embedder)`.

## Extras and licence

- `embeddings`: `fastembed`, `lancedb`, `pyarrow` (embeddings, chunk embeddings and search).
- `pdf`: `pymupdf` (reading PDFs). `import hiivmind_corpus_lib` and `import hiivmind_corpus_lib.pdf` import none of the extras' libraries.

Nothing is ever downloaded: a model that is not cached raises `NoModel`.

Licensed under the GNU Affero General Public License v3.0 or later ([LICENSE](LICENSE)), because the `pdf` extra builds on PyMuPDF, which is AGPL-3.0.

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
