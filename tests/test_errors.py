import pytest

from hiivmind_corpus_lib.errors import (CorpusError, ExtraMissing, InvalidChanges, InvalidFile, MigrationRefused, NoModel,
                                    NoSuchEntry, NoSuchSource, NotACorpus, Refusal, WriteFailed)


@pytest.mark.parametrize("cls, code", [
    (NotACorpus, "not-a-corpus"), (NoSuchSource, "unknown-source"), (NoSuchEntry, "unknown-entry"),
    (InvalidChanges, "invalid-changes"), (NoModel, "no-model"), (ExtraMissing, "extra-missing")])
def test_simple_errors_have_their_code(cls, code):
    assert issubclass(cls, CorpusError) and cls.code == code and cls("x").code == code


def test_invalid_file():
    e = InvalidFile("config.yaml", "sources", "`sources` must be a list, found a mapping")
    assert isinstance(e, CorpusError) and e.code == "invalid-file" and e.where == "sources"
    assert str(e) == "config.yaml: `sources` must be a list, found a mapping"


def test_write_failed_names_all():
    e = WriteFailed(("index.yaml",), ("config.yaml",), "disk full")
    assert isinstance(e, CorpusError) and e.code == "write-failed"
    assert all(s in str(e) for s in ("index.yaml", "config.yaml", "disk full"))


def test_migration_refused():
    e = MigrationRefused(Refusal.ALREADY_V2, "already v2")
    assert e.reason is Refusal.ALREADY_V2 and e.code == "migration-refused" and isinstance(e, CorpusError)
    assert [r.value for r in Refusal] == ["already-v2", "no-v1-index", "no-entries", "ids-lost"]
