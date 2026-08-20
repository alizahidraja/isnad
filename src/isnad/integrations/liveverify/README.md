# Live Verify Integration

Consume a [Live Verify](https://github.com/live-verify/live-verify) seal —
Paul Hammant's cryptographic document-attestation protocol — as a high-trust
narrator input to an ISNAD chain.

## What Live Verify is

Live Verify binds a document's **visible text** to an issuer's **domain** via
a SHA-256 hash plus a `verify:` lookup.  Anyone can confirm the document is
the one the issuer actually issued, unaltered — no blockchain, no PKI, no
credentials.  The trust anchor is DNS/TLS.

## Why this integration exists

ISNAD and Live Verify answer the same root question — "why should I trust
this claim that reached me through a chain of hands?" — from opposite ends of
the pipeline.  They are complementary, not competing.

The composition point (from Live Verify's own `comparison-to-isnad.md`):

> *A Live Verify seal is an ideal high-trust narrator input to an Isnad chain.
> A cryptographically-anchored, authority-chained source is exactly the kind of
> link that deserves a top narrator grade. Its integrity axis (ʿadālah) is
> anchored by cryptography and by an authority chain to a sovereign root,
> rather than by accumulated track record. A Live Verify seal can thus
> bootstrap a narrator to a high grade on day one, before any evidence history
> exists.*

That last sentence solves ISNAD's **cold-start problem**: instead of waiting
for the jarḥ–taʿdīl loop to accumulate evidence, a verified seal seeds the
source narrator's integrity on day one.

## Usage

```python
from isnad.integrations.liveverify import verify_claim, seal_to_narrator, register_sealed_source
from isnad.core.registry import Registry

# Verify a claim whose text carries a verify: line
result = verify_claim(
    "MSc Computer Science, Edinburgh University\n"
    "verify:degrees.ed.ac.uk/c"
)

# Map the result onto ISNAD's trust axes
sealed = seal_to_narrator(result)
print(sealed.narrator_id)  # "verify:degrees.ed.ac.uk"
print(sealed.grade)        # RELIABLE (integrity anchored by crypto)
print(sealed.adalah)       # HIGH
print(sealed.dabt)         # UNASSESSED  ← precision NOT claimed

# Or register directly into a registry (bootstraps day-one integrity)
reg = Registry()
sealed = register_sealed_source(reg, result, domain="education")
```

## The honest limit: authenticity ≠ truth

A `verified` seal proves the issuer stands behind this exact text, **unaltered**.
It does **not** prove the underlying claim is **true**.  The mapping respects
that line:

| ISNAD axis | What the seal provides | What the seal does NOT provide |
|------------|------------------------|-------------------------------|
| ʿadālah (integrity) | **HIGH** — cryptographically anchored, unaltered, issuer-attested | — |
| origin strength | **verified** — the issuer domain is the trust root | — |
| ḍabṭ (precision) | — | **UNASSESSED** — a genuine document can still be factually wrong |
| matn (content) | — | **unchanged** — the content critic must still judge truth |

A verified document can be a genuine, domain-attested **lie** (the
fabricated-clean-chain problem).  The seal anchors *where the claim came
from* and *that it wasn't tampered with* — it never substitutes for content
criticism.

## Byte-compatibility

The text normalization in `normalize.py` is a byte-compatible port of Live
Verify's canonical JavaScript.  This is the interop contract: if the hashes
drift, every verification fails.

Tests hold it to two independent guarantees:

1. **Fixture hashes** — the Python port must match Live Verify's own
   cross-platform fixtures (`tests/fixtures/liveverify/*.md`), where each
   filename is the expected SHA-256.
2. **JS cross-check** — when Node is present, the Python port must produce
   byte-identical output to the vendored canonical `normalize.js`.

## Components

| Module | Role |
|--------|------|
| `normalize.py` | Byte-compatible port of Live Verify text normalization |
| `client.py` | Protocol client: extract verify: URL → normalize → hash → GET |
| `adapter.py` | Map a verification result onto ISNAD's two trust axes |

## Status codes → ISNAD mapping

| Live Verify status | ʿadālah | NarratorGrade | origin |
|-------------------|---------|---------------|--------|
| `verified` | HIGH | RELIABLE | verified |
| `revoked` / `suspended` | COMPROMISED | REJECTED | compromised |
| `expired` / `superseded` / `lapsed` | ACCEPTABLE | ACCEPTABLE | attested |
| `404` / network error | UNASSESSED | UNGRADED | unknown |
