import pytest

from hiivmind_corpus_lib.errors import InvalidChanges
from hiivmind_corpus_lib.sources import Change, Changes, Listing, normalise_docs_root, parse_name_status


def test_the_spec_example():
    text = "M\0docs/source/user-guide/a.md\0A\0docs/source/new.md\0D\0README.md\0"
    assert parse_name_status(text, "docs/source") == Changes((Change("M", "user-guide/a.md"), Change("A", "new.md")), 1)


def test_a_missing_path_is_invalid():
    with pytest.raises(InvalidChanges, match="a path is missing after status D") as e:
        parse_name_status("M\0a.md\0D", ".")
    assert e.value.code == "invalid-changes"


def test_empty_text_is_no_changes():
    assert parse_name_status("", "docs") == Changes((), 0)


def test_other_statuses_pass_through():
    assert parse_name_status("T\0a.md\0", ".") == Changes((Change("T", "a.md"),), 0)


def test_a_sibling_directory_is_outside():
    assert parse_name_status("M\0docs/source-old/x.md\0", "docs/source") == Changes((), 1)


def test_listing_of():
    assert Listing.of("43d7572", ["docs/source/a.md", "README.md"], "docs/source") == Listing("43d7572", frozenset({"a.md"}), 1)


@pytest.mark.parametrize("value", [".", "", None, "./"])
def test_docs_root_forms_mean_the_same(value):
    assert normalise_docs_root(value) == "."
    assert parse_name_status("M\0a.md\0", value) == Changes((Change("M", "a.md"),), 0)
    assert Listing.of("h", ["a.md"], value).paths == frozenset({"a.md"})


@pytest.mark.parametrize("value", ["docs/", "./docs", "docs"])
def test_docs_subdirectory_forms(value):
    assert normalise_docs_root(value) == "docs"


def test_two_sources_of_one_repository_with_docs_and_the_root():
    text = "M\0docs/a.md\0M\0README.md\0"
    assert parse_name_status(text, "docs/") == Changes((Change("M", "a.md"),), 1)
    assert parse_name_status(text, ".") == Changes((Change("M", "docs/a.md"), Change("M", "README.md")), 0)
