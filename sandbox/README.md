# ISNAD sandbox — try it in 5 minutes

One command starts ISNAD, one command runs a real graded chain, and the
evidence is already sitting in `sandbox/evidence/` for you to inspect.

> **Plain-English:** ISNAD grades a claim by the *chain of hands* it passed
> through. A "weak" hand caps the whole chain (the weakest link), and every
> verdict ships with a signed proof you can re-verify yourself.

## 1. Start it

```bash
cp .env.example .env       # the .env already has dev-only sandbox values
docker compose up --build
```

Wait for the `api` service to report healthy.

## 2. Run the sample pipeline

In a second terminal (or the same one, after `up` finishes):

```bash
docker compose exec api uv run python examples/sandbox_demo.py
```

You'll see a graded verdict like:

```
claim : Applicant AC-2041 is eligible for a €40,000 term loan.
chain : source:credit-bureau → retriever:rag-vectorstore → model:eligibility-llm → reviewer:compliance-human
grade : HASAN
why   : claim '…' → chain HASAN (weakest: retriever:rag-vectorstore, acceptable)
```

No API keys, no network — the demo is fully local.

## 3. Open the evidence

Look in `sandbox/evidence/` — two files, already committed:

- `audit_record.json` — the signed audit record (grade, why, chain, and a
  `detached_signature`).
- `chain.json` — the four-hop chain with each hand's grade.

## 4. Verify it yourself

```bash
docker compose exec api uv run isnad verify \
  --record sandbox/evidence/audit_record.json \
  --hmac-secret "isnad-sandbox-dev-secret-do-not-use-in-production"
```

Expected output ends with `OK: … (detached signature verified)` and exit 0.

---

If you don't use Docker, the same two commands work locally:

```bash
uv run python examples/sandbox_demo.py
uv run isnad verify --record sandbox/evidence/audit_record.json \
  --hmac-secret "isnad-sandbox-dev-secret-do-not-use-in-production"
```
