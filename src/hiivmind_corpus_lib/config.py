"""`config.yaml`: the corpus's identity, sources, settings and render block."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from . import schema
from .errors import InvalidFile
from .schema import _found
from .sources import SOURCE_KINDS, Source, UnrecognisedSource
from .yamlio import dump_yaml, load_yaml

if TYPE_CHECKING:
    from .corpus import Corpus

FILE = "config.yaml"
Extra = tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class CorpusInfo:
    name: str | None = None
    display_name: str | None = None
    keywords: tuple[str, ...] | None = None
    created_at: datetime | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class IndexInfo:
    format: str | None = None
    last_updated_at: datetime | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Settings:
    include_patterns: tuple[str, ...] | None = None
    exclude_patterns: tuple[str, ...] | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Build:
    organization: str | None = None
    skip_sections: tuple[str, ...] | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class RenderSection:
    id: str
    title: str | None = None
    description: str | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Render:
    strategy: str = "single"
    sections: tuple[RenderSection, ...] = field(default=(), metadata={"omit_default": True})
    quick_reference: tuple[str, ...] = field(default=(), metadata={"omit_default": True})
    description: str | None = None
    extra: Extra = ()


@dataclass(frozen=True)
class Config:
    schema_version: int | None = None
    corpus: CorpusInfo | None = None
    sources: tuple[Source | UnrecognisedSource, ...] = field(default=(), metadata={"omit_default": True})
    index: IndexInfo | None = None
    settings: Settings | None = None
    build: Build | None = None
    render: Render = field(default_factory=Render, metadata={"omit_default": True})
    extra: Extra = ()

    @classmethod
    def loads(cls, text: str) -> Config:
        data = load_yaml(text, FILE)
        if not isinstance(data, dict):
            raise InvalidFile(FILE, "", f"the file must be a mapping, found {_found(data)}")
        rest = {k: v for k, v in data.items() if k != "sources"}
        config = schema.read(cls, rest, FILE)
        raw = data.get("sources")
        if raw is None:
            return config
        if not isinstance(raw, list):
            raise InvalidFile(FILE, "sources", f"`sources` must be a list, found {_found(raw)}")
        return _with_sources(config, tuple(_source(item, n) for n, item in enumerate(raw)))

    def dumps(self) -> str:
        body = schema.mapping(self)
        if self.sources:
            body["sources"] = [_dump_source(s) for s in self.sources]
        return dump_yaml(body)


def _with_sources(config: Config, sources: tuple) -> Config:
    from dataclasses import replace

    return replace(config, sources=sources)


def _source(raw: Any, n: int) -> Source | UnrecognisedSource:
    where = f"sources[{n}]"
    if not isinstance(raw, dict):
        raise InvalidFile(FILE, where, f"`{where}` must be a mapping, found {_found(raw)}")
    found_type = raw.get("type")
    if found_type is not None and not isinstance(found_type, str):
        raise InvalidFile(FILE, f"{where}.type",
                          f"`{where}.type` must be a string, found {_found(found_type)}")
    kind = SOURCE_KINDS.get(found_type)
    if kind is None:
        found_id = raw.get("id")
        return UnrecognisedSource(
            id=found_id if isinstance(found_id, str) else "",
            type=found_type,
            raw=dict(raw))
    return kind.parse(raw, where=where)


def _dump_source(source: Source | UnrecognisedSource) -> dict:
    if isinstance(source, UnrecognisedSource):
        return dict(source.raw)
    return SOURCE_KINDS[source.type].dump(source)


class ConfigCapability:
    def __init__(self, corpus: Corpus):
        self._corpus = corpus

    def load(self) -> Config:
        return Config.loads((self._corpus.path / FILE).read_text(encoding="utf-8"))
