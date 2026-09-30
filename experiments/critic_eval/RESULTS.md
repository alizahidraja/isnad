# Content Critic Evaluation — committed results (issue #96)

**Corpus:** 30 physics facts · **Cases:** 60 (20 consistent, 25 contradiction, 15 unrelated)

| Critic | Contra. recall | Contra. precision | Contra. F1 | False-consistent (danger) | False-contradiction | 3-way acc |
|---|---|---|---|---|---|---|
| EmbeddingCritic (TF-IDF) | 0.120 | 1.000 | 0.214 | 0.000 | 0.000 | 0.300 |
| LocalNLICritic (DeBERTa NLI) | 0.760 | 0.633 | 0.691 | 0.000 | 0.050 | 0.417 |
| HybridCritic (MiniLM → NLI) | 0.720 | 0.667 | 0.692 | 0.040 | 0.000 | 0.433 |
| LLMCritic (DeepSeek) | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 |

## Re-run status (honest)

- **EmbeddingCritic** re-run this sweep (offline, deterministic): the
  contradiction-only change is confirmed — **false-consistent 0.32 → 0.000**
  (it can no longer affirm consistency, so it can no longer bless a contradiction).
- **LocalNLI / Hybrid** rows preserve the prior committed numbers; the NLI models
  (DeBERTa ~500MB / MiniLM) were not re-downloaded in this environment. To reproduce:
  `uv run python experiments/critic_eval/run.py` with the models available.
- **LLMCritic** row preserves the prior committed run; it requires `DEEPSEEK_API_KEY`.

## Reading the numbers

- **Contradiction recall** — of the genuine contradictions, how many were flagged.
- **False-consistent rate** — contradictions *mislabeled* CONSISTENT (the dangerous error).
- **False-contradiction rate** — consistent claims flagged as contradictions.
- **3-way accuracy** — exact match across consistent/contradiction/unrelated.
