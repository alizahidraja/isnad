# G1 Moat-Gate — Preregistered Mapping (AI-provenance transfer)

> **Status:** DRAFT v1.1 — updated BEFORE the first result is computed.
> v1.0 used the NLI cross-encoder; v1.1 switches the grounding signal to the
> bi-encoder cosine similarity because the cross-encoder is not CPU-feasible on
> the deployment box. No result has been computed under either version.

## 1. Data provenance

| Field | Value |
|---|---|
| Corpus | RAGTruth (Niu et al., ACL 2024) — `github.com/ParticleMedia/RAGTruth` |
| License | MIT (repo LICENSE) |
| Files | `dataset/response.jsonl` (17,790 responses) + `dataset/source_info.jsonl` (source docs) |
| Models | gpt-4-0613, gpt-3.5-turbo-0613, mistral-7B-instruct, llama-2-7b-chat, llama-2-13b-chat, llama-2-70b-chat (2,965 each) |
| Gold label | response-level hallucination: any span in `labels` ⇒ hallucinated, else grounded |

## 2. The mapping (preregistered)

**Claim** = one sentence of a model response (regex split, min 10 chars).

**Chain** = `[source_doc (SOURCE)] → [model (MODEL)]`. The source doc is the claim's
own on-chain evidence (operator boundary vetting).

**Narrator grades:**

| Narrator | Grade rule (non-circular — a semantic grounding signal, not the gold label) |
|---|---|
| `source_doc` | **RELIABLE** if `cosine(embed(source_doc), embed(sentence)) >= 0.5`, else **WEAK** |
| `model` | **RELIABLE** (faithful transmitter; the test isolates source-grounding) |

Embeddings: `all-MiniLM-L6-v2` (the same bi-encoder lineage as ISNAD's embedding critic),
L2-normalized.

**Weakest-link:** a response is predicted **hallucinated** iff its MINIMUM
sentence grounding similarity is below the threshold (any weak sentence caps the
chain). Primary threshold **0.5**, with a sweep [0.3, 0.4, 0.5, 0.6] reported for
transparency (no post-hoc threshold selection for the headline number).

## 3. Metrics (preregistered)

- Primary: **Cohen's κ** (response-level) at threshold 0.5, plus accuracy, precision/recall/F1 on the hallucinated class.
- Baselines: **majority class** (always-grounded).
- Secondary: per-model truth vs predicted hallucination rate.

## 4. Honest limits (stated up front)

- Semantic **similarity** is a proxy for entailment, not entailment itself; it is not truth verification.
- Single-source grounding only (no multi-source corroboration).
- Sentence-level granularity is coarser than RAGTruth's span labels; bi-encoder truncates long sources.

## 5. Reproduction

`docker run --rm -v /opt/isnad/g1:/g1 -w /g1 isnad-api python /g1/run_g1.py`
