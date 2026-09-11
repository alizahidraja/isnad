# Concepts — how isnād–rijāl maps to multi-agent provenance

The idea ISNAD is built on: the oldest method humans invented for trusting a claim is
also the right one for trusting an LLM's.

## Why does a multi-agent chain need a provenance framework?

A claim that passes through five agents isn't more reliable — it's more obscured. Each
hop can introduce, drop, or distort information, and today no record says *which* hop
did *what* with *how much* authority. Provenance logs answer "what happened"; ISNAD
answers "who vouches for this, and how far can you trust them."

## What is an isnād?

An **isnād** is the transmission chain: the ordered list of who passed the claim to
whom. In ISNAD each link is a `ChainLinkSpec` — narrator id, transform type, version,
domain, and content hash — so the chain is a typed, hash-linked graph, not a log.

## What is rijāl, and why is it separate from the chain?

**Rijāl** is the narrator registry: a graded record of *who* each transmitter is and
how reliable they've been, per role and domain, decaying over time. It is graded
independently of what the narrator is saying right now — because trusting a source
based on how confidently it phrases an answer is circular (a confident lie earns a
confident-sounding answer). The registry breaks that circle: you grade the *narrator*,
not the *narration*.

## How does the weakest-link rule grade a chain?

A chain is only as strong as its weakest link. ISNAD walks the chain and lets each
narrator's grade set a floor, refined by transform type — a destructive summarizer's
grade is a permanent floor, a corroborated generative hop can raise it. One weak link
caps the whole chain, exactly as it should.

## What is matn criticism, and why doesn't ISNAD do it alone?

**Matn** is content criticism: does the claim contradict known evidence? ISNAD
deliberately does *not* judge truth itself — it produces a `ContentVerdict` via a
critic you plug in (deterministic, embedding, or LLM). The framework composes with
critics; it doesn't replace them. Provenance answers *who*, the critic answers
*whether*, and the two are different jobs.

## What is the decision matrix?

A 4×3 router combining chain grade (ṣaḥīḥ/ḥasan/ḍaʿīf/mawḍūʿ) with content verdict
(consistent/contradiction/unverifiable) into one action: **serve**, **serve-with-caveat**,
**review**, or **quarantine**. A sound chain with a contradiction is the most valuable
case — it's routed to human review, not auto-served.

## What does ISNAD measure, and what doesn't it claim?

It grades **who** transformed a claim and **how reliably** — ordinal grades (ṣaḥīḥ >
ḥasan > ḍaʿīf), never a fake numeric confidence. It does not claim to detect truth; the
content critic is the ceiling, and ISNAD states that ceiling instead of hiding it.

## Why does this map to multi-agent provenance so cleanly?

Because the three loops — chain, narrators, content — are exactly the three failure
axes of an agent pipeline: *who touched it*, *how trustworthy is each component*, and
*does the output contradict evidence*. ISNAD is the first framework to grade all three
with a benchmark (κ 0.871 against scholars' own verdicts over 577,024 chains) rather
than just an argument for them.
