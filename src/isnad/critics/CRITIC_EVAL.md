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
| --- | --- | --- | --- |
| `LLMCritic` (DeepSeek) | 1.000 | 0.000 | 1.000 |
| `LocalNLICritic` | 0.760 | 0.000 | 0.417 |
| `HybridCritic` | 0.720 | 0.040 | 0.433 |
| `EmbeddingCritic` | 0.120 | **0.000** (never affirms) | — |

(The NLI critics were fixed in issue 110 — swapped label order, raw logits vs
probability thresholds, and max-over-whole-corpus false positives — which took
them from 84–88% false-consistent to ~0%. The `EmbeddingCritic` was later made
contradiction-ONLY, so its false-consistent is 0.000 *by construction*, not by
measurement — see `docs/critics.md`.)

The earlier "deterministic-stub 100% / embedding 100%" table in this file was
measured on template-injected contradictions the critics were written to catch,
and is **retracted** — it overstated real capability. See
`docs/critics.md` for the honest hierarchy and the follow-up on the NLI
false-consistent failure.
