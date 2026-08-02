import { useRef } from 'react';
import { IconCircleCheck } from '@tabler/icons-react';
import { fmtDuration } from '../lib/format';
import type { RunState, RunStep, StepStatus } from '../lib/types';
import { HashChip } from './HashChip';

const STATUS_STYLE: Record<StepStatus, string> = {
  queued: 'text-ink-2',
  running: 'text-ink',
  passed: 'text-seal',
  retried: 'text-amber',
  failed: 'text-danger',
  discarded: 'text-ink-2',
};

const STATUS_TEXT: Record<StepStatus, string> = {
  queued: 'queued',
  running: 'running…',
  passed: 'passed',
  retried: 'retried',
  failed: 'failed',
  discarded: 'discarded',
};

function judgeScore(step: RunStep): number | null {
  const detail = step.detail;
  if (detail && typeof detail === 'object') {
    const score = (detail as Record<string, unknown>).score;
    if (typeof score === 'number' && isFinite(score)) return score;
  }
  return null;
}

function isJudgeStep(step: RunStep): boolean {
  return /judge/i.test(step.name) || /judge/i.test(step.label ?? '');
}

/** §8.2 judge-fail note, filled with the real score and reasons. */
function judgeNote(run: RunState, step: RunStep, index: number): string | null {
  if (!isJudgeStep(step)) return null;
  const score = judgeScore(step);
  if (score === null || score >= 70) return null;
  const detail = step.detail as { reasons?: unknown } | null;
  const reasons = Array.isArray(detail?.reasons)
    ? detail.reasons.filter((r): r is string => typeof r === 'string')
    : [];
  const reasonText = reasons.length > 0 ? reasons.join('; ') : 'below threshold';
  const retryFollows =
    step.status === 'retried' ||
    run.steps
      .slice(index + 1)
      .some((s) => /retry/i.test(s.name) || /retry/i.test(s.label ?? ''));
  const tail = retryFollows
    ? ' Retrying with adjusted parameters. The rejected attempt stays in your lineage.'
    : ' The rejected attempt stays in your lineage.';
  return `Judge scored ${score}/100: "${reasonText}."${tail}`;
}

/**
 * Vertical ledger of pipeline steps. When `live`, a receipt that appears for
 * the first time gets the single earned seal-stamp animation, exactly once.
 */
export function RunTimeline({ run, live = false }: { run: RunState; live?: boolean }) {
  const preexisting = useRef<Set<number> | null>(null);
  if (preexisting.current === null) {
    preexisting.current = new Set(
      run.steps.filter((s) => s.receipt_sha256).map((s) => s.seq),
    );
  }

  return (
    <div className="overflow-hidden rounded-card border border-line bg-white">
      {run.steps.length === 0 && (
        <p className="px-4 py-6 text-13 text-ink-2">Waiting for the first step…</p>
      )}
      {run.steps.map((step, index) => {
        const stamp =
          live && !!step.receipt_sha256 && !preexisting.current!.has(step.seq);
        const note = judgeNote(run, step, index);
        const score = judgeScore(step);
        return (
          <div key={step.seq} className={index > 0 ? 'border-t border-line' : ''}>
            <div className="grid grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)_6.5rem_4.5rem_minmax(0,10rem)] items-center gap-x-3 px-4 py-2.5">
              <span className="truncate text-15 text-ink" title={step.label ?? step.name}>
                {step.label || step.name}
              </span>
              <span className="truncate text-13 text-ink-2">
                {[step.provider, step.model].filter(Boolean).join(' / ') || '—'}
              </span>
              <span
                className={`text-13 font-medium tabular-nums ${
                  STATUS_STYLE[step.status] ?? 'text-ink-2'
                }`}
              >
                {STATUS_TEXT[step.status] ?? step.status}
                {isJudgeStep(step) && score !== null ? ` · ${score}/100` : ''}
              </span>
              <span className="text-right font-mono text-13 tabular-nums text-ink-2">
                {fmtDuration(step.duration_ms)}
              </span>
              <span className="flex items-center justify-end gap-1.5">
                {step.receipt_sha256 ? (
                  <span
                    className={`flex items-center gap-1.5 ${stamp ? 'seal-stamp' : ''}`}
                    title="Receipt sealed"
                  >
                    <IconCircleCheck
                      size={15}
                      stroke={2}
                      className="shrink-0 text-seal"
                      aria-hidden
                    />
                    <span className="sr-only">Receipt sealed</span>
                    <HashChip value={step.receipt_sha256} head={8} tail={0} />
                  </span>
                ) : (
                  <span className="text-13 text-ink-2">—</span>
                )}
              </span>
            </div>
            {note && (
              <p className="border-t border-line bg-paper px-4 py-2 text-13 text-ink-2">
                {note}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
