from datetime import UTC, datetime
from pathlib import Path

import pytest

from hiivmind_corpus.config import Config
from hiivmind_corpus.corpus import Corpus
from hiivmind_corpus.errors import InvalidFile, NotACorpus
from hiivmind_corpus.sources import GitSource, UnrecognisedSource
from support import FIXED, corpus_dir, golden, open_corpus

SHA = "5eaa000000000000000000000000000000000000"


def test_the_example_of_7_2():
    text = golden("corpus/polars/config.yaml")
    cfg = Config.loads(text)
    assert cfg.sources[0] == GitSource(
        id="polars", repo_url="https://github.com/pola-rs/polars", branch="main", docs_root="docs/source",
        last_commit_sha=SHA, last_indexed_at=datetime(2026, 11, 19, 10, 0, tzinfo=UTC))
    assert cfg.render.strategy == "single"
    assert "render" not in cfg.dumps()
    assert cfg.dumps() == text


def test_git_golden_has_a_tiered_render_and_an_extra():
    cfg = Config.loads(golden("config/git.yaml"))
    assert cfg.render.strategy == "tiered"
    assert cfg.render.sections[0].id == "guide"
    assert dict(cfg.sources[0].extra) == {"description": "The Polars docs"}


def test_an_unrecognised_kind_loads_and_is_written_back_as_found():
    text = golden("config/unrecognised.yaml")
    cfg = Config.loads(text)
    src = cfg.sources[0]
    assert isinstance(src, UnrecognisedSource)
    assert (src.id, src.type) == ("tickets", "github")
    assert list(src.raw) == ["id", "type", "base", "table", "view"]
    assert cfg.dumps() == text


def test_sources_as_a_mapping_is_invalid_file():
    with pytest.raises(InvalidFile) as e:
        Config.loads("sources:\n  a: 1\n")
    assert e.value.code == "invalid-file"
    assert e.value.file == "config.yaml"
    assert e.value.where == "sources"
    assert "`sources` must be a list, found a mapping" in str(e.value)


def test_a_commented_config_with_unknown_keys_is_a_fixed_point_and_loses_its_comments():
    text = (Path(__file__).parent / "drift" / "config-commented.yaml").read_text(encoding="utf-8")
    once = Config.loads(text).dumps()
    assert Config.loads(once).dumps() == once
    assert "#" not in once
    assert "lib_ref: v1.2" in once
    assert "owner: someone" in once
    assert "type: github" in once


def test_corpus_open(tmp_path, monkeypatch):
    c = open_corpus(tmp_path)
    assert c.name == "Polars"
    assert c.now() == FIXED
    assert c.repo_root == c.path.parent.parent
    assert c.config.load().corpus.name == "polars"
    d = corpus_dir(tmp_path / "x", "polars")
    (d / "config.yaml").write_text("sources: []\n")
    assert Corpus.open(d).name == "polars"
    assert Corpus.open(d, repo_root=Path("/repo")).repo_root == Path("/repo")
    with pytest.raises(NotACorpus) as e:
        Corpus.open("/tmp/nothing-here")
    assert e.value.code == "not-a-corpus"
    assert str(e.value) == "no config.yaml in /tmp/nothing-here"
    monkeypatch.setenv("HOME", str(tmp_path))
    assert Corpus.open("~/x/polars").path == d
    monkeypatch.chdir(tmp_path / "x")
    assert Corpus.open("polars").path == d
    assert isinstance(Corpus.open(d).now(), datetime)


def test_ready(tmp_path):
    assert open_corpus(tmp_path / "1").ready()
    d = corpus_dir(tmp_path / "2")
    (d / "config.yaml").write_text("schema_version: 2\n")
    assert not Corpus.open(d).ready()
    d = corpus_dir(tmp_path / "3")
    (d / "index.yaml").unlink()
    assert not Corpus.open(d).ready()
    d = corpus_dir(tmp_path / "4")
    (d / "index.md").write_text("# X\n\nRun hiivmind-corpus-build to create the index.\n")
    assert not Corpus.open(d).ready()


def test_absent_collections_stay_absent_and_explicit_empty_is_kept():
    absent = "corpus:\n  name: x\nsettings: {}\nbuild:\n  organization: flat\n"
    assert Config.loads(absent).dumps() == absent
    empty = ("corpus:\n  name: x\n  keywords: []\nsettings:\n  include_patterns: []\n"
             "build:\n  skip_sections: []\n")
    assert Config.loads(empty).dumps() == empty


@pytest.mark.parametrize("bad", ["[git]", "{name: git}"])
def test_a_non_string_source_type_is_invalid_file(bad):
    with pytest.raises(InvalidFile) as e:
        Config.loads(f"sources:\n  - id: a\n    type: {bad}\n")
    assert e.value.file == "config.yaml"
    assert e.value.where == "sources[0].type"
