"""The seam for source kinds.

A kind of source (git, web, llms-txt, local) is a module in this package with a class that has `freshness`, a line in
`SOURCE_KINDS`, its reference document `documents/sources/<type>.md`, and the server it needs in the instance.
Nothing else changes: the job, the other tools and the nodes' contracts stay as they are.
"""

from pathlib import Path
from typing import Protocol

from hiivmind_corpus.sources import git


class SourceKind(Protocol):
    def freshness(self, source: dict, corpus: Path) -> tuple[str, str | None]:
        """`("current" | "behind" | "unknown", error or None)`. Clones nothing and changes nothing."""
        ...


SOURCE_KINDS: dict[str, SourceKind] = {"git": git.GitSource()}


def kind_of(source: dict) -> SourceKind | None:
    """The handler of this source's `type`, or `None` when this instance does not handle that kind."""
    return SOURCE_KINDS.get(source.get("type"))
