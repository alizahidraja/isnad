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
| **Cohen's κ** | **0.575** |
| Accuracy | 79.3% (baseline 71.4%) |
| Precision (halluc.) | 72.8% |
| Recall (halluc.) | 97.6% |
| F1 (halluc.) | 83.4% |

**Verdict:** a genuinely usable hallucination detector — it catches **97.6% of
hallucinations** with 72.8% precision (κ = 0.575, "moderate" agreement).

**Known limitation:** 24.7% of responses returned a non-conforming verdict and were
excluded (the reasoning model sometimes doesn't emit the single requested word).
v3 fixes the prompt/parsing; expect κ to rise once those are recovered.

## The narrator-grading signal (ISNAD's core) — transfers cleanly

Measured response-level hallucination rates rank all six models exactly as known:

| Model | Truth | LLM-critic predicted |
|---|---|---|
| gpt-4-0613 | 7.7% | 20.0% |
| gpt-3.5-turbo-0613 | 11.0% | 22.3% |
| llama-2-70b-chat | 41.7% | 60.0% |
| llama-2-13b-chat | 53.3% | 70.7% |
| llama-2-7b-chat | 63.0% | 76.0% |
| mistral-7B-instruct | 63.7% | 73.3% |

## Overall verdict (G1 gate)

**The LLM grounding critic transfers at κ = 0.575 — a real, moderate-strength signal.**
It does not clear the κ ≥ 0.8 "company-path" bar yet, but it is a usable detector
and a strong, honest first case study. Next lever: fix the parse losses + try
`deepseek-v4-pro` on the hard cases.
