from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from hiivmind_corpus.errors import InvalidFile
from hiivmind_corpus.schema import NULL, Null, mapping, parse_timestamp, read, stamp
from hiivmind_corpus.yamlio import dump_yaml, load_yaml


@dataclass(frozen=True)
class Item:
    name: str
    tags: tuple[str, ...] | None = None
    line_range: tuple[int, ...] | None = None
    stale_since: datetime | Null | None = field(default=None, metadata={"nullable": True})
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Box:
    items: tuple[Item, ...] | None = None
    note: str | None = None
    meta: dict[str, Any] | None = None
    when: datetime | None = None
    count: int | None = None
    flag: bool | None = None
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Opts:
    strategy: str = "single"
    limit: int = 5
    extra: tuple[tuple[str, Any], ...] = ()


@dataclass(frozen=True)
class Edge:
    from_: str = field(default="", metadata={"key": "from"})
    to: str = ""
    opts: Opts = field(default_factory=Opts, metadata={"omit_default": True})
    kind: str | None = field(default=None, metadata={"omit_default": True})
    by_name: dict[str, Opts] | None = None
    reserved = ("type",)
    extra: tuple[tuple[str, Any], ...] = ()


def load(text, cls=Box):
    return read(cls, load_yaml(text, "index.yaml"), "index.yaml")


def dump(obj):
    return dump_yaml(mapping(obj))


def test_known_keys_in_declaration_order_unknown_after_in_the_order_found():
    box = load("zeta: 1\nnote: n\nitems:\n  - alpha: 1\n    name: a\n    tags: [x]\n    beta: 2\nalpha: [1, 2]\n")
    assert list(mapping(box)) == ["items", "note", "zeta", "alpha"]
    assert box.extra == (("zeta", 1), ("alpha", [1, 2]))
    assert list(mapping(box)["items"][0]) == ["name", "tags", "alpha", "beta"]
    assert box.items[0].extra == (("alpha", 1), ("beta", 2))


def test_absent_stays_absent_and_null_in_a_non_nullable_field_reads_as_absent():
    box = load("items:\n  - name: a\n    tags: null\nnote: null\n")
    assert box.note is None and box.items[0].tags is None
    assert dump(box) == "items:\n  - name: a\n"


def test_a_nullable_field_keeps_an_explicit_null():
    box = load("items:\n  - name: a\n    stale_since: null\n  - name: b\n")
    assert box.items[0].stale_since is NULL and box.items[1].stale_since is None
    assert dump(box) == "items:\n  - name: a\n    stale_since: null\n  - name: b\n"


def test_a_number_or_boolean_in_a_list_of_strings_reads_as_its_text():
    box = load("items:\n  - name: a\n    tags: [pixels, 2048, true]\n")
    assert box.items[0].tags == ("pixels", "2048", "true")


def test_integer_tuples():
    box = load("items:\n  - name: a\n    line_range: [10, 42]\n")
    assert box.items[0].line_range == (10, 42)
    assert dump(box) == "items:\n  - name: a\n    line_range:\n      - 10\n      - 42\n"
    text = "items:\n" + "  - name: x\n" * 3 + "  - name: a\n    line_range: [10, x]\n"
    with pytest.raises(InvalidFile) as e:
        load(text)
    assert e.value.where == "items[3].line_range[1]"


def test_a_value_that_does_not_fit_names_file_and_place():
    pad = "  - name: x\n" * 3
    with pytest.raises(InvalidFile) as e:
        load("items:\n" + pad + "  - name: a\n    tags: 5\n")
    assert e.value.file == "index.yaml" and e.value.where == "items[3].tags"
    with pytest.raises(InvalidFile) as e:
        load("count: true\n")
    assert e.value.where == "count"
    with pytest.raises(InvalidFile) as e:
        load("note: {a: 1}\n")
    assert e.value.where == "note"
    with pytest.raises(InvalidFile) as e:
        load("- a\n- b\n")
    assert e.value.file == "index.yaml" and e.value.where == ""
    with pytest.raises(InvalidFile) as e:
        load("flag: 1\n")
    assert e.value.where == "flag"
    with pytest.raises(InvalidFile) as e:
        load("items:\n  - name: a\n  - 7\n")
    assert e.value.where == "items[1]"


