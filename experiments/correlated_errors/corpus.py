"""ISNAD φ study — corpus.

The oracle source is the model-drift ``HARD_CORPUS`` (64 facts after pc09's
exclusion): 56 well-known facts (models answer correctly — the agreement control)
+ 8 post-cutoff facts (models err 50–75% — the error signal φ is computed on).

The §8 ``claims.json`` extraction is NOT a clean oracle source (textbook prose,
citations, list numbers), so it is deliberately excluded. Expanding the hard-facts
subset toward ~400 (synthetic recent/obscure facts) is a follow-up step before the
full sweep; the scaffold uses the 64 clean facts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from experiments.model_drift.corpus_hard import HARD_CORPUS  # noqa: E402


def build() -> list[dict[str, str]]:
    out = []
    for f in HARD_CORPUS:
        if getattr(f, "excluded", False):
            continue
        out.append(
            {
                "id": f"md_{f.fact_id}",
                "claim_text": f.question,
                "oracle_value": f.correct_value,
                "oracle_unit": "",
                "domain": f.tier,
            }
        )
    return out


def main() -> None:
    corpus = build()
    out_path = _HERE / "corpus.json"
    out_path.write_text(json.dumps(corpus, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(corpus)} facts to {out_path} "
          f"({sum(1 for c in corpus if c['domain'] == 'postcutoff')} post-cutoff)")


if __name__ == "__main__":
    main()
