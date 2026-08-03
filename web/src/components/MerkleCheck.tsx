import { useEffect, useState } from 'react';
import { checkAnchor, type AnchorCheckResult } from '../lib/merkle';
import type { AnchorInfo, Manifest } from '../lib/types';

type State = AnchorCheckResult | 'checking';

/** Recomputes the Merkle inclusion proof in-browser and reports honestly. */
export function MerkleCheck({
  anchor,
  manifest,
}: {
  anchor: AnchorInfo | null | undefined;
  manifest: Manifest | null;
}) {
  const [state, setState] = useState<State>('checking');

  useEffect(() => {
    let cancelled = false;
    if (!anchor) return;
    setState('checking');
    checkAnchor(anchor, manifest)
      .then((result) => {
        if (!cancelled) setState(result);
      })
      .catch(() => {
        if (!cancelled) setState('fail');
      });
    return () => {
      cancelled = true;
    };
  }, [anchor, manifest]);

  if (!anchor) return null;

  if (state === 'checking') {
    return (
      <p className="text-13 text-ink-2">Recomputing Merkle inclusion in-browser…</p>
    );
  }
  if (state === 'ok') {
    return (
      <p className="text-13 font-medium text-seal">
        ✓ Merkle inclusion recomputed in-browser, proof matches the anchored root.
      </p>
    );
  }
  if (state === 'unavailable') {
    return (
      <p className="text-13 text-ink-2">
        No inclusion proof provided for this record, so it wasn't recomputed here.
      </p>
    );
  }
  return (
    <p className="text-13 text-amber">
      Could not recompute the anchored Merkle root from this proof in-browser.
    </p>
  );
}
