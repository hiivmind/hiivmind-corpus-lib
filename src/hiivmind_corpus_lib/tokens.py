"""The one token count: the model's tokenizer when cached, else words x 1.3 rounded up."""

from __future__ import annotations

import math
from enum import StrEnum
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from . import embeddings

if TYPE_CHECKING:
    from .corpus import Corpus

TOKENS_PER_WORD = Fraction(13, 10)


class Tokenizer(Protocol):
    def count(self, text: str) -> int: ...


def count_tokens(text: str, tokenizer: Tokenizer | None = None) -> int:
    if not text.strip():
        return 0
    if tokenizer is not None:
        return tokenizer.count(text)
    return math.ceil(len(text.split()) * TOKENS_PER_WORD)


class TokenMethod(StrEnum):
    TOKENIZER = "tokenizer"
    WORDS = "words"


class _HfTokenizer:
    def __init__(self, inner):
        self._inner = inner

    def count(self, text: str) -> int:
        return len(self._inner.encode(text).ids)


@lru_cache(maxsize=None)
def _load(path: Path) -> _HfTokenizer:
    from tokenizers import Tokenizer as Hf

    inner = Hf.from_file(str(path))
    inner.no_truncation()
    return _HfTokenizer(inner)


class TokensCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    @property
    def tokenizer(self) -> Tokenizer | None:
        path = embeddings.cached_tokenizer_file()
        return None if path is None else _load(path)

    @property
    def method(self) -> TokenMethod:
        return TokenMethod.WORDS if self.tokenizer is None else TokenMethod.TOKENIZER

    def count(self, text: str) -> int:
        return count_tokens(text, self.tokenizer)
