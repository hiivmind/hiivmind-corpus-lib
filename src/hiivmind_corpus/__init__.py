"""The corpus capabilities: one Corpus object over a corpus directory."""

from .config import Config
from .corpus import Corpus
from .embeddings import EmbeddingsState, EmbedResult
from .errors import (
    CorpusError,
    ExtraMissing,
    InvalidChanges,
    InvalidFile,
    MigrationRefused,
    NoModel,
    NoSuchEntry,
    NoSuchSource,
    NotACorpus,
    Refusal,
    WriteFailed,
)
from .filemeta import FileMetadata, file_metadata, slug
from .graph import Graph, GraphReport, Issue
from .index import AssignResult, Entry, Heading, Index, MergeResult, ScanBatch, SetResult, Skip
from .migration import MigrationResult
from .previews import Preview
from .render import RenderResult
from .schema import NULL
from .sources import (
    SOURCE_KINDS,
    Change,
    Changes,
    DropResult,
    Freshness,
    Head,
    Listing,
    Location,
    ManifestHash,
    Observation,
    Snapshot,
    SourceStatus,
    Unobserved,
    UpdateResult,
    parse_name_status,
)
from .status import IndexFormat, Status

__all__ = [
    "AssignResult", "Change", "Changes", "Config", "Corpus", "CorpusError", "DropResult", "EmbedResult",
    "EmbeddingsState", "Entry", "ExtraMissing", "FileMetadata", "Freshness", "Graph", "GraphReport", "Head",
    "Heading", "Index", "IndexFormat", "InvalidChanges", "InvalidFile", "Issue", "Listing", "Location",
    "ManifestHash", "MergeResult", "MigrationRefused", "MigrationResult", "NULL", "NoModel", "NoSuchEntry",
    "NoSuchSource", "NotACorpus", "Observation", "Preview", "Refusal", "RenderResult", "SOURCE_KINDS", "ScanBatch",
    "SetResult", "Skip", "Snapshot", "SourceStatus", "Status", "Unobserved", "UpdateResult", "WriteFailed",
    "file_metadata", "parse_name_status", "slug",
]
