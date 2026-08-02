import { useEffect, useRef, useState } from 'react';
import { api } from '../lib/api';
import type { RunState } from '../lib/types';

const isTerminal = (s: RunState | null): boolean =>
  !!s && (s.status === 'complete' || s.status === 'failed');

/**
 * Subscribe to a run: SSE first (each message is the full RunState JSON,
 * server closes on terminal status), with a 1s polling fallback if the
 * stream drops mid-run.
 */
export function useRunStream(runId: string | null): RunState | null {
  const [run, setRun] = useState<RunState | null>(null);
  const latest = useRef<RunState | null>(null);

  useEffect(() => {
    latest.current = null;
    setRun(null);
    if (!runId) return;

    let disposed = false;
    let pollTimer: number | undefined;

    const update = (state: RunState) => {
      if (disposed) return;
      latest.current = state;
      setRun(state);
    };

    // Initial snapshot so the timeline renders before the first SSE message.
    api
      .run(runId)
      .then((state) => {
        if (latest.current === null) update(state);
      })
      .catch(() => {
        /* the stream or poller will surface state */
      });

    const es = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events`);

    es.onmessage = (event) => {
      try {
        const state = JSON.parse(event.data) as RunState;
        update(state);
        if (isTerminal(state)) es.close();
      } catch {
        /* ignore malformed frames */
      }
    };

    es.onerror = () => {
      es.close();
      if (isTerminal(latest.current) || disposed) return;
      if (pollTimer === undefined) {
        pollTimer = window.setInterval(async () => {
          try {
            const state = await api.run(runId);
            update(state);
            if (isTerminal(state) && pollTimer !== undefined) {
              window.clearInterval(pollTimer);
              pollTimer = undefined;
            }
          } catch {
            /* keep polling */
          }
        }, 1000);
      }
    };

    return () => {
      disposed = true;
      es.close();
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
    };
  }, [runId]);

  return run;
}
