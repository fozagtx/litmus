import { Link } from 'react-router-dom';
import { IconVolume } from '@tabler/icons-react';
import { thumbSrc } from '../lib/api';
import { firstWords, fmtDate } from '../lib/format';
import type { AssetSummary } from '../lib/types';
import { HashChip } from './HashChip';
import { SealedBadge } from './SealedBadge';

/** Vault grid card: thumb, first-6-words title, date, sealed badge, pHash chip. */
export function AssetCard({ asset }: { asset: AssetSummary }) {
  return (
    <Link
      to={`/asset/${asset.asset_id}`}
      className="block overflow-hidden rounded-card border border-line bg-white transition-colors duration-150 ease-out hover:border-ink-2"
    >
      {asset.kind === 'audio' ? (
        <div className="flex aspect-square items-center justify-center bg-mono-chip">
          <IconVolume size={28} stroke={1.5} className="text-ink-2" aria-hidden />
        </div>
      ) : (
        <img
          src={thumbSrc(asset)}
          alt={asset.prompt}
          loading="lazy"
          className="aspect-square w-full object-cover"
        />
      )}
      <div className="space-y-1.5 border-t border-line p-3">
        <p className="truncate text-15 font-medium text-ink">{firstWords(asset.prompt)}</p>
        <p className="text-13 tabular-nums text-ink-2">{fmtDate(asset.created_utc)}</p>
        <div className="flex flex-wrap items-center gap-1.5">
          <SealedBadge compact />
          <HashChip value={asset.phash64} />
        </div>
      </div>
    </Link>
  );
}
