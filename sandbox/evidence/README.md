# Sandbox evidence — what each file is

- `audit_record.json` — the signed **AuditRecord** for the loan-eligibility claim (grade, why, chain, and a detached signature in `integrity.detached_signature`).
- `chain.json` — the four-hop **transmission chain** (credit bureau → retriever → model → reviewer) with each hand's grade and transform type.

Re-verify the signature:

```
uv run isnad verify --record sandbox/evidence/audit_record.json \
  --hmac-secret "isnad-sandbox-dev-secret-do-not-use-in-production"
```

The secret is a **dev-only** placeholder committed only for the sandbox; never reuse it in production.