@pytest.mark.parametrize("raw, canonical", [
    ('"2026-03-11T00:00:00Z"', "2026-03-11T00:00:00Z"),
    ('"2026-03-11"', "2026-03-11T00:00:00Z"),
    ('"2026-03-11T10:00:00+10:00"', "2026-03-11T00:00:00Z"),
    ('"2026-03-11T00:00:00.123456+00:00"', "2026-03-11T00:00:00Z"),
    ("2026-03-11T00:00:00Z", "2026-03-11T00:00:00Z"),
    ("2026-03-11", "2026-03-11T00:00:00Z"),
])
def test_every_surveyed_timestamp_form_loads_and_dumps_canonical(raw, canonical):
    box = load(f"when: {raw}\n")
    assert box.when.tzinfo is not None and box.when.utcoffset().total_seconds() == 0
    assert dump(box) == f'when: "{canonical}"\n'


def test_a_timestamp_that_is_not_one_raises():
    with pytest.raises(InvalidFile) as e:
        load('when: "yesterday"\n')
    assert e.value.where == "when"
    assert parse_timestamp("2026-03-11", "f", "w") == datetime(2026, 3, 11, tzinfo=UTC)
    assert stamp(datetime(2026, 3, 11, 10, 0, tzinfo=UTC)) == "2026-03-11T10:00:00Z"


def test_the_dump_style_is_block_two_space_indented_sequences_unfolded():
    note = "word " * 60
    note = note.strip()
    assert len(note) == 299
    note += "!"
    box = Box(
        items=(Item(name="a", tags=("pixels", "2048", "é")), Item(name="b", tags=())),
        note=note, meta={"a": {"b": 1}, "list": [1, 2]})
    expected = (
        "items:\n"
        "  - name: a\n"
        "    tags:\n"
        "      - pixels\n"
        "      - '2048'\n"
        "      - é\n"
        "  - name: b\n"
        "    tags: []\n"
        f"note: {note}\n"
        "meta:\n"
        "  a:\n"
        "    b: 1\n"
        "  list:\n"
        "    - 1\n"
        "    - 2\n"
    )
    assert len(note) == 300
    assert dump(box) == expected
    assert load(expected) == box


def test_omit_default_and_key_alias():
    edge = load("from: a\nto: b\ntype: ignored\nopts: {strategy: single, limit: 5}\nzzz: 1\n", Edge)
    assert edge.from_ == "a" and edge.extra == (("zzz", 1),)
    assert dump(edge) == "from: a\nto: b\nzzz: 1\n"
    edge = load("from: a\nopts: {strategy: tiered}\nkind: ''\nby_name:\n  x: {limit: 1}\n", Edge)
    assert dump(edge) == ("from: a\nto: ''\nopts:\n  strategy: tiered\n  limit: 5\nkind: ''\nby_name:\n  x:\n    strategy: single\n    limit: 1\n")
    assert edge.by_name == {"x": Opts(limit=1)}


def test_a_required_field_that_is_absent_raises():
    with pytest.raises(InvalidFile) as e:
        load("items:\n  - tags: [a]\n")
    assert e.value.where == "items[0].name"


def test_load_yaml_of_empty_text_is_an_empty_mapping_and_a_syntax_error_is_invalid_file():
    assert load_yaml("", "x.yaml") == {} and load_yaml("# only a comment\n", "x.yaml") == {}
    with pytest.raises(InvalidFile) as e:
        load_yaml("a: [1, 2\nb: }", "config.yaml")
    assert e.value.file == "config.yaml" and e.value.where == ""


@pytest.mark.parametrize("text, where", [
    ("from: a\nby_name:\n  123: {limit: 1}\n", "by_name"),
    ("meta:\n  1: x\n", "meta"),
])
def test_a_non_string_mapping_key_is_rejected_with_its_place(text, where):
    cls = Edge if text.startswith("from") else Box
    with pytest.raises(InvalidFile) as e:
        load(text, cls)
    assert e.value.where == where


def test_an_unquoted_invalid_date_is_invalid_file_with_its_place():
    with pytest.raises(InvalidFile) as e:
        load("when: 2026-02-30\n")
    assert e.value.file == "index.yaml" and e.value.where == "when"
