# Testing

Use Python 3.12+ and [Hatch](https://hatch.pypa.io/). Run commands from the repository root.
[hatch.toml](hatch.toml) owns the environments and scripts; [pyproject.toml](pyproject.toml) owns the package, its
dependencies and the coverage, ruff and mypy settings; [pytest.ini](pytest.ini) owns pytest's.

## The two test environments

| Environment | Installs | Runs |
|---|---|---|
| `test_github` | the package alone | everything that needs no extra; the rest skip with the module they need |
| `test_extras` | the `embeddings` and `pdf` extras and `tokenizers` | the whole suite |

```bash
python -m pip install hatch
hatch run test_github:test
hatch run test_extras:test
hatch run test_extras:test-cov          # with a coverage report
```

Both run in CI on every pull request that touches the source or the tests
([python-run-pytest.yml](.github/workflows/python-run-pytest.yml)). A change that works only with an extra installed,
or only without one, fails one of the two.

For focused work, `test` passes its arguments to pytest:

```bash
hatch run test_extras:test tests/test_chunks.py -q
hatch run test_extras:test tests/test_search.py::test_hits_are_values_a_set_can_hold
```

Tests share one temporary directory (`test-tmp/`), so run one pytest process at a time.

## What no test does

No test touches the network, runs `git` or `gh`, or downloads a model. `tests/conftest.py` points the fastembed cache
at an empty directory, so the token count is the word estimate unless a test caches a tokenizer itself, and embeddings
use injected embedders. A test that needs an extra's module is marked `@needs("module")` (`tests/support.py`), or skips
its whole module with `pytest.importorskip`.

## Lint, types and complexity

```bash
hatch run ruff:check        # ruff over src; ruff:fix applies the fixes
hatch run mypy:check        # mypy over src and tests, with the extras installed so their imports are checked
hatch run radon:radon-cc    # cyclomatic complexity: blocks graded D or worse
hatch run radon:radon-mi    # maintainability index: modules graded D or worse
hatch build                 # the wheel and sdist, version from src/hiivmind_corpus_lib/__version__.py
```

Ruff, mypy and radon run in CI on pull requests that touch the source. Ruff and mypy fail the check on any finding;
radon only reports (a few functions grade D or E today), as in the mountainash packages.

## Branches

Feature, bugfix, chore and docs branches merge into `develop`. Only a `release/*` or `hotfix/*` branch may open a pull
request into `main` ([main-release-branch-validation.yml](.github/workflows/main-release-branch-validation.yml)).
