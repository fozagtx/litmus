/**
 * Canonical JSON, must EXACTLY match the backend:
 * recursively sort object keys, JSON.stringify with no whitespace, UTF-8 encode.
 * The signature field is removed by the caller before signing/verification.
 */
export function canonicalize(value: unknown): string {
  if (value === null) return 'null';
  const t = typeof value;
  if (t === 'number' || t === 'boolean' || t === 'string') {
    return JSON.stringify(value);
  }
  if (t === 'undefined') return 'null';
  if (Array.isArray(value)) {
    return `[${value.map((v) => canonicalize(v)).join(',')}]`;
  }
  const obj = value as Record<string, unknown>;
  const keys = Object.keys(obj).sort();
  const parts: string[] = [];
  for (const key of keys) {
    const v = obj[key];
    if (v === undefined) continue; // JSON.stringify drops undefined members
    parts.push(`${JSON.stringify(key)}:${canonicalize(v)}`);
  }
  return `{${parts.join(',')}}`;
}

/** Canonical UTF-8 bytes of a record with its `signature` member removed. */
export function canonicalUnsignedBytes(record: Record<string, unknown>): Uint8Array {
  const unsigned: Record<string, unknown> = {};
  for (const key of Object.keys(record)) {
    if (key !== 'signature') unsigned[key] = record[key];
  }
  return new TextEncoder().encode(canonicalize(unsigned));
}
