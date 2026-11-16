"""The package is a library of capabilities: it imports neither agent-core nor the instance (CRP-6)."""

import ast
from pathlib import Path

import hiivmind_corpus

PACKAGE = Path(hiivmind_corpus.__file__).parent
FORBIDDEN = ("agent_core", "agent_tools", "tools", "tests")


def test_the_package_imports_neither_agent_core_nor_the_instance():
    found = []
    for file in sorted(PACKAGE.rglob("*.py")):
        if "scripts" in file.relative_to(PACKAGE).parts:   # the plugin's scripts, run by `uv run`, never imported
            continue
        for node in ast.walk(ast.parse(file.read_text())):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
            found += [f"{file.relative_to(PACKAGE)}: {name}" for name in names if name.split(".")[0] in FORBIDDEN]
    assert found == []
