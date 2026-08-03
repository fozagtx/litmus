import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, GENERIC_ERROR, mediaUrl } from '../lib/api';
import { firstWords, fmtDate } from '../lib/format';
import type { AssetDetailPayload } from '../lib/types';
import { AudioPlayer } from '../components/AudioPlayer';
import { ErrorNote } from '../components/ui';
import { LineagePanel } from '../components/LineagePanel';
import { ManifestPanel } from '../components/ManifestPanel';
import { ReceiptChain } from '../components/ReceiptChain';
import { SealedBadge } from '../components/SealedBadge';
import { SkeletonRows } from '../components/SkeletonRows';

export default function AssetDetail() {
  const { id } = useParams<{ id: string }>();
  const [detail, setDetail] = useState<AssetDetailPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    setDetail(null);
    setError(null);
    api
      .asset(id)
      .then(setDetail)
      .catch((err) => {
        setError(err instanceof Error ? err.message : GENERIC_ERROR);
      });
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
        <ErrorNote message={error} onRetry={load} />
      </div>
    );
  }

  if (!detail || !id) {
    return (
      <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
        <SkeletonRows />
      </div>
    );
  }

  const { asset, manifest, receipts, lineage, anchor } = detail;
  const isAudio = asset.kind === 'audio';
  const mediaSrc =
    asset.media_url ||
    mediaUrl(asset.asset_id, isAudio ? 'narration.mp3' : 'original.png');

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <div className="grid gap-8 lg:grid-cols-[11fr_9fr] print:block">
        {/* Preview, left 55% */}
        <div className="min-w-0">
          <h1 className="font-display text-30 text-ink">{firstWords(asset.prompt)}</h1>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            <SealedBadge retainUntil={asset.retain_until} />
            <span className="text-13 tabular-nums text-ink-2">
              {fmtDate(asset.created_utc)}
            </span>
            <span className="text-13 text-ink-2">{asset.kind}</span>
          </div>
          <div className="mt-5">
            {isAudio ? (
              <AudioPlayer src={mediaSrc} />
            ) : (
              <img
                src={mediaSrc}
                alt={asset.prompt}
                className="w-full rounded-card border border-line bg-white"
              />
            )}
          </div>
        </div>

        {/* Panels, right 45%, stacked */}
        <div className="min-w-0 space-y-6 print:mt-8">
          <ManifestPanel manifest={manifest} anchor={anchor} />
          <ReceiptChain receipts={receipts} />
          <LineagePanel lineage={lineage} current={asset} />
        </div>
      </div>
    </div>
  );
}
