/** TypeScript shape of the ISNAD audit record (audit-record-v1). */

export interface GradingStrategy {
  name: string;
  version: string;
  parameters: Record<string, unknown>;
}

export interface ChainNodeAudit {
  narrator_id: string;
  narrator_type: string;
  grade: string;
  grade_rationale: string;
  model_identifier?: string | null;
  model_version?: string | null;
  invocation_timestamp?: string | null;
  input_hash?: string | null;
  output_hash?: string | null;
  upstream_ids?: string[];
}

export interface WeakestLink {
  narrator_id: string;
  grade: string;
  why: string;
}

export interface SourceDocument {
  uri: string;
  retrieved_at?: string | null;
  content_hash?: string | null;
  licence?: string | null;
}

export interface HumanOversight {
  actor_ref: string;
  action: string;
  timestamp: string;
  note?: string;
}

export interface Environment {
  isnad_version: string;
  python_version: string;
  platform: string;
}

export interface Integrity {
  record_hash: string;
  hash_algorithm?: string;
  canonicalisation?: string;
  detached_signature?: string | null;
}

export interface AuditRecord {
  record_id: string;
  record_version: string;
  generated_at: string;
  claim_id: string;
  claim_text: string;
  final_grade: string;
  grading_strategy: GradingStrategy;
  chain: ChainNodeAudit[];
  weakest_link: WeakestLink;
  source_documents: SourceDocument[];
  human_oversight: HumanOversight[];
  environment: Environment;
  integrity?: Integrity;
}

export const RECORD_VERSION = "1.0";
export const SCHEMA_VERSION = "audit-record-v1";
