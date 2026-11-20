"""Source facts, the source-kind protocol and the kinds."""

from .git import GitKind, GitSource
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

__all__ = [
    "SOURCE_KINDS", "Change", "Changes", "Freshness", "GitKind", "GitSource", "Head", "Listing", "Location",
    "ManifestHash", "Observation", "Snapshot", "Source", "SourceKind", "SourceStatus", "Unobserved",
    "UnrecognisedSource", "kind_of", "normalise_docs_root", "parse_name_status",
]
