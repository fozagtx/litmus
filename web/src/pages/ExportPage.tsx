import { useEffect, useState } from 'react';
import { api, GENERIC_ERROR } from '../lib/api';
import { Button, primaryClass } from '../components/ui';

type Phase =
  | { kind: 'idle' }
  | { kind: 'working'; exportId: string }
  | { kind: 'ready'; url: string }
  | { kind: 'error'; message: string };

export default function ExportPage() {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });

  useEffect(() => {
    if (phase.kind !== 'working') return;
    const exportId = phase.exportId;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const status = await api.exportStatus(exportId);
        if (cancelled) return;
        if (status.download_url) {
          setPhase({ kind: 'ready', url: status.download_url });
        } else if (status.error || status.status === 'failed') {
          setPhase({ kind: 'error', message: status.error || GENERIC_ERROR });
        }
      } catch {
        /* keep polling; transient errors shouldn't kill the export */
      }
    }, 1500);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [phase]);

  const start = async () => {
    try {
      const res = await api.startExport();
      setPhase({ kind: 'working', exportId: res.export_id });
    } catch (err) {
      setPhase({
        kind: 'error',
        message: err instanceof Error ? err.message : GENERIC_ERROR,
      });
    }
  };

  return (
    <div className="mx-auto w-full max-w-xl px-4 py-16 sm:px-6">
      <h1 className="font-display text-30 text-ink">Take everything with you.</h1>
      <p className="mt-4 text-17 text-ink-2">
        Your export contains every asset, manifest, receipt, and Merkle proof in your
        vault, plus a small offline script that verifies all of it without us. If Litmus
        disappeared tomorrow, this archive would still prove what you made, and when.
      </p>

      <div className="mt-8">
        {phase.kind === 'ready' ? (
          <div className="fade-in space-y-3">
            <p className="text-15 text-seal">Your archive is ready.</p>
            <a href={phase.url} download className={primaryClass}>
              Download archive (.zip)
            </a>
          </div>
        ) : (
          <div className="space-y-3">
            {phase.kind === 'error' && (
              <p className="text-15 text-danger">{phase.message}</p>
            )}
            <Button
              variant="primary"
              onClick={start}
              disabled={phase.kind === 'working'}
            >
              Export vault (.zip)
            </Button>
            {phase.kind === 'working' && (
              <p className="text-13 text-ink-2">
                Assembling your archive. This can take a moment for large vaults.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
