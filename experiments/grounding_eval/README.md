# Grounding-eval harness (#239)

Measures `ChainScopedGroundingPolicy`'s false-positive rate against a real NLI critic.

## Reproduction

```bash
uv sync --extra nli            # installs sentence-transformers + the NLI model
uv run python experiments/grounding_eval/run.py
```

Writes `results.json` + `RESULTS.md` here.

## Honest status

- The harness aborts (non-zero) when `LocalNLICritic` emits zero CONSISTENT verdicts
  on the positive cases — i.e. it refuses to report FP=0 *by construction* when the
  NLI model is absent. That guard is the point: the default `EmbeddingCritic` is
  contradiction-only, so a run on it would be a tautology.
- The committed `results.json` / `RESULTS.md` are **not present** in this sweep because
  the NLI model was unavailable in the re-run environment. The numbers in the docs are
  "measurable", not "already measured here".
