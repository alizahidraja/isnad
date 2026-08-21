# Contributing to ISNAD

## Branch Flow

We use a two-stage integration model. **Every change goes to `working` first,
then to `main`.** `main` is a release branch; `working` is the integration
branch where things get tested together before they ship.

```
feature/*  ──PR──▶  working  ──PR──▶  main  ──▶  PyPI release
                      │                  │
                 CI runs here      release workflow runs
                 (lint, format,    (bumps version, publishes)
                  type, tests)
```

### Why two stages?

- `working` is where multiple contributors' changes land and get tested
  together. Merge conflicts are caught here, not on `main`.
- `main` is always releasable. Only code that has passed CI on `working`
  gets merged in.
- Merging to `main` (with a `bump:` commit) triggers the PyPI release.

### Step-by-step

1. **Create a feature branch** from `working`:
   ```bash
   git checkout working
   git pull
   git checkout -b feature/my-change
   ```

2. **Make your change**, commit, push:
   ```bash
   git push -u origin feature/my-change
   ```

3. **Open a PR** from `feature/my-change` → **`working`**. CI runs
   automatically (lint, format, type check, tests). Get it reviewed and merged.

4. **When ready to release**, open a PR from `working` → `main`. Before
   merging, bump the version:
   ```bash
   python scripts/bump_version.py patch   # or minor, or major
   ```
   Commit with a message starting `bump:`:
   ```bash
   git commit -am "bump: patch release"
   ```

5. **Merge to `main`**. The release workflow runs tests, builds, and
   publishes to PyPI.

## Versioning

The version lives in **three places** — keep them in lockstep:

| File | Field |
|------|-------|
| `pyproject.toml` | `[project] version` |
| `src/isnad/__init__.py` | `__version__` |
| `CITATION.cff` | `version` |

**Never edit these by hand.** Use the bump script, which updates all three
and fails loudly if they've drifted apart:

```bash
python scripts/bump_version.py patch     # 2.0.9 -> 2.0.10
python scripts/bump_version.py minor     # 2.0.9 -> 2.1.0
python scripts/bump_version.py major     # 2.0.9 -> 3.0.0
python scripts/bump_version.py patch --dry-run   # preview only
```

## Quality Gates (run in CI on every PR)

```bash
uv sync --all-extras
uv run ruff check src/isnad tests        # lint
uv run ruff format --check src/isnad tests  # formatting
uv run mypy src/isnad                    # types
uv run pytest -v --tb=short              # tests
```

## Pull Request Checklist

- [ ] Target branch is `working` (not `main`)
- [ ] Tests pass locally: `uv run pytest -q`
- [ ] Lint clean: `uv run ruff check src/isnad tests`
- [ ] Format clean: `uv run ruff format --check src/isnad tests`
- [ ] No `bump:` commit (version bumps happen only on the `working` → `main` PR)
- [ ] If you changed behavior, update the docs and add a test

## Code Map — where things live

| Concern | Location |
|---------|----------|
| The store (Narrator, Registry, RegistryDB) | `src/isnad/core/registry.py` |
| Grading arithmetic (transition policies, axis split) | `src/isnad/core/policies.py` |
| Grade freshness / time-decay | `src/isnad/core/volatility.py` |
| Chain construction & persistence | `src/isnad/core/chain.py` |
| Weakest-link grading | `src/isnad/core/grading.py` |
| Corroboration + madār detection | `src/isnad/core/corroboration.py` |
| Decision matrix | `src/isnad/core/decision.py` |
| Content critics | `src/isnad/critics/` |
| Trace schema (capture ↔ viewer) | `src/isnad/trace/` |
| LangChain integration | `src/isnad/integrations/langchain/` |
| Live Verify integration (consumer + issuer) | `src/isnad/integrations/liveverify/` |
| Ordinal types, enums, protocols | `src/isnad/types.py` |
| Pydantic DTOs + SQLAlchemy ORM | `src/isnad/models.py` |

**Rule of thumb:** the store and the grading arithmetic are separate files on
purpose.  If you're adding a new *transition policy*, put it in `policies.py`,
not `registry.py`.  If you're adding a new *grading strategy*, `grading.py`.

## Notes for Reviewers

- `main` is protected — the version must be bumped and committed with a
  `bump:` message before the release workflow fires.
- The `scripts/bump_version.py` script asserts all three version locations
  agree, so drift is impossible if everyone uses it.
