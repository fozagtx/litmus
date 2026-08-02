export type RunStatus = 'queued' | 'running' | 'complete' | 'failed';

export type StepStatus =
  | 'queued'
  | 'running'
  | 'passed'
  | 'retried'
  | 'failed'
  | 'discarded';

export interface RunStep {
  seq: number;
  name: string;
  label: string | null;
  provider: string | null;
  model: string | null;
  status: StepStatus;
  started_utc: string | null;
  ended_utc: string | null;
  duration_ms: number | null;
  receipt_key: string | null;
  receipt_sha256: string | null;
  detail: Record<string, unknown> | null;
}

export interface RunState {
  run_id: string;
  status: RunStatus;
  prompt: string;
  narration: boolean;
  narration_text: string | null;
  created_utc: string;
  updated_utc: string;
  steps: RunStep[];
  asset_id: string | null;
  audio_asset_id: string | null;
  error: string | null;
}

export interface AssetSummary {
  asset_id: string;
  kind: string;
  status: string;
  prompt: string;
  created_utc: string;
  thumb_url: string | null;
  media_url: string | null;
  sha256: string;
  phash64: string;
  retain_until: string;
  has_lineage: boolean;
  parent_asset: string | null;
  run_id: string;
}

export interface Manifest {
  schema?: string;
  asset_id: string;
  created_utc: string;
  creator_pubkey: string;
  kind: string;
  prompt: string;
  provider: string;
  model: string;
  params: Record<string, unknown> | null;
  sha256: string;
  phash64: string;
  parent_asset: string | null;
  run_id: string;
  retain_until: string;
  signature: string;
}

export interface Receipt {
  schema?: string;
  run_id: string;
  seq: number;
  step: string;
  ts_utc: string;
  provider: string | null;
  model: string | null;
  input_sha256: string | null;
  output_sha256: string | null;
  detail: Record<string, unknown> | null;
  prev_receipt_sha256: string | null;
  signature: string;
}

/** Merkle proof entries: the backend contract does not pin a shape, so the
 *  verifier accepts bare hex strings or objects carrying hash + position. */
export type MerkleProofEntry =
  | string
  | {
      position?: string;
      side?: string;
      dir?: string;
      hash?: string;
      sha256?: string;
      value?: string;
      sibling?: string;
      left?: string;
      right?: string;
    };

export interface AnchorInfo {
  batch: string;
  merkle_root: string;
  proof?: MerkleProofEntry[];
  anchor_key?: string;
  leaf_count?: number;
  [key: string]: unknown;
}

export type LineageNode = string | ({ asset_id: string } & Partial<AssetSummary>);

export interface Lineage {
  parents: LineageNode[];
  children: LineageNode[];
  discarded: LineageNode[];
}

export interface AssetDetailPayload {
  asset: AssetSummary;
  manifest: Manifest;
  receipts: Receipt[];
  lineage: Lineage;
  anchor: AnchorInfo | null;
}

export interface Verdict {
  verdict: 'exact' | 'perceptual' | 'none';
  similarity?: number;
  distance?: number;
  uploaded: { sha256: string; phash64?: string };
  asset?: AssetSummary;
  manifest?: Manifest;
  receipts?: Receipt[];
  anchor?: AnchorInfo;
}

export interface PubkeyInfo {
  pubkey_b64: string;
  fingerprint: string;
  algorithm: string;
}

export interface ExportStatus {
  status: string;
  download_url?: string | null;
  error?: string | null;
}
