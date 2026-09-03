# Self-Maintaining KB Demo

A runnable demo of the isnad pipeline adapted to a knowledge base (Recipe 1 of
`docs/onboard-in-a-day.md`). It seeds a narrator registry, ingests a handful of
sample KB claims (each carrying a `source -> scraper -> model` chain), grades
every chain weakest-link, and then shows the *self-maintaining loop*: new
evidence re-grades a narrator and the served surface changes.

## Run it

```bash
uv run python examples/self-maintaining-kb/kb.py
```

The script uses only the public isnad API (`isnad` and `isnad.types`), needs no
API keys, and runs entirely in-memory, so it is idempotent.

Run the regression test:

```bash
uv run pytest tests/test_kb_demo.py -q
```

## What you should see

```
ISNAD — Self-maintaining KB demo (Recipe 1)
[1] SEED — provenance is prior (Estimated)
    source:internal-docs     reliable     prior_only=True   "Estimated"
    source:changelog         reliable     prior_only=True   "Estimated"
    scraper:web-generic      weak         prior_only=True   "Estimated"
    model:gpt-4o             acceptable   prior_only=True   "Estimated"
    source:fabricated-bot    rejected     prior_only=True   "Estimated"
[2] INGEST + GRADE
    A: chain SAHIH — weakest link source:internal-docs (reliable); content CONSISTENT → serve_with_caveat  [prior-only]
    B: chain DAIF — weakest link scraper:web-generic (weak); content CONSISTENT → review  [prior-only]
    C: chain MAWDU — weakest link source:fabricated-bot (rejected); content UNVERIFIABLE → reject_and_quarantine_narrator  [prior-only]
[3] SERVED SURFACE: A (serve_with_caveat)
[4] SELF-MAINTAINING RE-GRADE
    4a survival      source:internal-docs: observation_backed=True
        A: chain SAHIH -> action serve  [observation-backed]
    4b contradiction source:internal-docs: acceptable  # downgraded
        A: chain HASAN -> serve_with_caveat  [observation-backed]
    4c quarantine    source:fabricated-bot: rejected / compromised / inactive=True
        SERVED SURFACE: A (serve_with_caveat)
[5] HONEST SURVIVAL: self_verified=True -> no-op; duplicate -> no-op
    grade acceptable -> acceptable (unchanged); observed evidence 2 -> 2 (both no-ops)
```

## Reading the output, beat by beat

1. **SEED** — five narrators are seeded as `BOOTSTRAP_SEED` evidence, so their
   provenance is *prior* (`prior_only=True`). A prior is an assumption (an
   "Estimated" population estimate), never an observation.
2. **INGEST + GRADE** — each claim's chain is graded weakest-link:
   - **A** is a single-link chain through a `reliable` source → `sahih`, and
     content is `consistent`. But the source is *prior-only*, so the serve gate
     caps plain `serve` to `serve_with_caveat`.
   - **B** adds a `weak` scraper → the chain floor drops to `daif` → `review`.
   - **C** flows through a `rejected` source → `mawdu` → the claim is rejected
     and the narrator is quarantined.
3. **SURFACE** — only `serve` / `serve_with_caveat` verdicts are served. `B`
   (review) and `C` (rejected) are excluded.
4. **SELF-MAINTAINING LOOP** — new evidence mutates narrator grades and the
   surface follows:
   - **4a** a second source (`source:changelog`) confirms the claim, the
     operator records the survival, and the source's provenance flips from prior
     to observation-backed. Its grade stays `reliable`, so the prior-only caveat
     lifts and A becomes a plain `serve`.
   - **4b** the operator records a precision (ḍabṭ) strike — a correction
     disagrees with the ship date — which downgrades the source
     `reliable → acceptable`; A's chain drops `sahih → hasan` and A is no longer
     a plain `serve`.
   - **4c** the fabricated-bot is *quarantined* (`rejected` / `compromised` /
     inactive); its claim stays off the served surface.
5. **HONEST SURVIVAL** — the tazkiyah guard refuses self-verified survival, and
   claim-scoped dedup refuses a duplicate `(claim, source)`. Grades cannot be
   farmed.

## Honesty notes

- Every shipped seed is a **prior** ("Estimated"), never an observation. A
  prior-only chain can never plain-`serve`; it is capped to `serve_with_caveat`
  / `review` until someone observes the transmitter in the pipeline.
- Grades are **ordinal** (`sahih`/`hasan`/`daif`/`mawdu`); the demo never prints
  a numeric confidence — only `.value` ordinals and human-readable rationale.
- The **`DeterministicRuleCritic` is a reference stub** that does exact string
  matching. Here "consistent" means *the claim is verbatim a fact the KB already
  holds* — not semantic agreement with a source document. A production KB swaps
  in an embedding- or LLM-backed critic for real content criticism.
- The **survival in beat 4a is operator-recorded** (a real second source,
  `source:changelog`, is registered first) — it is not a self-seal, and it is
  never fabricated by the script.
- Quarantine is **active containment**: `rejected` + `compromised` + inactive,
  and it never time-decays.
