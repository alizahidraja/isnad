"""ISNAD φ study — corpus builder.

Builds ~393 facts: ~385 hard numeric facts (``corpus_hard.HARD_FACTS``) + the 8
post-cutoff facts from the model-drift ``HARD_CORPUS`` (ids ``md_pcXX`` kept stable
so the drift study stays comparable).

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
from experiments.model_drift.corpus_hard import HARD_CORPUS


def build() -> list[dict[str, object]]:
    out: list[dict[str, object]] = build_hard()
    for f in HARD_CORPUS:
        if f.tier != "postcutoff":
            continue
        if getattr(f, "excluded", False):
            continue
        out.append({
            "id": f"md_{f.fact_id}",
            "claim_text": f.question,
            "oracle_value": f.correct_value,
            "oracle_unit": "",
            "source": "model_drift_postcutoff",
            "domain": "postcutoff",
            "source_note": (
                "post-cutoff event outcome; oracle = documented result from the "
                "model_drift HARD_CORPUS (each outcome verified in the drift study, "
                "not fabricated)"
            ),
        })
    return out


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
