"""`Corpus`: one object over a corpus directory."""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime
from os import PathLike
from pathlib import Path

from .config import FILE, ConfigCapability
from .errors import NotACorpus
from .index import IndexCapability

PLACEHOLDER = "Run hiivmind-corpus-build"


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Corpus:
    def __init__(self, path: Path, repo_root: Path, clock: Callable[[], datetime]):
        self.path = path
        self.repo_root = repo_root
        self._clock = clock
        self.config = ConfigCapability(self)
        self.index = IndexCapability(self)

    @classmethod
    def open(cls, path: str | PathLike, *, clock: Callable[[], datetime] | None = None,
             repo_root: Path | None = None) -> Corpus:
        root = Path(os.path.abspath(os.path.expanduser(path)))
        if not (root / FILE).is_file():
            raise NotACorpus(f"no config.yaml in {root}")
        return cls(root, repo_root if repo_root is not None else root.parent.parent, clock or _utc_now)

    @property
    def name(self) -> str:
        info = self.config.load().corpus
        return (info.display_name or info.name if info else None) or self.path.name

    def now(self) -> datetime:
        return self._clock()

    def ready(self) -> bool:
        if not self.config.load().sources:
            return False
        if not (self.path / "index.yaml").is_file():
            return False
        page = self.path / "index.md"
        return not (page.is_file() and PLACEHOLDER in page.read_text(encoding="utf-8"))
