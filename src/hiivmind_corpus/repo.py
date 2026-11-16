"""The repository step before a refresh: `prepare_base`, the first part of the template's Phase 2. Branch, commit, push and
pull request are the `publish` node's procedure.

Every git command runs in the corpus directory, which may be the repository's root or a directory inside it. Nothing here
forces, rewrites history, or touches a file outside it.
"""

import subprocess
from pathlib import Path

REMOTE = "origin"
TIMEOUT = 300   # seconds for one git or gh command


class RepoError(RuntimeError):
    """A git or gh command failed or the repository is not ready. The message holds the command and what it said."""


def _run(command: list[str], cwd: Path, *, ok: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    try:
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        raise RepoError(f"{' '.join(command)} (in {cwd}) did not finish in {TIMEOUT} s") from None
    except OSError as e:
        raise RepoError(f"{' '.join(command)}: cannot run: {e}") from None
    if done.returncode not in ok:
        why = " ".join((done.stderr or done.stdout).split()) or "no message"
        raise RepoError(f"{' '.join(command)} (in {cwd}) exited {done.returncode}: {why}")
    return done


def _git(corpus: Path, *args: str) -> str:
    return _run(["git", *args], Path(corpus)).stdout.strip()


def prepare_base(corpus: Path, base_branch: str) -> bool:
    """Stop on a dirty tree; else check out `base_branch`, fetch `origin` and fast-forward; stop when the base branch has
    commits `origin` lacks. Returns True; a problem raises `RepoError` with what was found."""
    dirty = _git(corpus, "status", "--porcelain")
    if dirty:
        raise RepoError(f"the working tree is dirty: {'; '.join(line.strip() for line in dirty.splitlines())}")
    _git(corpus, "checkout", base_branch)
    _git(corpus, "fetch", "--prune", REMOTE)   # every branch of origin, so that none is missed and deleted ones go
    _git(corpus, "merge", "--ff-only", f"{REMOTE}/{base_branch}")
    ahead = int(_git(corpus, "rev-list", "--count", f"{REMOTE}/{base_branch}..HEAD"))
    if ahead > 0:   # an ff-only merge says nothing when the local branch is ahead, and the pull request would carry these
        raise RepoError(f"{base_branch} has {ahead} commit(s) that {REMOTE}/{base_branch} does not have")
    return True
