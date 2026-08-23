"""RAG chain → AuditRecord → verify — the audit evidence layer end-to-end.

No API keys, no LangChain runtime required: the "LLM" is a deterministic stub.
Builds a two-link chain (a source and a synthesis model), stores the claim,
exports a tamper-evident AuditRecord, then verifies its integrity.

Run:  python examples/audit_export_langchain.py
"""

from __future__ import annotations

import json
import tempfile

from sqlalchemy.orm import Session

from isnad.audit import build_audit_record
from isnad.audit.canonical import canonical_hash
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
    print("RAG chain → AuditRecord → verify")
    print("=" * 68)

    with tempfile.TemporaryDirectory() as d:
        url = f"sqlite:///{d}/isnad.db"
        reset_engine()
        init_db(url)
        engine = create_engine_from_url(url)

        # A deterministic "LLM" stub: the chain narrators.
        reg = Registry()
        reg.register(
            "source:openstax",
            "physics",
            grade=NarratorGrade.RELIABLE,
            narrator_type=NarratorType.SOURCE,
        )
        reg.register("model:gpt-stub", "physics", grade=NarratorGrade.ACCEPTABLE)

        chain = Chain([
            ChainLinkSpec("source:openstax", 0, domain="physics"),
            ChainLinkSpec("model:gpt-stub", 1, domain="physics"),
        ])

        with Session(engine) as session:
            store_claim(
                session,
                "force equals mass times acceleration",
                "physics",
                chain,
                chain_grade="hasan",
            )
            session.commit()
            claim_id = hash_claim_text(normalize_claim_text("force equals mass times acceleration"))
            record = build_audit_record(claim_id, session, reg)

        print("\nAuditRecord:")
        print(json.dumps(record.to_dict(), indent=2))

        # Verify integrity: recompute the hash over the payload.
        ok = record.integrity.record_hash == canonical_hash(record.to_dict(include_integrity=False))
        print(f"\nintegrity check: {'OK' if ok else 'FAILED'}")

        reset_engine()

    print("\n" + "=" * 68)
    print("Done.")
    print("=" * 68)


if __name__ == "__main__":
    main()
