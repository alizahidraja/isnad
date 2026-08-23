# AuditRecord → Governance Evidence Mapping

> **Informational mapping, last verified 23 August 2026. Not legal advice.
> ISNAD produces evidence artifacts; it does not certify compliance with
> any framework. Verify current obligations with qualified counsel.**
>
> Using ISNAD does **not** make you, your product, or your pipeline compliant
> with the EU AI Act, ISO/IEC 42001, the NIST AI RMF, the SDAIA framework, or
> any other regulation. This document maps the *fields* ISNAD emits to the
> *concepts* those instruments discuss, so an auditor can find the evidence
> more easily. It makes no claim of sufficiency.

## Reference dates

| Instrument | Date |
| --- | --- |
| EU AI Act — Art. 4 AI literacy | in force since February 2025 |
| EU AI Act — Art. 50 transparency duties (deployers) | in force since 2 August 2026 |
| Digital Omnibus (dates amended) | in force 27 July 2026 |
| EU AI Act — Annex III high-risk obligations | 2 December 2027 |
| EU AI Act — Annex I (embedded in regulated products) | 2 August 2028 |

## The mapping

Each row maps one `AuditRecord` field to the governance concepts it can
*support as evidence*. The right-hand columns are not "satisfied by" claims —
they are "helps an auditor find" pointers.

| AuditRecord field | EU AI Act | ISO/IEC 42001 (AIMS) | NIST AI RMF | SDAIA |
| --- | --- | --- | --- | --- |
| `record_id`, `generated_at` | Art. 12 record-keeping (logs) | A.7.5 documented information | MEASURE (tracking) | risk management |
| `claim_id`, `claim_text` | Art. 12 traceability; Annex IV tech documentation | A.9 system operation | MAP (context) | data governance |
| `chain[]` (who handled the claim, in order) | Art. 12 logging; Annex IV supply-chain description | A.8.2 AI system lifecycle | GOVERN (accountability) | model accountability |
| `chain[].upstream_ids[]` (the explicit DAG) | Annex IV (dependency graph); Art. 12 traceability | A.8.2 lifecycle | MAP (system structure) | model accountability |
| `chain[].grade`, `grade_rationale` | Art. 14 human-oversight evidence | A.9.3 monitoring | MEASURE (test/validation) | model accountability |
| `chain[].narrator_type` | Annex IV (actors); Art. 50 disclosure of AI use | A.5 roles & responsibilities | GOVERN | transparency |
| `chain[].model_identifier`, `model_version` | Annex IV (model identity); traceability | A.8.1 configuration management | MAP (model cards) | model accountability |
| `chain[].input_hash`, `output_hash` | Art. 12 (immutability of logs) | A.7.5 integrity of records | MEASURE (reproducibility) | data governance |
| `grading_strategy` (name, version, parameters) | Annex IV (methodology description) | A.8.1 configuration management | GOVERN (reproducibility) | model accountability |
| `weakest_link` | Annex IV risk description; Art. 9 risk management | A.8.4 impact assessment | MEASURE (weaknesses) | risk management |
| `source_documents[].uri`, `content_hash`, `licence` | Annex IV training-data documentation | A.7.2 data quality | MAP (data provenance) | data governance |
| `human_oversight[]` (actor, action, timestamp) | **Art. 14 human oversight** | A.5 roles; A.9.3 monitoring | GOVERN (oversight) | **human oversight** |
| `environment.isnad_version`, `python_version`, `platform` | Art. 12 (system identity) | A.8.1 configuration management | GOVERN (reproducibility) | transparency |
| `integrity.record_hash` | Art. 12 (log integrity) | A.7.5 integrity | GOVERN (auditability) | transparency |
| `integrity.detached_signature` (reserved) | Annex IV (authentication) | A.7.5 | GOVERN | — |

## What ISNAD deliberately does *not* provide

- **No conformity statement.** Nothing in an AuditRecord says "compliant."
- **No risk classification.** ISNAD does not decide whether a system is
  "high-risk" under Annex III — that is the provider's legal determination.
- **No human-oversight *decision*.** ISNAD routes to `REVIEW`; it does not
  perform the review.
- **No source-legitimacy attestation.** A `RELIABLE` narrator grade is an
  operator-assigned judgment, not a verified fact about the upstream source.

## Reading the mapping correctly

The columns answer "where does an auditor look for the thing this field
evidences?" — not "does this field satisfy that requirement?" A field can be
necessary evidence and still be insufficient on its own. If a lawyer, a
notified body, or a regulator asks whether ISNAD makes you compliant, the
answer is **no** — and this document exists so that answer is never ambiguous.
