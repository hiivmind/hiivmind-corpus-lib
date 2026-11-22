import tomllib
from pathlib import Path

PYPROJECT = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())


def test_markdown_it_is_a_base_dependency():  # design §6.2
    assert any(d.startswith("markdown-it-py") for d in PYPROJECT["project"]["dependencies"])


def test_the_pdf_extra_is_pymupdf_and_the_dev_group_can_test_it():  # design §6.2, PDF-2
    assert PYPROJECT["project"]["optional-dependencies"]["pdf"] == ["pymupdf>=1.24.0"]
    dev = PYPROJECT["dependency-groups"]["dev"]
    assert any(d.startswith("pymupdf") for d in dev) and any(d.startswith("tokenizers") for d in dev)
