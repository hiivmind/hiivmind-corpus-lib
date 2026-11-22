"""Typed failures: every one is a CorpusError with a stable `.code`."""

from enum import StrEnum


class CorpusError(Exception):
    code = "corpus-error"


class NotACorpus(CorpusError):
    code = "not-a-corpus"


class InvalidFile(CorpusError):
    code = "invalid-file"

    def __init__(self, file: str, where: str, detail: str):
        super().__init__(f"{file}: {detail}")
        self.file = file
        self.where = where
        self.detail = detail


class NoSuchSource(CorpusError):
    code = "unknown-source"


class NoSuchEntry(CorpusError):
    code = "unknown-entry"


class InvalidChanges(CorpusError):
    code = "invalid-changes"


class NoModel(CorpusError):
    code = "no-model"


class ExtraMissing(CorpusError):
    code = "extra-missing"


class Refusal(StrEnum):
    ALREADY_V2 = "already-v2"
    NO_V1_INDEX = "no-v1-index"
    NO_ENTRIES = "no-entries"
    IDS_LOST = "ids-lost"


class MigrationRefused(CorpusError):
    code = "migration-refused"

    def __init__(self, reason: Refusal, message: str):
        super().__init__(message)
        self.reason = reason


class WriteFailed(CorpusError):
    code = "write-failed"

    def __init__(self, restored: tuple[str, ...], unrestored: tuple[str, ...], cause: str):
        super().__init__(f"write failed: {cause}; restored: {', '.join(restored) or 'none'}; not restored: {', '.join(unrestored) or 'none'}")
        self.restored = restored
        self.unrestored = unrestored
        self.cause = cause


class NoEmbeddings(CorpusError):
    code = "no-embeddings"


class ModelMismatch(CorpusError):
    code = "model-mismatch"


class NoTextIndex(CorpusError):
    code = "no-text-index"
