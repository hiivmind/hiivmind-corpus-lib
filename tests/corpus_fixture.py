"""A corpus and its upstream built in a temporary directory, and a stand-in `gh`: the `Corpus` the package's tests and the
instance's tests both build on. It uses nothing of agent-core.

The layout of one corpus fixture, under `tmp_path`:

    upstream/      the documentation's own git repository (branch main): docs/a.md, b.md, c.md; a second commit
    origin.git/    the bare remote of the corpus repository
    clone/         a clone of origin holding hiivmind-corpus-test/ (the corpus) beside hiivmind-corpus-other/; `corpus_second`
                   holds hiivmind-corpus-second/ instead, whose source `guide` has its documents under manual/
    bin/gh         the stand-in `gh`, first on PATH
"""

import itertools
import json
import os
import shutil
import stat
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import yaml

FIXTURES = Path(__file__).resolve().parent / "fixtures"
RENDER_INDEX = FIXTURES / "render-index.sh"
BASE_SETTINGS = {"BASE_BRANCH": "main", "PUSH": False}   # the instance's config/base.yaml, under the generated settings file

GH_STANDIN = """#!{python}
import json, os, sys
args = sys.argv[1:]
with open(os.environ["GH_STANDIN_LOG"], "a") as log:
    log.write(json.dumps(args) + "\\n")
if args[:2] == ["pr", "list"]:
    canned = os.environ.get("GH_STANDIN_PRS", "")
    print(open(canned).read() if canned and os.path.exists(canned) else "[]")
elif args[:2] == ["pr", "create"]:
    print("https://github.com/test/test/pull/1")
"""


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)} (in {cwd}) failed: {r.stderr.strip()}")
    return r.stdout.strip()


def _init(path: Path, *args: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", *args, str(path)], check=True)
    if "--bare" not in args:
        for key, value in (("user.name", "Test"), ("user.email", "test@example.com"), ("commit.gpgsign", "false")):
            _git(path, "config", key, value)
    return path


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    if subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--quiet"]).returncode:
        _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _dump(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))


def _entry(source: str, name: str) -> dict:
    return {
        "id": f"{source}:{name}", "source": source, "path": name, "title": name.removesuffix(".md").upper(),
        "summary": f"The file {name}.", "tags": ["test"], "keywords": [name.removesuffix(".md")], "concepts": ["concept"],
        "category": "reference", "content_type": "markdown", "size": "standard", "grep_hint": None,
        "headings": [], "links_to": [], "links_from": [], "frontmatter": {}, "stale": False, "stale_since": None,
        "last_indexed": "2026-01-01T00:00:00Z",
    }


def _render(entries: list[dict]) -> str:
    """`index.md` as `render-index.sh` writes it for these entries, which all have one category."""
    lines = ["# Test Documentation Index", "", f"> Sources: 1 | Entries: {len(entries)} | Generated: 2026-01-01T00:00:00Z",
             "> Generated from `index.yaml` — do not edit directly", "", "---", "", "## Reference", ""]
    lines += [f"- **{e['title']}** `{e['id']}` - {e['summary']}" for e in sorted(entries, key=lambda e: e["title"])]
    lines += ["", "---", "", "*Rendered from index.yaml at 2026-01-01T00:00:00Z*", ""]
    return "\n".join(lines)


