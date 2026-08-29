## What

<!-- What does this change, and why? Link the issue (e.g. fixes #60). -->

## Scope / non-goals

<!-- What is deliberately NOT in this PR. -->

## How it was validated

<!-- ISNAD's charter is "not over-claiming". Say how this was tested, not just
     that it compiles: -->

- [ ] `uv run pytest` passes (full suite)
- [ ] `uv run ruff check src/ tests/ bench/ experiments/` clean
- [ ] `uv run ruff format --check` clean
- [ ] `uv run mypy src/isnad bench` clean

<!-- If the change affects grading, corroboration, or the decision matrix, say
     which mechanism is affected and how behaviour is unchanged-or-intended. -->

## Honesty check

<!-- Does this weaken any of: the honesty box, the confidence-gating "useless"
     row, the scope/limits section, the open-problems section, or the
     "evidence artifacts, not conformity" line? If yes, justify. -->
