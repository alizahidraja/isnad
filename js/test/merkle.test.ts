import { test } from "node:test";
import assert from "node:assert/strict";
import {
  MERKLE_EMPTY,
  buildBatch,
  sealBatches,
  verifyBatches,
  proveInclusion,
  verifyInclusion,
} from "../src/index";
import { golden } from "./golden";

const idA = golden.record_a_full.record_id as string;
const idB = golden.record_b_full.record_id as string;
const idC = golden.record_c_full.record_id as string;
const hashA = golden.record_a_full.integrity.record_hash as string;
const hashB = golden.record_b_full.integrity.record_hash as string;
const hashC = golden.record_c_full.integrity.record_hash as string;

function threeLeafBatch() {
  return buildBatch([
    [idA, hashA],
    [idB, hashB],
    [idC, hashC],
  ]);
}

test("MERKLE_EMPTY matches the Python sentinel", () => {
  assert.equal(MERKLE_EMPTY, golden.merkle_empty);
});

test("buildBatch root matches Python for the 3-record batch", () => {
  assert.equal(threeLeafBatch().root, golden.merkle_batch_root);
});

test("sealBatches sets prev_root correctly (single batch -> null)", () => {
  const sealed = sealBatches([threeLeafBatch()]);
  assert.equal(sealed[0].prev_root, null);
});

test("verifyBatches passes on an intact batch", () => {
  assert.equal(verifyBatches([threeLeafBatch()]), null);
});

test("verifyBatches detects a tampered root", () => {
  const batch = threeLeafBatch();
  batch.root = "0".repeat(64);
  assert.ok(verifyBatches([batch]) !== null);
});

test("proveInclusion + verifyInclusion match Python for record B", () => {
  const proof = proveInclusion(threeLeafBatch(), golden.merkle_proof_record_id);
  assert.ok(proof, "proof should exist");
  assert.equal(proof!.leaf_index, golden.merkle_proof_leaf_index);
  assert.equal(proof!.record_hash, golden.merkle_proof_record_hash);
  assert.deepEqual(proof!.audit_path, golden.merkle_proof_audit_path);
  assert.equal(verifyInclusion(proof!, golden.merkle_batch_root), true);
});

test("verifyInclusion rejects a tampered record_hash", () => {
  const proof = proveInclusion(threeLeafBatch(), idB)!;
  proof.record_hash = "0".repeat(64);
  assert.equal(verifyInclusion(proof, golden.merkle_batch_root), false);
});

test("proveInclusion returns null for an absent record", () => {
  assert.equal(proveInclusion(threeLeafBatch(), "does-not-exist"), null);
});
