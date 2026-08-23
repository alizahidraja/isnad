"""CI gate — fail a build when a claim's chain grade drops below a threshold.

Run from CI: any claim graded below the threshold (default ``hasan``) fails the
build with a non-zero exit code and a human-readable reason on stderr.

Usage:
    python examples/ci_gate.py --claim <id> [--min-grade hasan]
    python examples/ci_gate.py --self-test   # run against an in-memory claim

This is a *gate on grades*, not a security boundary — it fails loudly so a
human looks, it does not silently block a deployment.
"""

from __future__ import annotations

import argparse
import sys
import tempfile

from sqlalchemy.orm import Session

from isnad.core.chain import Chain, ChainLinkSpec, store_claim
from isnad.core.grading import grade_chain
from isnad.core.registry import Registry
from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine
from isnad.types import ChainGrade, NarratorGrade

# Ordinal order, worst → best (so we can compare).
_ORDER = {
    ChainGrade.MAWDU: 0,
    ChainGrade.DAIF: 1,
    ChainGrade.HASAN: 2,
    ChainGrade.SAHIH: 3,
}


def _grade_from_registry(chain: Chain, reg: Registry) -> ChainGrade:
    grades = [reg.get_grade_for_link(l.narrator_id, l.domain, l.version) for l in chain.links]
    return grade_chain(
        grades, [l.transform_type for l in chain.links], is_complete=chain.is_complete
    )


def _self_test() -> int:
    """Build an in-memory claim with a weak narrator and gate it."""
    reg = Registry()
    reg.register("source", "general", grade=NarratorGrade.RELIABLE)
    reg.register("model", "general", grade=NarratorGrade.WEAK)
    chain = Chain([
        ChainLinkSpec("source", 0, domain="general"),
        ChainLinkSpec("model", 1, domain="general"),
    ])
    grade = _grade_from_registry(chain, reg)
    print(f"self-test chain grade: {grade.value}")
    return 0 if _ORDER[grade] >= _ORDER[ChainGrade.HASAN] else 1


def _gate_claim(claim_id: str, min_grade: ChainGrade) -> int:
    from isnad.core.chain import get_chain_from_db

    registry = Registry()
    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{d}/gate.db"
        reset_engine()
        init_db(url)
        engine = create_engine_from_url(url)
        with Session(engine) as session:
            chain = get_chain_from_db(session, claim_id)
            if chain is None:
                print(f"claim {claim_id!r} not found", file=sys.stderr)
                return 1
            grade = _grade_from_registry(chain, registry)
        reset_engine()

    print(f"claim {claim_id} chain grade: {grade.value}")
    if _ORDER[grade] < _ORDER[min_grade]:
        print(
            f"GATE FAILED: {grade.value} < {min_grade.value}",
            file=sys.stderr,
        )
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail a build when a chain grade drops below a threshold."
    )
    parser.add_argument("--claim", help="stored claim id")
    parser.add_argument("--min-grade", default="hasan", help="minimum acceptable chain grade")
    parser.add_argument("--self-test", action="store_true", help="run against an in-memory claim")
    args = parser.parse_args()

    min_grade = ChainGrade(args.min_grade)
    if args.self_test:
        sys.exit(_self_test())
    if not args.claim:
        parser.error("--claim is required (or use --self-test)")
    sys.exit(_gate_claim(args.claim, min_grade))


if __name__ == "__main__":
    main()
