# Compliance coverage matrix — EU AI Act & NIST AI RMF (field-level)

Counsel-signed template. Every cell is **COVERED / PARTIAL / NOT COVERED** — never
"compliant." ISNAD produces evidence artifacts; conformity is the deployer's attestation.

## EU AI Act (timeline: high-risk obligations from 2 Dec 2027 — Annex III standalone; 2 Aug 2028 — Annex I embedded)

| Obligation | ISNAD | Coverage | Notes |
|---|---|---|---|
| **Art 12 — record-keeping (logging)** | Chain (isnād) + narrator registry (rijāl) = the operation log, machine-readable, per-transform hashed + graded | **COVERED** | The log ISNAD produces is the Art-12 artifact |
| **Art 13 — transparency to deployers** | Trace schema + decision-matrix rationale = the "interpret the log" mechanism | **PARTIAL** | Intended purpose / capabilities / human-oversight statements are the deployer's, not ISNAD's |
| **Art 9 — risk management** | Not a risk-management tool | **NOT COVERED** | ISNAD is evidence infrastructure |
| **Art 14 — human oversight** | Review-queue (`REVIEW`/`QUARANTINE` actions) + `human_oversight` field | **PARTIAL** | Provides the hook; the oversight process is the deployer's |
| **Art 15 — accuracy/robustness** | Grounding critic + content-madār (composes with critics) | **PARTIAL** | The critic is the coverage ceiling (disclosed); ISNAD doesn't certify accuracy |

## NIST AI RMF (voluntary)

| Function | ISNAD | Coverage |
|---|---|---|
| **Govern — accountability, transparency** | Hash-chained, signed audit records; ordinal grades; honesty box | **COVERED** |
| **Map — context, provenance** | Provenance-native: every claim traces to its source narrator + retrieved evidence (chain-scoped grounding) | **COVERED** |
| **Measure — test/eval, monitoring** | Benchmark (κ=0.871), critic eval, model-drift leaderboard | **PARTIAL** | Continuous production monitoring needs the SIEM export |
| **Manage — mitigation** | Decision matrix (serve/caveat/review/quarantine) + quarantine/reject | **COVERED** |

## ISO/IEC 42001 (AI management system)
- **Documented information / controlled records** — versioned narrator registry + hashed,
  signed records with retention = **COVERED**.
- **Management-system clauses (leadership, objectives, audits)** — organizational =
  **NOT COVERED** (ISNAD is not a management system).

## The one-sentence honesty note
ISNAD is **evidence infrastructure**: it produces the records a compliance officer or
auditor needs, and it never certifies AI-Act conformity, SOC 2, or RMF alignment.
