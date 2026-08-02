import * as ed from '@noble/ed25519';
import { sha512 } from '@noble/hashes/sha512';
import { canonicalUnsignedBytes } from './canonical';

// @noble/ed25519 v2 needs a sha512 implementation wired in for sync verify.
ed.etc.sha512Sync = (...messages: Uint8Array[]) => sha512(ed.etc.concatBytes(...messages));

export function b64ToBytes(b64: string): Uint8Array {
  const clean = b64
    .replace(/^ed25519:/, '')
    .replace(/-/g, '+')
    .replace(/_/g, '/')
    .replace(/\s+/g, '');
  const bin = atob(clean);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export function hexToBytes(hex: string): Uint8Array {
  const clean = hex.trim().toLowerCase();
  const out = new Uint8Array(clean.length >> 1);
  for (let i = 0; i < out.length; i++) {
    out[i] = parseInt(clean.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

export function bytesToHex(bytes: Uint8Array): string {
  let hex = '';
  for (const b of bytes) hex += b.toString(16).padStart(2, '0');
  return hex;
}

export async function sha256HexOfBytes(bytes: Uint8Array | ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as BufferSource);
  return bytesToHex(new Uint8Array(digest));
}

export async function sha256HexOfFile(file: File): Promise<string> {
  return sha256HexOfBytes(await file.arrayBuffer());
}

/**
 * Verify the Ed25519 signature on a manifest or receipt in-browser.
 * The signature is base64 over canonical JSON of the record minus `signature`.
 */
export function verifySignedRecord(
  record: Record<string, unknown>,
  pubkeyB64: string,
): boolean {
  const signature = record['signature'];
  if (typeof signature !== 'string' || signature.length === 0) return false;
  try {
    const message = canonicalUnsignedBytes(record);
    return ed.verify(b64ToBytes(signature), message, b64ToBytes(pubkeyB64));
  } catch {
    return false;
  }
}
