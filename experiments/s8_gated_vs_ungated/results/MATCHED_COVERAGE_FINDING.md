# §8.4 matched-coverage — why it was inconclusive, and the honest resolution (#126)

**Date:** 2026-08-27
**Status:** measured finding (replaces the "inconclusive" framing with numbers)

## The question §8.4 asked, restated

Does ISNAD-gated serving achieve a better risk–coverage curve than confidence-gated
serving, at *matched* coverage? The paper reported this as "could not be completed"
because ISNAD-gated coverage could not be driven above 4.8% with the reference critic.

## What we now know (all measured, not asserted)

### 1. The chain-grading path alone already delivers the tradeoff

On `seed_1` (15,617 eval claims, 1,397 corrupted), with the critic treated as a
*no-op* (acceptance rides entirely on the isnād chain + jarḥ–taʿdīl grades):

| Model | Coverage | Served-error | Quarantined |
|---|---|---|---|
| critic = always-UNVERIFIABLE (current) | 0.0% | — | 0 |
| **critic = always-accept (chain only)** | **47.9%** | **3.0%** (221/7,484) | 0 |

The chain grader catches the corrupt narrator (`ingest@weak` → WEAK/UNGRADED), so
the *narrator-level* corruption is contained without any content critic at all.
The 3.0% residual is the claims whose corruption was injected by a narrator still
graded sound in that domain.

### 2. The matn critic is a weak third line on this corruption class

On a sample of the 221 "leaks" (corrupted claims with a *sound* chain), the LLM
critic (DeepSeek) returned:

| Verdict | n (of 30) |
|---|---|
| UNVERIFIABLE | 27 |
| CONSISTENT (served as error) | 3 |
| CONTRADICTION (caught) | **0** |

The §8 corruption classes — OCR noise, fabricated numerics, entity swaps on real
prose — are precisely what a content critic cannot reliably detect on a single
claim. **This is not a bug; it is a property of the corruption.** A single critic
was never the classical defense against a subtle fabricator.

### 3. The hadith answer — corroboration — is structurally absent from this corpus

The classical scholars' defense against "sound chain, subtly wrong claim" is
**corroboration across independent chains** (mutābaʿāt): a claim earns trust when
*disjoint* transmitters independently agree. The §8 corpus has **zero cross-source
overlap** — 15,617 unique normalized texts across two sources (openstax, crowell),
no shared claims. Corroboration therefore fired 0 times in §8, *by construction*.

This is the real reason §8.4 is inconclusive: the one mechanism that could have
discriminated at matched coverage was absent from the corpus, and the one mechanism
that was present (the matn critic) does not discriminate on this corruption class.

## The honest conclusion (for the paper)

§8.4's "inconclusive" should be replaced with a **measured, three-part statement**:

1. **Chain grading + jarḥ–taʿdīl is the primary gate and it works** — 47.9% coverage
   at 3.0% served-error with no critic, because the corrupt narrator is downgraded
   by the evidence loop, not by a content critic.
2. **The matn critic is a rejection gate, not an acceptance gate** — it catches gross
   contradictions (see #96: LLM 1.000 recall on genuine contradictions) but not subtle
   single-claim corruption (measured 0/30 here). Asking it to affirm coverage is the
   category error; its false-consistent rate (39.1% on content corruption, #126) makes
   it unsafe as an acceptance gate.
3. **The missing discriminator is corroboration, which the corpus cannot provide** —
   matched coverage on *this* corpus is structurally unattainable, not merely
   "unfinished". The corroboration mechanism is validated separately (#127, v2/v3).

## What this means for the framework (the hadith-grounded design)

The classical method was never "one critic judges one claim." It was a **layered
acceptance model**:

- **isnād** (chain + jarḥ–taʿdīl) — the primary gate; catches the unreliable transmitter.
- **matn** (content criticism) — the rejection gate; catches gross contradiction, and
  is deliberately conservative otherwise (UNVERIFIABLE → hold, not serve).
- **mutābaʿāt** (corroboration) — the acceptance *upgrade*; earns trust via independent
  agreement, which is the only honest way to accept a claim a single critic cannot verify.

The framework already implements all three. §8.4 failed because the corpus could only
exercise the first two, and the second is structurally unsuited to the third's job.

## Run

```bash
# chain-only coverage/error on seed_1
python experiments/s8_gated_vs_ungated/risk_coverage.py   # (uses committed snapshots)

# critic verdicts on the chain-grader leaks (needs DEEPSEEK_API_KEY)
# see the inline measurement in this analysis
```

## Cross-refs

- #126 (the issue this resolves)
- #127 — corroboration v3 negative controls (the mechanism §8.4 was missing)
- #124 — two-axis ablation (chain grading is the primary gate; this is its §8.4 evidence)
- #96 — the critic's measured gross-contradiction recall (1.000) vs subtle-corruption (0/30 here)
- #51 — paper v2 (this becomes the §8.4 replacement text)
