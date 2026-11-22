"""Navigation structure of a docs site (MkDocs, sidebar, SUMMARY, Jupyter Book) and its coverage."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml

from hiivmind_corpus_lib.markdown import links


class NavFormat(StrEnum):
    MKDOCS = "mkdocs"
    SIDEBAR = "sidebar"
    SUMMARY = "summary"
    JUPYTER_BOOK = "jupyter-book"


@dataclass(frozen=True)
class NavItem:
    title: str
    path: str | None
    level: int
    children: tuple[NavItem, ...]


@dataclass(frozen=True)
class Coverage:
    nav_entries: int
    files_resolved: int
    files_missing: int
    total_markdown_files: int
    percent: float


@dataclass(frozen=True)
class Navigation:
    found: bool
    nav_file: str | None
    format: NavFormat | None
    hierarchy: tuple[NavItem, ...]
    coverage: Coverage


class _Loader(yaml.SafeLoader):
    """SafeLoader that reads unknown tags (`!!python/name:…`, `!ENV …`) as None."""


_Loader.add_constructor(None, lambda loader, node: None)

_CANDIDATES = (
    ("mkdocs.yml", NavFormat.MKDOCS),
    ("mkdocs.yaml", NavFormat.MKDOCS),
    ("_sidebar.md", NavFormat.SIDEBAR),
    ("SUMMARY.md", NavFormat.SUMMARY),
    ("src/SUMMARY.md", NavFormat.SUMMARY),
    ("_toc.yml", NavFormat.JUPYTER_BOOK),
)


def markdown_files(root: Path) -> tuple[str, ...]:
    if not root.is_dir():
        return ()
    return tuple(
        sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.suffix in (".md", ".mdx") and p.is_file())
    )


def _load_yaml(path: Path) -> Any:
    try:
        return yaml.load(path.read_text(encoding="utf-8"), Loader=_Loader)  # noqa: S506 - SafeLoader subclass
    except yaml.YAMLError:
        return None


def _mkdocs_items(entries: Any, level: int) -> tuple[NavItem, ...]:
    items: list[NavItem] = []
    for entry in entries if isinstance(entries, list) else ():
        if isinstance(entry, str):
            items.append(NavItem(entry, entry, level, ()))
        elif isinstance(entry, dict) and len(entry) == 1:
            ((title, value),) = entry.items()
            if isinstance(value, str):
                items.append(NavItem(str(title), value, level, ()))
            elif isinstance(value, list):
                items.append(NavItem(str(title), None, level, _mkdocs_items(value, level + 1)))
    return tuple(items)


def _mkdocs(path: Path) -> tuple[NavItem, ...]:
    data = _load_yaml(path)
    return _mkdocs_items(data.get("nav"), 0) if isinstance(data, dict) else ()


def _markdown_nav(path: Path, nav_file: str) -> tuple[NavItem, ...]:
    parent = posixpath.dirname(nav_file)
    roots: list[list[Any]] = []  # [title, path, level, children]
    stack: list[list[Any]] = []
    for link in links(path.read_text(encoding="utf-8")):
        target = posixpath.normpath(posixpath.join(parent, link.target)) if link.target else None
        node: list[Any] = [link.title, target, link.depth, []]
        while stack and stack[-1][2] >= link.depth:
            stack.pop()
        (stack[-1][3] if stack else roots).append(node)
        stack.append(node)

    def freeze(node: list[Any]) -> NavItem:
        return NavItem(node[0], node[1], node[2], tuple(freeze(c) for c in node[3]))

    return tuple(freeze(n) for n in roots)


def _toc_leaf(root: Path, entry: dict[str, Any], level: int) -> NavItem | None:
    file = entry.get("file")
    if not isinstance(file, str):
        return None
    if posixpath.splitext(file)[1]:
        target = file
    else:
        target = next((file + s for s in (".md", ".mdx") if (root / (file + s)).exists()), file + ".md")
    title = entry.get("title") or posixpath.splitext(posixpath.basename(file))[0]
    return NavItem(str(title), target, level, _toc_entries(root, entry.get("sections"), level + 1))


def _toc_entries(root: Path, entries: Any, level: int) -> tuple[NavItem, ...]:
    items: list[NavItem] = []
    for entry in entries if isinstance(entries, list) else ():
        if not isinstance(entry, dict):
            continue
        if "file" in entry:
            leaf = _toc_leaf(root, entry, level)
            if leaf:
                items.append(leaf)
        elif "chapters" in entry and "caption" in entry:
            items.append(NavItem(str(entry["caption"]), None, level, _toc_entries(root, entry["chapters"], level + 1)))
    return tuple(items)


def _jupyter_book(root: Path, path: Path) -> tuple[NavItem, ...]:
    data = _load_yaml(path)
    if not isinstance(data, dict):
        return ()
    items: list[NavItem] = []
    if isinstance(data.get("root"), str):
        leaf = _toc_leaf(root, {"file": data["root"]}, 0)
        if leaf:
            items.append(leaf)
    items.extend(_toc_entries(root, data.get("chapters"), 0))
    for part in data.get("parts") if isinstance(data.get("parts"), list) else ():
        if isinstance(part, dict):
            items.append(NavItem(str(part.get("caption", "")), None, 0, _toc_entries(root, part.get("chapters"), 1)))
    return tuple(items)


def _count(items: tuple[NavItem, ...]) -> list[str]:
    paths: list[str] = []
    for item in items:
        if item.path is not None:
            paths.append(item.path)
        paths.extend(_count(item.children))
    return paths


def navigation_of(root: Path) -> Navigation:
    total = len(markdown_files(root))
    if root.is_dir():
        for name, fmt in _CANDIDATES:
            path = root / name
            if not path.is_file():
                continue
            if fmt is NavFormat.MKDOCS:
                hierarchy = _mkdocs(path)
            elif fmt is NavFormat.JUPYTER_BOOK:
                hierarchy = _jupyter_book(root, path)
            else:
                hierarchy = _markdown_nav(path, name)
            if hierarchy:
                paths = _count(hierarchy)
                resolved = sum((root / p).exists() for p in paths)
                percent = round(resolved / total * 100, 1) if total else 0.0
                return Navigation(True, name, fmt, hierarchy, Coverage(len(paths), resolved, len(paths) - resolved, total, percent))
    return Navigation(False, None, None, (), Coverage(0, 0, 0, total, 0.0))
