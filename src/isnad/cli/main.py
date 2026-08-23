"""ISNAD CLI — serve, seed, and audit-evidence commands.

Usage:
    isnad serve                 Start the API server
    isnad seed                  Seed narrators from ISNAD_SEED_CONFIG env var
    isnad export --claim ID     Emit an AuditRecord (json|jsonl|csv) to stdout
    isnad verify --record PATH  Recompute a record hash; exit 0/1
    isnad verify-chain --chain PATH  Walk a hash chain; exit 0/1

The audit commands emit **evidence artifacts**, not compliance certificates.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys


def serve() -> None:
    """Start the ISNAD API server."""
    import uvicorn

    host = os.environ.get("ISNAD_HOST", "0.0.0.0")
    port = int(os.environ.get("ISNAD_PORT", "8000"))
    uvicorn.run("isnad.api.app:app", host=host, port=port, reload=False)


def seed() -> None:
    """Seed the narrator registry from ISNAD_SEED_CONFIG env var."""
    from isnad.storage.sqlalchemy import get_session, init_db

    init_db()
    config = json.loads(os.environ.get("ISNAD_SEED_CONFIG", "[]"))
    if not config:
        print("ISNAD_SEED_CONFIG is empty. Set it to a JSON array of {narrator_id, domain, grade}.")
        sys.exit(1)

    from isnad.core.registry import NarratorGrade, RegistryDB
    from isnad.types import Role

    grade_map = {
        "reliable": NarratorGrade.RELIABLE,
        "acceptable": NarratorGrade.ACCEPTABLE,
        "weak": NarratorGrade.WEAK,
        "rejected": NarratorGrade.REJECTED,
        "ungraded": NarratorGrade.UNGRADED,
    }

    with get_session() as session:
        reg = RegistryDB(session=session)
        reg.load()
        for entry in config:
            nid = entry["narrator_id"]
            dom = entry.get("domain", "general")
            grade = grade_map.get(entry.get("grade", "ungraded"), NarratorGrade.UNGRADED)
            role_raw = entry.get("role")
            role = Role(role_raw) if role_raw else None
            reg.registry.register(nid, dom, grade=grade, role=role)
        reg.flush()
        print(f"Seeded {len(config)} narrators.")


# ── Audit-evidence commands ─────────────────────────────────────────────────


def _load_registry_and_session():
    from isnad.core.registry import RegistryDB
    from isnad.storage.sqlalchemy import get_session, init_db

    init_db()
    session = get_session().__enter__()
    rdb = RegistryDB(session=session)
    rdb.load()
    return rdb.registry, session


def _serialize(record, fmt: str) -> str:
    d = record.to_dict()
    if fmt == "json":
        return json.dumps(d, indent=2, ensure_ascii=False)
    if fmt == "jsonl":
        return json.dumps(d, separators=(",", ":"), ensure_ascii=False)
    if fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "record_id",
            "claim_id",
            "final_grade",
            "weakest_link",
            "chain_length",
            "record_hash",
        ])
        writer.writerow([
            d["record_id"],
            d["claim_id"],
            d["final_grade"],
            d["weakest_link"]["narrator_id"],
            len(d["chain"]),
            d["integrity"]["record_hash"],
        ])
        return buf.getvalue().rstrip("\n")
    raise ValueError(f"unknown format: {fmt}")


def _export(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="isnad export", description="Emit an AuditRecord.")
    parser.add_argument("--claim", required=True, help="stored claim id")
    parser.add_argument("--format", choices=["json", "jsonl", "csv"], default="json")
    parser.add_argument("--out", default=None, help="write to file instead of stdout")
    parser.add_argument("--verify", action="store_true", help="recompute the hash and check")
    parser.add_argument("--chain-log", default=None, help="append the hash to a chain log")
    args = parser.parse_args(argv)

    from isnad.audit import build_audit_record

    registry, session = _load_registry_and_session()
    try:
        record = build_audit_record(args.claim, session, registry)
    finally:
        session.close()

    output = _serialize(record, args.format)

    if args.out:
        with open(args.out, "w") as f:
            f.write(output + "\n")
    else:
        print(output)

    # Human-readable summary → stderr, so stdout stays pipeable.
    print(
        f"record {record.record_id}: claim {record.claim_id} "
        f"→ {record.final_grade} (weakest link: {record.weakest_link.narrator_id})",
        file=sys.stderr,
    )

    if args.verify:
        from isnad.audit.canonical import canonical_hash

        recomputed = canonical_hash(record.to_dict(include_integrity=False))
        if recomputed != record.integrity.record_hash:
            print("verification FAILED: hash mismatch", file=sys.stderr)
            return 1
        print("verification OK: record hash matches", file=sys.stderr)

    if args.chain_log:
        from isnad.audit import append_record

        append_record(args.chain_log, record.record_id, record.integrity.record_hash)
        print(f"appended to chain log {args.chain_log}", file=sys.stderr)

    return 0


def _verify(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="isnad verify", description="Recompute a record hash.")
    parser.add_argument("--record", required=True, help="path to an AuditRecord JSON")
    args = parser.parse_args(argv)

    from isnad.audit.canonical import canonical_hash

    with open(args.record) as f:
        data = json.load(f)
    integrity = data.pop("integrity", {})
    stored = integrity.get("record_hash", "")
    recomputed = canonical_hash(data)
    if stored == recomputed:
        print(f"OK: {stored}")
        return 0
    print(f"MISMATCH: stored {stored!r} != recomputed {recomputed!r}")
    return 1


def _verify_chain(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="isnad verify-chain", description="Walk a hash chain.")
    parser.add_argument("--chain", required=True, help="path to a chain log JSONL")
    args = parser.parse_args(argv)

    from isnad.audit import verify_chain

    break_ = verify_chain(args.chain)
    if break_ is None:
        print("chain intact")
        return 0
    print(f"chain broken at entry {break_.index}: {break_.reason}")
    return 1


def main(argv: list[str] | None = None) -> None:
    """CLI dispatcher.

    Args:
        argv: Command-line arguments (defaults to sys.argv). Injectable for
            testing.
    """
    args = sys.argv if argv is None else ["isnad", *argv]
    if len(args) < 2:
        print("Usage: isnad [serve|seed|export|verify|verify-chain]")
        sys.exit(1)

    cmd = args[1]
    rest = args[2:]
    if cmd == "serve":
        serve()
    elif cmd == "seed":
        seed()
    elif cmd == "export":
        sys.exit(_export(rest))
    elif cmd == "verify":
        sys.exit(_verify(rest))
    elif cmd == "verify-chain":
        sys.exit(_verify_chain(rest))
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: isnad [serve|seed|export|verify|verify-chain]")
        sys.exit(1)


if __name__ == "__main__":
    main()
