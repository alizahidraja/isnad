"""ISNAD CLI — serve, seed, audit-evidence, and ingest commands.

Usage:
    isnad serve                 Start the API server
    isnad seed                  Seed narrators from ISNAD_SEED_CONFIG env var
    isnad export --claim ID     Emit an AuditRecord (json|jsonl|csv) to stdout
    isnad verify --record PATH  Recompute a record hash; exit 0/1
    isnad verify-chain --chain PATH  Walk a hash chain; exit 0/1
    isnad ingest --otlp PATH    Grade an OpenTelemetry GenAI trace
    isnad mcp             Serve the registry as an MCP server (grade_claim)

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
            role_raw = entry.get("role")
            role = Role(role_raw) if role_raw else None
            source = entry.get("source", "operator")
            # A benchmark accuracy may be given instead of (or to override) a
            # grade — cold-start bootstrapping (issue #33).
            if "accuracy" in entry:
                accuracy = float(entry["accuracy"])
                reg.registry.seed_from_benchmark(nid, dom, accuracy, role=role, benchmark=source)
            else:
                grade = grade_map.get(entry.get("grade", "ungraded"), NarratorGrade.UNGRADED)
                reg.registry.seed(nid, dom, grade, role=role, source=source)
        reg.flush()
        print(f"Seeded {len(config)} narrators.")


# ── Audit-evidence commands ─────────────────────────────────────────────────


def _redact_claim_text(field: str, value: object) -> object:
    """Redact claim text only — the main PII surface — leaving structure intact."""
    if field == "claim_text":
        return "<redacted>"
    return value


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
    parser.add_argument(
        "--sign",
        default=None,
        help="HMAC secret to sign the record with before emitting "
        "(defaults to $ISNAD_SIGNING_SECRET when the flag is passed without a value)",
        nargs="?",
        const=os.environ.get("ISNAD_SIGNING_SECRET", ""),
    )
    parser.add_argument(
        "--redact", action="store_true", help="redact claim text (PII) before hashing"
    )
    parser.add_argument("--chain-log", default=None, help="append the hash to a chain log")
    args = parser.parse_args(argv)

    from isnad.audit import build_audit_record

    registry, session = _load_registry_and_session()
    try:
        record = build_audit_record(
            args.claim, session, registry, redact_fn=_redact_claim_text if args.redact else None
        )
    finally:
        session.close()

    if args.sign is not None:
        from isnad.audit.sign import hmac_signer, sign_detached

        if not args.sign:
            print(
                "signing requires a secret: pass --sign SECRET or set ISNAD_SIGNING_SECRET",
                file=sys.stderr,
            )
            return 1
        sign_detached(record, hmac_signer(args.sign))

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
        from isnad.audit.canonical import canonical_hash, canonical_json
        from isnad.audit.sign import hmac_verifier

        recomputed = canonical_hash(record.to_dict(include_integrity=False))
        if recomputed != record.integrity.record_hash:
            print("verification FAILED: hash mismatch", file=sys.stderr)
            return 1
        detached = record.integrity.detached_signature
        secret = args.sign or os.environ.get("ISNAD_SIGNING_SECRET", "")
        if detached:
            if secret:
                payload = canonical_json(record.to_dict(include_integrity=False))
                if hmac_verifier(secret)(payload, detached):
                    print("verification OK: hash + detached signature", file=sys.stderr)
                else:
                    print("verification FAILED: detached signature mismatch", file=sys.stderr)
                    return 1
            else:
                # Fail closed: a detached signature is present but we have no
                # secret to check it against. Reporting "OK" here would be a
                # forgeable path in a tamper-evidence tool.
                print(
                    "verification INCONCLUSIVE: detached signature present but no "
                    "secret (--sign or ISNAD_SIGNING_SECRET); forge-resistance NOT checked",
                    file=sys.stderr,
                )
                return 1
        else:
            print(
                "verification OK: hash only — no detached signature (forge-resistance NOT checked)",
                file=sys.stderr,
            )
            return 1

    if args.chain_log:
        from isnad.audit import append_record

        append_record(args.chain_log, record.record_id, record.integrity.record_hash)
        print(f"appended to chain log {args.chain_log}", file=sys.stderr)

    return 0


def _ingest(argv: list[str]) -> int:
    """Grade an OpenTelemetry GenAI trace (issue #73)."""
    parser = argparse.ArgumentParser(
        prog="isnad ingest", description="Grade an OpenTelemetry GenAI trace."
    )
    parser.add_argument("--otlp", required=True, help="path to an OTLP/JSON trace export")
    parser.add_argument("--domain", default="general", help="domain tag for registry lookup")
    parser.add_argument(
        "--lenient", action="store_true", help="ungraded narrator → ḥasan (default: strict ḍaʿīf)"
    )
    args = parser.parse_args(argv)

    from isnad.integrations.otel import ingest_trace, parse_otlp_json

    registry, session = _load_registry_and_session()
    try:
        with open(args.otlp) as f:
            data = json.load(f)
        spans = parse_otlp_json(data)
        result = ingest_trace(spans, registry, args.domain, lenient_unknown=args.lenient)
    finally:
        session.close()

    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    summary = (
        f"trace {result.trace_id}: {result.transmitter_count} transmitters → {result.chain_grade}"
    )
    if result.weakest_link:
        summary += f" (weakest: {result.weakest_link})"
    if result.claim_text is None:
        summary += " — claim text not present in spans (chain grade only)"
    print(summary, file=sys.stderr)
    return 0


def _bench(argv: list[str]) -> int:
    """Grade a corpus — config-driven (self-contained) or classical (repo)."""
    parser = argparse.ArgumentParser(
        prog="isnad bench", description="Grade a claim corpus through a narrator set."
    )
    parser.add_argument("--config", default=None, help="JSON config: {domain, narrators, claims}")
    args = parser.parse_args(argv)

    if args.config:
        with open(args.config) as f:
            config = json.load(f)
        from isnad.bench import run_config

        print(json.dumps(run_config(config), indent=2, ensure_ascii=False))
        return 0

    print(
        "Usage:\n"
        "  isnad bench --config mine.json   # grade YOUR corpus + narrators\n"
        "\n"
        "The classical ISNAD-Bench (hadith ground truth) needs the repo checkout\n"
        "and the hadith-kg.db dataset:\n"
        "  uv run python -m bench.run\n"
        "See bench/README.md and bench/docs/RESULTS.md.",
        file=sys.stderr,
    )
    return 1


def _mcp(argv: list[str]) -> int:
    """Run the ISNAD MCP server (grades claims from the local registry)."""
    parser = argparse.ArgumentParser(
        prog="isnad mcp",
        description="Serve the local ISNAD registry as an MCP server (grade_claim tool).",
    )
    parser.add_argument(
        "--domain", default="general", help="default domain tag for grading (default: general)"
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    args = parser.parse_args(argv)

    from isnad.core.registry import RegistryDB
    from isnad.integrations.mcp import serve_mcp
    from isnad.storage.sqlalchemy import get_session, init_db

    init_db()
    with get_session() as session:
        reg_db = RegistryDB(session=session)
        reg_db.load()
        # Blocking: run the MCP server on the loaded registry.
        serve_mcp(reg_db.registry, domain=args.domain, transport=args.transport)
    return 0


def _verify(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="isnad verify",
        description="Recompute a record hash and (optionally) verify its detached signature.",
    )
    parser.add_argument("--record", required=True, help="path to an AuditRecord JSON")
    parser.add_argument(
        "--hmac-secret",
        default=None,
        help="HMAC secret for detached-signature verification (defaults to $ISNAD_SIGNING_SECRET)",
    )
    args = parser.parse_args(argv)

    from isnad.audit.canonical import canonical_hash, canonical_json
    from isnad.audit.sign import hmac_verifier

    with open(args.record) as f:
        data = json.load(f)

    integrity = data.pop("integrity", {})
    stored = integrity.get("record_hash", "")
    recomputed = canonical_hash(data)
    if stored != recomputed:
        print(f"MISMATCH: stored {stored!r} != recomputed {recomputed!r}")
        return 1

    # Self-hash is only tamper-evident against accidental corruption, not a
    # forger who rewrites the record and recomputes the hash (issue #97). If
    # the record carries a detached signature and a secret is available,
    # verify it. Otherwise say plainly what was NOT checked.
    detached = integrity.get("detached_signature")
    secret = args.hmac_secret or os.environ.get("ISNAD_SIGNING_SECRET", "")
    if detached:
        if secret:
            if hmac_verifier(secret)(canonical_json(data), detached):
                print(f"OK: {stored} (detached signature verified)")
                return 0
            print("MISMATCH: detached signature verification FAILED")
            return 1
        print(
            f"OK: {stored} (self-hash only — detached signature present but no "
            "ISNAD_SIGNING_SECRET; forge-resistance NOT checked)",
        )
        return 1

    print(
        f"OK: {stored} (self-hash only — record has no detached signature; "
        "forge-resistance NOT checked)",
    )
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


def _verify_merkle(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="isnad verify-merkle",
        description="Verify a Merkle batch log (parallel-friendly tamper-evidence).",
    )
    parser.add_argument("--log", required=True, help="path to a Merkle batch log JSONL")
    args = parser.parse_args(argv)

    from isnad.audit import read_batch_log, verify_batches
    from isnad.audit.merkle_log import MalformedLogError

    try:
        break_ = verify_batches(read_batch_log(args.log))
    except MalformedLogError as exc:
        print(f"batch log malformed at entry {exc.index}: {exc.reason}")
        return 1
    if break_ is None:
        print("batch log intact")
        return 0
    print(f"batch log broken at batch {break_.index}: {break_.reason}")
    return 1


def _scan(argv: list[str]) -> int:
    """Map pipeline transmitters onto the warm default registry (#206)."""
    parser = argparse.ArgumentParser(
        prog="isnad scan", description="Map pipeline transmitters onto the registry."
    )
    parser.add_argument(
        "--narrators",
        required=True,
        help="comma-separated narrator_ids (e.g. source:a,model:b,scraper:c)",
    )
    parser.add_argument("--domain", default="general", help="domain tag for registry lookup")
    parser.add_argument(
        "--vertical",
        default="self-maintaining-kb",
        help="default-registry vertical to scan against",
    )
    args = parser.parse_args(argv)

    from isnad.core.registry import default_registry
    from isnad.scan import scan_registry

    reg = default_registry(vertical=args.vertical)
    narrator_ids = [n.strip() for n in args.narrators.split(",") if n.strip()]
    result = scan_registry(narrator_ids, reg, args.domain)

    report = {
        "vertical": args.vertical,
        "domain": args.domain,
        "total": len(narrator_ids),
        "vouched": len(result.vouched),
        "cold": len(result.cold),
        "vouched_narrators": result.vouched,
        "cold_narrators": result.cold,
        "submit_hint": [c["narrator_id"] for c in result.cold],
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> None:
    """CLI dispatcher.

    Args:
        argv: Command-line arguments (defaults to sys.argv). Injectable for
            testing.
    """
    args = sys.argv if argv is None else ["isnad", *argv]
    usage = (
        "Usage: isnad [serve|seed|export|verify|verify-chain|verify-merkle|ingest|bench|mcp|scan]"
    )
    if len(args) < 2:
        print(usage)
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
    elif cmd == "verify-merkle":
        sys.exit(_verify_merkle(rest))
    elif cmd == "ingest":
        sys.exit(_ingest(rest))
    elif cmd == "bench":
        sys.exit(_bench(rest))
    elif cmd == "mcp":
        sys.exit(_mcp(rest))
    elif cmd == "scan":
        sys.exit(_scan(rest))
    else:
        print(f"Unknown command: {cmd}")
        print(usage)
        sys.exit(1)


if __name__ == "__main__":
    main()
