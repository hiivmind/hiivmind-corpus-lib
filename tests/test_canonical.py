"""The shared proofs. Later tasks add files under tests/golden/ and tests/drift/; these pick them up by glob.

A file whose class is not built yet is skipped with a reason, so the proofs stay green meanwhile.
"""

import dataclasses
import importlib
from pathlib import Path

import pytest
import yaml

HERE = Path(__file__).parent
GOLDEN = HERE / "golden"
DRIFT = HERE / "drift"

CLASSES = {"config": ("hiivmind_corpus.config", "Config"),
           "index": ("hiivmind_corpus.index", "Index"),
           "graph": ("hiivmind_corpus.graph", "Graph")}
DIR_KINDS = ("corpus", "render", "migrated")


def _rel(path: Path) -> str:
    return path.relative_to(HERE).as_posix()


def _golden_files() -> list[tuple[str, Path]]:
    found = []
    for kind in CLASSES:
        found += [(kind, p) for p in sorted((GOLDEN / kind).glob("*.yaml"))]
    for group in DIR_KINDS:
        for kind in CLASSES:
            found += [(kind, p) for p in sorted((GOLDEN / group).glob(f"*/{kind}.yaml"))]
    return found


def _drift_files() -> list[tuple[str, Path]]:
    found = []
    for p in sorted(DRIFT.glob("*.yaml")):
        kind = p.name.split("-", 1)[0]
        if kind in CLASSES:
            found.append((kind, p))
    return found


def _corpus_dirs() -> list[Path]:
    return [d for group in DIR_KINDS for d in sorted((GOLDEN / group).glob("*/"))
            if (d / "index.yaml").is_file() and (d / "config.yaml").is_file()]


def _cls(kind: str):
    module, name = CLASSES[kind]
    try:
        mod = importlib.import_module(module)
    except ModuleNotFoundError as e:
        if e.name != module:
            raise
        pytest.skip(f"{module} is not built yet")
    return getattr(mod, name)


def _cases(files):
    if not files:
        return [pytest.param(None, None, id="no-files", marks=pytest.mark.skip(reason="no files yet"))]
    return [pytest.param(kind, path, id=_rel(path)) for kind, path in files]


@pytest.mark.parametrize("kind, path", _cases(_golden_files()))
def test_every_golden_round_trips(kind, path):
    cls = _cls(kind)
    text = path.read_text(encoding="utf-8")
    assert cls.loads(text).dumps() == text


def _paths(node, prefix=()):
    """Key paths of every mapping key whose value is not null; list indexes are ignored."""
    if isinstance(node, dict):
        for k, v in node.items():
            if v is None:
                continue
            yield prefix + (k,)
            yield from _paths(v, prefix + (k,))
    elif isinstance(node, list):
        for item in node:
            yield from _paths(item, prefix)


@pytest.mark.parametrize("kind, path", _cases(_drift_files()))
def test_drift_is_a_fixed_point_and_unknown_keys_survive(kind, path):
    cls = _cls(kind)
    text = path.read_text(encoding="utf-8")
    once = cls.loads(text).dumps()
    assert cls.loads(once).dumps() == once
    lost = set(_paths(yaml.safe_load(text))) - set(_paths(yaml.safe_load(once)))
    assert not lost, f"keys lost by the round trip: {sorted(lost, key=str)}"


def _dir_cases():
    dirs = _corpus_dirs()
    if not dirs:
        return [pytest.param(None, id="no-dirs", marks=pytest.mark.skip(reason="no corpus goldens yet"))]
    return [pytest.param(d, id=_rel(d)) for d in dirs]


@pytest.mark.parametrize("directory", _dir_cases())
def test_the_markdown_goldens_are_what_render_writes(directory):
    try:
        render = importlib.import_module("hiivmind_corpus.render")
    except ModuleNotFoundError as e:
        if e.name != "hiivmind_corpus.render":
            raise
        pytest.skip("hiivmind_corpus.render is not built yet")
    config = _cls("config").loads((directory / "config.yaml").read_text(encoding="utf-8"))
    index = _cls("index").loads((directory / "index.yaml").read_text(encoding="utf-8"))
    corpus = getattr(config, "corpus", None)
    name = getattr(corpus, "display_name", None) or getattr(corpus, "name", None) or directory.name
    expected = {p.name: p.read_text(encoding="utf-8") for p in sorted(directory.glob("index*.md"))}
    assert render.render_texts(config, index, name) == expected
    reversed_index = dataclasses.replace(index, entries=index.entries[::-1])
    assert render.render_texts(config, reversed_index, name) == expected
