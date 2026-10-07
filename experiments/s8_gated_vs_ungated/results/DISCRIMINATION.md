# §8 chain discrimination — does the chain grade separate corrupted from clean claims?

**Date:** 2026-10-03 · **Corpus:** four-book (17,021 claims), 10 seeds, 11,918 eval claims/seed.
**Method:** offline + deterministic — rebuild each chain from `chain_json`, grade via
`grade_chain_from_registry` (integrity-threaded, mapping v2), label from `ground_truth.corrupted`.
Run: `uv run python experiments/s8_gated_vs_ungated/discrimination.py` → `results/discrimination.json`.

## 1. Corruption rate by chain grade

| Chain grade | n | corrupted | rate |
|---|---|---|---|
| hasan | 68,019 | 3,107 | **4.6%** |
| daif | 47,814 | 7,206 | **15.1%** |
| daif_jiddan | 3,347 | 498 | **14.9%** |

(No ṣaḥīḥ chains — every §8 chain passes through an ACCEPTABLE or WEAK ingest narrator, so
the weakest link is never better than ḥasan. No mawḍūʿ — §8 has no COMPROMISED-integrity narrator.)

**The chain grade discriminates:** a ḍaʿīf chain is **3.3× more likely to be corrupted** than a
ḥasan chain (15.1% vs 4.6%). This is a WHO signal — the corruption is injected per-narrator,
and the weakest-link grade correctly surfaces the weak narrator's higher fault rate.

## 2. Quarantine precision / recall

| | count |
|---|---|
| quarantined (DAIF_JIDDAN × CONTRADICTION) | 3,581 |
| quarantined + corrupted | 527 |
| **precision** | **14.7%** |

> The 3,581 above is the claim-level replay of this file's discrimination script. `run.py`
> reports a slightly different quarantined total (3,588 summed over 10 seeds) because it counts
> the DAIF_JIDDAN→QUARANTINE action per seed run; the two figures differ by a 7-claim counting
> nuance, not a substantive difference.

Quarantine precision (14.7%) is ~1.7× the overall corruption rate (~9.1%) — the quarantine
cell is a weak-but-real filter, and its value is containment (hold, don't serve), not detection.

## 3. Chain-only acceptance curve (matched coverage)

| X% served | chain-only served-error | random served-error |
|---|---|---|
| 10% | **4.2%** | 9.5% |
| 20% | **4.1%** | 8.9% |
| 30% | **4.3%** | 9.4% |
| 40% | **4.3%** | 9.1% |
| 50% | **4.3%** | 9.2% |

**Chain-only serving halves the served-error rate vs random at every coverage** (≈4.2% vs ≈9.2%).
The chain grade carries real signal that the current serving logic discards.

## What this corrects in the paper

The earlier §8 write-up ended with "the chain grades WHO, so it cannot rank WHETHER
(content) corruption." That conflates two things:

- **The grade itself does discriminate** (4.6% vs 15.1% corruption; 4.2% vs 9.2% served-error).
- **The serving logic discards it** — `run.py` assigns every REVIEW claim priority 0, so the
  review queue never orders by grade, which is why review precision is ≈ random.

The honest §8 sentence is: *"the chain grade separates corrupted from clean claims by ~3×,
but the current serving path does not exploit this ranking — a fixable gap, not a ceiling."*
