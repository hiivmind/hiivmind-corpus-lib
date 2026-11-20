"""`index.md` and `index-<section>.md`: the deterministic render of `index.yaml` (spec 7.7)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .config import Config
from .files import write_set
from .index import Entry, Index
from .schema import stamp

if TYPE_CHECKING:
    from .corpus import Corpus

UNKNOWN = "unknown"
RULE = "---"
NOTE = "> Generated from `index.yaml` — do not edit directly"
PREFIX = "index-"
SUFFIX = ".md"


@dataclass(frozen=True)
class RenderResult:
    written: tuple[str, ...]
    removed: tuple[str, ...]


def _category(entry: Entry) -> str:
    return entry.category or UNKNOWN


def _heading(category: str) -> str:
    return " ".join(word[:1].upper() + word[1:] for word in category.split())


def _label(entry: Entry) -> str:
    return entry.title or entry.id


def _line(entry: Entry, *, flags: bool = True) -> str:
    line = f"- **{_label(entry)}** `{entry.id}`"
    if entry.summary:
        line += f" - {entry.summary}"
    if flags:
        hint = entry.grep_hint
        if entry.size == "large" and isinstance(hint, str) and hint:
            line += f" ⚡ GREP - `{hint}`"
        if entry.stale is True:
            line += " ⏳ STALE"
    return line


def _entries(entries: Iterable[Entry]) -> list[str]:
    """Entry lines grouped by category (h2), each preceded by a blank line."""
    groups: dict[str, list[Entry]] = {}
    for entry in entries:
        groups.setdefault(_category(entry), []).append(entry)
    out: list[str] = []
    for category in sorted(groups):
        out += ["", f"## {_heading(category)}", ""]
        out += [_line(e) for e in sorted(groups[category], key=lambda e: (_label(e), e.id))]
    return out


def _header(name: str, config: Config, index: Index, generated: str) -> list[str]:
    return [f"# {name} Documentation Index", "",
            f"> Sources: {len(config.sources)} | Entries: {len(index.entries)} | Generated: {generated}", NOTE, ""]


def _footer(generated: str) -> list[str]:
    return ["", f"*Rendered from index.yaml at {generated}*"]


def _text(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _tiered(config: Config) -> bool:
    return config.render.strategy == "tiered"


def render_texts(config: Config, index: Index, name: str) -> dict[str, str]:
    """The files of the render, by name. Pure: nothing is read or written."""
    meta = index.meta
    generated = stamp(meta.generated_at) if meta is not None and meta.generated_at is not None else "unknown"
    head = _header(name, config, index, generated)
    foot = _footer(generated)
    if not _tiered(config):
        return {"index.md": _text(head + [RULE] + _entries(index.entries) + ["", RULE, *foot])}

    sections = config.render.sections
    valid = {s.id for s in sections}
    by_id = {e.id: e for e in index.entries}
    lines = head + ["This corpus uses a **tiered index**. Start here, then drill into the",
                    "sub-index files for detailed entries.", "", RULE]
    if config.render.quick_reference:
        lines += ["", "## Quick Reference", ""]
        lines += [_line(by_id[i], flags=False) for i in config.render.quick_reference if i in by_id]
        lines += ["", RULE]
    for section in sections:
        count = sum(1 for e in index.entries if e.section == section.id)
        lines += ["", f"## {section.title or section.id}"]
        if section.description:
            lines += [f"*{section.description}*", ""]
        lines += [f"→ See [{PREFIX}{section.id}{SUFFIX}]({PREFIX}{section.id}{SUFFIX}) for {count} detailed entries", "", RULE]
    main = [e for e in index.entries if not e.section or e.section not in valid]
    if main:
        lines += _entries(main) + ["", RULE]
    texts = {"index.md": _text(lines + foot)}
    for section in sections:
        own = [e for e in index.entries if e.section == section.id]
        sub = [f"# {name} — {section.title or section.id}", "",
               f"> Part of the {name} Documentation Index — back to [main index](index.md)", NOTE, "", RULE]
        texts[f"{PREFIX}{section.id}{SUFFIX}"] = _text(sub + _entries(own) + ["", RULE, *foot])
    return texts


def stale_sub_indexes(config: Config, present: Iterable[str]) -> tuple[str, ...]:
    """The `index-*.md` names in `present` of no configured section; `()` unless the strategy is tiered."""
    if not _tiered(config):
        return ()
    keep = {f"{PREFIX}{s.id}{SUFFIX}" for s in config.render.sections}
    return tuple(sorted(n for n in present if n.startswith(PREFIX) and n.endswith(SUFFIX) and n not in keep))


class RenderCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def texts(self) -> dict[str, str]:
        return render_texts(self._corpus.config.load(), self._corpus.index.load(), self._corpus.name)

    def write(self) -> RenderResult:
        config = self._corpus.config.load()
        texts = render_texts(config, self._corpus.index.load(), self._corpus.name)
        present = (p.name for p in self._corpus.path.glob(f"{PREFIX}*{SUFFIX}") if p.is_file())
        removes = stale_sub_indexes(config, present)
        changed = write_set(self._corpus.path, texts, removes)
        return RenderResult(tuple(n for n in changed if n in texts), tuple(n for n in changed if n not in texts))
