import { useCallback, useEffect, useState } from 'react';
import { api, GENERIC_ERROR } from '../lib/api';
import type { AssetSummary } from '../lib/types';
import { AssetCard } from '../components/AssetCard';
import { Card, ErrorNote, LinkButton } from '../components/ui';
import { SkeletonRows } from '../components/SkeletonRows';

const EMPTY_COPY =
  'Nothing in the vault yet. Generate your first asset and it will appear here with its birth certificate: sealed, signed, and yours to export at any time.';

export default function Vault() {
  const [kind, setKind] = useState('');
  const [hasLineage, setHasLineage] = useState(false);
  const [assets, setAssets] = useState<AssetSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setAssets(null);
    setError(null);
    api
      .assets({ kind: kind || undefined, hasLineage })
      .then((res) => {
        const sorted = [...res.assets].sort((a, b) =>
          b.created_utc.localeCompare(a.created_utc),
        );
        setAssets(sorted);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : GENERIC_ERROR);
      });
  }, [kind, hasLineage]);

  useEffect(() => {
    load();
  }, [load]);

  const filtersActive = kind !== '' || hasLineage;

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-10 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <h1 className="font-display text-30 text-ink">Vault</h1>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-13 text-ink-2">
            Type
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value)}
              className="rounded-input border border-line bg-white px-2 py-1.5 text-15 text-ink"
            >
              <option value="">All</option>
              <option value="image">Image</option>
              <option value="audio">Audio</option>
              <option value="composite">Composite</option>
            </select>
          </label>
          <label className="flex items-center gap-2 text-15 text-ink">
            <input
              type="checkbox"
              checked={hasLineage}
              onChange={(event) => setHasLineage(event.target.checked)}
              className="accent-ink"
            />
            Has lineage
          </label>
        </div>
      </div>

      <div className="mt-8">
        {error ? (
          <ErrorNote message={error} onRetry={load} />
        ) : assets === null ? (
          <SkeletonRows />
        ) : assets.length === 0 ? (
          <Card className="p-10 text-center">
            {filtersActive ? (
              <p className="mx-auto max-w-xl text-17 text-ink-2">
                No sealed assets match these filters. Clear them to see everything in the
                vault.
              </p>
            ) : (
              <>
                <p className="mx-auto max-w-xl text-17 text-ink-2">{EMPTY_COPY}</p>
                <LinkButton to="/studio" className="mt-6">
                  Open the studio
                </LinkButton>
              </>
            )}
          </Card>
        ) : (
          <div className="fade-in grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
            {assets.map((asset) => (
              <AssetCard key={asset.asset_id} asset={asset} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
