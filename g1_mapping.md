# G1 Moat-Gate — Preregistered Mapping (AI-provenance transfer)

> **Status:** RESULTS COMPUTED — post-hoc addendum (2026-09-11).
> The preregistered v1.1 bi-encoder signal scored weak (κ 0.099 at threshold 0.5).
> A v2 LLM grounding critic (DeepSeek V4 Flash) — NOT in the original preregistration —
> was then tried and scored κ = 0.4345 over ALL 1,800 responses (57 unparseable, 3.1%, fail-closed as hallucinated); recall 96.0%, precision 60.4%, 49.9% false-positive on grounded.
> Disclosed, not hidden: the headline result is post-hoc, not preregistered.

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

- **v1 bi-encoder (preregistered, weak κ ≈ 0.1):** `uv run python experiments/g1/run_g1.py` (needs `isnad[nli]` + the RAGTruth dataset).
- **v2 LLM critic (post-hoc, κ = 0.4345 over all 1,800):** `DEEPSEEK_API_KEY=… uv run python experiments/g1/g1_llm.py` — dataset from `github.com/ParticleMedia/RAGTruth` into `experiments/g1/ragtruth/dataset/` (or set `RAGTRUTH_DATA_DIR`).
