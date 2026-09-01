import { test } from "node:test";
import assert from "node:assert/strict";
import { canonicalize, canonicalHash, sha256Hex } from "../src/index";
import { golden } from "./golden";

test("canonicalize matches Python for ASCII record", () => {
  const { integrity, ...payload } = golden.record_a_full;
  assert.equal(canonicalize(payload), golden.canon_a);
});

test("canonicalHash matches Python for ASCII record", () => {
  const { integrity, ...payload } = golden.record_a_full;
  assert.equal(canonicalHash(payload), golden.hash_a);
});

test("canonicalize matches Python for Unicode record (emoji + accents + U+2028)", () => {
  const { integrity, ...payload } = golden.record_b_full;
  assert.equal(canonicalize(payload), golden.canon_b);
});

test("canonicalHash matches Python for Unicode record", () => {
  const { integrity, ...payload } = golden.record_b_full;
  assert.equal(canonicalHash(payload), golden.hash_b);
});

test("U+2028 and U+2029 are emitted literally, not escaped", () => {
  assert.equal(canonicalize({ a: "\u2028\u2029" }), '{"a":"\u2028\u2029"}');
});

test("keys are sorted lexicographically", () => {
  assert.equal(canonicalize({ b: 1, a: 2, c: 3 }), '{"a":2,"b":1,"c":3}');
});

test("nested objects sort keys at every level", () => {
  assert.equal(canonicalize({ z: { y: 1, x: 2 } }), '{"z":{"x":2,"y":1}}');
});

test("non-integer numbers are rejected (never-floats invariant)", () => {
  assert.throws(() => canonicalize({ a: 1.5 }), /non-integer/);
});

test("sha256Hex matches Python for the empty Merkle sentinel", () => {
  assert.equal(sha256Hex("isnad-merkle-empty"), golden.merkle_empty);
});
