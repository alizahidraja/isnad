/**
 * Detached-signature verification for audit records.
 *
 * Verifier-only: this package never signs. Signing stays in the Python core
 * (or a server-side Node process that holds the secret/private key). A browser
 * or untrusted client must only ever *verify*, never hold the shared secret.
 */
import { createHmac, createPublicKey, timingSafeEqual, verify as cryptoVerify } from "node:crypto";

/** HMAC-SHA256 hex digest (matches Python `hmac_signer`). */
export function hmacSha256Hex(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload, "utf8").digest("hex");
}

/** Constant-time HMAC-SHA256 verification (matches Python `hmac_verifier`). */
export function hmacVerify(secret: string, payload: string, signature: string): boolean {
  const expected = hmacSha256Hex(secret, payload);
  const a = Buffer.from(expected, "hex");
  const b = Buffer.from(signature, "hex");
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

// SPKI DER prefix for a raw 32-byte Ed25519 public key:
// SEQUENCE(42) / SEQUENCE(5) / OID 1.3.101.112 / BIT STRING(33, 0 unused) + key
const ED25519_SPKI_PREFIX = Buffer.from("302a300506032b6570032100", "hex");

/**
 * Ed25519 detached-signature verification from a raw 32-byte public key.
 * Matches Python `ed25519_verifier`. Returns false on any bad input
 * (wrong-length key/signature, invalid signature) rather than throwing.
 */
export function ed25519Verify(publicKeyHex: string, payload: string, signatureHex: string): boolean {
  try {
    const raw = Buffer.from(publicKeyHex, "hex");
    if (raw.length !== 32) return false;
    const spki = Buffer.concat([ED25519_SPKI_PREFIX, raw]);
    const key = createPublicKey({ key: spki, format: "der", type: "spki" });
    const sig = Buffer.from(signatureHex, "hex");
    if (sig.length !== 64) return false;
    return cryptoVerify(null, Buffer.from(payload, "utf8"), key, sig);
  } catch {
    return false;
  }
}
