"""`Graph` and `corpus.graph`: values, the six rules, `remove_entries` (spec 7.4, 8)."""

import os
from dataclasses import replace
from pathlib import Path

import pytest
from support import corpus_dir, golden, open_corpus

from hiivmind_corpus_lib.errors import InvalidFile
from hiivmind_corpus_lib.graph import Graph, GraphReport, Issue
from hiivmind_corpus_lib.index import Index

META = "meta:\n  generated_at: \"2026-01-01T00:00:00Z\"\n  concept_count: 2\n  relationship_count: 1\n"
CONCEPTS = ("concepts:\n  expressions:\n    label: Expressions\n    description: The expression API\n"
            "  other:\n    label: Other\n    description: Another\n")
REL = "relationships:\n  - from: expressions\n    to: other\n    type: see-also\n    origin: manual\n"


def graph_text(*, version="2", concepts=CONCEPTS, relationships=REL, meta=META) -> str:
    return f"schema_version: {version}\n{concepts}{relationships}{meta}"


def with_graph(tmp_path, text: str):
    corpus = open_corpus(tmp_path)
    (corpus.path / "graph.yaml").write_text(text, encoding="utf-8")
    return corpus


def name_concepts(corpus, entry_id: str, concepts: tuple[str, ...]) -> None:
    path = corpus.path / "index.yaml"
    index = Index.loads(path.read_text())
    entries = tuple(replace(e, concepts=concepts) if e.id == entry_id else e for e in index.entries)
    path.write_text(replace(index, entries=entries).dumps())


def found(corpus):
    report = corpus.graph.validate()
    return report, [(i.rule, i.severity) for i in report.issues]


def errors(report):
    return [(i.rule, i.detail) for i in report.issues if i.severity == "error"]


def test_the_fixture_graph_is_valid(tmp_path):
    assert open_corpus(tmp_path).graph.validate() == GraphReport(concepts=1, relationships=0, issues=(), valid=True)


def test_graph_exists(tmp_path):
    corpus = open_corpus(tmp_path)
    assert corpus.graph.exists() is True
    (corpus.path / "graph.yaml").unlink()
    assert corpus.graph.exists() is False


def test_schema_needs_version_2(tmp_path):
    report, rules = found(with_graph(tmp_path, graph_text(version="1")))
    assert ("schema", "error") in rules and report.valid is False
    assert errors(report)[0] == ("schema", "schema_version is 1, not 2")


def test_schema_needs_a_concept_label_and_description(tmp_path):
    concepts = "concepts:\n  expressions:\n    label: Expressions\n  other:\n    label: Other\n    description: Another\n"
    report, _ = found(with_graph(tmp_path, graph_text(concepts=concepts)))
    assert errors(report) == [("schema", "concept `expressions` has no description")] and report.valid is False


def test_schema_needs_each_relationship_field(tmp_path):
    rel = "relationships:\n  - from: expressions\n    to: other\n    type: see-also\n"
    report, _ = found(with_graph(tmp_path, graph_text(relationships=rel)))
    assert errors(report) == [("schema", "relationship 1 has no origin")] and report.valid is False


def test_schema_needs_the_meta_counts(tmp_path):
    meta = "meta:\n  generated_at: \"2026-01-01T00:00:00Z\"\n"
    report, _ = found(with_graph(tmp_path, graph_text(meta=meta)))
    assert errors(report) == [("schema", "meta has no concept_count"), ("schema", "meta has no relationship_count")]
    assert report.valid is False


def test_schema_needs_generated_at_and_a_meta(tmp_path):
    report, _ = found(with_graph(tmp_path, graph_text(meta="")))
    assert [d for _, d in errors(report)] == ["meta has no generated_at", "meta has no concept_count",
                                              "meta has no relationship_count"]


def test_a_dangling_concept_reference_is_an_error(tmp_path):
    corpus = with_graph(tmp_path, graph_text())
    name_concepts(corpus, "polars:c.md", ("expressions", "missing"))
    report, _ = found(corpus)
    assert errors(report) == [("dangling-concept", "entry polars:c.md names concept `missing`, which graph.yaml lacks")]
    assert report.valid is False


def test_a_dangling_relationship_is_an_error(tmp_path):
    rel = REL.replace("to: other", "to: nowhere")
    report, _ = found(with_graph(tmp_path, graph_text(relationships=rel)))
    assert errors(report) == [("dangling-relationship", "relationship 1 goes to `nowhere`, which is not a concept")]
    rel = REL.replace("from: expressions", "from: nowhere")
    report, _ = found(with_graph(tmp_path / "b", graph_text(relationships=rel)))
    assert errors(report) == [("dangling-relationship", "relationship 1 comes from `nowhere`, which is not a concept")]


def test_an_orphan_concept_is_a_warning(tmp_path):
    report, rules = found(with_graph(tmp_path, graph_text()))   # no entry names `other`
    assert rules == [("orphan-concept", "warning")] and "other" in report.issues[0].detail and report.valid is True


def test_an_absent_index_means_no_entries(tmp_path):
    corpus = with_graph(tmp_path, graph_text())
    (corpus.path / "index.yaml").unlink()
    _, rules = found(corpus)
    assert rules == [("orphan-concept", "warning"), ("orphan-concept", "warning")]


def test_an_origin_outside_the_vocabulary_is_a_warning(tmp_path):
    rel = REL.replace("manual", "embedding-analysis")
    corpus = with_graph(tmp_path, graph_text(relationships=rel, concepts=CONCEPTS.replace("  other:", "  other:")))
    name_concepts(corpus, "polars:c.md", ("other",))
    report, rules = found(corpus)
    assert rules == [("origin", "warning")] and report.valid is True


