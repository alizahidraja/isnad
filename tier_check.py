"""tier_check.py — ISNAD-Bench ground-truth provenance check (paper v2, Blocker 1).

Answers: are the `sanads.hukum` chain verdicts a pure function of the weakest
narrator tier (max_rank)? Pins the benchmark DB at SHA-256
d528084321e715006712e0e2461809a3afc9408065a1d1af90238c8b723815a6.

Result (2026-10-01): per-tier purity 0.876–0.968 — the weakest tier strongly but
NOT purely predicts the verdict (a pure template would be >= 0.99 at every tier).
The verdicts are largely rule-generated from Ibn Hajar's 12 tiers, with a 3–12%
residual that follows richer flags (gap, tadlis, ikhtilat), not independent
per-chain scholarly judgment. Hence v2 frames kappa = 0.871 as "conformance to a
rule-based grading convention at scale", not "agreement with scholars' verdicts".

Run:  uv run python tier_check.py   (requires data/hadith-kg.db downloaded)
"""

import collections
import sqlite3

from bench.mapping import chain_grade_from_hukum

db = sqlite3.connect("data/hadith-kg.db")
tab = collections.defaultdict(collections.Counter)
for rank, hukum in db.execute("SELECT max_rank, hukum FROM sanads WHERE max_rank < 12"):
    g = chain_grade_from_hukum(hukum)
    tab[rank][g.value if g else "unclassified"] += 1
for rank in sorted(tab):
    n = sum(tab[rank].values())
    top, k = tab[rank].most_common(1)[0]
    print(rank, n, top, round(k / n, 4), dict(tab[rank]))
