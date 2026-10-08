"""ISNAD try-before-you-buy sandbox — a loan-eligibility RAG chain, end-to-end.

Runs with zero network, zero API keys:

    uv run python examples/sandbox_demo.py

Grades one claim ("Applicant AC-2041 is eligible for a €40,000 term loan") as it
travels through four hands — credit-bureau source → RAG retriever → eligibility
LLM → human compliance reviewer — then writes a signed AuditRecord and the chain
to ``sandbox/evidence/``.

The demo is idempotent: with a fixed ``ISNAD_HMAC_SECRET`` it regenerates the
exact same evidence every run, so the committed files are reproducible.
"""

from __future__ import annotations

import json
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from isnad.audit.canonical import canonical_hash
from isnad.audit.schema import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    HumanOversight,
    Integrity,
    SourceDocument,
    WeakestLink,
)
from isnad.audit.sign import hmac_signer, sign_detached
from isnad.core.registry import Registry
from isnad.quick import grade
from isnad.types import AdalahGrade, NarratorGrade, NarratorType, TransformType

# The dev-only signing secret.  NEVER use this in production; it exists so the
# committed sandbox evidence has a stable, re-verifiable detached signature.
DEV_HMAC_SECRET = "isnad-sandbox-dev-secret-do-not-use-in-production"

CLAIM_ID = "AC-2041-eligibility"
CLAIM_TEXT = "Applicant AC-2041 is eligible for a €40,000 term loan."
DOMAIN = "lending"

# Four hands, in transmission order.  The retriever and the model are
# "acceptable" (not "reliable") so the weakest-link rule actually fires.
NARRATORS = [
    (
        "source:credit-bureau",
        NarratorType.SOURCE,
        NarratorGrade.RELIABLE,
        AdalahGrade.HIGH,
        "The credit-bureau pull — the authoritative income/debt source.",
    ),
    (
        "retriever:rag-vectorstore",
        NarratorType.TOOL,
        NarratorGrade.ACCEPTABLE,
        AdalahGrade.ACCEPTABLE,
        "The RAG step that surfaced the bureau record and the eligibility policy.",
    ),
    (
        "model:eligibility-llm",
        NarratorType.MODEL,
        NarratorGrade.ACCEPTABLE,
        AdalahGrade.ACCEPTABLE,
        "The LLM that produced the €40,000 eligibility figure.",
    ),
    (
        "reviewer:compliance-human",
        NarratorType.HUMAN,
        NarratorGrade.RELIABLE,
        AdalahGrade.HIGH,
        "The human compliance reviewer who signed off.",
    ),
]

TRANSFORM_TYPES = [
    TransformType.PASS_THROUGH,  # source: identity
    TransformType.PASS_THROUGH,  # retriever: identity (it retrieved, not invented)
    TransformType.GENERATIVE,  # model: produced the figure
    TransformType.PASS_THROUGH,  # reviewer: identity
]

EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "sandbox" / "evidence"


def _build_registry() -> Registry:
    reg = Registry()
    for nid, ntype, n_grade, adalah, _rationale in NARRATORS:
        reg.register(
            nid,
            DOMAIN,
            narrator_type=ntype,
            grade=n_grade,
            adalah=adalah,
            model_family=None,
            upstream_source=None,
        )
    return reg


def _build_audit_record(verdict: object, registry: Registry) -> AuditRecord:
    fixed_now = datetime(2026, 10, 8, 0, 0, 0, tzinfo=UTC).isoformat()
    chain_nodes = [
        ChainNodeAudit(
            narrator_id=nid,
            narrator_type=ntype.value,
            grade=registry.get_grade_for_link(nid, DOMAIN, None).value,
            grade_rationale=rationale,
        )
        for nid, ntype, _g, _a, rationale in NARRATORS
    ]
    return AuditRecord(
        record_id="00000000-0000-4000-8000-00000000c0de",
        record_version="1.0",
        generated_at=fixed_now,
        claim_id=CLAIM_ID,
        claim_text=CLAIM_TEXT,
        final_grade=verdict.chain_grade.value,
        grading_strategy=GradingStrategy(name="RefinedWeakestLink", version="1", parameters={}),
        chain=chain_nodes,
        weakest_link=WeakestLink(
            narrator_id=verdict.weakest_link,
            grade=registry.get_grade_for_link(verdict.weakest_link, DOMAIN, None).value,
            why="lowest-graded hand caps the whole chain",
        ),
        source_documents=[
            SourceDocument(
                uri="https://example.com/bureau/AC-2041",
                retrieved_at=fixed_now,
                content_hash=None,
                licence="proprietary",
            ),
        ],
        human_oversight=[
            HumanOversight(
                actor_ref="reviewer:compliance-human",
                action="approved",
                timestamp=fixed_now,
                note="reviewed the bureau record and the €40,000 figure",
            ),
        ],
        environment=Environment(
            isnad_version=_isnad_version(),
            python_version=f"{sys.version_info.major}.{sys.version_info.minor}",
            platform=platform.system(),
        ),
        integrity=Integrity(record_hash=""),
    )


def _isnad_version() -> str:
    import isnad

    return isnad.__version__


def main() -> int:
    secret = os.environ.get("ISNAD_HMAC_SECRET", DEV_HMAC_SECRET)
    registry = _build_registry()
    chain_ids = [nid for nid, *_ in NARRATORS]

    verdict = grade(
        CLAIM_TEXT,
        chain_ids,
        registry,
        domain=DOMAIN,
        transform_types=TRANSFORM_TYPES,
    )

    print("═" * 72)
    print("ISNAD sandbox — loan-eligibility RAG chain")
    print("═" * 72)
    print(f"claim : {CLAIM_TEXT}")
    print(f"chain : {' → '.join(chain_ids)}")
    print(f"grade : {verdict.chain_grade.value.upper()}")
    print(f"action: {verdict.action.value if verdict.action else '(none — chain grading only)'}")
    print(f"why   : {verdict.why}")
    print("═" * 72)

    record = _build_audit_record(verdict, registry)
    record.integrity.record_hash = canonical_hash(record.to_dict(include_integrity=False))
    sign_detached(record, hmac_signer(secret))

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    (EVIDENCE_DIR / "audit_record.json").write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE_DIR / "chain.json").write_text(
        json.dumps(
            {
                "claim_id": CLAIM_ID,
                "claim_text": CLAIM_TEXT,
                "domain": DOMAIN,
                "final_grade": verdict.chain_grade.value,
                "chain": [
                    {
                        "narrator_id": nid,
                        "narrator_type": ntype.value,
                        "grade": registry.get_grade_for_link(nid, DOMAIN, None).value,
                        "transform_type": tt.value,
                        "rationale": rationale,
                    }
                    for (nid, ntype, _g, _a, rationale), tt in zip(
                        NARRATORS, TRANSFORM_TYPES, strict=True
                    )
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"wrote {EVIDENCE_DIR / 'audit_record.json'}")
    print(f"wrote {EVIDENCE_DIR / 'chain.json'}")
    print(f"record hash: {record.integrity.record_hash}")
    print(f"signature  : {record.integrity.detached_signature[:32]}…")
    print()
    print("re-verify:")
    print(
        f"  uv run isnad verify --record sandbox/evidence/audit_record.json "
        f'--hmac-secret "{secret}"'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
