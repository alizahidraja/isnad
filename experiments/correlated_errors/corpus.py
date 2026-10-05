"""ISNAD φ study — corpus builder.

Builds 378 hard numeric facts (``corpus_hard.HARD_FACTS``). The 8 post-cutoff
``md_pcXX`` facts from the model-drift ``HARD_CORPUS`` were DROPPED (2026-10-05,
post-audit): their oracles were fabricated/unverifiable (e.g. "Knicks most recent
championship" oracle ``2026`` but the real answer is 1973) and violate the
corpus's fixed-verifiable-oracle contract. See ``PREREGISTRATION.md`` (corrections).

The oracle for every fact is a single canonical number; the question asks for it
directly so the runner can parse exactly one answer number.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from experiments.correlated_errors.corpus_hard import build_hard


def build() -> list[dict[str, object]]:
    return build_hard()


def main() -> None:
    corpus = build()
    out_path = _HERE / "corpus.json"
    out_path.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    domains: dict[str, int] = {}
    for c in corpus:
        domains[str(c["domain"])] = domains.get(str(c["domain"]), 0) + 1
    print(f"wrote {len(corpus)} facts to {out_path}")
    for d, n in sorted(domains.items()):
        print(f"  {d}: {n}")


if __name__ == "__main__":
    main()
