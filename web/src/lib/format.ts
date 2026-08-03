const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

const pad2 = (n: number) => String(n).padStart(2, '0');

/** `a3f9…c21b` style middle truncation (tail 0 = plain prefix). */
export function truncMiddle(value: string, head = 4, tail = 4): string {
  if (value.length <= head + tail + 1) return value;
  return tail > 0 ? `${value.slice(0, head)}…${value.slice(-tail)}` : value.slice(0, head);
}

/** "Mar 2027", for the sealed badge. */
export function fmtMonthYear(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/** "Aug 2, 2026" */
export function fmtDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

/** "2026-08-02 14:00:41 UTC", ledger timestamps. */
export function fmtUtcStamp(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return (
    `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ` +
    `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}:${pad2(d.getUTCSeconds())} UTC`
  );
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '·';
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function firstWords(text: string, count = 6): string {
  const trimmed = text.trim();
  const words = trimmed.split(/\s+/);
  if (words.length <= count) return trimmed;
  return `${words.slice(0, count).join(' ')}…`;
}

/** Whole-number similarity percent from either a 0–1 fraction or a percent. */
export function similarityPercent(
  similarity?: number,
  distance?: number,
): number | null {
  if (typeof similarity === 'number' && isFinite(similarity)) {
    return Math.round(similarity <= 1 ? similarity * 100 : similarity);
  }
  if (typeof distance === 'number' && isFinite(distance)) {
    return Math.round((1 - distance / 64) * 100);
  }
  return null;
}

/** Locked timestamp for the anchor line, derived from the batch id when
 *  it is the hourly "yyyy-mm-ddThh" form, else from any timestamp field. */
export function fmtAnchorLocked(anchor: { batch: string; [key: string]: unknown }): string {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2})$/.exec(anchor.batch);
  if (m) return `${m[1]} ${m[2]}:00`;
  for (const key of ['locked_utc', 'ts_utc', 'created_utc']) {
    const v = anchor[key];
    if (typeof v === 'string') {
      const d = new Date(v);
      if (!isNaN(d.getTime())) {
        return (
          `${d.getUTCFullYear()}-${pad2(d.getUTCMonth() + 1)}-${pad2(d.getUTCDate())} ` +
          `${pad2(d.getUTCHours())}:${pad2(d.getUTCMinutes())}`
        );
      }
    }
  }
  return anchor.batch;
}

/** "0:07" audio clock. */
export function fmtClock(seconds: number): string {
  if (!isFinite(seconds) || seconds < 0) return '0:00';
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${pad2(s)}`;
}
