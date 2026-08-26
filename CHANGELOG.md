# Changelog

## [2.6.2] — 2026-08-26

### Added

- **Merkle batch tamper-evidence log** (`isnad.audit.merkle_log`, `isnad
  verify-merkle`) — a parallel-friendly alternative to the linear hash chain
  (issue #69, thanks @AusafMo). Records enter as independent leaves (no
  back-reference), a seal step commits the ordered batch to a Merkle root, and
  batch roots chain via `prev_root`. Ships `build_batch`, `seal_batches`,
  `verify_batches`, and O(log n) inclusion proofs. See the README's audit
  section for linear-vs-Merkle guidance.

## [2.6.1] — 2026-08-26

### Changed

- **Corroboration now requires attested distinct lineage (issue #54, PR #83).**
  `SharedLineageDetector.compute_independence_score()` no longer returns full
  independence (`1.0`) when neither chain carries lineage metadata. Absent lineage
  evidence, independence is *unknown* (`UNKNOWN_LINEAGE_SCORE = 0.5`, below the
  corroboration gate), so unattested chains no longer silently corroborate —
  independence must be demonstrated, not assumed. Populate `model_family` /
  `upstream_source` on `register()` to keep corroboration firing. Thanks to
  @AusafMo.
- **Bayesian REJECTED threshold tightened (issue #91).** The weak/rejected
  boundary in `BetaState.to_grade()` moved from 0.50 → 0.60, so a narrator with
  ~>40% observed error is quarantined instead of lingering as WEAK. The three
  thresholds are now configurable on `BayesianTransitionPolicy`.

### Fixed

- **Seed grades are no longer clobbered (issue #90).**
  `register(grade=RELIABLE)` followed by its `BOOTSTRAP_SEED` marker keeps the
  seed (previously it collapsed to WEAK when the Bayesian posterior recomputed
  from a `Beta(1,1)` prior). The seed rides in the evidence metadata as a prior
  that real observations then update.
- **API fails closed with no default credential (issue #93).** Removed the
  hardcoded `isnad-admin:admin` default; with no `ISNAD_API_KEYS` configured,
  authenticated endpoints return 503. CORS is opt-in via `ISNAD_CORS_ORIGINS`.
- **Version reporting (issue #99).** The FastAPI app and `/v1/health` now report
  `__version__` instead of a hardcoded `"2.0.0"`.

### Performance

- **Lazy `sentence_transformers` import.** Importing the API (or
  `isnad.critics.nli`) no longer eagerly pulls in torch; the NLI critic builds
  lazily on first use. CI also no longer installs the unused `nli` extra.

## [2.6.0] — 2026-08-23

### Added

- **ISNAD-Bench** (`bench/`): a preregistered, reproducible benchmark grading
  577,024 real hadith chains against classical ground truth — Cohen's κ = 0.87
  vs the scholarly consensus (human ceiling κ = 0.33), with corroboration,
  human-ceiling, and ikhtilāṭ analyses plus negative controls.
- `--json` machine-readable export for the benchmark; `py.typed` marker.
- `lenient_unknown` opt-in on `grade_chain(...)`.

### Changed

- **Default flipped to strict:** an UNGRADED narrator now caps a chain at ḍaʿīf
  (the classical *majhūl* treatment) instead of ḥasan. The old behaviour is
  opt-in via `lenient_unknown=True`. Measured at 0.11 κ (0.76 → 0.87).

## [2.5.0] — 2026-08-23

### Added

- Multi-provider LLM critic: OpenRouter, OpenAI, DeepSeek, Anthropic, Gemini,
  Groq, Together, Ollama, and any OpenAI-compatible endpoint, via a named-provider
  catalog + `ISNAD_LLM_*` env vars.

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

## [2.2.0] — 2026-08-23

### Added

- **Period-sliced grades** (`get_grade_as_of()`) — re-derive a narrator's grade
  at any past instant from the append-only evidence log; the ikhtilāṭ (decline)
  remedy (issue #43).

## [2.1.0] — 2026-08-21

### Added

- **Per-role precision grading** — integrity (ʿadālah) per narrator, precision
  (ḍabṭ) per (narrator, role, domain) (issue #3).

## [2.0.0] — 2026-07-09

### Added

- The core framework: isnād chains, the rijāl registry, weakest-link grading,
  the 4×2 decision matrix, and content critics.
- Trace capture, the chain viewer, and the `isnad_trace` v0.1 schema
  (W3C PROV-aligned).
- Per-generative-link transformation-fidelity checking (issue #11).
- jarḥ–taʿdīl split by axis — integrity (ʿadālah) never forgets; precision
  (ḍabṭ) ages out (issues #9, #20).
- Live Verify integration — a `verify:` seal as a high-trust narrator input.
- LangChain integration (callback, tracer, decorator).
- The verified-vs-unverified A/B demonstration (issue #7).

> 2.0.x shipped 14 patch releases (2.0.1–2.0.14) over six weeks of rapid
> iteration; this entry consolidates them.

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
