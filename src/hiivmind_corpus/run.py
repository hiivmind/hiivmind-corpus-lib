"""The plugin's scripts, carried as package data and run as the nodes ran them: `uv run <script>`, each in the environment its
PEP 723 header names."""

import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent / "scripts"


def run_script(name: str, *args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """Run `uv run <SCRIPTS>/<name> <args>`; its exit code, standard output and error, as text."""
    return subprocess.run(
        ["uv", "run", str(SCRIPTS / name), *args], cwd=SCRIPTS, capture_output=True, text=True, stdin=subprocess.DEVNULL,
        timeout=timeout,
    )
