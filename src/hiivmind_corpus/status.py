"""`corpus_status`: the freshness pre-check. Reads the corpus; clones nothing, fetches nothing, changes nothing."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import yaml

from hiivmind_corpus.sources import kind_of

STALE_MARK = "\u23f3 STALE"


def _when(text: object) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _embeddings_generated_at(lance: Path, scripts: Path) -> datetime | None:
    """When the embeddings were made, by `lance_meta.py`; `None` when the directory has no `_meta` table (exit 2)."""
    script = scripts / "lance_meta.py"
    done = subprocess.run(["uv", "run", str(script), f"{lance}/"], cwd=scripts, capture_output=True, text=True)
    if done.returncode == 2:
        return None
    if done.returncode != 0:
        why = " ".join(done.stderr.split()) or "no message"
        raise RuntimeError(f"corpus_status: {script.name} exited {done.returncode} on {lance}: {why}")
    try:
        stamp = json.loads(done.stdout).get("generated_at")
    except (ValueError, AttributeError) as e:
        raise RuntimeError(f"corpus_status: {script.name} printed something that is not a JSON object: {e}") from None
    return _when(stamp) if stamp else None


def corpus_status(corpus: Path, scripts: Path) -> dict:
    """Whether the corpus needs a refresh: each source's freshness against its upstream, entries flagged stale, embedding lag.

    Returns `corpus`, `index_format` (`v2`, `v1`, `none`), `sources` (`id`, `type`, `freshness`: `current`, `behind` or
    `unknown`), `stale_entries`, `embeddings_lag` (`None` without embeddings), `refresh_needed` and `errors`.
    """
    corpus = Path(corpus)
    config_file = corpus / "config.yaml"
    if not config_file.is_file():
        raise FileNotFoundError(f"corpus_status: no config.yaml in {corpus}")
    config = yaml.safe_load(config_file.read_text()) or {}
    errors: list[str] = []

    index_file = corpus / "index.yaml"
    entries: list[dict] = []
    if index_file.is_file():
        index_format = "v2"
        entries = (yaml.safe_load(index_file.read_text()) or {}).get("entries") or []
    elif (corpus / "index.md").is_file():
        index_format = "v1"
    else:
        index_format = "none"

    sources = []
    for source in config.get("sources") or []:
        kind = kind_of(source)
        if kind is None:
            freshness, error = "unknown", f"source type `{source.get('type')}` is not handled by this instance yet"
        else:
            freshness, error = kind.freshness(source, corpus)
        if error:
            errors.append(error)
        sources.append({"id": source["id"], "type": source.get("type"), "freshness": freshness})

    if index_format == "v2":
        stale_entries = sum(1 for e in entries if e.get("stale") is True)
    elif index_format == "v1":
        stale_entries = sum(f.read_text().count(STALE_MARK) for f in sorted(corpus.glob("index*.md")))
    else:
        stale_entries = 0

    embeddings_lag = None
    lance = corpus / "index-embeddings.lance"
    if lance.exists():
        embedded_at = _embeddings_generated_at(lance, Path(scripts))
        if embedded_at is not None:
            embeddings_lag = sum(1 for e in entries if (when := _when(e.get("last_indexed"))) and when > embedded_at)

    return {
        "corpus": (config.get("corpus") or {}).get("name", corpus.name),
        "index_format": index_format,
        "sources": sources,
        "stale_entries": stale_entries,
        "embeddings_lag": embeddings_lag,
        "refresh_needed": any(s["freshness"] == "behind" for s in sources) or stale_entries > 0,
        "errors": errors,
    }
