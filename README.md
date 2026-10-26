# ISNAD

ISNAD grades who handled a claim in an AI pipeline (the transmitters and the chain) and can export each verdict as an audit record you can sign and verify.

Site: https://isnadhq.com/ · Docs: https://isnadhq.com/docs

[![CI](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml/badge.svg)](https://github.com/alizahidraja/isnad/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/alizahidraja/isnad/blob/v3.2.0/LICENSE)
[![arXiv](https://img.shields.io/badge/arXiv-2607.24117-b31b1b.svg)](https://arxiv.org/abs/2607.24117)
[![Downloads](https://static.pepy.tech/badge/isnad/month)](https://pypi.org/project/isnad/)
[![npm](https://img.shields.io/npm/v/isnad)](https://www.npmjs.com/package/isnad)
[![Glama MCP score](https://glama.ai/mcp/servers/alizahidraja/isnad/badges/score.svg)](https://glama.ai/mcp/servers/alizahidraja/isnad)

<p align="center"><img src="https://raw.githubusercontent.com/alizahidraja/isnad/v3.2.0/docs/images/isnad-seal-wax-512.png" width="140" alt="ISNAD — the wax seal (إسناد)"></p>

## Install

```bash
pip install isnad
```

## Status

3.2 is the stable release of the 3.x line. The `release/3.x` branch receives security
fixes only. If you depend on the current API, pin `isnad>=3.2,<4`.

## 30-second example

```python
from isnad import Registry, grade
from isnad.types import NarratorGrade

reg = Registry()
reg.register("openstax", "physics", grade=NarratorGrade.RELIABLE)
reg.register("pdf-scraper", "physics", grade=NarratorGrade.UNGRADED)
reg.register("ingest-model", "physics", grade=NarratorGrade.ACCEPTABLE)

verdict = grade("p = mv", ["openstax", "pdf-scraper", "ingest-model"], reg, domain="physics")
print(verdict.why)
# claim 'p = mv' → chain DAIF (weakest: pdf-scraper, ungraded)
```

A new pipeline starts with every narrator UNGRADED, so nothing serves; seed grades
with `Registry.seed()`.

A JavaScript/TypeScript verifier (`npm install isnad`) checks audit records from JS —
verifier only; grading stays in the Python core.

## How it works

A claim passes through a chain of transmitters — a scraper, a model, a tool. ISNAD:

1. records the chain, in order;
2. grades each transmitter in a registry (rijāl), on integrity and precision;
3. caps the chain at its weakest link;
4. combines chain grade with content criticism in a decision matrix — serve, review, or quarantine;
5. exports the result as an audit record you can sign and verify.

## How it differs

Most tools grade the output; ISNAD grades the chain that produced it.

| Tool | What it grades | Records the chain (lineage)? | Grades the transmitters / chain? |
| --- | --- | --- | --- |
| Cleanlab TLM | Trustworthiness of the LLM response | No | No |
| Galileo / Patronus / TruLens / RAGAS | Output faithfulness vs retrieved context | No | No |
| LangSmith / Langfuse / Arize | Traces + output evals | Yes | No |
| OpenLineage / Marquez / DataHub | Data lineage | Yes | No |
| ISNAD | The transmitters and the chain — weakest-link grading, corroboration with madār discounting, tamper-detecting audit | Yes | Yes |

Three objections, answered up front:

1. "Tracers already record who handled it." They record the order; they don't grade each
   transmitter, propagate a weakest-link verdict, or gate on it.
2. "Your grades are operator-assigned, so it's garbage-in-garbage-out." Grades are priors +
   audited observations + corroboration, propagated by a documented method. ISNAD makes
   trust explicit and auditable; it doesn't auto-measure it, and it doesn't pretend to.
3. "Claim critics measure truth better than you." Correct — ISNAD composes with them. It
   grades the chain that carried the claim, not the claim's truth.

## What's validated and what isn't

| Component | Status | Notes |
| --- | --- | --- |
| Weakest-link quarantine | Validated | Every COMPROMISED-integrity chain grades MAWDU and is blocked; a SUSPECT narrator grades ḍaʿīf jiddan — both quarantine. The SUSPECT→ḍaʿīf jiddan path is exercised in the gated-vs-ungated experiment; the COMPROMISED→mawḍūʿ path is unit-tested. |
| ISNAD-Bench | Measured | κ = 0.871 (3-way) / 0.8667 (5-way, mapping v2, post-hoc) / 0.761 (lenient) vs 575,060 chains graded by a rule-based convention. κ is conformance, not agreement with scholars; narrator-grade agreement κ = 0.331 (a different task, not a ceiling); shuffled control −0.0066 |
| Corroboration (mutābaʿāt, shawāhid) | Validated | 603/603 Wikipedia + 104/104 physics matched pairs; 8/8 + 9/9 negative controls; requires attested distinct lineage |
| Chain-scoped grounding | Partial | Flags a claim grounded only off its own chain — evidence, not an action. Inert with the default critic (contradiction-only); false-positive rate not yet measured |
| Content-madār fingerprint calibration | Measured | FP 0.375 on independent agreement (down from 0.750), token-bearing recall 1.0; near-miss boundary separated (0/4 false positives) |
| Seed-grade bootstrapping | Validated | Evidence-backed `Registry.seed()`; coverage is critic-bound — the offline `EmbeddingCritic` serves 0% (contradiction-only), so the LLM critic is the ceiling |
| Content criticism | Partial | The main constraint. LLM critic 1.000 recall / 0.000 false-consistent on the 60-case eval, but 39.1% false-consistent on the gated-vs-ungated content corruption; offline critics recall 0.36–0.76 |
| jarḥ–taʿdīl discovery | Partial | Finds injected weak narrators; good narrators need seed grades |
| Bayesian grading | Default | Beta posterior per (narrator, role, domain) |
| Confidence-gating | Useless | Model self-confidence is uncorrelated with defects |
| Tamper-detecting audit | Implemented | Self-hash + detached signatures + Merkle log; tail-truncation and forger limits disclosed |
| Period-sliced grades | Implemented | `get_grade_as_of()` — the ikhtilāṭ (decline) remedy |
| Integrity ladder + recoverability | Implemented | Integrity strikes are permanent; precision-driven REJECTED is recoverable |

Grades are ordinal-only (ṣaḥīḥ > ḥasan > ḍaʿīf > ḍaʿīf jiddan > mawḍūʿ, never a numeric
confidence). Cold-start is worse per-role; integrity is domain-scoped, not global; chain
independence cannot be proven from topology — only assumed from attested lineage, then
discounted; correlated errors across model families (shared training data) cannot be
detected; the content critic is the coverage ceiling; corroboration rarely fires on dense
technical corpora where genuine cross-source overlap is rare; the serving index is
in-memory (single-node; multi-worker HA is not yet supported).
Resolving a review item records the human decision as oversight evidence; it does not
change narrator grades. To move a grade, submit evidence with `Registry.record_evidence()`
or `POST /v1/evidence`.

## Decision matrix

Chain grade × content verdict → action:

| | CONSISTENT | CONTRADICTION | UNVERIFIABLE |
| --- | --- | --- | --- |
| Ṣaḥīḥ (sound) | SERVE — cache | REVIEW — contradiction (highest-value case) | SERVE WITH CAVEAT |
| Ḥasan (good) | SERVE WITH CAVEAT | REVIEW — hold | REVIEW |
| Ḍaʿīf (weak) | REVIEW — seek corroboration | QUARANTINE | REVIEW |
| Ḍaʿīf jiddan (very weak) | QUARANTINE | QUARANTINE | QUARANTINE |
| Mawḍūʿ (fabricated) | REJECT + QUARANTINE NARRATOR | REJECT + QUARANTINE NARRATOR | REJECT + QUARANTINE NARRATOR |

Contradictions go to a human by default; ṣaḥīḥ × contradiction is the highest-value signal,
not an error state. Two serve-side gates apply on top (both demote, never promote): the
prior-only gate — a narrator graded from a population prior alone can SERVE WITH CAVEAT at
most (plain SERVE requires observation- or human-backed narrators) — and hold-mode
UNVERIFIABLE, on with `ISNAD_SERVE_GATE=hold` or `ISNAD_SERVE_HOLD_DOMAINS=medical,legal`.

## Audit records

```bash
isnad export --claim <id> --format json    # jsonl|csv; --verify; --sign; --redact; --chain-log
```

A record contains the full chain (a DAG via `upstream_ids`), the weakest link, source-document
hashes, human-oversight evidence, the environment, and a SHA-256 integrity hash over the
RFC 8785-canonical payload — plus an optional detached signature (HMAC/Ed25519), a hash
chain, and a PII-redaction hook. The API signs with HMAC only when `ISNAD_HMAC_SECRET` is
set; otherwise records are emitted `audit_signed: false` (a self-hash a forger can recompute).

Two logs — a linear hash chain and a Merkle batch log — detect modification, middle-deletion,
and reordering. Neither detects tail truncation, and both commit to a self-hash, so they
detect post-hoc modification, not a forger who rebuilds the chain.

ISNAD produces evidence artifacts; it does not confer conformity with any regulation. See
[docs/evidence-mapping.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/docs/evidence-mapping.md).

## Integrations

- LangChain / LangGraph — callback handler, tracer, middleware. The callback handler is the
  stable capture path; the AgentMiddleware wiring targets a forward-looking LangChain API.
- CrewAI / LlamaIndex — adapters
- OpenTelemetry — `isnad ingest --otlp` grades an existing GenAI trace
- MCP — grade MCP servers as narrators; tool narrators stay UNGRADED by default
- Live Verify — consume a `verify:` seal as a high-trust narrator (proves authenticity, not truth)
- Chain viewer — `viewer/index.html` renders chains in the browser

LangChain callback, in five lines:

```python
from isnad.integrations.langchain import IsnadCallbackHandler, seed_registry

reg = seed_registry({"source:docs": "reliable", "model:gpt-4o": "acceptable"})
handler = IsnadCallbackHandler(registry=reg, domain="physics")
chain.invoke("What is F=ma?", config={"callbacks": [handler]})
trace = handler.to_trace()  # isnad_trace v0.1 JSON
```

## Scope and limitations

ISNAD grades post-entry provenance — who handled a claim after it entered the pipeline, and
how much you trust them — not whether the upstream source or the final answer is true. It
covers ordered chains + grades, weakest-link grading + the decision matrix, content criticism
against your corpus, and corroboration. It does not cover:

- Source legitimacy at the boundary — grades are operator-assigned assertions, not
  auto-verified facts.
- Novel claim truth — new, unverifiable claims are not auto-fact-checked.
- Faithful transmission of bad input — a RELIABLE fake publisher + a clean pipeline can
  still yield a high chain grade.

Boundary vetting is the operator's responsibility: vet sources before registering them as
RELIABLE; register unknowns as UNGRADED; use matn, corroboration, and human review as
downstream gates, not a replacement for it.

## Glossary

| Term | Meaning |
| --- | --- |
| isnād | The transmission chain — who handled a claim, in order |
| rijāl | The registry of transmitters and their grades |
| jarḥ–taʿdīl | The criticism-and-accreditation loop that moves grades with evidence |
| ʿadālah | Integrity — can this transmitter be trusted not to lie? |
| ḍabṭ | Precision — how often is this transmitter accurate? |
| ittiṣāl | Chain continuity (no gaps) |
| mutābaʿāt / shawāhid | Corroboration: other routes that agree with a claim, through the same source (mutābaʿāt) or a different one (shawāhid). ISNAD counts only routes with attested distinct lineage. |
| madār | The common link where chains converge: "independent" chains that actually share an upstream |
| matn | The claim content, criticized separately from the chain |
| ṣaḥīḥ / ḥasan / ḍaʿīf / ḍaʿīf jiddan / mawḍūʿ | Sound / good / weak / very weak / fabricated |
| ʿilal | Hidden defects that survive surface grading — not implemented; routed to review |
| contradiction (taʿāruḍ) | A sound chain whose content contradicts the corpus — routed to review |

## Research

**Paper:** [arXiv:2607.24117](https://arxiv.org/abs/2607.24117) · **Software DOI:** [10.5281/zenodo.21216872](https://doi.org/10.5281/zenodo.21216872)

**ISNAD-Bench.** ISNAD's weakest-link chain grading conforms to a rule-based grading
convention derived from Ibn Hajar's 12 narrator tiers at Cohen's κ = 0.871 (strict default),
across 575,060 chains, with a shuffled-rank control at κ = −0.0066. ISNAD conforms to the
rule-based convention; it is not "better than the scholars." The narrator-grade agreement —
how contested the underlying tiers are — is κ = 0.331; the 0.331 is narrator-grade context,
not a ceiling. The 5-way 0.8667 (mapping v2) is post-hoc. Full write-up:
[bench/docs/RESULTS.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/bench/docs/RESULTS.md).

**Transfer to AI pipelines.** On RAGTruth, the grounding critic ISNAD composes with transfers
at κ = 0.4345 over all 1,800 responses (57 unparseable, 3.2%, scored fail-closed) — 96.0%
hallucination recall at 60.4% precision, a 49.9% false-positive rate on grounded responses,
vs a 55.8% majority-class baseline. That number belongs to the composed critic, not to chain
grading. The weak bi-encoder signal (κ ≈ 0.1) is reported alongside. Case study:
[G1_CASE_STUDY.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/G1_CASE_STUDY.md).

**Datasets:** [alizahidraja/isnad-bench](https://huggingface.co/datasets/alizahidraja/isnad-bench)
· each folder under [experiments/](https://github.com/alizahidraja/isnad/tree/v3.2.0/experiments/) has its own RESULTS.md.

## Contributing and security

[CONTRIBUTING.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/CONTRIBUTING.md) · [CODE_OF_CONDUCT.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/CODE_OF_CONDUCT.md) ·
[SECURITY.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/SECURITY.md) · [THREAT_MODEL.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/THREAT_MODEL.md)

## Citation

```bibtex
@article{raja2026grading,
  author  = {Ali Zahid Raja},
  title   = {Grading the Narrators: An Isnād–Rijāl Framework for
             Claim-Level Provenance in Multi-Agent Knowledge Systems},
  year    = 2026,
  doi     = {10.48550/arXiv.2607.24117},
  eprint  = {2607.24117},
  archivePrefix = {arXiv},
}
```

## License and author

Code: Apache 2.0 (see [LICENSING.md](https://github.com/alizahidraja/isnad/blob/v3.2.0/LICENSING.md)) · Paper & docs: CC BY 4.0. The core
(`src/isnad/`) stays Apache-2.0.

Built by [Ali Zahid Raja](https://alizahidraja.com) · ORCID [0009-0003-7875-4590](https://orcid.org/0009-0003-7875-4590).
The method belongs to fourteen centuries of muḥaddithūn; the transfer to AI systems is the
contribution claimed here.
