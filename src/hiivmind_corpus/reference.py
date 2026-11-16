"""The reference documents the nodes read, carried as package data under `documents/`, whole or one section."""

import re
from pathlib import Path

DOCUMENTS = Path(__file__).resolve().parent / "documents"
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """`(line number, level, text)` of each heading outside a fenced code block."""
    found, fenced = [], False
    for n, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and (match := HEADING.match(line)):
            found.append((n, len(match.group(1)), match.group(2)))
    return found


def _names(text: str) -> set[str]:
    """What a heading answers to: its text, and its text without a closing `(...)`, as `Schema Definition (Strict)`."""
    return {text, re.sub(r"\s*\([^)]*\)$", "", text)}


def reference(doc: str, section: str | None = None) -> str:
    """The document `doc` (a path under `documents/` without `.md`, as `graph` or `sources/git`), or, with `section`, the
    part of it from the `##` or `###` heading `section` up to the next heading of the same or a higher level."""
    file = DOCUMENTS / f"{doc}.md"
    if not file.is_file():
        known = sorted(str(f.relative_to(DOCUMENTS).with_suffix("")) for f in DOCUMENTS.rglob("*.md"))
        raise FileNotFoundError(f"no document `{doc}`; the documents are: {', '.join(known)}")
    text = file.read_text()
    if section is None:
        return text
    lines = text.splitlines(keepends=True)
    headings = _headings(lines)
    for i, (start, level, title) in enumerate(headings):
        if level in (2, 3) and section in _names(title):
            end = next((n for n, lv, _ in headings[i + 1 :] if lv <= level), len(lines))
            return "".join(lines[start:end]).rstrip() + "\n"
    listed = [title for _, level, title in headings if level in (2, 3)]
    raise KeyError(f"`{doc}` has no section `{section}`; its sections are: {'; '.join(listed)}")
