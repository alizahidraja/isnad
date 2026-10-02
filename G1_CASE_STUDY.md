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
| **Cohen's κ** | **0.4345** |
| Accuracy | 70.3% (majority-class baseline 55.8%) |
| Precision (halluc.) | 60.4% |
| Recall (halluc.) | 96.0% |
| F1 (halluc.) | 74.1% |

**Verdict:** the grounding critic ISNAD composes with (its matn layer) transfers at κ = 0.4345
(moderate agreement) over **all 1,800** RAGTruth responses — 96.0% hallucination recall at 60.4% precision.
(Fail-closed: 57 unparseable responses, 3.1%, are scored as hallucinated, not dropped.)

**Known limitation:** 55 responses (3.1%) returned no parseable verdict and are scored
fail-closed as hallucinated. The **49.9% false-positive rate on grounded responses
(501/1,005)** sits beside the 96.0% recall — the decision matrix holds those, so the cost
is review, not a wrong serve. This is the honest cost of a high-recall grounding critic.

## The narrator-grading signal (ISNAD's core) — rank-orders models, but over-flags

The critic's predicted hallucination rate rank-orders the six models roughly right
(4/6 exact; the near-tied bottom two — mistral vs llama-2-7b — are swapped), but it
systematically **over-flags**: predicted rates are 1.3–3.4× the true rates (the 49.9%
false-positive on grounded responses, above).

| Model | Truth | LLM-critic predicted |
|---|---|---|
| gpt-4-0613 | 12.3% | 42.0% |
| gpt-3.5-turbo-0613 | 16.0% | 46.3% |
| llama-2-70b-chat | 46.0% | 76.3% |
| llama-2-13b-chat | 57.0% | 84.0% |
| llama-2-7b-chat | 66.3% | 89.3% |
| mistral-7B-instruct | 67.3% | 85.3% |

Used as registry evidence (benchmark-accuracy → narrator grade bands), the critic's
over-flagged rates would **REJECT all six models**; the true rates put GPT-4 (12.3%) and
GPT-3.5 (16.0%) at ACCEPTABLE.

## Overall verdict (G1 gate)

**The LLM grounding critic transfers at κ = 0.4345 — a moderate signal with a real false-positive cost.**
It does not clear the κ ≥ 0.8 "company-path" bar yet, but it is a usable high-recall/low-precision screening signal
and a strong, honest first case study. Next lever: reduce the false-positive rate on
grounded responses, or license affirmation through a clean eval set (the 49.9% FP cost
is the real blocker, not parse loss).
