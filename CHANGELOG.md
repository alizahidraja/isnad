# Changelog

## [2.4.0] — 2026-08-23

### Added

- Audit record DAG support: `chain[].upstream_ids[]` makes branching/merging
  agent graphs explicit, not just linear chains.
- `human_oversight[]` evidence (Art. 14 / SDAIA human-oversight pillar).
- `redact_fn` PII-redaction hook (`isnad export --redact`).
- `grading_strategy{name, version, parameters}`, `weakest_link.grade`,
  `source_documents.licence`, `integrity.canonicalisation`, `record_version` 1.0.
- Examples: `multi_agent_dag.py` (branching DAG + the honest "weakest_link
  misses the sleeper's first lie" case) and `ci_gate.py` (fail a build on a
  degraded chain).
- `docs/evidence-mapping.md` now includes Art. 4 AI literacy and the verified
  banner; README gains "Who this is for" and "Open problems".

## [2.3.0] — 2026-08-23

### Added

- **Audit evidence layer** (`isnad.audit`): `AuditRecord` schema + JSON Schema,
  `build_audit_record()` exporter, RFC 8785-canonical SHA-256 integrity, and
  tamper-evident hash chaining (no blockchain). CLI: `isnad export | verify |
  verify-chain`. Produces *evidence artifacts* — does not certify compliance.
- `docs/evidence-mapping.md` — informational field-by-field mapping of the
  audit record to the EU AI Act, ISO/IEC 42001, NIST AI RMF, and SDAIA
  (not legal advice).
- Examples: `audit_export_langchain.py`, `multi_agent_handoff.py`.

## [1.0.0] — 2026-07-06

### Added

- Initial release of the Isnād–Rijāl framework reference implementation.
- Five core components: Rijāl Registry, Isnād Engine, Weakest-Link Evaluator,
  Corroboration, and Matn Criticism.
- Decision matrix (4×2) combining chain grade with content criticism.
- Pluggable strategy interfaces for all open parameters:
  `GradingStrategy`, `TransitionPolicy`, `CorroborationPolicy`,
  `CorrelationDetector`, `ContentCritic`.
- SQLAlchemy 2.0 ORM models with Alembic migrations for PostgreSQL + SQLite.
- Comprehensive test suite (90+ tests) enforcing all epistemic commitments
  from the paper "Grading the Narrators" (Raja, 2026).
- Paper's worked example (§4.5) as a runnable demo and integration test.
- Pydantic v2 DTOs, full type hints, ruff + mypy strict-mode CI.
- Apache 2.0 license; CITATION.cff for GitHub citation support.
