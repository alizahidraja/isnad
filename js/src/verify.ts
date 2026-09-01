/**
 * Audit-record verification: self-hash and detached-signature checks.
 * Mirrors the Python core's `audit/canonical.py` + `audit/sign.py`.
 */
import { canonicalHash, canonicalize } from "./canonical";
import type { AuditRecord } from "./schema";

/** Recompute the record's self-hash and compare to `integrity.record_hash`. */
export function verifyRecordHash(record: AuditRecord): boolean {
  const integrity = record.integrity;
  if (!integrity || !integrity.record_hash) return false;
  const { integrity: _ignored, ...payload } = record;
  return canonicalHash(payload) === integrity.record_hash;
}

export type SignatureVerifier = (payload: string, signature: string) => boolean;

/**
 * Verify the stored detached signature over the canonical payload
 * (the record WITHOUT its `integrity` block). Returns false when there is no
 * signature — a self-hashed record is not tamper-evident against a forger.
 */
export function verifyDetachedSignature(record: AuditRecord, verifier: SignatureVerifier): boolean {
  const sig = record.integrity?.detached_signature;
  if (!sig) return false;
  const { integrity: _ignored, ...payload } = record;
  return verifier(canonicalize(payload), sig);
}

export interface VerifyResult {
  hashValid: boolean;
  /** null = no signature present; boolean = whether it verified. */
  signatureValid: boolean | null;
}

/**
 * Full verification of a record: self-hash always, plus the detached signature
 * when one is present and a `verifier` is supplied.
 */
export function verifyRecord(record: AuditRecord, verifier?: SignatureVerifier): VerifyResult {
  const hashValid = verifyRecordHash(record);
  const sig = record.integrity?.detached_signature;
  let signatureValid: boolean | null = null;
  if (sig != null && sig !== "") {
    signatureValid = verifier ? verifyDetachedSignature(record, verifier) : false;
  }
  return { hashValid, signatureValid };
}
