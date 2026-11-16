"""The repository step before a refresh: `repo_prepare` (the template's Phase 2). Branch, commit, push and pull request
are the `publish` node's procedure.

Every git command runs in `CORPUS_PATH`, which may be the repository's root or a directory inside it. Nothing here forces,
rewrites history, or touches a file outside `CORPUS_PATH`.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REMOTE = "origin"
TIMEOUT = 300   # seconds for one git or gh command
BRANCH_SUFFIX = re.compile(r"\d{4}-\d{2}-\d{2}(-\d+)?")   # what `repo_branch` appends to the prefix


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


def _git(settings, *args: str) -> str:
    return _run(["git", *args], Path(settings.CORPUS_PATH)).stdout.strip()


def _pull_requests(settings, branch: str) -> list[dict]:
    command = ["gh", "pr", "list", "--repo", settings.CORPUS_REPO, "--head", branch, "--state", "open", "--json", "number,createdAt"]
    out = _run(command, Path(settings.CORPUS_PATH)).stdout
    try:
        return json.loads(out)
    except ValueError as e:
        raise RepoError(f"{' '.join(command)} printed something that is not JSON: {e}") from None


def _age_days(created_at: str) -> int:
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - created).days


def repo_prepare(settings) -> dict:
    """Stop on a dirty tree; else check out `BASE_BRANCH`, fetch `origin` and fast-forward, and list the earlier refresh branches.

    Returns `main_advanced` (the pull moved `BASE_BRANCH`) and `stale_branches`: `branch`, `pr_number` and `pr_age_days`
    (both `None` when the branch has no open pull request): each `origin/<BRANCH_PREFIX>-*` branch with an open pull
    request, or with commits that `BASE_BRANCH` does not have.
    """
    dirty = _git(settings, "status", "--porcelain")
    if dirty:
        raise RepoError(f"the working tree is dirty: {'; '.join(line.strip() for line in dirty.splitlines())}")
    _git(settings, "checkout", settings.BASE_BRANCH)
    before = _git(settings, "rev-parse", "HEAD")
    _git(settings, "fetch", "--prune", REMOTE)   # every branch of origin, so that none is missed and deleted ones go
    _git(settings, "merge", "--ff-only", f"{REMOTE}/{settings.BASE_BRANCH}")
    ahead = int(_git(settings, "rev-list", "--count", f"{REMOTE}/{settings.BASE_BRANCH}..HEAD"))
    if ahead > 0:   # an ff-only merge says nothing when the local branch is ahead, and the pull request would carry these
        raise RepoError(f"{settings.BASE_BRANCH} has {ahead} commit(s) that {REMOTE}/{settings.BASE_BRANCH} does not have")
    advanced = _git(settings, "rev-parse", "HEAD") != before

    listed = _git(settings, "for-each-ref", "--format=%(refname:short)", f"refs/remotes/{REMOTE}").splitlines()
    stale = []
    for ref in sorted(listed):
        prefix = f"{REMOTE}/{settings.BRANCH_PREFIX}-"
        if not ref.startswith(prefix) or not BRANCH_SUFFIX.fullmatch(ref.removeprefix(prefix)):   # not `...-testing-`, not `...-test-cloud-`
            continue
        branch = ref.removeprefix(f"{REMOTE}/")
        prs = _pull_requests(settings, branch)
        if prs:
            stale.append({"branch": branch, "pr_number": prs[0]["number"], "pr_age_days": _age_days(prs[0]["createdAt"])})
        elif int(_git(settings, "rev-list", "--count", f"{settings.BASE_BRANCH}..{ref}")) > 0:   # work no one has seen
            stale.append({"branch": branch, "pr_number": None, "pr_age_days": None})
    return {"main_advanced": advanced, "stale_branches": stale}

