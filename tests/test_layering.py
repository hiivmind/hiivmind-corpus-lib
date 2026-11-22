"""The package is a library of capabilities: it imports neither agent-core nor the instance, runs no command, ships no scripts."""

import ast
import subprocess
import sys
from pathlib import Path

import hiivmind_corpus_lib

PACKAGE = Path(hiivmind_corpus_lib.__file__).parent
ROOT = PACKAGE.parent.parent
FORBIDDEN = ("agent_core", "agent_tools", "tools", "tests")
BANNED_CALLS = {("os", "system"), ("os", "popen"), ("shutil", "which")}


def _trees():
    for file in sorted(PACKAGE.rglob("*.py")):
        yield file, ast.parse(file.read_text())


def test_the_package_imports_neither_agent_core_nor_the_instance():
    found = []
    for file, tree in _trees():
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
            found += [f"{file.name}: {name}" for name in names if name.split(".")[0] in FORBIDDEN]
    assert found == []


def test_the_package_runs_no_command():
    found = []
    for file, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                found += [f"{file.name}: import {a.name}" for a in node.names if a.name.split(".")[0] == "subprocess"]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                module = node.module or ""
                if module.split(".")[0] == "subprocess":
                    found.append(f"{file.name}: from {module}")
                if module == "sys" and any(a.name == "path" for a in node.names):
                    found.append(f"{file.name}: from sys import path")
                if module in ("os", "shutil"):
                    found += [f"{file.name}: {module}.{a.name}" for a in node.names if (module, a.name) in BANNED_CALLS]
            elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if (node.value.id, node.attr) in BANNED_CALLS or (node.value.id, node.attr) == ("sys", "path"):
                    found.append(f"{file.name}: {node.value.id}.{node.attr}")
    assert found == []


def test_the_package_has_no_script_files():
    found = [str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("*") if p.is_dir() and p.name in ("scripts", "templates", "documents")]
    found += [str(p.relative_to(PACKAGE)) for p in PACKAGE.rglob("__main__.py")]
    for p in PACKAGE.rglob("*"):
        if p.is_file() and "__pycache__" not in p.relative_to(PACKAGE).parts:
            data = p.read_bytes()
            if data.startswith(b"#!") or b"# /// script" in data:
                found.append(str(p.relative_to(PACKAGE)))
    if "[project.scripts]" in (ROOT / "pyproject.toml").read_text():
        found.append("pyproject.toml: [project.scripts]")
    assert found == []


def test_importing_the_package_imports_no_extra():
    code = ("import sys, hiivmind_corpus_lib, hiivmind_corpus_lib.pdf; "
            "assert not {'fastembed', 'lancedb', 'pyarrow', 'pymupdf', 'fitz'} & set(sys.modules)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
