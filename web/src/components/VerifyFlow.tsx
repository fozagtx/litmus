import { useEffect, useRef, useState } from 'react';
import { api, GENERIC_ERROR } from '../lib/api';
import { sha256HexOfFile } from '../lib/crypto';
import type { Verdict } from '../lib/types';
import { Button } from './ui';
import { DropZone } from './DropZone';
import { HashChip } from './HashChip';
import { SkeletonRows } from './SkeletonRows';
import { VerdictCard } from './VerdictCard';

type Phase =
  | { kind: 'idle' }
  | { kind: 'working'; fileName: string; clientSha: string | null; previewUrl: string }
  | { kind: 'error'; message: string }
  | { kind: 'done'; verdict: Verdict; clientSha: string | null; previewUrl: string };

const MAX_BYTES = 25 * 1024 * 1024;

/** Drop zone → skeleton ledger rows → verdict card. Used on / and /verify. */
export function VerifyFlow({ fullBleed = false }: { fullBleed?: boolean }) {
  const [phase, setPhase] = useState<Phase>({ kind: 'idle' });
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    };
  }, []);

  const reset = () => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setPhase({ kind: 'idle' });
  };

  const handleFile = async (file: File) => {
    if (!/^image\/(png|jpe?g|webp)$/.test(file.type)) {
      setPhase({
        kind: 'error',
        message: "That file type isn't supported yet. Drop a PNG, JPEG, or WebP image.",
      });
      return;
    }
    if (file.size > MAX_BYTES) {
      setPhase({
        kind: 'error',
        message:
          'Files up to 25 MB for now. For anything larger, verification by hash is in the docs.',
      });
      return;
    }
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    const previewUrl = URL.createObjectURL(file);
    previewUrlRef.current = previewUrl;
    setPhase({ kind: 'working', fileName: file.name, clientSha: null, previewUrl });

    // Compute SHA-256 in the browser and show it while the server works.
    sha256HexOfFile(file)
      .then((sha) => {
        setPhase((p) => (p.kind === 'working' ? { ...p, clientSha: sha } : p));
      })
      .catch(() => {
        /* the server hash still arrives with the verdict */
      });

    try {
      const verdict = await api.verify(file);
      setPhase((p) => ({
        kind: 'done',
        verdict,
        previewUrl,
        clientSha: p.kind === 'working' ? p.clientSha : null,
      }));
    } catch (err) {
      setPhase({
        kind: 'error',
        message: err instanceof Error ? err.message : GENERIC_ERROR,
      });
    }
  };

  return (
    <div>
      {phase.kind === 'idle' && <DropZone onFile={handleFile} fullBleed={fullBleed} />}

      {phase.kind === 'working' && (
        <div className="fade-in space-y-3">
          <div className="flex flex-wrap items-center gap-2 text-13 text-ink-2">
            <span className="max-w-xs truncate text-15 text-ink">{phase.fileName}</span>
            <span>SHA-256</span>
            {phase.clientSha ? (
              <HashChip value={phase.clientSha} head={8} tail={8} />
            ) : (
              <span>computing in your browser…</span>
            )}
          </div>
          <SkeletonRows />
        </div>
      )}

      {phase.kind === 'error' && (
        <div className="fade-in rounded-card border border-line bg-white p-6">
          <p className="text-15 text-danger">{phase.message}</p>
          <Button className="mt-4" onClick={reset}>
            Try another file
          </Button>
        </div>
      )}

      {phase.kind === 'done' && (
        <div className="space-y-4">
          <VerdictCard
            verdict={phase.verdict}
            previewUrl={phase.previewUrl}
            clientSha={phase.clientSha}
          />
          <Button onClick={reset}>Verify another file</Button>
        </div>
      )}

      <p className="mt-4 text-13 text-ink-2">
        Heavy crops, mirrors, and rotations can defeat perceptual matching.
      </p>
    </div>
  );
}
