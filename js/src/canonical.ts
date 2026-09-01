/**
 * Canonical JSON serialization matching the Python core's
 * `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
 *
 * ISNAD audit records contain only strings, integers, booleans, null, arrays,
 * and objects — never floats. Floats are rejected (the "never floats"
 * invariant), which is what makes this byte-compatible with RFC 8785 for every
 * object ISNAD emits: the only genuinely fiddly part of JCS (number
 * serialization) is enforced away instead of reimplemented.
 */
import { createHash } from "node:crypto";

const HEX = "0123456789abcdef";

function escapeString(s: string): string {
  let out = '"';
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c === 0x22) out += '\\"';
    else if (c === 0x5c) out += "\\\\";
    else if (c === 0x08) out += "\\b";
    else if (c === 0x0c) out += "\\f";
    else if (c === 0x0a) out += "\\n";
    else if (c === 0x0d) out += "\\r";
    else if (c === 0x09) out += "\\t";
    else if (c < 0x20) {
      out += "\\u" + HEX[(c >> 12) & 0xf] + HEX[(c >> 8) & 0xf] + HEX[(c >> 4) & 0xf] + HEX[c & 0xf];
    } else {
      // Literal, including non-ASCII (UTF-8 emitted on hash) and U+2028/U+2029
      // (Python's ensure_ascii=False does NOT escape these; neither do we).
      out += s[i];
    }
  }
  return out + '"';
}

function compareByCodePoint(a: string, b: string): number {
  const ac = Array.from(a, (c) => c.codePointAt(0)!);
  const bc = Array.from(b, (c) => c.codePointAt(0)!);
  const n = Math.min(ac.length, bc.length);
  for (let i = 0; i < n; i++) {
    if (ac[i] !== bc[i]) return ac[i] - bc[i];
  }
  return ac.length - bc.length;
}

function serialize(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "string") return escapeString(value);
  if (typeof value === "number") {
    if (!Number.isInteger(value)) {
      throw new Error(
        "canonicalize: non-integer numbers are not allowed (ISNAD audit records never contain floats)",
      );
    }
    return String(value);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  if (Array.isArray(value)) {
    return "[" + value.map(serialize).join(",") + "]";
  }
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj);
    keys.sort(compareByCodePoint);
    return "{" + keys.map((k) => escapeString(k) + ":" + serialize(obj[k])).join(",") + "}";
  }
  throw new Error("canonicalize: unsupported type " + typeof value);
}

/** Serialize a value to ISNAD's canonical (RFC 8785-compatible) JSON form. */
export function canonicalize(value: unknown): string {
  return serialize(value);
}

/** Lowercase hex SHA-256 of UTF-8 text. */
export function sha256Hex(text: string): string {
  return createHash("sha256").update(text, "utf8").digest("hex");
}

/** SHA-256 over the canonical JSON of a value (the audit record hash). */
export function canonicalHash(value: unknown): string {
  return sha256Hex(canonicalize(value));
}
