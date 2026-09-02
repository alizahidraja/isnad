# Provenance

ISNAD's audit contract: **every grade is backed by evidence, and every record can be
verified.** The framework emits *evidence artifacts*, not compliance certificates.

## Three kinds of evidence — three honest labels

A narrator's grade is derived from an append-only evidence log. Each entry is classified
into one of three provenance buckets, and the label is **honest about which one produced
it**:

| Label | Evidence | Meaning |
| --- | --- | --- |
| `observation (Supported)` | `OBSERVED` | Real pipeline evidence: a measured, hash-pinned evaluation. |
| `prior (Estimated)` | `BOOTSTRAP_SEED` | A population prior (benchmark accuracy, publisher reputation). An assumption, not a measurement. |
| `human (Reviewed)` | `HUMAN_REVIEW` | A human intervened (review, quarantine, override). |
| `unvalidated` | *(none)* | A grade with no observed, human, or prior evidence. Never silently promoted. |

The key honesty rule: **"Supported" is only ever earned, never shipped.** A shipped seed
can never plain-`SERVE`; it is capped to `SERVE_WITH_CAVEAT` or `REVIEW` by the serve
gate until real observations arrive.

## No numeric confidence

ISNAD deliberately refuses to emit a `0.87 confidence`. It emits an **ordinal grade**
(`reliable → acceptable → weak → rejected → ungraded`) plus the **evidence that produced
it**. A number would invite over-trust; the evidence invites review.

## Tamper-evident records

Every judgment can be exported as an `AuditRecord` with:

* **SHA-256** canonical hashing (RFC 8785 JSON canonicalization),
* a **Merkle batch log** for append-only histories, and
* **detached Ed25519 signatures** for third-party verification.

The JavaScript verifier (`npm install isnad`) re-checks these byte-for-byte against the
Python core via golden vectors — see the [trace schema](trace-schema.md).

## Verify it

```bash
isnad verify --record audit.json        # recompute the hash and check
isnad verify-merkle --log batch.jsonl   # replay a Merkle batch log
isnad verify-chain --chain chain.jsonl  # replay a hash chain log
```

> **Tamper-evident, not tamper-proof.** ISNAD records *evidence of tampering*, it does
> not *prevent* it. For an append-only transparency log you host yourself, pair ISNAD with
> Rekor / Sigstore — see [trace-schema](trace-schema.md).
