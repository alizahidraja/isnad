# ISNAD (JavaScript/TypeScript) — audit-record verifier

Verify the integrity of [ISNAD](https://github.com/alizahidraja/isnad) audit
records from JavaScript/TypeScript.

> **Verifier only — this package does not grade claims.** Grading, the narrator
> registry, weakest-link evaluation, and corroboration live in the Python core
> (`pip install isnad`), which is the *sole grading authority*. This package
> only checks the tamper-evidence that the Python core emits.

## Install

```bash
npm install isnad
```

Requires Node.js >= 18.

## What it verifies

- **Self-hash** — `integrity.record_hash` is a SHA-256 over the RFC 8785
  canonical form of the record (minus the `integrity` block).
- **Detached signatures** — HMAC-SHA256 (shared secret) or Ed25519 (asymmetric)
  over the same canonical payload.
- **Merkle batch logs** — batch roots, chain linkage (`prev_root`), and O(log n)
  inclusion proofs.

It does **not** grade, register narrators, corroborate, or emit new records.

## Usage

```ts
import { verifyRecord, hmacVerify, ed25519Verify } from "isnad";

// A record emitted by the Python core (JSON).
const record = JSON.parse(fs.readFileSync("audit.json", "utf8"));

// 1. Verify the self-hash.
const result = verifyRecord(record, (payload, sig) => hmacVerify("my-secret", payload, sig));
// result.hashValid === true
// result.signatureValid === true | false | null  (null = no signature present)

// 2. Or with Ed25519 (raw 32-byte public key, hex):
verifyRecord(record, (payload, sig) => ed25519Verify(PUBLIC_KEY_HEX, payload, sig));
```

### Merkle batch logs

```ts
import { buildBatch, verifyBatches, proveInclusion, verifyInclusion } from "isnad";

const batch = buildBatch([
  ["record-id-1", "hash1"],
  ["record-id-2", "hash2"],
]);

verifyBatches([batch]); // null = intact, or { index, reason } = break

const proof = proveInclusion(batch, "record-id-2");
verifyInclusion(proof, batch.root); // true
```

## Honesty & scope

- **Byte-identical canonicalization** with the Python core is pinned by
  *golden conformance vectors* generated from the Python test suite
  (`test/golden.json`). Cross-language hash divergence fails CI.
- **Never floats**: the canonicalizer rejects non-integer numbers, so the only
  fiddly part of RFC 8785 is enforced away rather than reimplemented.
- **Never holds a secret in a browser**: this package verifies only. A shared
  HMAC secret must never ship to a client; signing stays server-side.

## License

Apache-2.0.
