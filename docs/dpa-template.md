# DPA template + sub-processor inventory

Data-processing addendum skeleton. Fill the bracketed fields; have counsel review before
the first enterprise signature. ISNAD's PII surface is **claim_text** and narrator ids —
everything else in the audit record is hashes/ids, so the data exposure is narrow.

## 1. Data categories
- **Customer content**: `claim_text` (the user's claim — the main PII surface), source
  document text, narrator ids.
- **Provenance metadata**: hashes, grades, timestamps, domain/role tags, action verdicts.
- **Redaction default**: `claim_text` is hashed in the audit record and redacted on reads;
  full content is opt-in (`capture_full_content`).

## 2. Sub-processors (each needs its own DPA + a named legal basis)
| Sub-processor | Purpose | Data | Location | DPA |
|---|---|---|---|---|
| LLM critic provider (e.g. DeepSeek) | content criticism | claim_text + evidence (transient) | [region] | [required] |
| Database host (Postgres/SQLite) | persist records | full audit record | [region] | [required] |
| SIEM destination (Splunk/Datadog/Snowflake) | archiving/export | signed-JSON (redacted) | [region] | [required] |

## 3. Retention & deletion
- Audit records: retain per the customer's retention policy (default [7] years for regulated
  use); the tamper-detecting chain requires **append-only** retention (deletion breaks the chain).
- Redacted/derived records: delete on request within [30] days.
- The 1.6 GB benchmark dataset (`hadith-kg.db`) is public CC-BY-4.0 and contains **no customer data**.

## 4. Security measures (ISNAD provides)
- Detached HMAC/Ed25519 signing, hash-chained + Merkle-batched records with an anchored head.
- Admin-gated writes, constant-time API-key auth, `audit_signed` fail-closed when unconfigured.
- PII redaction default-on in the export path.

## 5. Breach notification
- The company notifies the customer within [72] hours of a confirmed breach affecting customer
  content, per the customer's jurisdiction.

## 6. The honest boundary
ISNAD is a **self-hostable library**, not a hosted processor by default. If you run a managed
cloud, *you* become the processor and this DPA becomes yours to sign. A Fortune-500 buyer will
ask "are you a processor?" — the honest answer today is "no, you self-host; here is the evidence
you'd want in a processor."
