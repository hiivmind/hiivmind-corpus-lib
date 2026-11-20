"""`save`: the one multi-file write of a corpus (spec 6, PKG-10, PKG-11)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from . import config as config_module
from . import graph as graph_module
from . import index as index_module
from .config import Config
from .files import write_set
from .graph import Graph
from .index import Index
from .render import PREFIX, SUFFIX, render_texts, stale_sub_indexes

if TYPE_CHECKING:
    from .corpus import Corpus


def save(corpus: Corpus, *, config: Config | None = None, index: Index | None = None,
         graph: Graph | None = None, removes: Sequence[str] = ()) -> tuple[str, ...]:
    """Write the canonical text of each value given and, when `config` or `index` is given, the render of the final
    pair (the other loaded from disk) with its stale `index-*.md` removed, all in one `write_set`.
    Returns the names changed."""
    texts: dict[str, str] = {}
    gone = list(removes)
    if config is not None:
        texts[config_module.FILE] = config.dumps()
    if index is not None:
        texts[index_module.FILE] = index.dumps()
    if graph is not None:
        texts[graph_module.FILE] = graph.dumps()
    if config is not None or index is not None:
        final_config = config if config is not None else corpus.config.load()
        final_index = index if index is not None else corpus.index.load()
        texts.update(render_texts(final_config, final_index, corpus.name_in(final_config)))
        present = (p.name for p in corpus.path.glob(f"{PREFIX}*{SUFFIX}") if p.is_file())
        gone += [n for n in stale_sub_indexes(final_config, present) if n not in gone]
    return write_set(corpus.path, texts, gone)
