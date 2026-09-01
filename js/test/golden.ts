import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

export interface Golden {
  canon_a: string;
  hash_a: string;
  hmac_a: string;
  ed25519_pub_raw_hex: string;
  ed25519_sig_a_hex: string;
  canon_b: string;
  hash_b: string;
  merkle_empty: string;
  merkle_batch_root: string;
  merkle_sealed_prev_root: string | null;
  merkle_proof_record_id: string;
  merkle_proof_record_hash: string;
  merkle_proof_leaf_index: number;
  merkle_proof_audit_path: [string, "left" | "right"][];
  record_a_full: any;
  record_b_full: any;
  record_c_full: any;
}

const here = dirname(fileURLToPath(import.meta.url));
export const golden: Golden = JSON.parse(readFileSync(join(here, "golden.json"), "utf8"));
