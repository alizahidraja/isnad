# Content Critic Evaluation

**Date:** 2026-07-07
**Eval set:** 20 labeled claims (50% consistent, 50% template-injected contradictions)

## Results

| Critic | Precision | Recall | F1 | False-Consistent | Accuracy |
|---|---|---|---|---|---|
| deterministic-stub | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 |
| embedding-word-overlap | 1.000 | 1.000 | 1.000 | 0.000 | 1.000 |

## Interpretation

The 100% scores are on **template-injected contradictions** — claims with
obvious negation or opposite-word patterns that both the stub and embedding
critic catch trivially. This is NOT representative of real-world contradiction
detection performance.

**These numbers overstate real capability.** The deterministic stub achieves
100% here because the eval contradictions were built from its own hardcoded
pattern list (e.g., "is" vs "is not"). The embedding critic catches them
because word-overlap similarity + negation heuristic fires on the templates.

A real evaluation requires:
- **A labeled corpus of genuine physics contradictions** (does not exist)
- **Real model-induced errors** (not template injections)
- **Diverse domains** beyond physics
- **LLM critic comparison** (requires API key, not run here)

## Limitations

- **Template contradictions only** — 10 hand-written pairs, obvious contrasts.
- **No real model errors** — real ingest/generation faults are more subtle.
- **Single domain** — physics only.
- **Embedding critic** uses word-overlap, not semantic embeddings.
- **LLM critic not evaluated** — requires API key and is cost-gated.
- **Small eval set** (20 claims) — insufficient for statistical confidence.
- **No false-consistent test on subtle errors** — the dangerous case
  where a claim is wrong but looks plausible isn't tested.

## Recommendation

For practical deployment: the embedding critic provides a reasonable baseline
for catching obvious contradictions (negations, opposite terms, large numeric
divergences). It will MISS subtle contradictions where the vocabulary differs.

**Safe to use for obvious contradiction detection. Not safe as the sole
gate for auto-serving HASAN claims in production.** Use with human review
for high-stakes claims, or pair with an LLM-backed critic for better coverage.

The deterministic stub should NOT be used on real text — it only matches
its hardcoded pattern list and returns UNVERIFIABLE for everything else.
It exists for testing and offline demonstration only.
