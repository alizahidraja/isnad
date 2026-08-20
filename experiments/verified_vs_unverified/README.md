# Verified vs. Unverified — A/B Demonstration

**Question (issue #7):** Does the trust layer change the output trajectory on
identical queries — not in aggregate, but query-by-query, visibly?

**Answer:** Yes, when it can see the failure. And — honestly — no, when the
failure defeats both of its defenses at once.

This is a *demonstration*, not a statistical experiment.  The statistical
answer already lives in
[`experiments/s8_gated_vs_ungated/`](../s8_gated_vs_ungated/README.md)
(20K claims, 10 seeds, error-vs-coverage curves).  This directory is the
artifact a reader actually *looks at*: the same six queries run through an
identical pipeline with the trust layer off, then on.

## Run it

```bash
python experiments/verified_vs_unverified/run.py
```

No LLM, no API keys, no randomness.  Deterministic and CI-safe.

## What it shows

Six hand-authored scenarios, each a concrete physics query:

| ID | Query | Ground truth | OFF | ON | Outcome |
|----|-------|-------------|-----|-----|---------|
| A | Photon momentum | correct | served | served w/ caveat | baseline ✓ |
| B | Energy conserved? | corrupted | served | **quarantined** | caught |
| C | Fine-structure constant | corrupted (subtle) | served | served w/ caveat | **missed** |
| D | Lorentz factor | corrupted (plausible lie) | served | served w/ caveat | **missed** |
| E | Speed of light | correct | served | recovered via corroboration | recovered ✓ |
| F | Momentum of moving object | corrupted (regime) | served | **review** | caught |

**Summary: 2 caught, 2 missed, 0 false positives.**

## Why the misses are the point

ISNAD has **two independent defenses**, and an honest demonstration must show
both working *and* both failing in concert:

1. **Chain grading** (isnād/rijāl) — catches weak or corrupt transmitters.
2. **Content criticism** (matn) — catches wrong content via the corpus.

A real miss requires **both** to fail at once:

- **Scenario C (stale grade, issue #4):** the scraper is still graded RELIABLE
  but has drifted, corrupting a constant's last digits. Chain grading passes
  (all links look sound); content criticism returns UNVERIFIABLE (the error is
  too subtle). Served.
- **Scenario D (fabricated clean chain, issue #11):** every narrator looks
  RELIABLE, but the source itself is wrong. Chain grading can't see a bad
  source behind a clean chain; content criticism returns UNVERIFIABLE on a
  plausible-sounding lie. Served.

These two scenarios are *deliberately* built around the two open issues the
framework hasn't solved.  That's the honesty discipline: the demonstration
shows the failure modes as prominently as the successes.

## What the caught cases demonstrate

- **B (weak narrator):** the weakest-link rule catches a weak scraper that
  actually corrupts. Content criticism independently flags the negation.
- **E (corroboration):** a DAIF chain is upgraded to HASAN by a second,
  genuinely independent source (different upstream, different model family).
  The `mutābaʿāt` mechanism recovers a claim that would otherwise need review.
- **F (ʿilal):** a sound chain carrying contradicted content — the
  highest-value review case. Content criticism catches what chain grading
  cannot.

## Ground-truth firewall

`fixtures.py` knows ground truth.  `run.py` uses it **only at the end** to
report caught/missed — never during grading or gating.  The grading path
(`build_registry`, `build_chain`, `run_on`) never imports ground truth.
This mirrors the §8 experiment's `ground_truth.py` firewall.

## Relationship to the §8 experiment

| | §8 (statistical) | This (demonstrative) |
|---|---|---|
| Unit | 20,000 claims | 6 queries |
| Question | served-error rate at fixed budget | per-query trajectory |
| Output | error/coverage curves | side-by-side table |
| Honesty | confidence intervals, null result | explicit miss scenarios |

They are complementary.  §8 answers "does it work, statistically?"  This
answers "what does it look like, per query?" — and shows the limits.
