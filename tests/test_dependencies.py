import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())
HATCH = tomllib.loads((ROOT / "hatch.toml").read_text())


def test_markdown_it_is_a_base_dependency():  # design §6.2
    assert any(d.startswith("markdown-it-py") for d in PYPROJECT["project"]["dependencies"])


def test_the_pdf_extra_is_pymupdf_and_the_extras_test_environment_can_test_it():  # design §6.2, PDF-2
    assert PYPROJECT["project"]["optional-dependencies"]["pdf"] == ["pymupdf>=1.24.0"]
    extras = HATCH["envs"]["test_extras"]
    assert {"embeddings", "pdf"} <= set(extras["features"])
    assert any(d.startswith("tokenizers") for d in extras["extra-dependencies"])
