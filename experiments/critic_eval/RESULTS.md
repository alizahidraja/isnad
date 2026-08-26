# Content Critic Evaluation — committed results (issue #96)

**Corpus:** 30 physics facts · **Cases:** 60 (20 consistent, 25 contradiction, 15 unrelated)

| Critic | Contra. recall | Contra. precision | Contra. F1 | False-consistent (danger) | False-contradiction | 3-way acc |
|---|---|---|---|---|---|---|
| EmbeddingCritic (TF-IDF) | 0.120 | 1.000 | 0.214 | 0.320 | 0.000 | 0.550 |
| LocalNLICritic (DeBERTa NLI) | 0.120 | 0.750 | 0.207 | 0.880 | 0.000 | 0.383 |
| HybridCritic (MiniLM → NLI) | 0.160 | 0.667 | 0.258 | 0.840 | 0.050 | 0.383 |
| LLMCritic (DeepSeek) | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 |

## Reading the numbers

- **Contradiction recall** — of the genuine contradictions, how many were flagged.
  This is the headline "semantic recall" the docs quote.
- **False-consistent rate** — contradictions *mislabeled* CONSISTENT. This is the
  dangerous error: a wrong claim served as if correct.
- **False-contradiction rate** — consistent claims flagged as contradictions
  (wasted review, not a safety failure).
- **3-way accuracy** — exact match across consistent/contradiction/unrelated.

The offline critics (Embedding / LocalNLI / Hybrid) are deterministic; the
LLM critic was run once with `temperature=0`. Results are committed so the
numbers in `docs/critics.md` are measured, not estimated.
