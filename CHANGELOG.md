# Changelog

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
