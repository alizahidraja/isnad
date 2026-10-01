# SOC 2 readiness — ISNAD's evidence, and what the company must add

SOC 2 is an **organizational attestation**, not a code feature. ISNAD provides the
evidence artifacts a SOC 2 auditor wants; the company (you) provides the operating
controls. This is the scoping doc — hand it to your auditor or a readiness firm.

## Type I vs Type II
- **Type I**: point-in-time — are the controls *designed* correctly? (Weeks, one audit.)
- **Type II**: period (3–12 months) — did the controls *operate* correctly? (The real
  enterprise unlock; start only after Type I + live customers.)

Both use the same five **Trust Services Criteria**: Security, Availability, Processing
Integrity, Confidentiality, Privacy.

## What ISNAD already produces (your evidence)
| TSC | ISNAD artifact |
|---|---|
| **Processing Integrity** | Tamper-evident audit records — SHA-256 per claim, detached HMAC/Ed25519 signature, hash-chained + Merkle-batched with an anchored head (`src/isnad/audit/`) |
| **Security** | Admin-gated writes, constant-time API-key auth, `audit_signed` derived from the signature (never a stored bool), PII redaction on reads |
| **Confidentiality** | `claim_text` redaction + `redact_fn` in the export path; records are hash-first (content optional) |
| **Privacy** | `--redact` export, `audit_signed` fail-closed when no secret is configured |
| **Logging & Monitoring** | The chain + registry log (EU AI Act Art 12), exportable to SIEM (Splunk/Datadog/Snowflake) |

## What the company must add (the auditor will ask; ISNAD cannot provide it)
1. **Entity + policy**: security policy, access-control policy, incident-response plan, vendor-management policy, change-management, and a named security owner.
2. **Access control**: SSO, RBAC, key rotation, separation of duties (a solo founder is a *compensating-control* problem — document it honestly).
3. **Infrastructure**: HA, backups, retention (7-year for audit logs), monitoring/alerting, patching.
4. **DPA + sub-processor inventory**: the LLM critic provider, the DB host, and any SIEM destination are sub-processors — each needs a DPA.
5. **Pen test** before any "Type II" or "compliant" claim.

## The honest line (never cross it)
ISNAD's audit record says *"produces evidence artifacts; does not confer conformity with
any regulation."* SOC 2, EU AI Act, and NIST mapping are the **company's** attestations,
not the library's. State COVERED / PARTIAL / NOT COVERED — never "compliant."

## Recommended path
1. SOC 2 Type I (dated) on the single-tenant self-host engine — ~4–6 weeks with a readiness firm.
2. `docs/compliance-coverage-matrix.md` (EU AI Act / NIST field-level, counsel-signed).
3. DPA template (`docs/dpa-template.md`) + sub-processor list.
4. SOC 2 Type II only after 1–2 paying customers + a 3-month observation period.
