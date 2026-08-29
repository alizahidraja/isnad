# Threat Model

This is the explicit statement of what ISNAD defends against, what it
deliberately does not, and where the trust boundary lies. It is written to be
read alongside [`SECURITY.md`](SECURITY.md) and the README's "What's Validated
vs. What's Not" table, and it is deliberately conservative: an over-stated
guarantee is a vulnerability.

## Assets

- **The registry** (`rijāl`): the operator's local table of narrator grades.
- **Grades**: per `(narrator, role, domain)` precision, per `(narrator, domain)`
  integrity.
- **Evidence**: the append-only jarḥ–taʿdīl log that justifies every grade.
- **Traces** (`isnad_trace` v0.1): the record of how one claim was handled.
- **The decision matrix**: the serve / review / quarantine router.

## Trust boundary

**The operator is the root of trust.** ISNAD grades what happens *after* the
operator admits a narrator at the boundary. It cannot make a bad onboarding
decision good; it can make the *payoff* of a bad decision small (per-domain,
capped) and the *exposure* of a caught narrator permanent (integrity strike).

Concretely, ISNAD does **not**:

- verify that `metadata["source"]` is authentic;
- fact-check a claim that has no contradiction in the operator's corpus;
- detect that a `RELIABLE` fake source plus a clean pipeline is still fake.

## Adversaries and mitigations

### 1. The sleeper narrator (trust earned to be spent once)

An identity that transmits faithfully for a long period, earns a high grade,
then spends it once on one target. See
[`docs/case-study-xz-sleeper-narrator.md`](docs/case-study-xz-sleeper-narrator.md).

**Mitigations in place:** per-domain grades (standing does not transfer across
domains); integrity (ʿadālah) is permanent and strikes are human-only
(`default_axis_for` resolves automated jarḥ to precision); corroboration is
capped at `HASAN`, never `SAHIH`; `alias@version` endpoint identity resets on
version drift.

**Not mitigated (honest):** a payload engineered to have no observable
contradiction until a specific condition fires. Detection is retrospective;
containment is prospective. See #34 and #43.

### 2. Reputation farming / Sybil

Many identities laundering one good grade, or one identity buying standing to
be resold.

**Mitigations in place:** grades are **local** — there is no shared registry to
poison; `SharedLineageDetector` collapses correlated chains (the sock-puppet
echo); corroboration requires genuinely independent narrators.

**Not mitigated:** grade *import* between operators. The no-federation
invariant is stated here explicitly so the first "let's share registries"
proposal sees the cost: importing grades re-introduces the Sybil surface the
local registry removes. See #44.

### 3. Integrity bypass (containment escape)

A quarantined narrator recovering through precision evidence, or a precision
strike being treated as permanent.

**Mitigations in place:** `quarantine()` sets `adalah=COMPROMISED` and REJECTED
is sticky *only* when integrity-driven (#40); integrity strikes impose a
permanent ceiling that precision cannot lift (#30).

**Not mitigated:** sub-quarantine integrity
strikes are per-role, not per-person (#29). (Quarantine *does* span domains —
`registry.py` treats integrity compromise as narrator-wide, #28.)

### 4. Machine-critic false positives

A scanner or semantic critic that flags good claims as bad, or worse, issues
permanent strikes on false positives.

**Mitigations in place:** automated signals resolve to precision (recoverable);
an integrity strike requires `HUMAN_REVIEW` or an explicit `INTEGRITY` tag.

**Design stance (not yet a hard contract):** a machine critic may emit
precision evidence and pull the cord (`QUARANTINE`), but must never *convict*.
`default_axis_for()` is currently an internal default, not an enforced
contract — see #40's framing and the xz case study §8.

### 5. Trust-elevation at the boundary

A self-declared endorser treated as independent, or a shallow authority chain.

**Mitigations in place:** Live Verify seals consume `authorizedBy` presence as
the endorser signal; self-verified seals are refused by the survival primitive
(tazkiyah guard).

**Not mitigated:** the authority chain is not walked to a root — presence of
`authorizedBy` is not proof the endorser endorses (#37).

## Non-goals (deliberate)

- **Source legitimacy.** The operator vets sources; ISNAD does not.
- **Novel-claim truth.** Matn catches contradiction with the operator's corpus;
  it does not establish ground truth.
- **Faithful transmission of bad input.** A clean pipeline over a fake source
  grades high; that is correct grading of transmission, not a bug.
- **Crypto attestation of origin.** Complementary to (not replaced by) Live
  Verify, Sigstore, SLSA, and C2PA. See #47 for the interoperability story.

## Reporting

See [`SECURITY.md`](SECURITY.md). An over-stated guarantee is a vulnerability.
