"""`corpus.previews`: the opening words of each entry's text with a token estimate (spec 7.8)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .tokens import TOKENS_PER_WORD

if TYPE_CHECKING:
    from .corpus import Corpus


@dataclass(frozen=True)
class Preview:
    entry_id: str
    title: str | None
    summary: str | None
    source_path: str | None
    content_preview: str | None
    estimated_tokens: int


class PreviewsCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def of(self, entry_ids: Sequence[str], token_limit: int = 500,
           texts: Mapping[str, str] | None = None) -> tuple[Preview, ...]:
        wanted = set(entry_ids)
        limit = int(token_limit / TOKENS_PER_WORD)
        out = []
        for entry in self._corpus.index.load().entries:
            if entry.id not in wanted or entry.tier == "section":
                continue
            text = self._text(entry, texts)
            if text is None:
                content, tokens = None, 0
            else:
                words = text.split()
                if len(words) > limit:
                    words = words[:limit]
                    text = " ".join(words)
                content, tokens = text, self._corpus.tokens.count(text)
            out.append(Preview(entry.id, entry.title, entry.summary, entry.path, content, tokens))
        return tuple(out)

    def _text(self, entry, texts: Mapping[str, str] | None) -> str | None:
        location = self._corpus.sources.locate(entry)
        if location.file is not None:
            try:
                return location.file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
        if location.url is not None and texts is not None:
            return texts.get(entry.id)
        return None
