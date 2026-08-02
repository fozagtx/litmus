import { thumbSrc } from '../lib/api';
import { fmtAnchorLocked, similarityPercent } from '../lib/format';
import type { Verdict } from '../lib/types';
import { HashChip } from './HashChip';
import { ManifestPanel } from './ManifestPanel';
import { MerkleCheck } from './MerkleCheck';
import { ReceiptChain } from './ReceiptChain';

const TONE: Record<Verdict['verdict'], string> = {
  exact: 'border-seal bg-seal-tint',
  perceptual: 'border-amber bg-amber-tint',
  none: 'border-line bg-white',
};

/** The hero verdict card (§7.2 rule 8, §8.5 verbatim copy). */
export function VerdictCard({
  verdict,
  previewUrl,
  clientSha,
}: {
  verdict: Verdict;
  previewUrl: string | null;
  clientSha: string | null;
}) {
  const kind = verdict.verdict;
  const pct = similarityPercent(verdict.similarity, verdict.distance);
  const match = kind === 'exact' || kind === 'perceptual';
  const anchor = verdict.anchor;

  const heading =
    kind === 'exact'
      ? 'Verified — original file.'
      : kind === 'perceptual'
        ? 'Verified — modified copy.'
        : 'No record found.';

  const body =
    kind === 'exact'
      ? 'This file matches a sealed record bit for bit. Its full history is below.'
      : kind === 'perceptual'
        ? `This file is a close derivative of a sealed original${
            pct !== null ? ` (similarity ${pct}%)` : ''
          }. It has been re-encoded, cropped, or resized since sealing. The original and its history are below.`
        : "This vault holds no sealed record matching this file. That doesn't prove the file is AI-generated or authentic — only that it wasn't sealed here.";

  return (
    <div className="fade-in">
      <section className={`rounded-card border p-8 sm:p-12 ${TONE[kind]}`}>
        <h2 className="font-display text-30 text-ink sm:text-44">{heading}</h2>
        <p className="mt-3 max-w-2xl text-17 text-ink">{body}</p>

        <div className="mt-6 flex flex-wrap items-center gap-2 text-13 text-ink-2">
          <span>Uploaded file SHA-256</span>
          <HashChip value={clientSha ?? verdict.uploaded.sha256} head={8} tail={8} />
          {clientSha && <span>computed in your browser</span>}
        </div>

        {kind === 'perceptual' && verdict.asset && (
          <div className="mt-6 grid max-w-xl grid-cols-2 gap-4">
            <figure className="min-w-0">
              {previewUrl && (
                <img
                  src={previewUrl}
                  alt="Uploaded copy"
                  className="aspect-square w-full rounded-input border border-line bg-white object-contain"
                />
              )}
              <figcaption className="mt-1 text-13 text-ink-2">Uploaded copy</figcaption>
            </figure>
            <figure className="min-w-0">
              <img
                src={thumbSrc(verdict.asset)}
                alt="Sealed original"
                className="aspect-square w-full rounded-input border border-line bg-white object-contain"
              />
              <figcaption className="mt-1 text-13 text-ink-2">
                Sealed original{pct !== null ? ` · similarity ${pct}%` : ''}
              </figcaption>
            </figure>
          </div>
        )}

        {match && anchor && (
          <div className="mt-6 space-y-1.5">
            <p className="text-15 text-ink">
              Independently verifiable: sealed in batch #{anchor.batch}, Merkle root{' '}
              <HashChip value={anchor.merkle_root} head={8} tail={4} />, locked{' '}
              {fmtAnchorLocked(anchor)} UTC.
            </p>
            <MerkleCheck anchor={anchor} manifest={verdict.manifest ?? null} />
          </div>
        )}
      </section>

      {match && verdict.manifest && (
        <div className="mt-6 space-y-6">
          <ManifestPanel manifest={verdict.manifest} anchor={anchor ?? null} />
          <ReceiptChain receipts={verdict.receipts ?? []} />
        </div>
      )}
    </div>
  );
}
