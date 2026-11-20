"""Shared test helpers."""

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

FIXED = datetime(2026, 11, 20, 9, 0, tzinfo=UTC)

GOLDEN = Path(__file__).parent / "golden"


def golden(path: str) -> str:
    return (GOLDEN / path).read_text(encoding="utf-8")


@dataclass(frozen=True)
class StubCorpus:
    """What a source kind needs of a Corpus: its path, repo root, name and clock."""

    path: Path
    repo_root: Path

    @property
    def name(self) -> str:
        return self.path.name

    def now(self) -> datetime:
        return FIXED


def write_tree(root: Path, files: dict[str, str]) -> Path:
    root = Path(root)
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def corpus_dir(tmp_path: Path, name: str = "polars") -> Path:
    import shutil

    target = Path(tmp_path) / name
    shutil.copytree(GOLDEN / "corpus" / name, target)
    return target


def open_corpus(tmp_path: Path, name: str = "polars"):
    from hiivmind_corpus.corpus import Corpus

    return Corpus.open(corpus_dir(tmp_path, name), clock=lambda: FIXED)
