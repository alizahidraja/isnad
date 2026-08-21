# Issue #11 Fix: Chain-Integrity vs. Content, Made Distinguishable

This document details the changes across two stacked branches
(`fix/11-content-aware-routing`, `fix/11-transformation-fidelity`) that address
[#11](../../../issues/11) — *"Weakest-link scoring can rank a fabricated pristine chain
above a degraded sound one."*

## The problem, in one paragraph

Weakest-link grading looks only at *who* transmitted a claim (each narrator's general
historical track record), never *what* the claim says. A true claim that degrades at one
weak mid-chain link scores low. A fabricated claim carried by individually clean-looking
narrators — reinforced by fake "independent" parallel chains for a corroboration boost —
could score *higher*. Content criticism only ever ran once, at the very end, against the
external corpus, and corroboration ran with zero visibility into content at all. The issue's
own three proposed directions: (1) separate chain-integrity from origin-strength instead of
collapsing both through `min()`, (2) treat a contradiction as an investigation trigger, not a
tiebreak the higher score just wins, (3) make low confidence diagnostic — surface *where* a
chain degraded, not just that it did.

All three are addressed below. Two of the three needed no schema change at all — the fields
already existed in the database from the initial migration, just never read or written by any
application code.

---

## Fix 1 — Direction 1: ʿAdālah (integrity) as a second, separate axis

**Files**: `types.py`, `core/grading.py`, `core/registry.py`, `core/chain.py`

**The gap**: `narrator_registry.adalah_grade` (the `AdalahGrade` enum — integrity/manipulation-
resistance) was already a fully modeled column on every narrator, alongside the ordinary
`NarratorGrade` (precision/accuracy). But `RefinedWeakestLink.compute_chain_grade()` only ever
consumed `NarratorGrade` — a narrator could have `AdalahGrade.COMPROMISED` (a known integrity
failure, e.g. a caught prompt-injection attempt) and still contribute a clean `RELIABLE`
signal to chain grading, because that axis was simply never read.

**The fix**:
- `Registry.get_adalah_grade(narrator_id, domain_tag)` — new accessor, mirrors the existing
  `get_grade()` exactly.
- `chain.adalah_grades_for_chain(registry, chain)` — new helper, mirrors the existing
  `grades_for_chain()` exactly.
- `RefinedWeakestLink.compute_chain_grade()` gains an optional `link_adalah_grades` parameter
  (default `None` → unchanged behavior, not a breaking change to the `GradingStrategy`
  protocol). If any link's `AdalahGrade` is `COMPROMISED`, the chain is forced to `MAWDU` —
  immediately, before the weakest-link walk even begins, exactly parallel to the existing
  `REJECTED`-narrator check.

**Before → after**:
```python
# Before: a chain of all-RELIABLE narrators is SAHIH, full stop — even if one
# of them has a documented integrity failure, because that axis is never read.
grade_chain([RELIABLE, RELIABLE, RELIABLE], [...]) == ChainGrade.SAHIH

# After: passing the (previously ignored) adalah axis catches it.
grade_chain(
    [RELIABLE, RELIABLE, RELIABLE], [...],
    link_adalah_grades=[HIGH, COMPROMISED, HIGH],
) == ChainGrade.MAWDU
```

**Severity note**: `MAWDU` here is deliberate and mirrors the existing `REJECTED`-narrator
behavior — a known-compromised narrator is treated as poisoning the whole chain, same as a
narrator the registry has already rejected. (Contrast with Fix 3 below, which caps at `DAIF`,
not `MAWDU` — a single fidelity failure is a different, weaker kind of evidence than a
registry-level integrity determination.)

**Tests**: `tests/test_grading.py::TestAdalahIntegrityAxis` (4 tests — forces `MAWDU` despite
reliable grades, no effect when nothing's compromised, `UNASSESSED` is neutral, omitting the
param is backward-compatible).

---

## Fix 2 — Direction 2 + its own open question: contradiction-gated corroboration, and an actual review queue

**Files**: `core/corroboration.py`, `api/endpoints/claims.py`, `api/endpoints/review.py` (new),
`api/app.py`

### 2a. Corroboration can no longer launder a live contradiction

**The gap**: `CorroborationEngine.evaluate()`/`evaluate_direct()` computed an upgrade purely
from chain grades and narrator-independence scores — with zero visibility into whether the
claim being evaluated currently contradicts something else. A fabricator could build several
differently-named, undeclared-lineage "chains" for the same fabricated claim; as long as the
independence check saw no shared metadata (the default when nothing is declared), the
corroboration math would upgrade the claim's grade with no way to check it against a
contradiction.

**The fix**: `CorroborationEngine.evaluate()` / `.evaluate_direct()` / the shared
`_evaluate_core()` all take a new `has_live_contradiction: bool = False`. When true, the
method short-circuits to "no upgrade" immediately after the existing `MAWDU`-cannot-be-
corroborated check — before any independence scoring or effective-weight math runs at all.

In `api/endpoints/claims.py`, `submit_claim()` was **reordered**: content criticism (`cv`) now
runs *before* the corroboration engine is invoked (previously the opposite), so
`has_live_contradiction = (cv == ContentVerdict.CONTRADICTION)` is available in time to gate
the corroboration call.

**Before → after**:
```python
# Same inputs, only the contradiction flag differs — direct proof it's the deciding factor.
engine.evaluate_direct(DAIF, ["narr-A"], [{"grade": "hasan", ...}, {"grade": "sahih", ...}],
                        has_live_contradiction=False).upgraded  # True — upgrades to HASAN
engine.evaluate_direct(DAIF, ["narr-A"], [{"grade": "hasan", ...}, {"grade": "sahih", ...}],
                        has_live_contradiction=True).upgraded   # False — withheld
```

**Tests**: `tests/test_corroboration.py::TestContentAwareGating` (3 tests, including an
A/B pair with identical inputs differing only by the flag).

### 2b. The dead `ReviewQueue` table is now populated, linking both sides of a contradiction

**The gap**: `models.py` already defines `ReviewQueue` (with a `conflicting_claim_ids` field
meant for exactly this purpose) and `ReviewQueueItemDTO` — but neither was referenced anywhere
outside `models.py`. `"action": "review"` in an API response was a label in an in-memory dict
that nothing ever read; the older, contradicted claim was never re-flagged or linked to the
new one.

**The fix**:
- `_find_best_matching_claim_id()` (new helper in `claims.py`) locates the specific existing
  claim a `CONTRADICTION` verdict matched, via a lightweight `TFIDFIndex` lookup (already
  public in `critics/embedding.py`) — deliberately independent of whichever `ContentCritic`
  actually produced the verdict, so this doesn't touch that protocol at all.
- When `action` is `REVIEW`, `QUARANTINE`, or `REJECT_AND_QUARANTINE_NARRATOR`, `submit_claim()`
  now inserts a `ReviewQueue` row, with `conflicting_claim_ids=[matched_claim_id]` populated
  when a contradiction match was found.
- New `api/endpoints/review.py`: `GET /v1/review-queue` (list unresolved items) and
  `GET /v1/review-queue/{id}` (detail), registered in `app.py`.

**Tests**: `tests/test_api.py::TestReviewQueue` (3 tests, end-to-end through the real API —
submits two contradicting claims, confirms the queue entry links both claim IDs).

---

## Fix 3 — Direction 3: per-generative-link transformation fidelity

**Files**: `models.py`, `core/chain.py`, `core/fidelity.py` (new), `types.py`,
`core/grading.py`, `api/dependencies.py`, `api/endpoints/claims.py`,
`alembic/versions/3937bac5b5a1_add_chain_link_content_snapshots.py` (new)

**The gap**: Content criticism (matn) only ever ran once, at the very end, against the
external corpus — comparing the *final* claim text to what already exists. It has no way to
catch a claim that started true and was quietly corrupted by a GENERATIVE link partway
through the chain, and it structurally cannot verify a claim that has nothing in the corpus
yet to compare against. This matters specifically because of a distinction the classical
hadith tradition itself drew (*riwāya bi-l-lafẓ* vs. *riwāya bi-l-maʿnā* — exact-wording vs.
meaning transmission): a narrator who merely **transmits** can only lose or preserve
information (`DESTRUCTIVE`/`PASS_THROUGH` links); a narrator who **generates** — synthesizes,
reasons, extends — can introduce brand-new content that didn't exist upstream at all. An LLM
agent is not just a narrator carrying a message forward, it is expected to add to the
knowledge — but what it adds must still be a coherent extension of what it received, not
something fundamentally incoherent with or contradictory to it.

**The fix**: a third axis, distinct from both `NarratorGrade` (general track record) and matn
criticism (corpus comparison): does this specific generative link's *output* actually follow
from its own *input*, right now, in this one chain.

- **Schema**: `ChainLink`/`ChainLinkSpec` gain nullable `input_snapshot`/`output_snapshot`
  fields — the claim text entering and leaving a link's transformation. New migration
  `3937bac5b5a1` (upgrade/downgrade both verified against a fresh DB).
- **`core/fidelity.py`** (new): `compute_fidelity_verdicts(chain, critic)`. For each
  `GENERATIVE` link with both snapshots present, calls
  `critic.evaluate(output_snapshot, output_snapshot, [input_snapshot], domain)` — reusing the
  existing `ContentCritic` protocol directly rather than inventing a new critic class or
  verdict type. Feeding the link's own input as the sole "corpus" entry turns the critic's
  ordinary consistent/contradiction/unverifiable judgment into exactly the needed
  entailment/contradiction/not-checked signal:
  - `CONSISTENT` → the output is a coherent, entailed extension of the input (the LLM did its
    job — synthesized, didn't fabricate).
  - `CONTRADICTION` → the output is incoherent with or contradicts its own input (possible
    fabrication — a flipped sign, a changed number, an inverted claim).
  - `UNVERIFIABLE` → not checked (non-generative link, missing snapshots, or no NLI-capable
    critic configured) — never penalized, matching the framework's existing "no data means no
    penalty" pattern.
  - Non-generative links (`DESTRUCTIVE`/`PASS_THROUGH`) are never checked — they can only lose
    or preserve information, never invent it, so there's nothing to check for fabrication.
- **`RefinedWeakestLink.compute_chain_grade()`** gains an optional `link_fidelity_verdicts`
  parameter. A `CONTRADICTION` verdict caps that link's contribution at `DAIF` — *before* the
  existing `DESTRUCTIVE`/`GENERATIVE`/`PASS_THROUGH` branching runs — regardless of the
  narrator's own `NarratorGrade`. This also correctly blocks the link from repairing the floor
  via `corroboration_support`, since its now-capped grade no longer clears the
  acceptable-or-better threshold that branch requires.
- **`api/dependencies.get_fidelity_critic()`** (new): tries `LocalNLICritic`, returns `None`
  (not an `EmbeddingCritic` fallback) if `sentence-transformers` isn't installed. Unlike the
  main content critic, this deliberately does not degrade to TF-IDF — a symmetric-similarity
  metric can't distinguish "the output followed from the input" from "the output contradicts
  the input," which is exactly the directional judgment this check needs.
- **`api/endpoints/claims.py`**: `submit_claim()` accepts per-link snapshots, computes fidelity
  verdicts after building the chain, passes them into `grade_chain()`, and surfaces them in
  the response as `link_fidelity_verdicts`.

**Before → after**:
```python
# Before: a RELIABLE generative narrator's output is trusted regardless of
# whether it coheres with what it was given.
grade_chain([RELIABLE, RELIABLE], [PASS_THROUGH, GENERATIVE], is_complete=True) == SAHIH

# After: the same RELIABLE grades, but this specific output contradicted its
# own input — capped at DAIF, independent of the narrator's registry standing.
grade_chain(
    [RELIABLE, RELIABLE], [PASS_THROUGH, GENERATIVE], is_complete=True,
    link_fidelity_verdicts=[UNVERIFIABLE, CONTRADICTION],
) == DAIF
```

**Severity note**: capped at `DAIF`, not `MAWDU` (contrast with Fix 1). A single contradicted
generation could be an honest mistake, not proof the narrator is a fabricator — that stronger
claim stays reserved for a registry-level `REJECTED`/`COMPROMISED` determination, which itself
would need sustained evidence accumulated over many claims (the existing jarḥ–taʿdīl loop via
`record_evidence()`) — this fix doesn't wire that feedback loop, only the per-instance check.

**Explicitly out of scope**: LangChain auto-capture of snapshots (would need new
`on_llm_end`/`on_tool_end` callback hooks — only `*_start` hooks exist today — plus
event-matching logic across a run); this branch is API-only, callers supply snapshots
explicitly. Also out of scope: a claim fabricated at the very origin with nothing in the
corpus yet to contradict it — fidelity-checking requires a legitimate prior state to compare
against, so it cannot catch a lie present from the first link. That case is a separate,
already-acknowledged gap (#1 — independence detection) resting on origin-narrator integrity
grading and genuine corroboration independence.

**Tests**: `tests/test_fidelity.py` (6 unit tests against a deterministic fake critic, isolating
the wiring logic from any real model's judgment quality), `tests/test_grading.py::TestFidelityAxis`
(5 tests, including a direct A/B pair proving the contradiction specifically blocks the
corroboration-repair path that otherwise succeeds), `tests/test_api.py::TestTransformationFidelity`
(3 tests, end-to-end through the real API).

---

## Verification summary

| Check | Result |
|---|---|
| New/touched tests | 20 new tests across both branches, all passing on first run after two caught-and-fixed bugs (a UUID-parsing issue in the review-queue endpoint; a leftover dead conditional in the grading walk — both fixed before landing) |
| Full suite | 208/209 pass |
| The one failure | `test_firewall.py`, a pre-existing Windows-codepage/UTF-8 decode issue in the test's own file-reading helper — confirmed present on unmodified `main` via `git stash`, unrelated to these changes |
| Migration | `alembic upgrade head` / `alembic downgrade -1` both verified against a fresh SQLite DB |
| Lint/format/types | `ruff check`, `ruff format --check`, `mypy` all clean on every touched/new source and test file |

## What this does *not* claim to solve

- **Fresh fabrication with nothing to contradict yet** (no existing counter-claim in the
  corpus) — neither contradiction-gating nor fidelity-checking reaches this, since both need
  *something* to compare against. Defense here still rests on origin-narrator integrity
  grading and genuine corroboration independence.
- **Independence detection itself** (#1) — the `SharedLineageDetector` still defaults to
  "assume independent" when narrators declare no shared metadata. Untouched by this fix; a
  fabricator who avoids declaring shared `model_family`/`upstream_source` across their fake
  parallel chains still passes that check. This fix specifically prevents that scenario from
  *also* laundering a live contradiction — it does not fix independence detection itself.
