"""Three agents, one degrades — and the audit record names it.

A handoff chain: a reliable retriever, a reliable synthesis model, and a
*degraded* summariser.  The weakest-link grading caps the chain at the degraded
link, and the AuditRecord's `weakest_link` field identifies it — surfacing
*where* a chain degraded, not just that it did.

Run:  python examples/multi_agent_handoff.py
"""

from __future__ import annotations

import tempfile

from sqlalchemy.orm import Session

from isnad.audit import build_audit_record
from isnad.core.chain import (
    Chain,
    ChainLinkSpec,
    hash_claim_text,
    normalize_claim_text,
    store_claim,
)
from isnad.core.registry import Registry
from isnad.storage.sqlalchemy import create_engine_from_url, init_db, reset_engine
from isnad.types import NarratorGrade, NarratorType


def main() -> None:
    print("=" * 68)
    print("Three agents, one degrades")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{d}/isnad.db"
        reset_engine()
        init_db(url)
        engine = create_engine_from_url(url)

        reg = Registry()
        reg.register(
            "agent:retriever",
            "general",
            grade=NarratorGrade.RELIABLE,
            narrator_type=NarratorType.SCRAPER,
        )
        reg.register(
            "agent:synthesis",
            "general",
            grade=NarratorGrade.RELIABLE,
            narrator_type=NarratorType.MODEL,
        )
        # The degraded link: a summariser that drops to WEAK.
        reg.register(
            "agent:summariser",
            "general",
            grade=NarratorGrade.WEAK,
            narrator_type=NarratorType.MODEL,
        )

        chain = Chain([
            ChainLinkSpec("agent:retriever", 0, domain="general"),
            ChainLinkSpec("agent:synthesis", 1, domain="general"),
            ChainLinkSpec("agent:summariser", 2, domain="general"),
        ])

        with Session(engine) as session:
            store_claim(
                session, "water freezes at 0 degrees Celsius", "general", chain, chain_grade="daif"
            )
            session.commit()
            claim_id = hash_claim_text(normalize_claim_text("water freezes at 0 degrees Celsius"))
            record = build_audit_record(claim_id, session, reg)

        print(f"\nfinal chain grade: {record.final_grade}")
        print(f"weakest link: {record.weakest_link.narrator_id}")
        print(f"why: {record.weakest_link.why}")
        print("\nper-link grades:")
        for node in record.chain:
            print(f"  {node.narrator_id:20} -> {node.grade}")

        print("\nThe degraded link is named, not just the degradation.")
        reset_engine()

    print("\n" + "=" * 68)
    print("Done.")
    print("=" * 68)


if __name__ == "__main__":
    main()
