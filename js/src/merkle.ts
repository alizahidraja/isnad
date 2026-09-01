/**
 * Merkle batch audit log — byte-identical port of the Python core's
 * `audit/merkle_log.py` (Certificate-Transparency style, lone-node promotion
 * to avoid CVE-2012-2459).
 */
import { sha256Hex } from "./canonical";

const LEAF_PREFIX = "isnad-merkle-leaf:";
const NODE_PREFIX = "isnad-merkle-node:";

/** Root of an empty leaf set = sha256("isnad-merkle-empty"). */
export const MERKLE_EMPTY = sha256Hex("isnad-merkle-empty");

/** Hash a leaf, binding record_id to record_hash. */
export function leafHash(recordId: string, recordHash: string): string {
  return sha256Hex(LEAF_PREFIX + recordId + "\x00" + recordHash);
}

/** Hash an internal node from its two child hashes. */
export function nodeHash(left: string, right: string): string {
  return sha256Hex(NODE_PREFIX + left + "\x00" + right);
}

/** Merkle root of an ordered list of leaf hashes (lone node promoted). */
export function merkleRoot(leafHashes: string[]): string {
  if (leafHashes.length === 0) return MERKLE_EMPTY;
  let level = leafHashes.slice();
  while (level.length > 1) {
    const next: string[] = [];
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 < level.length) next.push(nodeHash(level[i], level[i + 1]));
      else next.push(level[i]);
    }
    level = next;
  }
  return level[0];
}

export interface MerkleBatch {
  leaves: [string, string][];
  root: string;
  prev_root: string | null;
}

export interface BatchBreak {
  index: number;
  reason: string;
}

/** Build an unsealed batch from ordered `(record_id, record_hash)` leaves. */
export function buildBatch(leaves: [string, string][]): MerkleBatch {
  const leafHashes = leaves.map(([rid, rh]) => leafHash(rid, rh));
  return { leaves: leaves.slice(), root: merkleRoot(leafHashes), prev_root: null };
}

/** Link a sequence of batches into a chain (roots recomputed from leaves). */
export function sealBatches(batches: MerkleBatch[]): MerkleBatch[] {
  const sealed: MerkleBatch[] = [];
  let prev: string | null = null;
  for (const b of batches) {
    const root = merkleRoot(b.leaves.map(([rid, rh]) => leafHash(rid, rh)));
    sealed.push({ leaves: b.leaves.slice(), root, prev_root: prev });
    prev = root;
  }
  return sealed;
}

/** Verify a sealed batch chain; return the first break, or null if intact. */
export function verifyBatches(batches: MerkleBatch[]): BatchBreak | null {
  let prev: string | null = null;
  for (let i = 0; i < batches.length; i++) {
    const b = batches[i];
    const recomputed = merkleRoot(b.leaves.map(([rid, rh]) => leafHash(rid, rh)));
    if (recomputed !== b.root) {
      return { index: i, reason: `batch ${i} root ${b.root} != recomputed ${recomputed}` };
    }
    if (i === 0) {
      if (b.prev_root !== null) return { index: i, reason: "first batch has a non-null prev_root" };
    } else if (b.prev_root !== prev) {
      return { index: i, reason: `batch ${i} prev_root ${b.prev_root} != previous root ${prev}` };
    }
    prev = b.root;
  }
  return null;
}

export interface InclusionProof {
  record_id: string;
  record_hash: string;
  audit_path: [string, "left" | "right"][];
  leaf_index: number;
}

/** Build an O(log n) inclusion proof for `record_id`, or null if absent. */
export function proveInclusion(batch: MerkleBatch, recordId: string): InclusionProof | null {
  const index = batch.leaves.findIndex(([rid]) => rid === recordId);
  if (index < 0) return null;
  const recordHash = batch.leaves[index][1];
  let level = batch.leaves.map(([rid, rh]) => leafHash(rid, rh));
  let idx = index;
  const path: [string, "left" | "right"][] = [];
  while (level.length > 1) {
    const next: string[] = [];
    for (let i = 0; i < level.length; i += 2) {
      if (i + 1 < level.length) {
        if (i === idx) path.push([level[i + 1], "right"]);
        else if (i + 1 === idx) path.push([level[i], "left"]);
        next.push(nodeHash(level[i], level[i + 1]));
      } else {
        next.push(level[i]);
      }
    }
    idx = Math.floor(idx / 2);
    level = next;
  }
  return { record_id: recordId, record_hash: recordHash, audit_path: path, leaf_index: index };
}

/** Recompute the root from a proof and check it equals `root`. */
export function verifyInclusion(proof: InclusionProof, root: string): boolean {
  let node = leafHash(proof.record_id, proof.record_hash);
  for (const [sibling, side] of proof.audit_path) {
    node = side === "left" ? nodeHash(sibling, node) : nodeHash(node, sibling);
  }
  return node === root;
}
