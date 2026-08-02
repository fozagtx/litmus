import { canonicalize } from './canonical';
import { hexToBytes, sha256HexOfBytes } from './crypto';
import type { AnchorInfo, Manifest, MerkleProofEntry } from './types';

/**
 * Client-side Merkle inclusion check.
 *
 * The API contract fixes the anchor payload as {batch, merkle_root, proof,
 * anchor_key} but does not pin the proof entry shape or the leaf definition,
 * so this verifier is deliberately tolerant:
 *  - entries may be bare hex strings or objects with hash + left/right position
 *  - when an entry carries no position, both concatenation orders are tried
 *  - internal nodes are sha256 over the concatenated raw 32-byte hashes
 */

interface ParsedEntry {
  hash: string;
  pos: 'left' | 'right' | null;
}

function isHex(s: string): boolean {
  const t = s.trim();
  return t.length >= 16 && t.length % 2 === 0 && /^[0-9a-fA-F]+$/.test(t);
}

function parseEntry(entry: MerkleProofEntry): ParsedEntry | null {
  if (typeof entry === 'string') {
    return isHex(entry) ? { hash: entry.trim().toLowerCase(), pos: null } : null;
  }
  if (!entry || typeof entry !== 'object') return null;
  const e = entry as Record<string, unknown>;
  let hash: string | null = null;
  let pos: 'left' | 'right' | null = null;
  for (const key of ['hash', 'sha256', 'value', 'sibling']) {
    const v = e[key];
    if (typeof v === 'string' && isHex(v)) {
      hash = v.trim().toLowerCase();
      break;
    }
  }
  if (!hash) {
    if (typeof e.left === 'string' && isHex(e.left)) {
      hash = e.left.trim().toLowerCase();
      pos = 'left';
    } else if (typeof e.right === 'string' && isHex(e.right)) {
      hash = e.right.trim().toLowerCase();
      pos = 'right';
    }
  }
  if (!hash) return null;
  if (!pos) {
    const p = e.position ?? e.side ?? e.dir;
    if (typeof p === 'string') {
      const pl = p.toLowerCase();
      if (pl.startsWith('l')) pos = 'left';
      else if (pl.startsWith('r')) pos = 'right';
    }
  }
  return { hash, pos };
}

async function hashPair(leftHex: string, rightHex: string): Promise<string> {
  const left = hexToBytes(leftHex);
  const right = hexToBytes(rightHex);
  const joined = new Uint8Array(left.length + right.length);
  joined.set(left, 0);
  joined.set(right, left.length);
  return sha256HexOfBytes(joined);
}

export async function verifyMerkleInclusion(
  leafHex: string,
  proof: MerkleProofEntry[],
  rootHex: string,
): Promise<boolean> {
  const root = rootHex.trim().toLowerCase();
  let candidates = new Set<string>([leafHex.trim().toLowerCase()]);
  for (const entry of proof) {
    const parsed = parseEntry(entry);
    if (!parsed) return false;
    const next = new Set<string>();
    for (const current of candidates) {
      if (parsed.pos === 'left') {
        next.add(await hashPair(parsed.hash, current));
      } else if (parsed.pos === 'right') {
        next.add(await hashPair(current, parsed.hash));
      } else {
        next.add(await hashPair(current, parsed.hash));
        next.add(await hashPair(parsed.hash, current));
      }
    }
    if (next.size === 0 || next.size > 4096) return false;
    candidates = next;
  }
  return candidates.has(root);
}

/** Possible leaf values for an anchored manifest, most authoritative first. */
async function leafCandidates(
  anchor: AnchorInfo,
  manifest: Manifest | null,
): Promise<string[]> {
  const out: string[] = [];
  const a = anchor as Record<string, unknown>;
  for (const key of ['leaf', 'leaf_sha256', 'manifest_sha256', 'sha256']) {
    let v = a[key];
    // The API's proof_for() ships the leaf as {key, sha256}.
    if (v && typeof v === 'object' && 'sha256' in (v as Record<string, unknown>)) {
      v = (v as Record<string, unknown>)['sha256'];
    }
    if (typeof v === 'string' && isHex(v)) out.push(v.trim().toLowerCase());
  }
  if (manifest) {
    const enc = new TextEncoder();
    // sha256 of the canonical manifest JSON (as stored in the vault)
    out.push(await sha256HexOfBytes(enc.encode(canonicalize(manifest))));
    const unsigned: Record<string, unknown> = {};
    const record = manifest as unknown as Record<string, unknown>;
    for (const key of Object.keys(record)) {
      if (key !== 'signature') unsigned[key] = record[key];
    }
    out.push(await sha256HexOfBytes(enc.encode(canonicalize(unsigned))));
    if (isHex(manifest.sha256)) out.push(manifest.sha256.trim().toLowerCase());
  }
  return [...new Set(out)];
}

export type AnchorCheckResult = 'ok' | 'fail' | 'unavailable';

export async function checkAnchor(
  anchor: AnchorInfo,
  manifest: Manifest | null,
): Promise<AnchorCheckResult> {
  if (typeof anchor.merkle_root !== 'string' || !isHex(anchor.merkle_root)) {
    return 'unavailable';
  }
  const proof = anchor.proof;
  if (!Array.isArray(proof)) return 'unavailable';
  const leaves = await leafCandidates(anchor, manifest);
  if (leaves.length === 0) return 'unavailable';
  const root = anchor.merkle_root.trim().toLowerCase();
  if (proof.length === 0) {
    // Single-leaf batch: the root is the leaf itself.
    return leaves.includes(root) ? 'ok' : 'fail';
  }
  for (const leaf of leaves) {
    if (await verifyMerkleInclusion(leaf, proof, root)) return 'ok';
  }
  return 'fail';
}
