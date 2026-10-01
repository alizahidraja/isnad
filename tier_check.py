import sqlite3, collections
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
