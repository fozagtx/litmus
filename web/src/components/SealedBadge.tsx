import { IconLock } from '@tabler/icons-react';
import { fmtMonthYear } from '../lib/format';

/** "Sealed" pill; the full form carries the retention date (§8.3). */
export function SealedBadge({
  retainUntil,
  compact = false,
  className = '',
}: {
  retainUntil?: string;
  compact?: boolean;
  className?: string;
}) {
  const label =
    compact || !retainUntil
      ? 'Sealed'
      : `Sealed · cannot be altered until ${fmtMonthYear(retainUntil)}`;
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-seal-tint px-2.5 py-0.5 text-13 font-medium text-seal ${className}`}
    >
      <IconLock size={13} stroke={1.75} aria-hidden />
      {label}
    </span>
  );
}
