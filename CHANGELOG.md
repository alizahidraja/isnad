# Changelog

## [2.21.1] — 2026-08-30

### Fixed

- **Serving path now warms from the evidence-sourced default registry (#203/#204).**
  `isnad serve` previously seeded a divergent hardcoded physics list with no evidence
  source; it now seeds from `default_seed_entries()` (Estimated priors, BOOTSTRAP_SEED,
  gated to SERVE_WITH_CAVEAT/REVIEW).
- **`isnad scan` no longer fabricates "Supported" provenance (#206).** A narrator with
  a grade but no observed/human evidence is now labeled "unvalidated"; a UNGRADED
  narrator is reported "cold" (was "vouched"). Provenance branches on
  observation_backed / prior_only / unvalidated.
- **CHANGELOG honesty:** `--reproduce` lives on `python -m bench.run`, not the
  `isnad bench` CLI; reworded the 2.21.0 entry accordingly.
- **`test_edge_stress` positive gate always collected.** `test_edge_stress_all_passed`
  is now defined unconditionally, so a green run collects + asserts (was 0 items on
  success).

## [2.21.0] — 2026-08-30

### Added

- **Warm default registry (#203, #204).** `default_registry()` ships a
  conservative, evidence-sourced seed set (~39 narrators across sources,
  models, scrapers, tools) so a fresh pipeline no longer starts fully UNGRADED.
  Every seed is a BOOTSTRAP_SEED prior ("Estimated"), gated to
  SERVE_WITH_CAVEAT/REVIEW — never plain SERVE, and never "Supported" without
  real observations.
- **`python -m bench.run --reproduce` (#205).** Hard-fails on a wrong hadith-kg.db
  SHA-256 and adds db_hash + harness_rev to the JSON receipt, so κ=0.871 is
  independently re-runnable, not self-asserted.
- **`isnad scan` (#206).** Maps a live pipeline's transmitter ids onto the
  registry and reports vouched vs cold (UNGRADED → REVIEW). Evidence listing
  only — ordinal grade + provenance, never a numeric trust score.
- **Interchange positioning (#207).** `isnad_trace` is documented as an
  *evaluative profile* over W3C PROV / PROV-AGENT, not a competing standard;
  emit receipts, don't host a transparency log.

### Fixed

- **Test harness no longer aborts the whole run on a flaky check (#209).**
  The edge/stress module-level assertion is deferred to a test function.

## [2.20.1] — 2026-08-30

### Fixed

- **CI green.** Re-synced the golden conformance vectors after the 2.20.0
  version bump (the `isnad_version` embedded in `js/test/golden.json` had gone
  stale, failing the JS drift gate), and `ruff format`-ed the files the 2.20.0
  commits left unformatted.

## [2.20.0] — 2026-08-30

### Security & integrity — brutal-audit hardening

- **Serving-path tamper-evidence (#189).** `POST /v1/claims` now emits an
  `AuditRecord` (self-hash + optional HMAC/Ed25519 detached signature + optional
  chain-log append); `audit_record_hash`/`audit_signature` are persisted on
  `rijal_claims` (migration `2a4b5c6d7e08`) so the evidence survives restart.
- **Admin-gated grade mutations (#190).** Quarantine / flag_contradiction /
  renew_grade now require the admin role; a reader can submit but not poison
  the registry.
- **Auth + redaction on claim reads (#191).** `GET /v1/claims/{id}` and `/chain`
  require an API key and strip raw `input_snapshot`/`output_snapshot`.
- **Fail-closed persistence (#192).** `store_claim` failure → HTTP 500 (and
  rolls back the in-memory write); DB init failure raises; `/v1/health` probes
  the DB and reports `degraded`.
- **Human-intervention path (#193).** `POST /v1/review-queue/{id}/resolve`
  (admin) writes resolution + reviewer evidence and persists it on the claim.
- **Affirmation-gate exact match (#200).** No provider/model wildcards — a
  provider-less eval record no longer licenses any model.

### Honesty

- Labeled hand-set corroboration constants as assumptions, not measurements
  (#194–196); flagged the soft-caveat default as unsuitable for high-stakes
  domains (#202); corrected the κ human-ceiling framing (#197); documented the
  single-node serving index (#199).
- **Migrations run on start (#198).** Dockerfile runs `python -m alembic upgrade
  head` before serving.
- **False-consistent fix (#202→#6).** `_parse_verdict('NOT CONSISTENT')` no
  longer returns CONSISTENT.

### Reverted

- RFC 8785 shorthands: the audit panel claimed `\n`/`\t` shorthands were
  non-compliant; verified against RFC 8785 §3.2.2.2 they are *mandatory*.

## [2.19.0] — 2026-08-30

### Added

- **Default-ON content-critic affirmation gate (#34).** No critic may return
  `CONSISTENT` unless a domain-scoped eval record proves its false-consistent
  rate ≤ threshold (default 0.0). Without a valid, unexpired, re-runnable
  record, affirmation is refused (`CONSISTENT` → `UNVERIFIABLE`, fail safe).
  `ISNAD_AFFIRMATION_RECORDS_DIR` / `_MAX_FCR` / `_MAX_AGE_DAYS` configure it;
  `affirmation_gate.register()` for programmatic/test callers. Gated critics:
  `LLMCritic` (incl. its cache-hit path), `LocalNLICritic`, `HybridCritic`.

- **Widened content-level shared-error fingerprint (#54).** `ErrorFingerprint`
  now detects the *same specific mistake* beyond numbers/negation: shared named
  entities (via set equality, so a shared subject alone is not a shared error),
  dates, citations, and number+unit pairs, plus zero-dep lexical shingling for
  near-paraphrase. Result field `content_madar_detected` → `shared_error_detected`
  (evidence-consistent-with, not proof of a common upstream). Still oracle-gated
  on the base claim being CONTRADICTION; never withholds a correct agreement.

- **Co-failure calibration harness (#54).** `isnad.core.co_failure` computes
  the double-fault rate (P both narrators wrong together) and Yule's Q over a
  labeled eval set — the *measurable* signature of a shared blind spot that
  grounds the flat corroboration prior. Pure, dependency-free; `prior()` floors
  at the chance product so absence of observed co-failure is never mistaken for
  independence.

- **Measured-prior wiring + opt-in joint-failure aggregation (#54).**
  `CappedCorroborationPolicy(measured_priors=..., joint_failure=...)`: operator
  measured co-failure priors override the hand-set `BLIND_SPOT_MATRIX`;
  `joint_failure=True` switches the aggregation to the P(all fail together)
  mixture (`(1-p)·e(base)·∏eᵢ^sᵢ + p·0.10`). Opt-in and strictly more
  conservative — at the default flat prior it does not fire (honest, not a bug):
  the joint model upgrades only with calibrated/attested priors. Default is
  unchanged (pairwise, backward compatible).

### Fixed

- **Public claim record no longer leaks raw corroboration floats (issue 187).**
  `corroboration_result` dropped `effective_weight`, `effective_witnesses`,
  `shared_blind_spot_prior`, and per-chain `independence` scores from the API
  surface — they read as numeric confidence against the "no numeric confidence"
  moat. The public surface is now ordinal grade + boolean `upgraded` + integer
  chain counts + `shared_signals` provenance + reason string.

- **CI coverage floor (issue 186).** `ci.yml` now runs pytest with
  `--cov=src/isnad --cov-fail-under=88` (measured 91%), so a deleted test file
  fails the build instead of passing silently.

## [2.18.0] — 2026-08-30

### Fixed — five remaining decisions (10-person panel, 10/10 converged)

- **D1 · critic corpus now accepts operator KB docs.** `submit_claim` takes an
  optional `corpus_docs` field; when supplied, the content critic checks the
  claim against the operator's retrieved documents (the actual evidence
  artifacts) instead of only prior claims (which are themselves unverified).
  Provenance is surfaced (`critic_corpus_operator_docs`); an operator corpus is
  an assumption, not an observation.
- **D2 · TF-IDF never affirms consistency + ensemble wiring.** `EmbeddingCritic`
  now returns only CONTRADICTION or UNVERIFIABLE (never CONSISTENT) — symmetric
  lexical overlap cannot bless a ≤3× dose error or an unlisted antonym.
  `best_available_critic()` now wraps every tier in
  `EnsembleCritic(semantic, RecomputeCritic())` so numeric-aggregate
  contradictions are caught deterministically.
- **D3 · hold mode: unverifiable content never caveat-serves.** New
  `hold_unverifiable()` remaps `SAHIH × UNVERIFIABLE → SERVE_WITH_CAVEAT` to
  REVIEW in hold domains (`ISNAD_SERVE_GATE=hold` / `ISNAD_SERVE_HOLD_DOMAINS`).
  A caveat is a label, not evidence.
- **D4 · endorsed Live Verify seals now record survival.**
  `register_sealed_source` records OBSERVED survival evidence for an endorsed
  (green) seal, making the narrator observation-backed (unlocks plain-SERVE
  under the prior-only gate). Self-verified (amber) seals stay refused by the
  tazkiyah guard.
- **D5 · numeric-float honesty.** `chain_independence[].score` is renamed
  `independence` (0.0 = shared lineage, 1.0 = fully independent — NOT a
  confidence) and the corroboration floats are annotated as structural witness
  counts.

## [2.17.0] — 2026-08-30

### Fixed — serving-path P0s from the 7-persona 3-user audit

- **P0-A · restart no longer destroys the contradiction signal.** `RijalClaim`
  now persists `content_verdict` + `action` (migration `1c2d3e4f5a07`), and
  rehydration is faithful: a held `SAHIH × CONTRADICTION → REVIEW` stays REVIEW
  instead of being silently re-derived as `SAHIH × UNVERIFIABLE →
  SERVE_WITH_CAVEAT`. Legacy rows without the columns fall back to the
  conservative re-derivation (never a serve).
- **P0-B · a prior-only (seeded, unobserved) narrator can no longer plain-SERVE.**
  New `gate_serve()` caps SERVE → SERVE_WITH_CAVEAT when any serving-chain
  narrator's grade rests on a population prior with zero observed instances
  (classical majhūl al-ḥāl, not thiqa). The gate changes the *action*, never the
  *grade*. High-stakes domains opt into a hard gate (`ISNAD_SERVE_GATE=hold` or
  `ISNAD_SERVE_HOLD_DOMAINS=medical,legal`) → REVIEW. Structured
  `prior_only_narrators` is surfaced on the record.
- **P0-C · quarantine is now active containment, not passive labeling.**
  `submit_claim` actually calls `registry.quarantine()` (COMPROMISED + inactive)
  and flushes. `registry.load()` restores `is_active` (was reset to True on
  every reload — an inactive narrator reactivated after restart).
  `GET /v1/claims` defaults to `served_only=true` so a downstream RAG no longer
  reads quarantined/rejected claims.
- **P0-D (legal custody) · full SHA-256, no fabricated timestamps, no "None"
  doc_id.** `_hash_content` no longer truncates to 64 bits; the trace
  `content_hash` is a real 256-bit digest. `doc_id` is a true NULL when absent
  (was the literal string "None"). Per-link `invocation_timestamp` is wired from
  `chain_links.timestamp`; `ChainLinkSpec.to_dict()` no longer fabricates
  `datetime.now()` at serialization (storage time masquerading as transmission
  time).

### Fixed — re-grade loop orphaned (P1)

- A live contradiction now records jarh evidence against the new claim's
  narrators (`flag_contradiction`); a corroboration upgrade renews their grade
  window (`renew_grade`). Previously both were computed but never applied.

### Hygiene

- CITATION.cff version/DOI lockstep (2.16.0 → 2.17.0; permanent paper DOI
  10.5281/zenodo.21211290; software DOI 10.5281/zenodo.21216873).
- LangChain callback comment no longer self-contradicts corroboration status.

## [2.16.0] — 2026-08-29

### Added

- **`isnad mcp` — a runnable MCP server** (`serve_mcp` + CLI subcommand). Runs a
  real FastMCP server over stdio (or sse/streamable-http) exposing `grade_claim`
  and `list_narrators` tools backed by the operator's local registry. Lazy-imports
  the SDK; `pip install isnad[mcp]`; a clear ImportError guides install otherwise.

### Fixed

- **Quarantine escape via version bump** — `bump_version` previously cleared
  `adalah=COMPROMISED`, so a fabricator escaped containment by shipping "v2".
  Integrity is now per-person and survives the bump (precision still resets).
- **content-madar negation** now catches sentence-initial "Never" (was mid-string
  only), matching the document-hash/witness-type detection breadth.
- **Removed dead `_narrator_to_chain_grade`** (UNGRADED→HASAN, contradicted the
  strict majhūl default).

### Test suite hardening (multi-persona audit)

- The ~166 full-system + wiring checks in `verify_*.py` never ran under pytest/CI
  (no `test_*` functions, not in `python_files`). Now collected
  (`python_files=['test_*.py','verify_*.py']`), with `sys.exit` gates converted
  to `pytest.fail`. Fixed 11 stale checks encoding pre-change behavior.
- Pinned JCS canonicalization (control-char short escapes), corroboration
  boundary thresholds, the add_pattern class-state isolation, and added real
  assertions to previously zero-assertion callback tests.

## [2.15.0] — 2026-08-29

### Added

- **isnad-mcp** (`isnad.integrations.mcp`, #59) — grade MCP servers as narrators.
  `MCPToolObserver` records MCP tool calls as TOOL narrator links and grades the
  chain; a `grade_claim` tool exposes the operator's local registry to an agent.
  Honest by construction: tool narrators stay UNGRADED by default (never
  auto-graded from call volume), and the server returns operator-assigned grades,
  never manufactured ones (#44 no-federation invariant). Duck-typed — no `mcp`
  SDK import, so it ships and tests without it (`pip install isnad[mcp]`).
- **`NarratorType.TOOL`** — the taxonomy now has a first-class tool narrator (was
  only `Role.TOOL`); the LangChain `tool:`/`retriever:` prefix inference now maps
  to TOOL (was SCRAPER), and the volatility + audit mappings carry it.

### Fixed

- Removed the drift hazard of a dead, misleading `NARRATOR_TYPES` tuple in
  `audit/schema.py` (now aligned with the enum + governance map, #185).

## [2.14.0] — 2026-08-29

### Changed

- **Corroboration threshold decoupled** (#185, panel decision 3/3 DECOUPLE). The
  engine no longer silently overwrites the policy's `MIN_EFFECTIVE_WEIGHT` (2.0)
  with `min_independent_chains` (1.0). `min_independent_chains` is now a COUNT
  gate; the weight gate stays 2.0, so a single HASAN corroborator no longer
  elevates a DAIF chain — ~2 HASAN-equivalent (or 1 SAHIH) is required. This
  closes a one-shot trust-elevation/poisoning path and reconciles the engine
  with the policy and paper §4.3.
- **MAWDU corroborating chains contribute zero weight** — a fabricated narrator's
  agreement is not corroboration (active containment).

### Fixed

- **#182 contestability durability** — `adjudicate(overturn=True)` now records its
  target grade and survives the next recompute AND `get_grade_as_of`: the
  overturned integrity strike is re-accredited, not silently re-applied.
- **#183 integration honesty (3 bugs)** — `IsnadTracer` now passes retrieved
  documents as the critic's corpus (content criticism was an empty-corpus no-op);
  `IsnadMiddleware.gate()` now gates every action the matrix does not serve
  (a SAHIH/HASAN contradiction no longer passes through un-blocked); Live Verify's
  authority-chain walk treats an endorser cycle as self-verified (amber), not
  confirmed (green).
- **#184 experiment honesty (2 bugs)** — `verified_vs_unverified` no longer
  hardcodes a SAHIH corroborator (it grades the real chain, so the recovery is
  genuine and the 2-caught/2-missed/0-FP summary is true); `adversarial_benchmark`
  collapsed its fictional "pattern vs semantic" split into a single honest
  `content-contradiction` class.
- **#185 correctness** — `renew_grade` no longer logs a freshness renewal as an
  OBSERVED corroboration outcome (new `FRESHNESS_RENEWAL` META type);
  `bump_version` refreshes the alias index after the role reset; `RecomputeCritic`
  no longer misreads a year/date as an inflated total or a category named "count"
  as the grand total.

## [2.13.0] — 2026-08-29

### Changed

- **REJECTED / COMPROMISED now dominate the completeness cap (#181).** A chain
  that is both incomplete *and* contains a REJECTED narrator (or a COMPROMISED
  ʿadālah) now grades **MAWDU**, not DAIF. Previously the completeness cap ran
  first, so adding a gap *raised* a fabricated chain to (corroboratable) DAIF —
  an anti-monotonic move that reopened the corroboration-upgrade path for a
  quarantined fabricator. The paper's own decision matrix (§4.4) and MAWDU
  definition ("a rejected narrator is present") already implied this; the code
  order was the error.
- **Benchmark numbers regenerated** as a consequence (the 3-way headline κ =
  0.8714 is unchanged; the finer 4-way κ moves 0.8571 → 0.8745, agreement
  89.7% → 90.9%, and the shuffled control moves 0.0446 → −0.0066, closer to its
  expected ~0). This is a grading-rule change, not a mapping change; the
  preregistered rank→grade mapping is untouched.

### Fixed

- **`isnad export --verify` fails closed** on an unverifiable detached
  signature — it previously printed "verification OK" + exit 0 when a detached
  signature was present but no secret was available (a forgeable path). Now
  reports INCONCLUSIVE and exits 1; also verifies against `--sign` when given.

## [2.12.0] — 2026-08-29

### Added

- **Content-level madār detection wired into the corroboration engine** (#54).
  `detect_content_madar` is no longer an exported-but-unused helper: when the
  base claim's content verdict is CONTRADICTION and a nominally-independent
  corroborating chain repeats the *same error* (identical wrong number or
  flipped negation), `CorroborationEngine` now withholds the upgrade and reports
  `content_madar_detected=True` with a precise reason. This closes the "detectable
  half" of the chain-independence gap — the undetectable half (correlated training
  data across model families) remains an open, stated limit.
- `CorroborationResult` now carries `content_madar_detected`,
  `shared_blind_spot_prior`, and `effective_witnesses` through the API response
  (`corroboration_result`), so the madār signal is visible in the audit record.
- `evaluate` / `evaluate_direct` accept `base_content_verdict` (and the API
  threads each stored claim's `content_verdict`) so the engine can fingerprint
  corroborators' errors.

## [2.11.0] — 2026-08-29

### Added

- **Deterministic numeric-aggregate critics** (#170, PR #168/#180) —
  `RecomputeCritic` (recomputes count/sum aggregates from corpus rows;
  never blesses on a numeric match alone), `EnsembleCritic` (contradiction-
  priority: any CONTRADICTION wins, CONSISTENT requires both critics), and
  `AggregateRouter` (scopes a semantic critic's corpus to a summary for count
  claims so NLI stops collapsing to indiscriminate contradiction at scale).
  Additive and opt-in; tested with real critics so no false claim reaches
  CONSISTENT.
- **Audit/API hardening (external audit follow-up).** `isnad verify` and
  `isnad export --verify` now check the **detached signature** (HMAC/Ed25519),
  not just the self-hash (#97); `isnad export --sign` emits a signed record.
  The API rehydrates its in-memory claim index from the DB on boot, so claims
  survive a restart (#93); `store_claim` accepts an explicit `claim_id` so the
  API's served key matches the persisted key.

### Fixed

- `docker-compose.yml` no longer ships a hardcoded admin credential or DB
  password — API keys and `POSTGRES_PASSWORD` are injected from the host env
  (#93).
- `BayesianTransitionPolicy.seed_grade()` dropped a spurious +1 Laplace term
  that silently shifted a RELIABLE prior (0.96) down to ACCEPTABLE; documented
  that `evaluate_transition` is the authoritative grading path (#90-class).
- `THREAT_MODEL.md` no longer contradicts the shipped code on cross-domain
  quarantine (#28): integrity compromise now spans domains.
- `audit/schema.py` no longer marks `detached_signature` as "reserved — not
  implemented" (#97).

### Docs

- README: differentiation positioning ("grades the transmitters and the chain,
  not just the claim") + a competitor comparison (Cleanlab TLM, Galileo,
  Patronus, TruLens, RAGAS, LangSmith/Langfuse/Arize); critic-count (945 vs
  1,015) and test-count (~790) drift reconciled; §8 negative-control status
  updated (8/8 Wikipedia + 9/9 physics, #127).
- `bench/human_ceiling.py` computes the critic count from the DB instead of
  hardcoding it; `bench/docs/bench_jsonld.py` + `mapping.md` disambiguate
  945 (critics with statements) vs 1,015 (named critics).
- `CITATION.cff` updated to the κ=0.871 benchmark + 9/9 physics controls.

## [2.10.1] — 2026-08-28

### Added

- **Witness-type-aware tawātur prior** (#54) — the blind-spot prior is now a
  function of witness type, grounded in the classical distinction between
  **mutābaʿa** (same-teacher confirmation — weak corroboration) and **shāhid**
  (different-companion confirmation — strong corroboration).
  `CappedCorroborationPolicy.BLIND_SPOT_MATRIX` keys pairwise priors by narrator
  type (model+model → 0.25, model+human → 0.05, model+source → 0.08); every cell
  is a stated default to calibrate, not an asserted truth. The engine derives each
  chain's dominant narrator type and threads per-chain priors through
  `compute_corroborated_grade` / `_compute_effective_weight`.

## [2.10.0] — 2026-08-28

### Added

- **Tawātur discount (N_eff) + content-level madār detection** (#54) — the
  chain-independence limit is addressed the way the classical scholars addressed
  it: not by proving per-pair independence (unfalsifiable from topology), but by
  pricing in joint failure probability. `CappedCorroborationPolicy` gains
  `shared_blind_spot_prior` (default 0.20): every chain's witness weight is scaled
  by (1 − prior), so no chain earns full witness credit.
  `CorroborationResult` reports `effective_witnesses` and
  `shared_blind_spot_prior`. `prior=0.0` is backward compatible; `prior=1.0`
  disables corroboration.

## [2.9.9] — 2026-08-27

### Added

- **ISNAD-Bench export** (`bench/export.py`) — per-chain graded output as JSONL
  with a reproducibility header (source SHA-256, mapping SHA-256, invocation);
  shared `bench/_grade.py` extracted from `run.py` so export and compute can
  never drift (#134). Dataset card + HF card + `Dataset` JSON-LD + leaderboard.
- **Published the benchmark** outside the repo: HF dataset
  `alizahidraja/isnad-bench` (derived output, CC-BY-4.0, κ=0.8714 reproducible
  from the hosted JSONL) and Zenodo DOI 10.5281/zenodo.22132880 (#134).

### Changed

- **Release publishing → Trusted Publishing (OIDC)** — no long-lived PyPI token
  (#162).
- Consolidated `MalformedLogError` into `canonical.py` (was duplicated in the
  two readers); `verify_chain` now returns a `ChainBreak` on malformed input
  (credits @AusafMo, #129).

### Docs

- §8.4 matched-coverage measured resolution (`results/MATCHED_COVERAGE_FINDING.md`).
- Chain-viewer deployed to GitHub Pages (#131).

## [2.9.8] — 2026-08-27

### Added

- **Live Verify `supersede_verdict`** — a re-graded claim flips its old hash to
  `{"status": "superseded", "superseded_by": …}` and publishes the new one, so a
  published verdict never silently stays "verified" forever (#122).

## [2.9.7] — 2026-08-27

### Fixed

- **`verify-merkle` / `verify-chain` report malformed logs instead of crashing**
  — a corrupted/truncated log now produces "broken at entry N" with exit 1, not
  an uncaught traceback (#108).

## [2.9.6] — 2026-08-27

### Added

- **End-to-end utility experiment** (`experiments/e2e_utility/`) — real
  LLM-generated claims (DeepSeek) graded by the full pipeline against a
  deterministic oracle: gated 0.0% served-error vs ungated 50.0% (#128).

## [2.9.5] — 2026-08-27

### Added

- **Two-axis ablation** (`experiments/two_axis_ablation/`) — proves the
  ʿadālah/ḍabṭ split quarantines a "fabricator who is usually accurate" at 3
  integrity strikes where a blended score still serves; the inverse case proves
  precision recovery (#124).

## [2.9.4] — 2026-08-27

### Fixed

- Corrected the critic fault classification in the #126 measurement:
  `fabricated_numeric` is content corruption, not transmission noise. The
  corrected LLM false-consistent rate on content corruption is 39.1%. (#126)

## [2.9.3] — 2026-08-27

### Added

- **LLM critic false-consistent measurement** (`critic_false_consistent.py`) —
  the two-axis split applied to measurement: content corruption vs transmission
  noise (#126).

## [2.9.2] — 2026-08-27

### Added

- **Critic false-consistent safety gate** + `best_available_critic()` wired
  into the §8 gate (replacing the stale inline DeepSeek critic) (#126).

## [2.9.1] — 2026-08-27

### Added

- **9 negative controls for corroboration v3** (physics corpus), including the
  document-hash hard-correlation case — a 100% fire rate is now backed by a
  discrimination check (#127).

## [2.9.0] — 2026-08-27

### Added

- **Chain independence — emit + populate (step 3)** (#125): `detect()` returns a
  structured `IndependenceAssessment` (score + which shared signals fired);
  `CorroborationResult` carries per-chain provenance; `document_hashes` threaded
  through the API + DB.

## [2.8.0] — 2026-08-27

### Added

- **Chain independence — detect + discount (steps 1–2)** (#125): document-hash
  overlap in `SharedLineageDetector` (the madār case) and the disjointness
  discount (corroboration weighted by independence score).

### Changed

- Visibility sweep: Beta status, full `all` extra, README first-screen keywords,
  architecture diagram (PNG/SVG) + viewer GIF, licensing commitment
  (`LICENSING.md`).

## [2.7.0] — 2026-08-26

### Added

- **Committed critic evaluation** (`experiments/critic_eval/`) — a 60-case labeled
  eval set + runner + results; the critic recall numbers are now measured, not
  estimated (#96).
- **Local Ollama LLM critic** — the LLM tier now works with a local server (no
  API key) (#113).
- **Evidence-backed cold-start seeding** — `Registry.seed()` / `seed_from_benchmark()`
  / `accuracy_to_grade()` record `BOOTSTRAP_SEED` evidence so seeds survive the
  posterior; the Live Verify source bootstrapper is likewise evidence-backed (#114, #115).
- **Detached audit signatures** — `sign_detached` / `verify_detached` + HMAC and
  Ed25519 signers (#97).
- **`best_available_critic()` prefers the LLM tier by default** — the serving
  gate (tracer, API, middleware) now uses the LLM critic when one is configured (#116).
- **Live end-to-end demo** (`examples/end_to_end_live_demo.py`).

### Changed

- **NLI critics fixed** — corrected label order, softmax-normalized scores, and
  same-subject retrieval + contradiction-first-with-margin: false-consistent
  rate dropped from 0.84–0.88 to ~0.00–0.04, recall 0.12–0.16 → 0.72–0.76 (#110).

### Fixed

- API: Pydantic request validation (malformed body → 422) + louder persistence
  failure logging (#93).
- Firewall test is now field-level (grading may read `corrupted`, not the
  manifest fields) (#98).
- Middleware `gate()` runs the full decision matrix when given a critic + corpus (#63).
- Richer PyPI metadata: project URLs + classifiers + keywords (#62).

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
