"""The corpus capabilities: one Corpus object over a corpus directory."""

from .config import Config
from .corpus import Corpus
from .errors import CorpusError, InvalidFile, NotACorpus

__all__ = ["Config", "Corpus", "CorpusError", "InvalidFile", "NotACorpus"]
