"""Generate golden conformance vectors for the JS verifier.

Run from the Python repo (isnad importable):
    uv run python js/scripts/generate_golden.py

Writes deterministic golden values to js/test/golden.json that the
JS package verifies against byte-for-byte. All inputs are fixed (no random
UUIDs/timestamps) so the vectors are reproducible.
"""
from __future__ import annotations

import json
from pathlib import Path

from isnad import __version__
from isnad.audit import (
    AuditRecord,
    ChainNodeAudit,
    Environment,
    GradingStrategy,
    Integrity,
    SourceDocument,
    WeakestLink,
    hmac_signer,
)
from isnad.audit.canonical import canonical_json, sha256_hex
from isnad.audit.merkle_log import (
    _EMPTY,
    build_batch,
    prove_inclusion,
    seal_batches,
)


def make_record(rid: str, cid: str, text: str, grade: str) -> AuditRecord:
    return AuditRecord(
        record_id=rid,
        record_version="1.0",
        generated_at="2026-08-30T00:00:00+00:00",
        claim_id=cid,
        claim_text=text,
        final_grade=grade,
        grading_strategy=GradingStrategy("RefinedWeakestLink", "1"),
        chain=[ChainNodeAudit("src", "dataset", "reliable", "r")],
        weakest_link=WeakestLink("src", "reliable", "lowest grade"),
        source_documents=[SourceDocument("https://example.com/x")],
        human_oversight=[],
        environment=Environment(__version__, "3.12", "test"),
    )


def finalize(rec: AuditRecord) -> tuple[dict, str]:
    """Fill integrity.record_hash and return (payload_dict, record_hash)."""
    payload = rec.to_dict(include_integrity=False)
    rec.integrity = Integrity(record_hash=sha256_hex(canonical_json(payload)))
    return payload, rec.integrity.record_hash


# --- record A: ASCII ---
ra = make_record(
    "00000000-0000-4000-8000-000000000001", "c1", "p = mv", "hasan"
)
payload_a, hash_a = finalize(ra)
canon_a = canonical_json(payload_a)
hmac_a = hmac_signer("test-secret")(canon_a)

# --- record B: Unicode (emoji + accented + astral) ---
rb = make_record(
    "00000000-0000-4000-8000-000000000002",
    "c2",
    "café — naïve résumé 🚀 \u2028line-sep\U0001F600",
    "daif",
)
payload_b, hash_b = finalize(rb)
canon_b = canonical_json(payload_b)

# --- record C: another ASCII for the Merkle batch ---
rc = make_record(
    "00000000-0000-4000-8000-000000000003", "c3", "E = mc^2", "sahih"
)
payload_c, hash_c = finalize(rc)

# --- Ed25519 deterministic key (seed = bytes 0..31) ---
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

priv = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
pub = priv.public_key()
pub_raw = pub.public_bytes_raw()  # 32 raw bytes
ed_sig_a = priv.sign(canon_a.encode()).hex()

# --- Merkle batch over the three records ---
leaves = [
    (ra.record_id, ra.integrity.record_hash),
    (rb.record_id, rb.integrity.record_hash),
    (rc.record_id, rc.integrity.record_hash),
]
batch = build_batch(leaves)
sealed = seal_batches([batch])
proof = prove_inclusion(batch, rb.record_id)

golden = {
    "canon_a": canon_a,
    "hash_a": hash_a,
    "hmac_a": hmac_a,
    "ed25519_pub_raw_hex": pub_raw.hex(),
    "ed25519_sig_a_hex": ed_sig_a,
    "canon_b": canon_b,
    "hash_b": hash_b,
    "merkle_empty": _EMPTY,
    "merkle_batch_root": batch.root,
    "merkle_sealed_prev_root": sealed[0].prev_root,
    "merkle_proof_record_id": proof.record_id,
    "merkle_proof_record_hash": proof.record_hash,
    "merkle_proof_leaf_index": proof.leaf_index,
    "merkle_proof_audit_path": [[h, side] for h, side in proof.audit_path],
    "record_a_full": ra.to_dict(include_integrity=True),
    "record_b_full": rb.to_dict(include_integrity=True),
    "record_c_full": rc.to_dict(include_integrity=True),
}

out = Path(__file__).resolve().parent.parent / "test" / "golden.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(golden, indent=2, ensure_ascii=False) + "\n")
print(f"wrote {out}")
print("hash_a:", hash_a)
print("merkle_root:", batch.root)
print("empty:", _EMPTY)
