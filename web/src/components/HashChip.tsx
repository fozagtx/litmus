import type { MouseEvent } from 'react';
import { truncMiddle } from '../lib/format';
import { useToast } from './Toast';

interface HashChipProps {
  value: string | null | undefined;
  /** Characters kept before the ellipsis (default 4). */
  head?: number;
  /** Characters kept after the ellipsis (default 4; 0 = plain prefix). */
  tail?: number;
  className?: string;
}

/** Mono pill for hashes, keys, and IDs. Middle-truncated, copies on click.
 * Renders nothing for absent values (audio assets have no pHash, the first
 * receipt in a chain has no predecessor hash). */
export function HashChip({ value, head = 4, tail = 4, className = '' }: HashChipProps) {
  const toast = useToast();

  if (!value) return null;

  const copy = async (event: MouseEvent<HTMLButtonElement>) => {
    // Chips can sit inside links/cards; copying must not navigate.
    event.preventDefault();
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(value);
      toast('Copied.');
    } catch {
      toast('Copy failed.');
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      title={value}
      className={`inline-flex max-w-full cursor-pointer items-center rounded-full bg-mono-chip px-2.5 py-0.5 font-mono text-13 text-ink transition-colors duration-150 ease-out hover:bg-line ${className}`}
    >
      <span className="truncate">{truncMiddle(value, head, tail)}</span>
    </button>
  );
}
