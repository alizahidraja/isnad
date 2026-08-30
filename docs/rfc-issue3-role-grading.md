# RFC — Per-Role Precision Grading (Issue #3)

- **Status:** Shipped (role dimension in `Registry.register(role=...)`, issue #3 closed)
- **Issue:** #3 "Reliability grades are too coarse: score per role/task, not per model"
- **Author:** Ali Zahid Raja (with multi-persona audit)
- **Scope:** make the *precision* (ḍabṭ) axis of narrator grading per-role,
  while keeping *integrity* (ʿadālah) per-narrator.

---

## 1. Problem (verified in code, not assumed)

The registry grades per `(narrator_id, domain)` only. The trace schema's
`Grade` already declares `(narrator_id, role, domain)`, and the LangChain
callback *captures* a role per link but *ignores* it when looking up the grade:

```python
# src/isnad/integrations/langchain/callback.py:482
narrator = self.registry.get(narrator_id, self.domain)   # role is dropped
```

So one model gets the same grade whether it retrieved, extracted, or
synthesized — exactly the "one number averaged across both looks rigorous and
carries no signal" failure the issue describes.

## 2. Design — the axis split already answers this

The framework already separates two axes (paper §4.2, `policies.py`):

| Axis | Classical meaning | Recoverable? |
|------|-------------------|--------------|
| ʿadālah (integrity) | a judgment of the *person* | **No** — permanent |
| ḍabṭ (precision) | task-specific competence | **Yes** — windowed |

Issue #3 is a statement about **ḍabṭ only** ("a model can extract well and
synthesize poorly"). Classical rijāl agree: a narrator's ʿadālah is *one*
judgment of the person, but their ḍabṭ is task-specific ("thiqa in fiqh, weak
in ḥadīth"). Therefore:

- **Integrity (ʿadālah) → per `(narrator, domain)`.** A liar is a liar in every
  role. Quarantine spans roles.
- **Precision (ḍabṭ) → per `(narrator, role, domain)`.** Extraction competence
  does not imply synthesis competence.

The composite grade for a role is the precision grade, floored by the integrity
state (quarantine → REJECTED regardless of role).

### 2.1 Backward compatibility (hard requirement)

Every registry method gains an optional `role: Role | None = None`.
`role=None` (the default, and every existing caller) keeps the legacy key
`(narrator, domain)` and is **bit-for-bit today's behaviour**. No existing test
changes meaning.

### 2.2 Honest scope (what this RFC does *not* do — by design)

1. **Integrity is domain-scoped, not global.** A narrator quarantined in
   `physics` is not auto-quarantined in `biology`. (Chosen: issue explicitly
   prefers domain scoping; globalizing ʿadālah across domains is a separate,
   larger change.)
2. **Sub-quarantine integrity strikes are per-role.** `quarantine()` (active
   containment, `adalah=COMPROMISED`) spans all roles — that is the cross-role
   integrity mechanism. A single evidence-driven *jarḥ al-ʿadālah* recorded
   against one role lowers that role's grade but does **not** yet lower sibling
   roles. Full cross-role propagation of sub-quarantine integrity strikes is
   future work, stated in code and README.
3. **The Bayesian policy's existing partial axis-split is not changed here.**
   The default `BayesianTransitionPolicy` already enforces REJECTED-stickiness
   but (unlike the threshold policies) does not implement the strikes-per-tier
   integrity ladder. That is an orthogonal pre-existing gap; this RFC does not
   silently claim to fix it.

These limits are the point: the repo's credibility is built on not over-claiming.

## 3. What changes

| Layer | Change |
| ------- | -------- |
| `types.py` | Add `Role` enum (moved from `trace/schema.py`; re-exported there for compatibility) |
| `registry.py` | `role` param on `register`, `get`, `get_grade`, `effective_grade`, `needs_recheck`, `get_adalah_grade`, `get_grade_for_link`, `register_versioned`, `get_metadata`, `evidence_provenance`, `record_evidence`, `record_survival`, `flag_contradiction`, `renew_grade`, `bump_version`. Precision state keyed `(narrator, role, domain)`; integrity state keyed `(narrator, domain)` and shared. `quarantine` propagates to all roles. |
| `models.py` | `role` column on `narrator_registry` (part of PK) and `narrator_evidence`. |
| Alembic | New migration: add `role` (default `""`) to both tables; widen PK/FK to include `role`. |
| `callback.py` | Pass the link's `role` into the registry lookup so traces carry per-role grades. |
| `registry.py` `RegistryDB.load/flush` | Persist + restore the `role` dimension. |
| Tests | New `test_role_grading.py`; migration test asserts `role` column. |
| Docs | README honesty box + this RFC + docstrings. |

## 4. Effective-grade rule (the whole semantics in one place)

```
effective_grade(narrator, domain, role=X):
    default = get(narrator, domain)              # integrity + default precision
    if default is quarantined (adalah=COMPROMISED or grade=REJECTED):
        return REJECTED                           # integrity spans roles
    role_rec = get(narrator, X, domain)
    if role_rec exists:
        return time_decay(role_rec.grade)         # role-scoped precision
    if default exists:
        return time_decay(default.grade)          # fall back to default precision
    return UNGRADED
```

`role=None` short-circuits to the default record → today's behaviour exactly.

## 5. Non-goals / follow-ups (kept explicit so nothing is fake)

- Cross-domain ʿadālah globalization.
- Cross-role propagation of sub-quarantine integrity strikes.
- A free-form `task` tag beyond the six `Role` values (ordinal, not over-built).
- Fixing the Bayesian policy's strikes-per-tier gap.

---

## 6. Multi-persona audit

Each persona below reviewed the implementation as an adversary.  Where an
objection *survived* (a change was made), the change is recorded.  Where it was
*overruled*, the reason is recorded — nothing is overruled silently.

### 6.1 Classical Rijāl Scholar

- **Objection:** "Does per-role precision actually match the tradition?"
  → **Survives.** ʿAdālah is a judgment of the person; ḍabṭ is task-specific
  ("thiqa in fiqh, weak in ḥadīth"). The split is faithful.
- **Objection:** "A proven liar in synthesis should be suspect in *every* role
  and domain — your integrity is domain-scoped."
  → **Overruled (scope), recorded honestly.** The issue and author chose
  domain-scoped integrity; globalizing ʿadālah across domains is a separate,
  larger change listed under non-goals. Quarantine *does* span roles within a
  domain — the critical containment property holds.

### 6.2 Systems / Backend Engineer

- **Objection:** "Changing a PK/FK in SQLite needs a table recreate — is data
  preserved?"
  → **Survives.** The migration copies rows (`INSERT … SELECT`), drops the old
  table, then rebuilds indexes (index names are global in SQLite, so indexes are
  created *after* the drop). Pinned by `test_migrations.py`.
- **Objection:** "The PostgreSQL migration path is not exercised by CI."
  → **Survives as a documented gap.** CI tests SQLite only; the Postgres branch
  is written but unverified by automation. Noted here, not hidden.
- **Objection:** "`bump_version` clears role evidence in memory but `flush` is
  append-only — the reset would not survive a DB round-trip."
  → **Survives — caught in self-review, fixed.** Role reset now mirrors the
  default record: reset grade/clocks, log `VERSION_BUMP`, keep the append-only
  audit trail. No in-memory/DB divergence.

### 6.3 Honesty Auditor

- **Objection:** "Does the README disclose the cost (cold-start sparsity)?"
  → **Survives.** The README "Honest limits" block states the trade plainly and
  links to this RFC. No result is overstated.
- **Objection:** "The docstrings must not imply cross-role integrity
  propagation that isn't there."
  → **Survives.** `record_evidence`, `effective_grade`, and the RFC all state
  that sub-quarantine integrity strikes are per-role.

### 6.4 Security Engineer

- **Objection:** "Could role-scoped precision evidence rehabilitate a
  quarantined narrator?"
  → **Survives.** `_effective_role_grade` floors to REJECTED *before* reading
  the role's precision record. Pinned by `test_quarantine_blocks_role_precision_recovery`.
- **Objection:** "Self-verified survival must stay refused in a role too."
  → **Survives.** The tazkiyah guard in `record_survival` is role-agnostic and
  applies before any role record is touched.

### 6.5 Data Scientist / ML Practitioner

- **Objection:** "Six roles is coarse — why not a free-form task tag?"
  → **Overruled (ordinal-first).** Six categorical roles match the declared
  trace schema and avoid an unbounded key space; a finer `task` tag is a
  non-goal, not a denial.
- **Objection:** "Cold-start gets worse — is per-role grading actually better?"
  → **Survives as a documented trade.** A per-role UNGRADED is more honest than
  a wrong cross-role grade; the cost is real and stated, not papered over.

### 6.6 OSS Maintainer

- **Objection:** "Is `Role` importable everywhere it needs to be?"
  → **Survives.** `Role` lives in `types.py` and is re-exported from
  `isnad` and `isnad.trace` (explicit `as Role` re-export so strict mypy is
  happy).
- **Objection:** "`get_adalah_grade` takes no `role` — is that confusing?"
  → **Survives (documented).** Integrity is per (narrator, domain) and
  role-independent; the method signature reflects that.
- **Observation:** `NarratorDTO`/`EvidenceDTO` are dead code and were left
  untouched (no `role` added). Recorded as tech debt, not fixed in this pass.

---

*This audit is the source of truth for the design's trade-offs. If a later
change contradicts it, update the RFC, don't delete the note.*
