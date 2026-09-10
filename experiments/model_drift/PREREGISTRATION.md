# Model-drift leaderboard — preregistered methodology (#71)

**Status: FROZEN.** This methodology is committed before any result is computed.
A change to this file after the freeze produces a new methodology version and a new
result version — never a silent edit. The git SHA at freeze is recorded in
`results/methodology_sha.txt` (generated on first `run.py` execution).

**Freeze date:** 2026-09-09
**Issue:** #71 (public model-drift leaderboard)

---

## 1. The question

How does the **hallucination rate** of a claim change as it passes through an
increasingly **deep multi-agent chain** (depth 1 → N), and how well does ISNAD's
chain-grade + content-critic + decision-matrix pipeline **catch** that hallucination
at each depth? Ranked per model family, with negative controls.

This is **not** a single-hop accuracy benchmark and **not** a claim of general
hallucination-detection superiority.

## 2. Dataset

- **Fact corpus:** a fixed set of ground-truth assertions (one per fact), across
  domains (geography, physics, astronomy, history, biology, chemistry). Each fact
  carries a deterministic set of key (entity, value) pairs used by the oracle.
- **Chain templates:** for each depth `d` in the sweep, a fixed multi-agent topology
  (retriever → synthesis → critic → re-synthesis → …) whose hops map to ISNAD
  `TransformType` (PASS_THROUGH / GENERATIVE / DESTRUCTIVE).
- **Determinism:** the corpus and templates are committed and hash-pinned
  (`dataset_sha256`).

## 3. Ground truth (non-circular)

- `oracle.py` labels each generated claim as `faithful` / `hallucinated` /
  `unverifiable`, using **only** the fact corpus's key (entity, value) pairs — a
  deterministic entailment/keyword matcher. The oracle is **never** the critic under
  test, and is human-verified against a gold sample (≥ 95% agreement) before any
  result is trusted.

## 4. Metric

- **Primary:** per-depth `hallucination_rate` = (# hallucinated claims) / (# claims).
- **Secondary:** per-depth `served_error_rate` = (# hallucinated claims that ISNAD
  still SERVEs) / (# hallucinated claims). This is the number that matters: does the
  pipeline *catch* the drift, or serve it?
- **Aggregate:** a pre-declared depth-aggregated mean across the sweep, reported
  **beside** the per-depth breakdown (never a single conflated average without it).

## 5. Model roster & depth sweep

- Depth sweep: **1, 2, 3, 4, 5**.
- Model families: pinned `(provider, model_id)` tuples, each run at
  `temperature=0.0`, fixed `seed`, recorded in the result provenance. **Live runs
  require paid API keys and incur cost** — the harness runs an **offline mode** that
  substitutes a deterministic drift-injector (a preregistered corruption probability
  per hop) and renders real numbers for the *pipeline*, while any live-model cell that
  was not actually run is rendered as **"not run"**, never fabricated.

## 6. Negative controls

- **No-gating baseline:** serve-everything (decision matrix bypassed) — the
  hallucination rate with zero ISNAD gating.
- **Shuffled/empty critic:** a critic that returns UNVERIFIABLE always — the
  pipeline's behavior with a useless critic.

## 7. Reproduction

`uv run python -m experiments.model_drift.run --seed 0 [--offline]` produces
byte-identical raw results on two consecutive runs for every pinned model at a given
depth. Every emitted row carries exact provenance: model/provider ID, temperature,
seed, generation date, API config, dataset SHA-256.

## 8. Hard limits (stated on the public page)

- Live multi-family runs require paid API keys and incur cost.
- Single dataset domain (the fixed fact corpus).
- The critic identity per run is recorded.
- The metric does **not** claim general hallucination-detection superiority.
