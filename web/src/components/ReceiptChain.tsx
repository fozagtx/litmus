import { fmtUtcStamp } from '../lib/format';
import type { Receipt } from '../lib/types';
import { Card } from './ui';
import { HashChip } from './HashChip';
import { SignatureStatus } from './SignatureStatus';

/** Ordered ledger of pipeline receipts (§6.5, §8.3). */
export function ReceiptChain({ receipts }: { receipts: Receipt[] }) {
  return (
    <Card className="p-5">
      <h2 className="font-display text-22 text-ink">Receipt chain</h2>
      <p className="mt-1 text-13 text-ink-2">
        Every pipeline decision, signed and locked — including the attempts we threw away.
      </p>
      {receipts.length === 0 ? (
        <p className="mt-4 text-13 text-ink-2">No receipts returned for this record.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-13">
            <thead>
              <tr className="border-b border-line text-ink-2">
                <th scope="col" className="py-2 pr-3 font-medium">
                  Step
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Timestamp
                </th>
                <th scope="col" className="py-2 pr-3 font-medium">
                  Input → output hash
                </th>
                <th scope="col" className="py-2 font-medium">
                  Signature
                </th>
              </tr>
            </thead>
            <tbody>
              {receipts.map((receipt) => (
                <tr
                  key={`${receipt.run_id}-${receipt.seq}`}
                  className="border-b border-line align-top last:border-b-0"
                >
                  <td className="py-2.5 pr-3 whitespace-nowrap">
                    <span className="font-mono tabular-nums text-ink-2">
                      {String(receipt.seq).padStart(2, '0')}
                    </span>{' '}
                    {receipt.step}
                  </td>
                  <td className="py-2.5 pr-3 whitespace-nowrap tabular-nums">
                    {fmtUtcStamp(receipt.ts_utc)}
                  </td>
                  <td className="py-2.5 pr-3">
                    <span className="flex items-center gap-1">
                      {receipt.input_sha256 ? (
                        <HashChip value={receipt.input_sha256} />
                      ) : (
                        <span className="text-ink-2">—</span>
                      )}
                      <span aria-hidden className="text-ink-2">
                        →
                      </span>
                      {receipt.output_sha256 ? (
                        <HashChip value={receipt.output_sha256} />
                      ) : (
                        <span className="text-ink-2">—</span>
                      )}
                    </span>
                  </td>
                  <td className="py-2.5">
                    <SignatureStatus
                      record={receipt as unknown as Record<string, unknown>}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}
