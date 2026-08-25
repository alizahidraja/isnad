---
title: "ISNAD: a claim-level provenance and trust-grading framework for multi-agent AI systems"
tags:
  - python
  - provenance
  - machine-learning
  - ai-safety
  - trust
  - observability
authors:
  - name: "Ali Zahid Raja"
    orcid: "0009-0003-7875-4590"
    corresponding: true
    affiliation: 1
affiliations:
  - name: "Independent researcher"
    index: 1
date: "26 August 2026"
bibliography: paper.bib
---

# Summary

ISNAD is a Python library that grades *how much to trust* the claims a
multi-agent AI system produces — not by re-checking each fact, but by grading
the *transmitters* a claim passed through. It adapts the isnād–rijāl method,
the twelve-century-old transmission science of hadith scholarship, to modern AI
pipelines: every claim carries an ordered chain of who handled it (the isnād);
every handler carries a reliability grade that moves with evidence (the rijāl
registry); a chain is graded by its weakest link; and the result is routed to
one of three actions — serve, review, or quarantine. The library ships with a
pluggable grading engine, content criticism, independent-chain corroboration, a
tamper-evident audit record, and integrations for LangChain, LangGraph,
CrewAI, LlamaIndex, and OpenTelemetry. It is Apache-2.0 licensed, tested by a
600-test suite on Python 3.12 and 3.13, and installable with `pip install
isnad`.

# Statement of need

Execution provenance tools record *what* a system did; they cannot answer
*whether to believe the result*. When a claim passes from a scraper to a
retriever to a model to a serving layer, each hand can drop, distort, or invent
information, and the number of hands is growing as agents compose into larger
pipelines. Existing observability (OpenTelemetry) standardises model, token, and
latency attributes but is explicit that it does **not** cover output evaluation
or quality [@otel]. Provenance standards (W3C PROV) describe *who did what* but
attach no trust judgement [@prov]. ISNAD fills the gap between "we can see what
ran" and "we know how much to trust the output", for practitioners who build or
operate multi-agent systems and need a defensible, auditable answer to the
question a regulator or auditor will ask: *why was this claim served, and how
do you know it is reliable?*

# State of the field

Three adjacent ecosystems solve neighbouring problems. **W3C PROV** models
activity and attribution but not reliability. **OpenTelemetry GenAI** observes
span-level model and token attributes but deliberately leaves evaluation out of
scope. **Artifact provenance** (SLSA, SBOM, Sigstore) attests *origin* at the
build boundary, not *transmission* inside a running pipeline. LLM evaluation
harnesses measure output quality but carry no transmission lineage. ISNAD is
distinct in grading the *transmitters* — the persistent identities that survive
across many claims — rather than scoring one output at a time, and in making
the distinction between *execution* provenance and *trust* provenance explicit.

# Software design

The core is four decoupled loops that meet in a decision matrix. The **isnād**
is an ordered, gap-checked chain of transmitters per claim. The **rijāl**
registry grades each transmitter on two axes — ʿadālah (integrity) and ḍabṭ
(precision) — keyed by `(narrator, domain, role)`, with grades evolving through
an append-only, evidence-driven state machine. **Weakest-link grading** combines
per-link grades into one ordinal chain grade (ṣaḥīḥ / ḥasan / ḍaʿīf / mawḍūʿ),
refined by whether a link is destructive or generative. **Content criticism**
checks the claim against the corpus independently of chain quality, and
**corroboration** (mutābaʿāt) upgrades trust when *independent* chains agree.
These combine in a 4×2 decision matrix routing claims to serve, review, or
quarantine. Two further mechanisms matter in practice: **period-sliced grades**
re-derive a narrator's grade at any past instant (the *ikhtilāṭ* remedy for a
transmitter who was sound and then declined), and an **integrity ladder** makes
an integrity strike permanent while a precision strike remains recoverable.
Every grade is an ordinal band, never a numeric confidence, and the audit layer
emits a tamper-evident, SHA-256-hashed record of each decision.

# Research impact

The framework is validated in two ways. The companion paper [@raja2026grading]
presents a 20,000-claim experiment showing the weakest-link rule correctly
quarantines every claim from a rejected narrator. ISNAD-Bench, a preregistered
benchmark shipped with the software, grades 577,024 real hadith chains against
the scholars' own verdicts and reaches **Cohen's κ = 0.871** with the consensus
— where the scholars themselves agree with each other at only κ = 0.331,
demonstrating that ISNAD faithfully implements, rather than exceeds, its
source method. The software carries a Zenodo DOI, is published on PyPI, and its
grading primitive (`isnad bench --config`, `isnad ingest --otlp`) is designed so
a third party can run it on their own data without adopting the library.

# AI usage disclosure

Generative AI assistance was used during the development of this software and in
the drafting of this paper, including code generation and documentation.
Drafting and review of the final text were performed with human oversight.

# Acknowledgements

The author thanks the reviewers of this submission.

# References
