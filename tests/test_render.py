"""The renderer: `render_texts`, `stale_sub_indexes`, `corpus.render` (spec 7.7, REN-1..3)."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from support import FIXED, corpus_dir, golden

from hiivmind_corpus.config import Config
from hiivmind_corpus.corpus import Corpus
from hiivmind_corpus.index import Entry, Index
from hiivmind_corpus.render import RenderResult, render_texts, stale_sub_indexes


def render_corpus(tmp_path: Path, name: str, clock=lambda: FIXED) -> Corpus:
    import shutil

    from support import GOLDEN

    target = tmp_path / name
    shutil.copytree(GOLDEN / "render" / name, target)
    return Corpus.open(target, clock=clock)


def entry(**fields) -> Entry:
    return Entry(**{"id": "docs:a.md", "source": "docs", **fields})


def single(entries, meta=None) -> dict[str, str]:
    config = Config.loads(golden("render/single/config.yaml"))
    return render_texts(config, Index(meta=meta, entries=tuple(entries)), "Single")


def test_no_category_renders_under_unknown():
    text = single([entry(title="A", summary="s"), entry(id="docs:b.md", title="B", category="unknown")])["index.md"]
    assert text.count("## Unknown") == 1
    assert "Null" not in text and "None" not in text


def test_counts_are_of_the_entries_present(tmp_path):
    corpus = render_corpus(tmp_path, "single")
    text = (corpus.path / "index.yaml").read_text()
    assert "entry_count: 3" in text
    index = Index.loads(text.replace("entry_count: 3", "entry_count: 9"))
    assert index.meta.entry_count == 9 and len(index.entries) == 3
    out = render_texts(corpus.config.load(), index, "Single")["index.md"]
    assert "Entries: 3 |" in out and "Entries: 9" not in out


def test_nothing_depends_on_the_clock(tmp_path):
    a = render_corpus(tmp_path / "a", "tiered", clock=lambda: datetime(2020, 1, 1, tzinfo=UTC))
    b = render_corpus(tmp_path / "b", "tiered", clock=lambda: datetime(2031, 5, 5, tzinfo=UTC))
    assert a.render.texts() == b.render.texts()


def test_a_title_less_entry_renders_and_sorts_by_its_id():
    new = entry(id="polars:new.md", source="polars", summary="Pending re-scan", category="guide", stale=True)
    text = single([new])["index.md"]
    assert "- **polars:new.md** `polars:new.md` - Pending re-scan ⏳ STALE\n" in text
    tied = [entry(id="docs:b.md", title="Same", category="x"), entry(id="docs:a.md", title="Same", category="x"),
            entry(id="docs:0.md", category="x")]
    lines = [ln for ln in single(tied)["index.md"].splitlines() if ln.startswith("- **")]
    assert [ln.split("`")[1] for ln in lines] == ["docs:a.md", "docs:b.md", "docs:0.md"]  # "Same" < "docs:0.md" by code point


def test_an_entry_without_a_summary_omits_it():
    text = single([entry(title="A", category="x")])["index.md"]
    assert "- **A** `docs:a.md`\n" in text


def test_an_index_without_meta_renders_unknown():
    text = single([entry(title="A")], meta=None)["index.md"]
    assert "Generated: unknown" in text
    assert text.endswith("*Rendered from index.yaml at unknown*\n")


def test_a_quick_reference_id_the_index_lacks_is_left_out(tmp_path):
    corpus = render_corpus(tmp_path, "tiered")
    config = replace(corpus.config.load(), render=replace(
        corpus.config.load().render, quick_reference=("docs:gone.md", "docs:api.md")))
    text = render_texts(config, corpus.index.load(), "Tiered")["index.md"]
    assert "docs:gone.md" not in text
    assert "- **Api** `docs:api.md` - The API.\n" in text


def test_stale_sub_indexes_only_when_tiered():
    tiered = Config.loads(golden("render/tiered/config.yaml"))
    assert stale_sub_indexes(tiered, ["index.md", "index-guide.md", "index-old.md", "notes.md"]) == ("index-old.md",)
    assert stale_sub_indexes(Config.loads(golden("render/single/config.yaml")), ["index-notes.md"]) == ()


def test_a_section_removed_from_config_removes_its_sub_index(tmp_path):
    corpus = render_corpus(tmp_path, "tiered")
    config_path = corpus.path / "config.yaml"
    config = Config.loads(config_path.read_text())
    config_path.write_text(replace(config, render=replace(config.render, sections=config.render.sections[:1])).dumps())
    (corpus.path / "index-old.md").write_text("old\n")
    for gone in ("index-guide.md", "index-api.md"):
        (corpus.path / gone).unlink()
    (corpus.path / "index.md").unlink()
    result = corpus.render.write()
    assert result == RenderResult(written=("index.md", "index-guide.md"), removed=("index-old.md",))
    assert not (corpus.path / "index-old.md").exists()
    assert "docs:api.md" in (corpus.path / "index.md").read_text()
    assert "[index-api.md]" not in (corpus.path / "index.md").read_text()
    assert corpus.render.write().written == ()
    assert corpus.render.write() == RenderResult(written=(), removed=())


def test_a_single_corpus_leaves_other_sub_indexes_alone(tmp_path):
    corpus = render_corpus(tmp_path, "single")
    (corpus.path / "index-notes.md").write_text("mine\n")
    (corpus.path / "index.md").unlink()
    result = corpus.render.write()
    assert result == RenderResult(written=("index.md",), removed=())
    assert (corpus.path / "index-notes.md").read_text() == "mine\n"
    assert (corpus.path / "index.md").read_text() == golden("render/single/index.md")


def test_texts_names_the_files_write_leaves(tmp_path):
    corpus = render_corpus(tmp_path, "tiered")
    (corpus.path / "index-old.md").write_text("old\n")
    texts = corpus.render.texts()
    corpus.render.write()
    assert set(texts) == {p.name for p in corpus.path.glob("index*.md")}
    assert texts["index-guide.md"] == golden("render/tiered/index-guide.md")


def test_polars_golden_is_its_single_render(tmp_path):
    corpus = Corpus.open(corpus_dir(tmp_path), clock=lambda: FIXED)
    assert corpus.render.texts() == {"index.md": golden("corpus/polars/index.md")}
