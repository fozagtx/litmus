import { useEffect, useState } from 'react';
import { getPubkey } from '../lib/api';
import { verifySignedRecord } from '../lib/crypto';

type State = 'checking' | 'ok' | 'fail' | 'unavailable';

/** Ed25519 check of one signed record, done in this browser. */
export function SignatureStatus({ record }: { record: Record<string, unknown> }) {
  const [state, setState] = useState<State>('checking');

  useEffect(() => {
    let cancelled = false;
    setState('checking');
    getPubkey()
      .then((pk) => {
        if (cancelled) return;
        setState(verifySignedRecord(record, pk.pubkey_b64) ? 'ok' : 'fail');
      })
      .catch(() => {
        if (!cancelled) setState('unavailable');
      });
    return () => {
      cancelled = true;
    };
  }, [record]);

  if (state === 'checking') {
    return <span className="whitespace-nowrap text-13 text-ink-2">checking…</span>;
  }
  if (state === 'ok') {
    return (
      <span className="whitespace-nowrap text-13 font-medium text-seal">
        ✓ verified in-browser
      </span>
    );
  }
  if (state === 'unavailable') {
    return (
      <span className="whitespace-nowrap text-13 text-ink-2">
        public key unavailable — not checked
      </span>
    );
  }
  return (
    <span className="whitespace-nowrap text-13 font-medium text-danger">
      signature check failed in-browser
    </span>
  );
}
