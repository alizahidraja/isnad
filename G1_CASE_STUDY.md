# G1 Transfer Test — Case Study (RAGTruth)

**Does ISNAD's source-grounding transfer to AI hallucination detection?** Two signals, honest results.

## The question

Can "grade who transmitted the claim" detect when an LLM fabricates content not
present in its source? Corpus: RAGTruth (17,790 responses, 6 models, span-level
hallucination labels). Sample: stratified by model, seed 0.

## v1 — bi-encoder cosine (cheap, local)

`all-MiniLM-L6-v2` similarity between each sentence and its source; weakest-link over sentences.

| Threshold | Cohen's κ | Accuracy |
|---|---|---|
| 0.3 (best) | 0.215 | 59.7% |
| 0.5 (preregistered) | 0.099 | 51.3% |

**Verdict:** too weak — semantic similarity is not entailment, and long sources get truncated.

## v2 — LLM grounding critic (DeepSeek V4 Flash)

A strict grounding judge: *"is this response fully grounded in its source?"*

| Metric | Value |
|---|---|
| **Cohen's κ** | **0.433** |
| Accuracy | 70.3% (majority-class baseline 55.8%) |
| Precision (halluc.) | 60.2% |
| Recall (halluc.) | 96.2% |
| F1 (halluc.) | 74.1% |

**Verdict:** the grounding critic ISNAD composes with (its matn layer) transfers at κ = 0.433
(moderate agreement) over **all 1,800** RAGTruth responses — 96.2% hallucination recall at 60.2% precision.
(Fail-closed: 55 unparseable responses, 3.1%, are scored as hallucinated, not dropped.)

**Known limitation:** 55 responses (3.1%) returned no parseable verdict and are scored
fail-closed as hallucinated. The **50.2% false-positive rate on grounded responses
(505/1,005)** sits beside the 96.2% recall — the decision matrix holds those, so the cost
is review, not a wrong serve. This is the honest cost of a high-recall grounding critic.

## The narrator-grading signal (ISNAD's core) — transfers cleanly

Measured response-level hallucination rates rank the six models in the right order
(4/6 exact; the bottom two — mistral vs llama-2-7b, near-tied at 63.7% vs 63.0% — are swapped):

| Model | Truth | LLM-critic predicted |
|---|---|---|
| gpt-4-0613 | 7.7% | 20.0% |
| gpt-3.5-turbo-0613 | 11.0% | 22.3% |
| llama-2-70b-chat | 41.7% | 60.0% |
| llama-2-13b-chat | 53.3% | 70.7% |
| llama-2-7b-chat | 63.0% | 76.0% |
| mistral-7B-instruct | 63.7% | 73.3% |

## Overall verdict (G1 gate)

**The LLM grounding critic transfers at κ = 0.433 — a moderate signal with a real false-positive cost.**
It does not clear the κ ≥ 0.8 "company-path" bar yet, but it is a usable detector
and a strong, honest first case study. Next lever: fix the parse losses + try
`deepseek-v4-pro` on the hard cases.