class Corpus:
    """A corpus repository clone and everything around it. Every helper that changes the corpus commits and pushes, so the tree stays clean and main is not ahead of origin."""

    SCRIPTS: Path | None = None   # the scripted-backend scripts `scripts()` fills: an instance's `tests/scripts/`

    def __init__(
        self, base: Path, *, at_root: bool, push: bool, extra_files: int, stale: tuple[str, ...], checkout: bool,
        corpus_name: str = "test", source: str = "docs", docs_root: str = "docs",
    ):
        self.base = base
        self.upstream = _init(base / "upstream")
        self.origin = _init(base / "origin.git", "--bare")
        self.clone = _init(base / "clone")
        self.bin = base / "bin"
        self.gh_log = base / "gh.log"
        self.gh_prs = base / "gh-prs.json"
        self._counter = itertools.count(1)
        self.branch_prefix = f"automated/corpus-refresh-{corpus_name}"

        names = ["a.md", "b.md", "c.md"] + [f"m{i:02d}.md" for i in range(1, extra_files + 1)]
        (self.upstream / docs_root).mkdir()
        for name in names:
            (self.upstream / docs_root / name).write_text(f"# {name}\n\nFirst version of {name}.\n")
        self.first_sha = _commit(self.upstream, "docs: first")
        (self.upstream / docs_root / "a.md").write_text("# a.md\n\nChanged.\n")
        (self.upstream / docs_root / "d.md").write_text("# d.md\n\nNew.\n")
        (self.upstream / docs_root / "c.md").unlink()
        self.upstream_head = _commit(self.upstream, "docs: change a, add d, delete c")

        self.path = self.clone if at_root else self.clone / f"hiivmind-corpus-{corpus_name}"
        self.path.mkdir(exist_ok=True)
        _dump(self.path / "config.yaml", {
            "schema_version": 2,
            "corpus": {"name": corpus_name, "display_name": corpus_name.title(), "created_at": "2026-01-01T00:00:00Z", "keywords": [corpus_name]},
            "sources": [{
                "id": source, "type": "git", "repo_url": str(self.upstream), "branch": "main", "docs_root": docs_root,
                "last_commit_sha": self.first_sha, "last_indexed_at": "2026-01-01T00:00:00Z",
            }],
            "index": {"format": "markdown", "last_updated_at": "2026-01-01T00:00:00Z"},
            "settings": {"include_patterns": ["**/*.md"], "exclude_patterns": ["**/_*.md"]},
        })
        entries = [_entry(source, name) for name in names]
        _dump(self.path / "index.yaml", {
            "meta": {"corpus": corpus_name, "source": source, "generated_at": "2026-01-01T00:00:00Z", "entry_count": len(entries)},
            "entries": entries,
        })
        (self.path / "graph.yaml").write_text(
            'schema_version: 2\n\nconcepts:\n  concept:\n    label: "Concept"\n    description: "The one concept of the test corpus"\n'
            '    tags: ["test"]\n'
        )
        shutil.copy(RENDER_INDEX, self.path / "render-index.sh")
        (self.path / "index.md").write_text(_render(entries))
        if not at_root:
            other = self.clone / "hiivmind-corpus-other"
            other.mkdir()
            (other / "config.yaml").write_text("schema_version: 2\n")
        (self.clone / ".gitignore").write_text("**/.source/\n**/.cache/\n")
        _commit(self.clone, "corpus: first")
        _git(self.clone, "remote", "add", "origin", str(self.origin))
        _git(self.clone, "push", "-q", "-u", "origin", "main")

        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text(GH_STANDIN.format(python=sys.executable))
        gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        self.settings_file = base / "settings.yaml"
        written = {"CORPUS_PATH": str(self.path), "CORPUS_REPO": "test/test", "BRANCH_PREFIX": self.branch_prefix, "PUSH": push}
        _dump(self.settings_file, written)
        self.settings = SimpleNamespace(**{**BASE_SETTINGS, **written, "CORPUS_PATH": self.path})

        if checkout:  # the working copy of the source, at the upstream's head, where the scanner reads its files
            source_clone = self.path / ".source" / source
            source_clone.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "clone", "-q", str(self.upstream), str(source_clone)], check=True)
        if stale:
            self.mark_stale(*stale)

    def next_dir(self, label: str) -> Path:
        """A path under the fixture's directory that no one has been given before; not created."""
        return self.base / f"{label}-{next(self._counter)}"

    # --- the environment the stand-in `gh` needs -------------------------------------------------------------------
    def environment(self) -> dict[str, str]:
        return {
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "GH_STANDIN_LOG": str(self.gh_log),
            "GH_STANDIN_PRS": str(self.gh_prs),
        }

    # --- reading and writing the clone -----------------------------------------------------------------------------
    def git(self, *args: str) -> str:
        """Run git in the clone; the standard output, stripped."""
        return _git(self.clone, *args)

    def write(self, path: str, text: str) -> None:
        """Write a file, relative to the corpus directory. Does not commit."""
        target = (self.path / path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def entry(self, id: str) -> dict:
        """The entry of `index.yaml` with this id, as it is on disk now."""
        found = [e for e in yaml.safe_load((self.path / "index.yaml").read_text())["entries"] if e["id"] == id]
        assert len(found) == 1, f"{len(found)} entries with id {id}"
        return found[0]

    def _save(self, message: str) -> None:
        """Commit on main and push it: `repo_prepare` refuses a main that is ahead of origin's."""
        _commit(self.clone, message)
        _git(self.clone, "push", "-q", "origin", "HEAD:refs/heads/main")

    def _edit(self, file: str, change, message: str) -> None:
        data = yaml.safe_load((self.path / file).read_text())
        change(data)
        _dump(self.path / file, data)
        self._save(message)

    # --- helpers that set up state; each commits --------------------------------------------------------------------
    def set_last_sha(self, sha: str) -> None:
        self._edit("config.yaml", lambda d: d["sources"][0].__setitem__("last_commit_sha", sha), "test: set last_commit_sha")

    def set_repo_url(self, url: str) -> None:
        self._edit("config.yaml", lambda d: d["sources"][0].__setitem__("repo_url", url), "test: set repo_url")

    def add_source(self, source: dict) -> None:
        self._edit("config.yaml", lambda d: d["sources"].append(source), "test: add a source")

    def add_entry(self, entry: dict) -> None:
        self._edit("index.yaml", lambda d: d["entries"].append(entry), "test: add an entry")

    def mark_stale(self, *ids: str) -> None:
        def change(data: dict) -> None:
            for e in data["entries"]:
                if e["id"] in ids:
                    e["stale"], e["stale_since"] = True, date.today().isoformat()
            assert {e["id"] for e in data["entries"] if e.get("stale")} >= set(ids), f"no such entries: {ids}"
        self._edit("index.yaml", change, "test: mark entries stale")

    def set_concepts(self, id: str, concepts: list[str]) -> None:
        def change(data: dict) -> None:
            [entry] = [e for e in data["entries"] if e["id"] == id]
            entry["concepts"] = concepts
        self._edit("index.yaml", change, "test: set concepts")

    def break_lance_dir(self) -> None:
        """Put a file where the embeddings directory goes, so that `lance_meta.py` cannot open it; committed."""
        target = self.path / "index-embeddings.lance"
        if target.is_dir():
            shutil.rmtree(target)
        target.write_text("not a lance directory\n")
        self._save("test: break the embeddings directory")

    def make_lance(self, generated_at: str) -> None:
        """Give the corpus an embeddings directory whose `_meta` table says it was made at `generated_at`; committed."""
        script = RENDER_INDEX.parent / "make_lance.py"
        subprocess.run(["uv", "run", str(script), str(self.path / "index-embeddings.lance"), generated_at], check=True, capture_output=True)
        self._save("test: add embeddings")

    def set_gh_open_prs(self, prs: list[dict], branch: str | None = None) -> None:
        """Make `gh pr list` print `prs`, and give origin the branch those pull requests are from (four days old by default)."""
        self.gh_prs.write_text(json.dumps(prs))
        branch = branch or f"{self.branch_prefix}-{(date.today() - timedelta(days=4)).isoformat()}"
        _git(self.clone, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")

    # --- scripted-backend scripts -----------------------------------------------------------------------------------
    def scripts(self, case: str | None = None, **tokens: str) -> Path:
        """A filled copy of `tests/scripts/<case or ok>/`, in a temporary directory; its path.

        A node the case has no file for is played from `tests/scripts/ok/`.

        A script is a template. `@CORPUS@` becomes the corpus directory, `@CLONE@` the clone, `@UPSTREAM@` the upstream,
        `@OLD_SHA@` the `last_commit_sha` the corpus holds now, `@NEW_SHA@` the upstream's head, `@OLD_SHA7@` and `@NEW_SHA7@` their first seven characters, `@TODAY@` today's date;
        `tokens` add or replace tokens: `scripts("ok", FILE="a.md")` fills `@FILE@`.
        """
        case = case or "ok"
        old = yaml.safe_load((self.path / "config.yaml").read_text())["sources"][0]["last_commit_sha"]
        fill = {
            "CORPUS": str(self.path), "CLONE": str(self.clone), "UPSTREAM": str(self.upstream), "OLD_SHA": old,
            "NEW_SHA": self.upstream_head, "OLD_SHA7": old[:7], "NEW_SHA7": self.upstream_head[:7],
            "TODAY": date.today().isoformat(), **tokens,
        }
        out = self.next_dir(f"scripts-{case}")
        out.mkdir()
        files = {file.name: file for file in sorted((self.SCRIPTS / "ok").glob("*.json"))}
        files.update({file.name: file for file in sorted((self.SCRIPTS / case).glob("*.json"))})
        for name, file in files.items():
            text = file.read_text()
            for token, value in fill.items():
                text = text.replace(f"@{token}@", json.dumps(value)[1:-1])
            (out / name).write_text(text)
        return out


def make_corpus(monkeypatch, *args, **kwargs) -> Corpus:
    """A `Corpus`, with the environment its stand-in `gh` needs set for the test."""
    corpus = Corpus(*args, **kwargs)
    for key, value in corpus.environment().items():
        monkeypatch.setenv(key, value)
    return corpus
