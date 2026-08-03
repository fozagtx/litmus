import type {
  AssetDetailPayload,
  AssetSummary,
  ExportStatus,
  PubkeyInfo,
  RunState,
  Verdict,
} from './types';

/** §8.6 generic error copy, used verbatim for any unexplained failure. */
export const GENERIC_ERROR =
  'Something failed on our side. Nothing was lost: your vault only ever gains records, it never loses them.';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, GENERIC_ERROR);
  }
  if (!res.ok) {
    let message = GENERIC_ERROR;
    try {
      const body: unknown = await res.json();
      if (body && typeof body === 'object') {
        const b = body as Record<string, unknown>;
        if (typeof b.detail === 'string') message = b.detail;
        else if (typeof b.error === 'string') message = b.error;
        else if (typeof b.message === 'string') message = b.message;
      }
    } catch {
      /* keep the generic copy */
    }
    throw new ApiError(res.status, message);
  }
  return (await res.json()) as T;
}

export const api = {
  pubkey: () => request<PubkeyInfo>('/api/pubkey'),

  generate: (body: { prompt: string; narration?: boolean; narration_text?: string }) =>
    request<{ run_id: string }>('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),

  run: (runId: string) => request<RunState>(`/api/runs/${encodeURIComponent(runId)}`),

  runs: () => request<{ runs: RunState[] }>('/api/runs'),

  assets: (params: { kind?: string; hasLineage?: boolean }) => {
    const q = new URLSearchParams();
    if (params.kind) q.set('kind', params.kind);
    if (params.hasLineage) q.set('has_lineage', 'true');
    const qs = q.toString();
    return request<{ assets: AssetSummary[] }>(`/api/assets${qs ? `?${qs}` : ''}`);
  },

  asset: (assetId: string) =>
    request<AssetDetailPayload>(`/api/assets/${encodeURIComponent(assetId)}`),

  verify: (file: File) => {
    const fd = new FormData();
    fd.append('file', file);
    return request<Verdict>('/api/verify', { method: 'POST', body: fd });
  },

  startExport: () => request<{ export_id: string }>('/api/export', { method: 'POST' }),

  exportStatus: (exportId: string) =>
    request<ExportStatus>(`/api/exports/${encodeURIComponent(exportId)}`),
};

let pubkeyPromise: Promise<PubkeyInfo> | null = null;

/** Cached fetch of the service public key used for in-browser verification. */
export function getPubkey(): Promise<PubkeyInfo> {
  if (!pubkeyPromise) {
    pubkeyPromise = api.pubkey().catch((err) => {
      pubkeyPromise = null;
      throw err;
    });
  }
  return pubkeyPromise;
}

export function mediaUrl(assetId: string, name: string): string {
  return `/api/media/${encodeURIComponent(assetId)}/${name}`;
}

export function thumbSrc(asset: { asset_id: string; thumb_url?: string | null }): string {
  return asset.thumb_url || mediaUrl(asset.asset_id, 'thumb.webp');
}
