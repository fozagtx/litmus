import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { IconChevronDown } from '@tabler/icons-react';
import { api, GENERIC_ERROR, mediaUrl } from '../lib/api';
import { firstWords, fmtUtcStamp } from '../lib/format';
import type { RunState, RunStatus } from '../lib/types';
import { useRunStream } from '../hooks/useRunStream';
import { Button, Card } from '../components/ui';
import { RunTimeline } from '../components/RunTimeline';
import { SealedBadge } from '../components/SealedBadge';
import { HashChip } from '../components/HashChip';

const RUN_STATUS_STYLE: Record<RunStatus, string> = {
  queued: 'text-ink-2',
  running: 'text-ink',
  complete: 'text-seal',
  failed: 'text-danger',
};

const RUN_STATUS_TEXT: Record<RunStatus, string> = {
  queued: 'queued',
  running: 'running…',
  complete: 'complete',
  failed: 'failed',
};

const linkClass =
  'underline decoration-line transition-colors duration-150 ease-out hover:decoration-ink';

function CompletedAssetCard({ run }: { run: RunState }) {
  if (!run.asset_id) return null;
  return (
    <Card className="fade-in overflow-hidden">
      <div className="flex gap-4 p-4">
        <img
          src={mediaUrl(run.asset_id, 'thumb.webp')}
          alt={run.prompt}
          className="h-28 w-28 shrink-0 rounded-input border border-line object-cover"
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <SealedBadge compact />
            <span className="text-13 tabular-nums text-ink-2">
              {fmtUtcStamp(run.updated_utc)}
            </span>
          </div>
          <p className="mt-1.5 truncate text-15 font-medium text-ink">
            {firstWords(run.prompt)}
          </p>
          <p className="mt-1 text-13 text-seal">
            Sealed. This asset now has a permanent, verifiable history.
          </p>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-13 text-ink">
            <Link to={`/asset/${run.asset_id}`} className={linkClass}>
              Birth certificate and lineage
            </Link>
            <Link to="/verify" className={linkClass}>
              Verify
            </Link>
            {run.audio_asset_id && (
              <Link to={`/asset/${run.audio_asset_id}`} className={linkClass}>
                Narration asset
              </Link>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

function HistoryRow({ run }: { run: RunState }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-t border-line first:border-t-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="grid w-full grid-cols-[minmax(0,1fr)_auto_5rem_auto] items-center gap-3 px-4 py-3 text-left"
      >
        <span className="truncate text-15 text-ink">{firstWords(run.prompt, 8)}</span>
        <span className="text-13 tabular-nums text-ink-2">
          {fmtUtcStamp(run.created_utc)}
        </span>
        <span className={`text-13 font-medium ${RUN_STATUS_STYLE[run.status] ?? 'text-ink-2'}`}>
          {RUN_STATUS_TEXT[run.status] ?? run.status}
        </span>
        <IconChevronDown
          size={15}
          stroke={1.75}
          aria-hidden
          className={`text-ink-2 transition-transform duration-150 ease-out ${
            open ? 'rotate-180' : ''
          }`}
        />
      </button>
      {open && (
        <div className="fade-in space-y-3 px-4 pb-4">
          <div className="flex flex-wrap items-center gap-2 text-13 text-ink-2">
            <span>Run</span>
            <HashChip value={run.run_id} head={10} tail={4} />
          </div>
          {run.error && <p className="text-13 text-danger">{run.error}</p>}
          <RunTimeline run={run} />
          {run.asset_id && (
            <Link to={`/asset/${run.asset_id}`} className={`text-13 ${linkClass}`}>
              View sealed asset
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export default function Studio() {
  const [prompt, setPrompt] = useState('');
  const [narration, setNarration] = useState(false);
  const [narrationText, setNarrationText] = useState('');
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const run = useRunStream(activeRunId);
  const [history, setHistory] = useState<RunState[] | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const loadHistory = useCallback(() => {
    api
      .runs()
      .then((res) => {
        const sorted = [...res.runs].sort((a, b) =>
          b.created_utc.localeCompare(a.created_utc),
        );
        setHistory(sorted);
        setHistoryError(null);
      })
      .catch((err) => {
        setHistoryError(err instanceof Error ? err.message : GENERIC_ERROR);
      });
  }, []);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const terminal = run !== null && (run.status === 'complete' || run.status === 'failed');

  useEffect(() => {
    if (terminal) loadHistory();
  }, [terminal, loadHistory]);

  const busy =
    submitting ||
    (activeRunId !== null &&
      (run === null || run.status === 'queued' || run.status === 'running'));

  const onGenerate = async (event: FormEvent) => {
    event.preventDefault();
    if (!prompt.trim() || busy) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      const body: { prompt: string; narration: boolean; narration_text?: string } = {
        prompt: prompt.trim(),
        narration,
      };
      if (narration && narrationText.trim()) body.narration_text = narrationText.trim();
      const res = await api.generate(body);
      setActiveRunId(res.run_id);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : GENERIC_ERROR);
    } finally {
      setSubmitting(false);
    }
  };

  const pastRuns = (history ?? []).filter((r) => r.run_id !== activeRunId);

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-8 px-4 py-10 sm:px-6 lg:grid-cols-[2fr_3fr]">
      {/* Left 40%: prompt card */}
      <Card className="self-start p-5">
        <form onSubmit={onGenerate}>
          <label htmlFor="prompt" className="font-display text-22 text-ink">
            What are we making?
          </label>
          <textarea
            id="prompt"
            rows={4}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="A lighthouse keeper's desk at dawn, tilt-shift, warm film grain…"
            className="mt-3 w-full resize-y rounded-input border border-line bg-white px-3 py-2 text-15 text-ink placeholder:text-ink-2 focus:border-ink focus:outline-none"
          />
          <div className="mt-4">
            <label className="flex items-center gap-2 text-15 text-ink">
              <input
                type="checkbox"
                checked={narration}
                onChange={(event) => setNarration(event.target.checked)}
                className="accent-ink"
              />
              Add narration
            </label>
            <p className="mt-1 text-13 text-ink-2">
              We'll generate a voice track and seal it to the same lineage.
            </p>
            {narration && (
              <textarea
                rows={2}
                value={narrationText}
                onChange={(event) => setNarrationText(event.target.value)}
                placeholder="Defaults to your prompt."
                aria-label="Narration text"
                className="mt-2 w-full resize-y rounded-input border border-line bg-white px-3 py-2 text-15 text-ink placeholder:text-ink-2 focus:border-ink focus:outline-none"
              />
            )}
          </div>
          <p className="mt-4 border-t border-line pt-3 text-13 text-ink-2">
            Anyone who verifies this asset can read its prompt.
          </p>
          {submitError && <p className="mt-3 text-13 text-danger">{submitError}</p>}
          <Button
            type="submit"
            variant="primary"
            disabled={busy || !prompt.trim()}
            className="mt-4 w-full"
          >
            {busy ? 'Sealing as we go…' : 'Generate'}
          </Button>
        </form>
      </Card>

      {/* Right 60%: run timeline + history */}
      <div className="min-w-0 space-y-6">
        {run && run.status === 'complete' && <CompletedAssetCard run={run} />}
        {run && run.status === 'failed' && (
          <div className="fade-in rounded-card border border-line bg-white p-4">
            <p className="text-15 text-danger">{run.error || GENERIC_ERROR}</p>
          </div>
        )}
        {run && (
          <section>
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <h2 className="font-display text-22 text-ink">Run</h2>
              <HashChip value={run.run_id} head={10} tail={4} />
            </div>
            <RunTimeline run={run} live />
          </section>
        )}

        <section>
          <h2 className="font-display text-22 text-ink">History</h2>
          <div className="mt-2">
            {historyError ? (
              <p className="text-15 text-danger">{historyError}</p>
            ) : history === null ? (
              <p className="text-13 text-ink-2">Loading past runs…</p>
            ) : pastRuns.length === 0 && !run ? (
              <Card className="p-6">
                <p className="text-15 text-ink-2">
                  No runs yet. Your first generation will appear here as a step-by-step,
                  receipted timeline, every decision sealed as it happens.
                </p>
              </Card>
            ) : pastRuns.length === 0 ? (
              <p className="text-13 text-ink-2">No earlier runs.</p>
            ) : (
              <Card className="overflow-hidden">
                {pastRuns.map((r) => (
                  <HistoryRow key={r.run_id} run={r} />
                ))}
              </Card>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
