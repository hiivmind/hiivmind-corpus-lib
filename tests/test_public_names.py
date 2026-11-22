"""The public surface (PKG-4 to PKG-7)."""

import dataclasses
import enum
import tomllib
from pathlib import Path

import pytest
from support import FIXED, open_corpus

import hiivmind_corpus_lib
from hiivmind_corpus_lib import sources
from hiivmind_corpus_lib.errors import CorpusError

NAMES = """Corpus CorpusError NotACorpus InvalidFile NoSuchSource NoSuchEntry InvalidChanges NoModel ExtraMissing
MigrationRefused Refusal WriteFailed Head ManifestHash Snapshot Unobserved Observation Change Changes Listing
parse_name_status Freshness IndexFormat EmbeddingsState Location SourceStatus Status UpdateResult DropResult
MergeResult Skip AssignResult SetResult ScanBatch RenderResult Preview EmbedResult MigrationResult FileMetadata
Heading GraphReport Issue Config Index Entry Graph NULL SOURCE_KINDS file_metadata slug
count_tokens Tokenizer TokenMethod HeadingLine Link headings links Section sections Strategy Chunk chunks NavFormat
NavItem Coverage Navigation navigation_of LargeFile Merge ThinResult ChunkEmbedResult EmbeddingsMeta Mode Hit
NoEmbeddings ModelMismatch NoTextIndex""".split()

KIND_CLASSES = ("GitSource", "GeneratedDocsSource", "ObsidianSource", "SelfSource", "LocalSource", "WebSource",
                "LlmsTxtSource", "UnrecognisedSource")

RESULTS = ("Head ManifestHash Snapshot Unobserved Change Changes Listing Location SourceStatus Status UpdateResult "
           "DropResult MergeResult Skip AssignResult SetResult ScanBatch RenderResult Preview EmbedResult "
           "MigrationResult FileMetadata Heading GraphReport Issue HeadingLine Link Section Chunk NavItem Coverage "
           "Navigation LargeFile Merge ThinResult ChunkEmbedResult EmbeddingsMeta Hit").split()
ENUMS = ("Freshness", "IndexFormat", "EmbeddingsState", "Refusal", "TokenMethod", "Strategy", "NavFormat", "Mode")


@pytest.mark.parametrize("name", NAMES)
def test_every_interface_name_imports(name):
    assert hasattr(hiivmind_corpus_lib, name)


def test_all_lists_every_interface_name():
    assert set(NAMES) <= set(hiivmind_corpus_lib.__all__)


@pytest.mark.parametrize("name", KIND_CLASSES)
def test_every_kind_class_imports_from_sources(name):
    assert hasattr(sources, name)


def test_a_corpus_exposes_its_capabilities(tmp_path):
    corpus = open_corpus(tmp_path)
    for attr in ("config", "index", "graph", "sources", "status", "render", "previews", "embeddings", "migration"):
        assert getattr(corpus, attr) is not None


def test_results_are_frozen_dataclasses_or_enums():
    for name in RESULTS:
        cls = getattr(hiivmind_corpus_lib, name)
        assert dataclasses.is_dataclass(cls), name
        assert cls.__dataclass_params__.frozen, name
    for name in ENUMS:
        assert issubclass(getattr(hiivmind_corpus_lib, name), enum.Enum), name


def test_asdict_works_on_the_results(tmp_path):
    corpus = open_corpus(tmp_path)
    status = corpus.status.report({})
    assert dataclasses.asdict(status)["corpus"] == status.corpus
    update = dataclasses.asdict(hiivmind_corpus_lib.UpdateResult(0, (), (), (), (), (), (), 0))
    assert update["files_changed"] == 0
    migration = hiivmind_corpus_lib.MigrationResult(migrated=1, skipped=(), strategy="single", sections=())
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


PDF_NAMES = """TocEntry Box TextBlock FontInfo Chapter ChapterPdf Manifest CrossRef outline page_count text_blocks
strip_headers_footers fonts chapters chapters_from_outline chapters_by_font split heading code_block table callout
frontmatter chapter_markdown wikilink safe_file_name dehyphenate cross_references resolve split_subtables
expand_newline_cells merge_continuation_rows strip_empty_columns layout_table tables is_math_font decode_math""".split()


def test_the_pdf_subpackage_names_every_pdf_capability():              # CMP-1, design §5
    from hiivmind_corpus_lib import pdf
    assert set(PDF_NAMES) == set(pdf.__all__)


def test_a_corpus_has_the_new_capabilities(tmp_path):                  # PKG-4 extended
    corpus = open_corpus(tmp_path)
    assert all(hasattr(corpus, name) for name in ("tokens", "content", "search"))


@pytest.mark.parametrize("name", ["NoEmbeddings", "ModelMismatch", "NoTextIndex"])
def test_the_new_errors_have_their_codes(name):                        # P-4
    codes = {"NoEmbeddings": "no-embeddings", "ModelMismatch": "model-mismatch", "NoTextIndex": "no-text-index"}
    assert getattr(hiivmind_corpus_lib, name).code == codes[name]
