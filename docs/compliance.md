# Compliance — how ISNAD maps to AI governance frameworks

The enterprise question isn't "does your framework grade AI claims." It's "do you have
the records my auditor will ask for." ISNAD produces **tamper-evident audit records** —
a SHA-256 hash per graded claim, per link — that map onto the frameworks below.

## What does ISNAD record, and why is it tamper-evident?

Every claim gets a typed transmission chain (who → who), a narrator-reliability grade
per hop, a content verdict, and the resulting decision — each link hashed and the whole
record signable (HMAC) with `audit_signed` marking whether a secret was present. Records
are hash-chained, so altering any hop breaks the hash.

## How does ISNAD satisfy EU AI Act Article 12 (record-keeping)?

Article 12 obliges providers to **generate and keep logs** of the system's operation.
ISNAD's chain + registry is exactly that log, made machine-readable: each transform is a
timestamped, hashed, graded link — an auditable trace of how an output was produced,
not just what it says.

## How does ISNAD satisfy EU AI Act Article 13 (transparency)?

Article 13 requires providers to document — where relevant — the mechanisms letting
deployers **collect, store, and interpret logs**, plus intended purpose, capabilities,
limitations, and human-oversight measures. ISNAD's trace schema is that mechanism: the
decision matrix and grade rationale are the interpretation layer, and the honesty box
states limits up front rather than hiding them.

## How does ISNAD map to ISO/IEC 42001?

ISO/IEC 42001 requires **documented information** as controlled records — versioned,
retained, and protected from alteration — for AI lifecycle and decision evidence.
ISNAD's versioned narrator registry (who was graded, when, at what version), the
per-link content hashes, and signed records are exactly the controlled evidence an
42001 audit collects.

## How does ISNAD map to NIST AI RMF?

The RMF's Govern/Map functions call for **provenance and traceability** — documenting
sources, origins, transformations, and dependencies so outputs can be traced back.
ISNAD is provenance-native: every claim traces back through its chain to its source
narrator and retrieved evidence, with the chain-scoped grounding separating *what this
chain actually retrieved* from *what was claimed*.

## How does ISNAD map to SDAIA (Saudi Data & AI Authority)?

SDAIA's AI ethics principles require **transparency, accountability, and traceability**
in AI systems. ISNAD's graded, hash-chained provenance record is a direct implementation
of those principles. (Specific SDAIA clause-by-clause mapping should be confirmed
against the latest published guidance.)

## What ISNAD does not claim for compliance

ISNAD is **evidence infrastructure**, not a certification. It produces the records a
compliance officer or auditor needs; it does not itself certify AI-Act conformity,
ISO/IEC 42001 certification, or RMF alignment. That separation is the point: your
auditors get verifiable artifacts, not a vendor's assertion.
