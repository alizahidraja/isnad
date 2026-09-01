import { test } from "node:test";
import assert from "node:assert/strict";
import { verifyRecordHash, verifyRecord, hmacVerify } from "../src/index";
import { golden } from "./golden";

test("verifyRecordHash passes on the intact Python record", () => {
  assert.equal(verifyRecordHash(golden.record_a_full), true);
});

test("verifyRecordHash fails on a tampered record", () => {
  const tampered = JSON.parse(JSON.stringify(golden.record_a_full));
  tampered.claim_text = "tampered";
  assert.equal(verifyRecordHash(tampered), false);
});

test("verifyRecordHash fails when integrity is missing", () => {
  const { integrity, ...noIntegrity } = golden.record_a_full;
  assert.equal(verifyRecordHash(noIntegrity), false);
});

test("verifyRecord reports hashValid + no signature (null) on unsigned record", () => {
  const res = verifyRecord(golden.record_a_full);
  assert.equal(res.hashValid, true);
  assert.equal(res.signatureValid, null);
});

test("verifyRecord verifies a correct HMAC when present", () => {
  const signed = JSON.parse(JSON.stringify(golden.record_a_full));
  signed.integrity.detached_signature = golden.hmac_a;
  const res = verifyRecord(signed, (payload, sig) => hmacVerify("test-secret", payload, sig));
  assert.equal(res.hashValid, true);
  assert.equal(res.signatureValid, true);
});

test("verifyRecord rejects a wrong-secret HMAC", () => {
  const signed = JSON.parse(JSON.stringify(golden.record_a_full));
  signed.integrity.detached_signature = golden.hmac_a;
  const res = verifyRecord(signed, (payload, sig) => hmacVerify("wrong", payload, sig));
  assert.equal(res.hashValid, true);
  assert.equal(res.signatureValid, false);
});

test("verifyRecord flags an unverifiable signature (no verifier supplied)", () => {
  const signed = JSON.parse(JSON.stringify(golden.record_a_full));
  signed.integrity.detached_signature = golden.hmac_a;
  const res = verifyRecord(signed);
  assert.equal(res.signatureValid, false);
});
