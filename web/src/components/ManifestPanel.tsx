import { useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { fmtUtcStamp } from '../lib/format';
import type { AnchorInfo, Manifest } from '../lib/types';
import { Card } from './ui';
import { HashChip } from './HashChip';
import { SignatureStatus } from './SignatureStatus';

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[8.5rem_minmax(0,1fr)] gap-3 border-t border-line py-2 first:border-t-0">
      <dt className="text-13 text-ink-2">{label}</dt>
      <dd className="min-w-0 text-15">{children}</dd>
    </div>
  );
}

/** The birth certificate: manifest as a definition list, raw JSON on toggle. */
export function ManifestPanel({
  manifest,
  anchor,
}: {
  manifest: Manifest;
  anchor?: AnchorInfo | null;
}) {
  const [raw, setRaw] = useState(false);
  const params = manifest.params ?? {};
  const paramText = Object.entries(params)
    .map(([key, value]) => `${key}: ${JSON.stringify(value)}`)
    .join(' · ');

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-4">
        <h2 className="font-display text-22 text-ink">Birth certificate</h2>
        <button
          type="button"
          onClick={() => setRaw((v) => !v)}
          className="text-13 text-ink-2 underline decoration-line transition-colors duration-150 ease-out hover:text-ink print:hidden"
        >
          {raw ? 'View certificate' : 'View raw JSON'}
        </button>
      </div>
      {raw ? (
        <pre className="mt-4 overflow-x-auto rounded-input bg-mono-chip p-3 font-mono text-13">
          {JSON.stringify(manifest, null, 2)}
        </pre>
      ) : (
        <dl className="mt-4">
          <Row label="Asset ID">
            <HashChip value={manifest.asset_id} head={10} tail={4} />
          </Row>
          <Row label="Created">
            <span className="tabular-nums">{fmtUtcStamp(manifest.created_utc)}</span>
          </Row>
          <Row label="Creator key">
            <HashChip value={manifest.creator_pubkey} head={12} tail={4} />
          </Row>
          <Row label="Kind">{manifest.kind}</Row>
          <Row label="Prompt">
            <span className="break-words">{manifest.prompt}</span>
          </Row>
          <Row label="Provider">{manifest.provider}</Row>
          <Row label="Model">{manifest.model}</Row>
          <Row label="Params">
            {paramText ? (
              <span className="font-mono text-13">{paramText}</span>
            ) : (
              <span className="text-ink-2">—</span>
            )}
          </Row>
          <Row label="SHA-256">
            <HashChip value={manifest.sha256} head={8} tail={8} />
          </Row>
          <Row label="pHash">
            <HashChip value={manifest.phash64} head={8} tail={4} />
          </Row>
          <Row label="Parent asset">
            {manifest.parent_asset ? (
              <Link
                to={`/asset/${manifest.parent_asset}`}
                className="underline decoration-line transition-colors duration-150 ease-out hover:decoration-ink"
              >
                {manifest.parent_asset}
              </Link>
            ) : (
              <span className="text-ink-2">none — first of its line</span>
            )}
          </Row>
          <Row label="Run">
            <HashChip value={manifest.run_id} head={10} tail={4} />
          </Row>
          <Row label="Retention lock">
            <span className="tabular-nums">{fmtUtcStamp(manifest.retain_until)}</span>
          </Row>
          {anchor && (
            <Row label="Merkle anchor">
              <span className="flex flex-wrap items-center gap-1.5">
                <span>batch #{anchor.batch}</span>
                <HashChip value={anchor.merkle_root} head={8} tail={4} />
              </span>
            </Row>
          )}
          <Row label="Signature">
            <span className="flex flex-wrap items-center gap-2">
              <HashChip value={manifest.signature} head={8} tail={8} />
              <SignatureStatus record={manifest as unknown as Record<string, unknown>} />
            </span>
          </Row>
        </dl>
      )}
    </Card>
  );
}
