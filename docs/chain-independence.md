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
- **The corroboration engine no longer assumes independence from empty
  metadata (PR #83).** `SharedLineageDetector` now returns an `UNKNOWN_LINEAGE_SCORE`
  (0.5, below the gate) when either chain carries no lineage metadata — the
  chains are excluded from corroboration rather than silently trusted as
  independent. Independence is *inferred from* attested-distinct *declared*
  lineage (`model_family` / `upstream_source`) — never *proven*, because distinct
  vendors/families still co-fail on correlated training data (issue 54).
  metadata scored `1.0` — the framework assumed independence exactly when it
  knew the least.

## Candidate approaches (now shipped)

1. **Attestation-backed independence** — require each corroborating chain to
   carry a signed provenance attestation (SLSA/SBOM), and treat "independent"
   as "attested-distinct lineage" (#47). *Status: the half that does not need
   cryptography is shipped — `UNKNOWN_LINEAGE_SCORE` below the gate (PR #83);
   the full SLSA/SBOM hand-off is #47.*
2. **Calibration, not detection** — the **tawātur discount (N_eff)**, shipped in
   v2.10.0: `shared_blind_spot_prior` (default 0.20) prices in the unobservable
   shared-failure probability, so every witness weight is scaled by (1 − prior);
   v2.10.1 makes the prior **witness-type-aware** (shāhid vs mutābaʿa).
3. **Content-level madār detection** — the **detectable half is now shipped and
   engine-wired (v2.12.0)**: when the base claim is CONTRADICTION and a
   corroborating chain repeats the *same error* (identical wrong number or
   flipped negation), `CorroborationEngine` withholds the upgrade and reports
   `content_madar_detected=True` (`core/content_madar.py`).

The *undetectable* half — correlated training data across distinct model
families with no shared source and no checkable error — remains an open,
stated limit.

## Related

- #44 — "share evidence, never grades" (federation makes independence
  *verifiable* rather than *assumed*)
- #47 — provenance interop (SLSA/SBOM attestations can carry training-data
  provenance)
- `docs/case-study-xz-sleeper-narrator.md` §4 — the sock-puppet echo as the
  *detectable* case; the correlated-blind-spot case is the *undetectable* one.
