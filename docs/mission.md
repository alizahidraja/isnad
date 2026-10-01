# ISNAD's mission — a WHO-graded registry (not a "who's-truthful" score)

This is the public-facing goal that replaces the "global factual-reliability registry" idea.
It's the thing people can relate to, argue with, and measure against.

## The mission (one line)

> **A shared registry of *who you can trust* across AI agents — graded by transmission
> reliability, never by how "true" their output looks.**

## Why this framing (and not the other one)

The tempting version is "a global scoreboard of which models are factually reliable"
(GPT-4o = X, Llama-3 = Y). We are **not** building that, because:

1. **It grades WHETHER, not WHO.** "Factually reliable" is a truth claim about a model.
   ISNAD's whole thesis is that truth is the *critic's* job, not the *provenance layer's*.
2. **It's numeric.** A "reliability score" is the fake numeric confidence ISNAD refuses
   (ordinal-only: ṣaḥīḥ > ḥasan > ḍaʿīf > mawḍūʿ).
3. **It's circular.** Grading a narrator by how confidently its *output* reads is exactly
   the content-inferred trust that Nous (2606.22030) proved is gameable (a confidently-
   phrased poison earns 0.96).

## The registry ISNAD actually wants

An **ordinal, per-(narrator, domain), version-bump-resetting** registry of *transmission*
reliability:
- who relayed what, in what order, with what transform,
- graded by attested lineage + corroboration + content-madār (shared-error fingerprint),
- **never** a global "truthfulness" number — a narrator's grade is scoped to a domain and
  resets to UNGRADED on a new model version.

## What "winning" looks like (the audience's reaction)

- A fine-tuned Llama-3 answers confidently but keeps dropping its *source* → its **WHO**
  grade drops, and ISNAD says *why* (ordinal, with provenance) — not "it's 0.83 reliable."
- Two "independent" agents turn out to share an upstream → content-madār flags the shared
  error, and the corroboration is discounted — the registry catches the *hidden pivot*,
  not the confident answer.

## The honest status

This is a **mission**, not a shipped feature. The primitive (per-(narrator, domain) ordinal
registry + jarḥ–taʿdīl loop) ships today; the *shared* registry is a roadmap goal. Say so —
the audience respects a mission that's honest about what exists vs. what's next.
