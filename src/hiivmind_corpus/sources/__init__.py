"""Source facts, the source-kind protocol and the kinds."""

from .generated_docs import GeneratedDocsKind, GeneratedDocsSource
from .git import GitKind, GitSource
from .llms_txt import LlmsTxtKind, LlmsTxtSource
from .local import LocalKind, LocalSource
from .obsidian import ObsidianKind, ObsidianSource
from .self_docs import SelfKind, SelfSource
from .web import WebKind, WebSource
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
SOURCE_KINDS["local"] = LocalKind()
SOURCE_KINDS["web"] = WebKind()
SOURCE_KINDS["llms-txt"] = LlmsTxtKind()

__all__ = [
    "SOURCE_KINDS", "Change", "Changes", "Freshness", "GeneratedDocsKind", "GeneratedDocsSource", "GitKind", "GitSource", "Head", "Listing", "LlmsTxtKind", "LlmsTxtSource", "LocalKind", "LocalSource", "Location",
    "ManifestHash", "ObsidianKind", "ObsidianSource", "Observation", "SelfKind", "SelfSource", "Snapshot", "Source", "SourceKind", "SourceStatus", "Unobserved", "WebKind", "WebSource",
    "UnrecognisedSource", "kind_of", "normalise_docs_root", "parse_name_status",
]
