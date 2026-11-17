"""`validate_graph`: the six validation rules of `graph.md` over `graph.yaml` and `index.yaml`, as code. Reads; changes nothing."""

from pathlib import Path

import yaml

RELATIONSHIP_TYPES = ("includes", "depends-on", "see-also", "extends", "contrast-with")
ORIGINS = ("wikilink", "tag", "frontmatter", "manual")
_RELATIONSHIP_FIELDS = ("from", "to", "type", "origin")
_META_FIELDS = ("generated_at", "concept_count", "relationship_count")


def graph_exists(corpus: Path) -> bool:
    """True when the corpus has `graph.yaml`."""
    return (Path(corpus) / "graph.yaml").is_file()


def validate_graph(corpus: Path) -> dict:
    """Check `graph.yaml` against `graph.md`'s rules. Returns `concepts` and `relationships` (counts), `issues`
    (`{"severity", "rule", "detail"}`, in the order of the rules) and `valid` (no issue is an error).

    Errors: `schema`, `dangling-concept`, `dangling-relationship`. Warnings: `orphan-concept`, and `relationship-type` and
    `origin` for a value outside `graph.md`'s vocabulary (the corpora use others; the graph is still consistent)."""
    corpus = Path(corpus)
    data = yaml.safe_load((corpus / "graph.yaml").read_text()) or {}
    index_file = corpus / "index.yaml"
    entries = ((yaml.safe_load(index_file.read_text()) or {}).get("entries") or []) if index_file.is_file() else []
    concepts = data.get("concepts") or {}
    relationships = data.get("relationships") or []
    issues: list[dict] = []

    def issue(severity: str, rule: str, detail: str) -> None:
        issues.append({"severity": severity, "rule": rule, "detail": detail})

    # 1. schema
    if data.get("schema_version") != 2:
        issue("error", "schema", f"schema_version is {data.get('schema_version')!r}, not 2")
    if not isinstance(concepts, dict):
        issue("error", "schema", "concepts is not a mapping")
        concepts = {}
    for cid, concept in concepts.items():
        for field in ("label", "description"):
            if not isinstance(concept, dict) or not isinstance(concept.get(field), str):
                issue("error", "schema", f"concept `{cid}` has no {field}")
    if not isinstance(relationships, list):
        issue("error", "schema", "relationships is not a list")
        relationships = []
    relationships = [r if isinstance(r, dict) else {} for r in relationships]
    for n, rel in enumerate(relationships, 1):
        for field in _RELATIONSHIP_FIELDS:
            if not rel.get(field):
                issue("error", "schema", f"relationship {n} has no {field}")
            elif not isinstance(rel[field], str):
                issue("error", "schema", f"relationship {n}: {field} is not a string")
    # the later rules read only the fields that are strings
    relationships = [{k: v for k, v in rel.items() if isinstance(v, str)} for rel in relationships]
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    for field in _META_FIELDS:
        if field not in meta:
            issue("error", "schema", f"meta has no {field}")
        elif field == "generated_at" and not isinstance(meta[field], str):
            issue("error", "schema", "meta.generated_at is not a string")
        elif field != "generated_at" and not isinstance(meta[field], int):
            issue("error", "schema", f"meta.{field} is not an integer")

    # 2. dangling concept references
    named: set[str] = set()
    for entry in entries:
        for cid in entry.get("concepts") or []:
            named.add(cid)
            if cid not in concepts:
                issue("error", "dangling-concept", f"entry {entry.get('id')} names concept `{cid}`, which graph.yaml lacks")

    # 3. dangling relationships
    for n, rel in enumerate(relationships, 1):
        for end, verb in (("from", "comes from"), ("to", "goes to")):
            if rel.get(end) and rel[end] not in concepts:
                issue("error", "dangling-relationship", f"relationship {n} {verb} `{rel[end]}`, which is not a concept")

    # 4. orphan concepts
    for cid in concepts:
        if cid not in named:
            issue("warning", "orphan-concept", f"concept `{cid}` is named by no entry")

    # 5 and 6. the vocabularies
    for n, rel in enumerate(relationships, 1):
        if rel.get("type") and rel["type"] not in RELATIONSHIP_TYPES:
            issue("warning", "relationship-type", f"relationship {n} uses `{rel['type']}`")
    for n, rel in enumerate(relationships, 1):
        if rel.get("origin") and rel["origin"] not in ORIGINS:
            issue("warning", "origin", f"relationship {n} has origin `{rel['origin']}`")

    return {
        "concepts": len(concepts), "relationships": len(relationships), "issues": issues,
        "valid": not any(i["severity"] == "error" for i in issues),
    }
