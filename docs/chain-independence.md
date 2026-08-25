# Chain independence — the framework's known open limit

> This is issue #54, stated publicly so it is never mistaken for a solved
> problem. Anyone building on ISNAD should read this before relying on
> corroboration in a high-stakes setting.

## What corroboration assumes

Corroboration (*mutābaʿāt*) upgrades a claim only when the corroborating chains
are **independent** — otherwise a single error laundered through two correlated
sources would double-count as two independent witnesses.

The `SharedLineageDetector` checks three structural signals and discounts
corroboration when any is found:

1. shared narrator identity,
2. shared model family,
3. shared upstream source.

## What topology cannot prove

Two chains can share **none** of those three signals and still fail together:

1. **Correlated training data / model blind spots** — different models,
   different families, no shared source, yet both reproduce the same
   corpus-wide mistake.
2. **Content-level correlated error** — two genuinely independent sources
   repeating the same *received* mistake (the classical madār problem in a
   different guise).

This is a **structural limit of topology-based independence, not an
implementation bug**. The detector can *prove dependence* (shared signals), but
it can never *prove independence* — it can only fail to find shared signals.

## What ISNAD does about it

- The independence verdict is now **`assumed`** (not `verified`) when no shared
  ancestry is found: *"independence is assumed from topology, not proven
  (correlated blind spots are undetectable)."*
- `shared_ancestry_detected` is the only *proven* outcome — it means
  dependence was found, and corroboration is discounted.
- Corroboration is **capped at ḥasan** regardless — it can never reach ṣaḥīḥ by
  corroboration alone, so the over-trust ceiling is bounded.

## Candidate approaches (none chosen yet)

1. **Attestation-backed independence** — require each corroborating chain to
   carry a signed provenance attestation (SLSA/SBOM), and treat "independent"
   as "attested-distinct lineage" (#47).
2. **Calibration, not detection** — emit a corroboration-strength score that
   decays with the prior probability of shared lineage.
3. **Content-level madār detection** — detect when multiple "independent"
   sources share an identical normalized error pattern, and discount those.

## Related

- #44 — "share evidence, never grades" (federation makes independence
  *verifiable* rather than *assumed*)
- #47 — provenance interop (SLSA/SBOM attestations can carry training-data
  provenance)
- `docs/case-study-xz-sleeper-narrator.md` §4 — the sock-puppet echo as the
  *detectable* case; the correlated-blind-spot case is the *undetectable* one.