def test_a_part_of_relationship_is_a_warning_and_the_graph_is_valid(tmp_path):
    rel = REL.replace("see-also", "part-of")
    corpus = with_graph(tmp_path, graph_text(relationships=rel))
    name_concepts(corpus, "polars:c.md", ("other",))
    report, rules = found(corpus)
    assert rules == [("relationship-type", "warning")] and "part-of" in report.issues[0].detail and report.valid is True
    assert (report.concepts, report.relationships) == (2, 1)


def test_the_rules_run_in_the_old_order(tmp_path):
    rel = REL.replace("to: other", "to: nowhere").replace("see-also", "part-of").replace("manual", "x")
    report, rules = found(with_graph(tmp_path, graph_text(version="1", relationships=rel)))
    assert [r for r, _ in rules] == ["schema", "dangling-relationship", "orphan-concept",
                                     "relationship-type", "origin"]
    assert Issue("warning", "origin", "relationship 1 has origin `x`") == report.issues[-1]


@pytest.mark.parametrize("text, where", [
    ("schema_version: 2\nconcepts: [a]\n", "concepts"),
    ("schema_version: 2\nrelationships:\n  - from: a\n    to: 3\n    type: t\n    origin: o\n", "relationships[0].to"),
    ("schema_version: 2\nmeta:\n  concept_count: many\n", "meta.concept_count"),
])
def test_a_malformed_graph_is_invalid_file_on_load(tmp_path, text, where):
    corpus = with_graph(tmp_path, text)
    with pytest.raises(InvalidFile) as e:
        corpus.graph.validate()
    assert (e.value.code, e.value.file, e.value.where) == ("invalid-file", "graph.yaml", where)


def test_the_relationship_from_is_the_file_key():
    graph = Graph.loads(golden("graph/schema-2.yaml"))
    assert graph.relationships[0].from_ == "expressions" and graph.relationships[0].evidence == "polars:a.md"
    assert graph.relationships[1].evidence is None
    assert list(graph.concepts) == ["expressions", "lazy-evaluation"]
    assert "from: expressions" in graph.dumps()


def test_evidence_null_reads_as_absent():
    text = (Path(__file__).parent / "drift" / "graph-evidence-null.yaml").read_text()
    graph = Graph.loads(text)
    assert graph.relationships[0].evidence is None and graph.concepts["a"].tags is None
    assert "evidence" not in graph.dumps()


def test_remove_entries_schema_1(tmp_path):
    corpus = with_graph(tmp_path, golden("graph/schema-1.yaml"))
    corpus.graph.remove_entries({"sas:b.md", "sas:nope.md"})
    after = Graph.loads((corpus.path / "graph.yaml").read_text())
    assert after.concepts["basis"].entries == ("sas:a.md", "sas:c.md") and after.concepts["basis"].entry_count == 2
    assert after.concepts["macros"].entries == () and after.concepts["macros"].entry_count == 0
    expected = golden("graph/schema-1.yaml")
    text = (corpus.path / "graph.yaml").read_text()
    assert "    status: draft\n" in text and list(after.concepts) == ["basis", "macros"]
    assert text == (expected.replace("      - sas:b.md\n", "", 1).replace("entry_count: 3", "entry_count: 2")
                    .replace("    entries:\n      - sas:b.md\n    entry_count: 1", "    entries: []\n    entry_count: 0"))


def test_remove_entries_writes_nothing_when_nothing_is_removed(tmp_path):
    corpus = with_graph(tmp_path, golden("graph/schema-1.yaml").replace("schema_version: 1", "schema_version: 1\n"))
    path = corpus.path / "graph.yaml"
    os.utime(path, (1_000_000, 1_000_000))
    corpus.graph.remove_entries({"sas:nope.md"})
    assert path.stat().st_mtime == 1_000_000


def test_remove_entries_schema_2_changes_nothing(tmp_path):
    corpus = open_corpus(tmp_path)
    path = corpus.path / "graph.yaml"
    before = path.read_bytes()
    os.utime(path, (1_000_000, 1_000_000))
    corpus.graph.remove_entries({"polars:a.md"})
    assert path.read_bytes() == before and path.stat().st_mtime == 1_000_000


def test_remove_entries_without_a_graph_does_nothing(tmp_path):
    corpus = open_corpus(tmp_path)
    (corpus.path / "graph.yaml").unlink()
    corpus.graph.remove_entries(["polars:a.md"])
    assert not (corpus.path / "graph.yaml").exists()


def test_empty_graph_collections_are_kept_and_absent_ones_stay_absent():
    text = "schema_version: 2\nconcepts: {}\nrelationships: []\n"
    graph = Graph.loads(text)
    assert graph.concepts == {} and graph.relationships == () and graph.dumps() == text
    bare = Graph.loads("schema_version: 2\n")
    assert bare.concepts is None and bare.relationships is None and bare.dumps() == "schema_version: 2\n"


def test_validate_treats_absent_collections_as_empty(tmp_path):
    report = with_graph(tmp_path, "schema_version: 2\n").graph.validate()
    assert (report.concepts, report.relationships) == (0, 0)


def test_remove_entries_schema_1_keeps_an_empty_relationships_list(tmp_path):
    text = golden("graph/schema-1.yaml").replace("relationships:\n  - from: basis\n    to: macros\n    type: includes\n    origin: tag\n", "relationships: []\n")
    corpus = with_graph(tmp_path, text)
    corpus.graph.remove_entries({"sas:a.md"})
    out = (corpus.path / "graph.yaml").read_text()
    assert "relationships: []\n" in out and "      - sas:a.md" not in out
