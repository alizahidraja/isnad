import { test } from "node:test";
import assert from "node:assert/strict";
import { hmacVerify, ed25519Verify } from "../src/index";
import { golden } from "./golden";

test("HMAC verifies the Python-produced signature", () => {
  assert.equal(hmacVerify("test-secret", golden.canon_a, golden.hmac_a), true);
});

test("HMAC rejects a wrong secret", () => {
  assert.equal(hmacVerify("wrong-secret", golden.canon_a, golden.hmac_a), false);
});

test("HMAC rejects a tampered payload", () => {
  assert.equal(hmacVerify("test-secret", golden.canon_a + "x", golden.hmac_a), false);
});

test("Ed25519 verifies the Python-produced signature", () => {
  assert.equal(
    ed25519Verify(golden.ed25519_pub_raw_hex, golden.canon_a, golden.ed25519_sig_a_hex),
    true,
  );
});

test("Ed25519 rejects a wrong public key", () => {
  assert.equal(ed25519Verify("0".repeat(64), golden.canon_a, golden.ed25519_sig_a_hex), false);
});

test("Ed25519 rejects a tampered payload", () => {
  assert.equal(
    ed25519Verify(golden.ed25519_pub_raw_hex, golden.canon_a + "x", golden.ed25519_sig_a_hex),
    false,
  );
});

test("Ed25519 rejects a malformed signature", () => {
  assert.equal(ed25519Verify(golden.ed25519_pub_raw_hex, golden.canon_a, "abcd"), false);
});
