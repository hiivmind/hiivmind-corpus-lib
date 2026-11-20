"""Source facts, the source-kind protocol and the kinds."""

from .generated_docs import GeneratedDocsKind, GeneratedDocsSource
from .git import GitKind, GitSource
from .obsidian import ObsidianKind, ObsidianSource
from .self_docs import SelfKind, SelfSource
from .types import (
    SOURCE_KINDS,
    Change,
    Changes,
    Freshness,
    Head,
    Listing,
    Location,
    ManifestHash,
    Observation,
    Snapshot,
    Source,
    SourceKind,
    SourceStatus,
    Unobserved,
    UnrecognisedSource,
    kind_of,
    normalise_docs_root,
    parse_name_status,
)

SOURCE_KINDS["git"] = GitKind()
SOURCE_KINDS["generated-docs"] = GeneratedDocsKind()
SOURCE_KINDS["obsidian"] = ObsidianKind()
SOURCE_KINDS["self"] = SelfKind()

__all__ = [
    "SOURCE_KINDS", "Change", "Changes", "Freshness", "GeneratedDocsKind", "GeneratedDocsSource", "GitKind", "GitSource", "Head", "Listing", "Location",
    "ManifestHash", "ObsidianKind", "ObsidianSource", "Observation", "SelfKind", "SelfSource", "Snapshot", "Source", "SourceKind", "SourceStatus", "Unobserved",
    "UnrecognisedSource", "kind_of", "normalise_docs_root", "parse_name_status",
]
