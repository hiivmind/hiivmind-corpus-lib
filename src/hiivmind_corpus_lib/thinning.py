"""Pure thinning of an `Index`: merge small section entries into a neighbor."""

from __future__ import annotations

from dataclasses import replace

from .index import Entry, Index, Merge, ThinResult
from .sections import Count
from .tokens import count_tokens


def _size(entry: Entry, count: Count) -> int:
    return count(f"{entry.summary or ''} {' '.join(entry.keywords or ())}".strip())


def _start(entry: Entry) -> int:
    return entry.line_range[0] if entry.line_range else 0


def _merged(first: tuple[str, ...] | None, second: tuple[str, ...] | None) -> tuple[str, ...] | None:
    return tuple(dict.fromkeys((*(first or ()), *(second or ())))) or None


def _absorb(target: Entry, section: Entry) -> Entry:
    changes: dict = {"keywords": _merged(target.keywords, section.keywords),
                     "concepts": _merged(target.concepts, section.concepts)}
    if target.line_range and section.line_range:
        changes["line_range"] = (target.line_range[0], max(target.line_range[-1], section.line_range[-1]))
    if section.summary:
        changes["summary"] = f"{(target.summary or '').strip()} {section.summary}".strip()
    return replace(target, **changes)


def thin(index: Index, min_tokens: int = 300, count: Count = count_tokens) -> tuple[Index, ThinResult]:
    """Merge each section under `min_tokens` into its nearest earlier sibling, else its parent."""
    work = {e.id: e for e in index.entries}
    parents = {e.parent for e in index.entries if e.parent}
    sections = [e for e in index.entries if e.tier == "section"]
    visit = sorted(sections, key=lambda e: -(e.heading_level or 0))
    merges: list[Merge] = []
    for original in visit:
        section = work[original.id]
        if original.id in parents or _size(section, count) >= min_tokens:
            continue
        siblings = [w for w in work.values()
                    if w.tier == "section" and w.parent == section.parent and w.source == section.source
                    and w.id != section.id and _start(w) < _start(section)]
        target = max(siblings, key=_start) if siblings else work.get(section.parent or "")
        if target is None or target.source != section.source:
            continue
        work[target.id] = _absorb(target, section)
        del work[section.id]
        merges.append(Merge(section.id, target.id))
    thinned = replace(index, entries=tuple(work[e.id] for e in index.entries if e.id in work))
    return thinned, ThinResult(len(sections), len(sections) - len(merges), tuple(merges))
