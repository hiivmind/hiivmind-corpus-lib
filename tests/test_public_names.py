"""The public surface (PKG-4 to PKG-7)."""

import dataclasses
import enum
import tomllib
from pathlib import Path

import pytest
from support import FIXED, open_corpus

import hiivmind_corpus
from hiivmind_corpus import sources
from hiivmind_corpus.errors import CorpusError

NAMES = """Corpus CorpusError NotACorpus InvalidFile NoSuchSource NoSuchEntry InvalidChanges NoModel ExtraMissing
MigrationRefused Refusal WriteFailed Head ManifestHash Snapshot Unobserved Observation Change Changes Listing
parse_name_status Freshness IndexFormat EmbeddingsState Location SourceStatus Status UpdateResult DropResult
MergeResult Skip AssignResult SetResult ScanBatch RenderResult Preview EmbedResult MigrationResult FileMetadata
Heading GraphReport Issue Config Index Entry Graph NULL SOURCE_KINDS file_metadata slug""".split()

KIND_CLASSES = ("GitSource", "GeneratedDocsSource", "ObsidianSource", "SelfSource", "LocalSource", "WebSource",
                "LlmsTxtSource", "UnrecognisedSource")

RESULTS = ("Head ManifestHash Snapshot Unobserved Change Changes Listing Location SourceStatus Status UpdateResult "
           "DropResult MergeResult Skip AssignResult SetResult ScanBatch RenderResult Preview EmbedResult "
           "MigrationResult FileMetadata Heading GraphReport Issue").split()
ENUMS = ("Freshness", "IndexFormat", "EmbeddingsState", "Refusal")


@pytest.mark.parametrize("name", NAMES)
def test_every_interface_name_imports(name):
    assert hasattr(hiivmind_corpus, name)


def test_all_lists_every_interface_name():
    assert set(NAMES) <= set(hiivmind_corpus.__all__)


@pytest.mark.parametrize("name", KIND_CLASSES)
def test_every_kind_class_imports_from_sources(name):
    assert hasattr(sources, name)


def test_a_corpus_exposes_its_capabilities(tmp_path):
    corpus = open_corpus(tmp_path)
    for attr in ("config", "index", "graph", "sources", "status", "render", "previews", "embeddings", "migration"):
        assert getattr(corpus, attr) is not None


def test_results_are_frozen_dataclasses_or_enums():
    for name in RESULTS:
        cls = getattr(hiivmind_corpus, name)
        assert dataclasses.is_dataclass(cls), name
        assert cls.__dataclass_params__.frozen, name
    for name in ENUMS:
        assert issubclass(getattr(hiivmind_corpus, name), enum.Enum), name


def test_asdict_works_on_the_results(tmp_path):
    corpus = open_corpus(tmp_path)
    status = corpus.status.report({})
    assert dataclasses.asdict(status)["corpus"] == status.corpus
    update = dataclasses.asdict(hiivmind_corpus.UpdateResult(0, (), (), (), (), (), (), 0))
    assert update["files_changed"] == 0
    migration = hiivmind_corpus.MigrationResult(migrated=1, skipped=(), strategy="single", sections=())
    assert dataclasses.asdict(migration)["migrated"] == 1


def test_error_codes_are_distinct():
    def subclasses(cls):
        for sub in cls.__subclasses__():
            yield sub
            yield from subclasses(sub)

    classes = [CorpusError, *subclasses(CorpusError)]
    codes = [c.code for c in classes]
    assert len(codes) == len(set(codes))


def test_python_floor():
    pyproject = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["requires-python"] == ">=3.12"
