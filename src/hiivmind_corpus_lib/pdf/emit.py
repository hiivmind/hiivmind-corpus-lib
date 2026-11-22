"""Markdown emitters and text clean-up."""

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ..yamlio import dump_yaml


def heading(text: str, level: int) -> str:
    return f"{'#' * level} {text}"


def code_block(text: str, language: str = "") -> str:
    return f"```{language}\n{text}\n```"


def table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    data_rows = "\n".join("| " + " | ".join(row) + " |" for row in rows)
    return f"{header_row}\n{separator}\n{data_rows}"


def callout(text: str, kind: str) -> str:
    return f"> **{kind.capitalize()}:** {text}"


def frontmatter(metadata: Mapping[str, Any]) -> str:
    return "---\n" + dump_yaml(dict(metadata)) + "---\n"


def chapter_markdown(metadata: Mapping[str, Any], body: str) -> str:
    return frontmatter(metadata) + "\n" + body


def wikilink(target: str, display: str) -> str:
    return f"[[{target}|{display}]]"


def safe_file_name(title: str, max_length: int = 50) -> str:
    safe = re.sub(r"[^\w\s-]", "", title)
    safe = re.sub(r"[\s]+", "_", safe)
    return safe[:max_length].strip("_")


def dehyphenate(text: str) -> str:
    """Join "inde- pendent" to "independent"; the fragment needs 2+ characters and a lowercase continuation."""
    return re.sub(r"(\w{2,})- ([a-z])", lambda m: m.group(1) + m.group(2), text)
