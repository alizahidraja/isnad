# Content Critic Evaluation

**Committed results — `experiments/critic_eval/` (issue #96).**

The committed eval set is `experiments/critic_eval/eval_set.py` — a 30-fact
physics corpus plus 60 hand-labeled cases (20 consistent, 25 genuine
contradiction, 15 unrelated), with contradictions that are *diverse* (wrong
relationships, wrong magnitudes, negation, regime confusion) rather than the
template word-swaps this earlier file's 100%-on-templates numbers were based on.

Run it with:

```bash
DEEPSEEK_API_KEY=sk-... python experiments/critic_eval/run.py
```

Measured numbers (deterministic for the offline critics; LLM at temperature 0):

| Critic | Contra. recall | False-consistent (danger) | 3-way acc |
|---|---|---|---|
| `LLMCritic` (DeepSeek) | 1.000 | 0.000 | 1.000 |
| `EmbeddingCritic` | 0.120 | 0.320 | 0.550 |
| `HybridCritic` | 0.160 | 0.840 | 0.383 |
| `LocalNLICritic` | 0.120 | 0.880 | 0.383 |

The earlier "deterministic-stub 100% / embedding 100%" table in this file was
measured on template-injected contradictions the critics were written to catch,
and is **retracted** — it overstated real capability. See
`docs/critics.md` for the honest hierarchy and the follow-up on the NLI
false-consistent failure.
