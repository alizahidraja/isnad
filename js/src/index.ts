/**
 * ISNAD audit-record verifier (JS/TS).
 *
 * Verifier only: this package checks the integrity of ISNAD audit records
 * (SHA-256 self-hash, Merkle batch logs, detached signatures). It does NOT
 * grade claims, run the narrator registry, or corroborate — grading stays in
 * the Python core (`pip install isnad`), which remains the sole grading
 * authority.
 */
export { canonicalize, canonicalHash, sha256Hex } from "./canonical";
export { hmacSha256Hex, hmacVerify, ed25519Verify } from "./sign";
export {
  MERKLE_EMPTY,
  leafHash,
  nodeHash,
  merkleRoot,
  buildBatch,
  sealBatches,
  verifyBatches,
  proveInclusion,
  verifyInclusion,
} from "./merkle";
export type { MerkleBatch, BatchBreak, InclusionProof } from "./merkle";
export { verifyRecordHash, verifyDetachedSignature, verifyRecord } from "./verify";
export type { SignatureVerifier, VerifyResult } from "./verify";
export { RECORD_VERSION, SCHEMA_VERSION } from "./schema";
export type {
  AuditRecord,
  Integrity,
  GradingStrategy,
  ChainNodeAudit,
  WeakestLink,
  SourceDocument,
  HumanOversight,
  Environment,
} from "./schema";
