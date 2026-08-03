#!/usr/bin/env python3
"""Generate the Litmus Ed25519 signing keypair.

Writes the private key (PEM, mode 0600) to SIGNING_KEY_PATH (default
data/signing_key.pem) and prints the public key + fingerprint. Refuses to
overwrite an existing key unless --force is passed, the key is the trust
root for every sealed record.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import signing_key_path  # noqa: E402
from server.signing import fingerprint, generate_keypair, public_key_b64  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Litmus Ed25519 signing key.")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing key (DESTROYS the old trust root)."
    )
    args = parser.parse_args()

    path = signing_key_path()
    if path.exists() and not args.force:
        print(f"Refusing to overwrite existing signing key at {path}.")
        print("Every record sealed so far was signed with it. Pass --force only if")
        print("you understand that previously sealed records will no longer verify")
        print("against the new public key.")
        return 1

    generate_keypair(path)
    print(f"Ed25519 signing key written to {path} (mode 0600)")
    print(f"public key (base64, raw 32 bytes): {public_key_b64()}")
    print(f"fingerprint (sha256 first 16 hex): {fingerprint()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
