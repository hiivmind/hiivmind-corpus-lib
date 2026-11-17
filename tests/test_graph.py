"""`validate_graph`: the six rules of `graph.md` over `graph.yaml` and `index.yaml`, each with its severity (design §4.4)."""

import yaml

from hiivmind_corpus.graph import graph_exists, validate_graph

META = {"generated_at": "2026-01-01T00:00:00Z", "concept_count": 2, "relationship_count": 1}


def graph(corpus, *, concepts=None, relationships=None, meta=None, version=2) -> None:
    """Write `graph.yaml`: by default two concepts, `concept` (the one the fixture's entries name) and `other`, and one valid
    relationship between them."""
    concepts = concepts if concepts is not None else {
        "concept": {"label": "Concept", "description": "The test concept"},
        "other": {"label": "Other", "description": "Another"},
    }
    relationships = relationships if relationships is not None else [{"from": "concept", "to": "other", "type": "see-also", "origin": "manual"}]
    corpus.write("graph.yaml", yaml.safe_dump({"schema_version": version, "concepts": concepts, "relationships": relationships, "meta": meta or META}))


def found(corpus) -> dict:
    result = validate_graph(corpus.path)
    return result | {"rules": [(i["rule"], i["severity"]) for i in result["issues"]]}


def errors(result: dict) -> list[tuple[str, str]]:
    return [(i["rule"], i["detail"]) for i in result["issues"] if i["severity"] == "error"]


def test_the_fixture_graph_is_valid(corpus):
    assert found(corpus) == {"concepts": 1, "relationships": 0, "issues": [], "valid": True, "rules": []}


def test_schema_needs_version_2(corpus):
    graph(corpus, version=1)
    result = found(corpus)
    assert ("schema", "error") in result["rules"] and result["valid"] is False


def test_schema_needs_a_concept_label_and_description(corpus):
    graph(corpus, concepts={"concept": {"label": "Concept"}, "other": {"label": "Other", "description": "Another"}})
    result = found(corpus)
    assert errors(result) == [("schema", "concept `concept` has no description")] and result["valid"] is False


def test_schema_needs_each_relationship_field(corpus):
    graph(corpus, relationships=[{"from": "concept", "to": "other", "type": "see-also"}])
    result = found(corpus)
    assert errors(result) == [("schema", "relationship 1 has no origin")] and result["valid"] is False


def test_schema_needs_the_meta_counts(corpus):
    graph(corpus, meta={"generated_at": "2026-01-01T00:00:00Z"})
    result = found(corpus)
    assert errors(result) == [("schema", "meta has no concept_count"), ("schema", "meta has no relationship_count")]
    assert result["valid"] is False


def test_a_dangling_concept_reference_is_an_error(corpus):
    corpus.set_concepts("docs:a.md", ["concept", "missing"])
    result = found(corpus)
    assert errors(result) == [("dangling-concept", "entry docs:a.md names concept `missing`, which graph.yaml lacks")]
    assert result["valid"] is False


def test_a_dangling_relationship_is_an_error(corpus):
    graph(corpus, relationships=[{"from": "concept", "to": "nowhere", "type": "see-also", "origin": "manual"}])
    result = found(corpus)
    assert errors(result) == [("dangling-relationship", "relationship 1 goes to `nowhere`, which is not a concept")]
    assert result["valid"] is False


def test_an_orphan_concept_is_a_warning(corpus):
    graph(corpus)   # no entry names `other`
    result = found(corpus)
    assert result["rules"] == [("orphan-concept", "warning")] and "other" in result["issues"][0]["detail"] and result["valid"] is True


def test_an_origin_outside_the_vocabulary_is_a_warning(corpus):
    corpus.set_concepts("docs:b.md", ["other"])
    graph(corpus, relationships=[{"from": "concept", "to": "other", "type": "see-also", "origin": "embedding-analysis"}])
    result = found(corpus)
    assert result["rules"] == [("origin", "warning")] and result["valid"] is True


def test_a_part_of_relationship_is_a_warning_and_the_graph_is_valid(corpus):
    corpus.set_concepts("docs:b.md", ["other"])
    graph(corpus, relationships=[{"from": "concept", "to": "other", "type": "part-of", "origin": "manual"}])
    result = found(corpus)
    assert result["rules"] == [("relationship-type", "warning")] and "part-of" in result["issues"][0]["detail"] and result["valid"] is True
    assert (result["concepts"], result["relationships"]) == (2, 1)


def test_graph_exists(corpus):
    assert graph_exists(corpus.path) is True
    (corpus.path / "graph.yaml").unlink()
    assert graph_exists(corpus.path) is False
