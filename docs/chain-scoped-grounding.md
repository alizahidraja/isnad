# Chain-scoped grounding

Chain-scoped grounding answers a question the plain content critic cannot: *"is this
claim grounded in evidence that actually traveled **its own** transmission chain?"*

The content critic checks whether a claim's information is present in a merged corpus.
In a multi-agent run that merged corpus loses track of **which agent fetched which row**,
so a claim can look "grounded" in a row a *different* agent on a *different* branch
fetched — context pollution. Chain-scoped grounding makes grounding provenance-aware.

## The primitive

- `ChainLinkSpec.retrieved_rows` — the **content** of the rows a link retrieved, carried
  **runtime-only** (never serialized into `to_dict()` / the signed record; the signed
  record commits to `document_hashes` only, so raw row content never enters the RFC 8785
  canonical form or the `--redact` surface).
- `chain_scoped_corpus(chain)` — the deduplicated, order-preserving union of every link's
  `retrieved_rows` — "the evidence that traveled this claim's own path".

The scoping is **chain-level, not link-level**: a synthesis link retrieves nothing and
legitimately grounds in the *upstream* retrieval link's rows, so a link-local check would
wrongly flag every legitimate synthesis.

## The policy

`ChainScopedGroundingPolicy` (via `evaluate_chain_grounding`) returns a `GroundingResult`:

| Field | Meaning |
|---|---|
| `grounded_off_chain_only` | `True` iff the claim is CONSISTENT against off-chain rows **and** UNVERIFIABLE against its own chain — a **grounding gap**, not proven contamination |
| `on_chain_verdict` | the critic verdict against the chain-scoped corpus (`None` = provenance unknown) |
| `off_chain_verdict` | the critic verdict against the off-chain rows |

**The flag is evidence, not an action.** It deliberately has **no route** into the
SERVE/REVIEW/QUARANTINE decision matrix — that mapping is a separate decision.

## Honest limits

- **Critic capability.** The flag only fires when the critic can affirm `CONSISTENT`.
  The default `EmbeddingCritic` is **contradiction-only** (never returns CONSISTENT), and
  NLI/LLM critics downgrade CONSISTENT → UNVERIFIABLE when their affirmation gate is on.
  A CONSISTENT-capable critic requires `gate_affirmation=False` (or a configured LLM).
  The serving API surfaces this as `grounding.grounding_capable`.
- **Persistence.** `retrieved_rows` is runtime-only. A chain reloaded from the database
  carries `retrieved_rows_known=False`, and the policy returns `on_chain_verdict=None`
  (never flags) rather than falsely flagging a provenance-unknown chain (#241).
- **Spoofable split.** `off_chain_rows` is **caller-supplied and unverified** — a planted
  off-chain row can false-flag a rival's claim; `off_chain_rows=[]` silently disables the
  flag. Establishing the split honestly is the caller's responsibility.
- **Measured, not asserted.** The flag's false-positive rate is measured in
  `experiments/grounding_eval/` (#239) against a real NLI critic — see the "measure,
  don't assert" discipline. Small pilot set; treat as a direction, not a tight estimate.

## Wiring

`POST /v1/claims` accepts optional `retrieved_rows` per chain link, computes the
chain-scoped corpus, runs the policy, and returns a `grounding` block (flag, both
verdicts, corpus sizes, `grounding_capable`). The flag does not change the decision.
