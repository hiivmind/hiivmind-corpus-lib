"""A git source: fresh when the upstream branch's head is the commit the corpus was indexed at."""

import os
import subprocess
from pathlib import Path

TIMEOUT = 60   # seconds for `git ls-remote`


class GitSource:
    def freshness(self, source: dict, corpus: Path) -> tuple[str, str | None]:
        """`git ls-remote <repo_url> refs/heads/<branch>` against `last_commit_sha`. Clones and changes nothing."""
        repo_url, branch = source.get("repo_url"), source.get("branch", "main")
        if not repo_url:
            return "unknown", f"source `{source['id']}` has no repo_url"
        # Never wait for a password: a pre-check that cannot ask anyone must fail instead.
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        try:
            done = subprocess.run(
                ["git", "ls-remote", str(repo_url), f"refs/heads/{branch}"], capture_output=True, text=True, env=env,
                stdin=subprocess.DEVNULL, timeout=TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return "unknown", f"source `{source['id']}`: git ls-remote {repo_url} did not finish in {TIMEOUT} s"
        if done.returncode != 0:
            why = " ".join(done.stderr.split()) or f"exit {done.returncode}"
            return "unknown", f"source `{source['id']}`: git ls-remote {repo_url} failed: {why}"
        lines = done.stdout.split()
        if not lines:
            return "unknown", f"source `{source['id']}`: {repo_url} has no branch `{branch}`"
        return ("current" if lines[0] == source.get("last_commit_sha") else "behind"), None
