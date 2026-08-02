#!/usr/bin/env python3
"""One-shot B2 account bootstrap using the master application key.

The master key cannot talk to B2's S3-compatible API (which the server uses),
so this script uses the NATIVE B2 API once to:

  1. authorize and discover the account's S3 region,
  2. create the three buckets — the vault with Object Lock enabled at
     creation (irreversible choice) + a COMPLIANCE default retention,
  3. mint a scoped runtime application key for the server,
  4. write B2_REGION / B2_KEY_ID / B2_APP_KEY / bucket names into .env.

Reads B2_MASTER_KEY_ID / B2_MASTER_APP_KEY from .env. Idempotent: existing
buckets are reused (the vault's lock status is verified), and a fresh runtime
key is minted on every run (old ones can be deleted in the B2 console).
Secrets are written to .env only — never printed.
"""

from __future__ import annotations

import base64
import re
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

RUNTIME_KEY_CAPABILITIES = [
    "listBuckets",
    "readBuckets",
    "listFiles",
    "readFiles",
    "shareFiles",
    "writeFiles",
    "deleteFiles",
    "readFileRetentions",
    "writeFileRetentions",
    "readBucketRetentions",
    "writeBucketRetentions",
    "readBucketEncryption",
]

BUCKETS = {
    # short role -> (env var, base name, file lock enabled)
    "assets": ("B2_ASSETS_BUCKET", "litmus-assets", False),
    "vault": ("B2_VAULT_BUCKET", "litmus-vault", True),
    "state": ("B2_STATE_BUCKET", "litmus-state", False),
}


def die(msg: str) -> None:
    print(f"ERROR: {msg}")
    sys.exit(1)


def main() -> int:
    env = dotenv_values(ENV_PATH)
    master_id = (env.get("B2_MASTER_KEY_ID") or "").strip()
    master_key = (env.get("B2_MASTER_APP_KEY") or "").strip()
    if not master_id or not master_key:
        die("B2_MASTER_KEY_ID / B2_MASTER_APP_KEY missing from .env")

    # 1. Authorize (native API) ------------------------------------------------
    basic = base64.b64encode(f"{master_id}:{master_key}".encode()).decode()
    resp = httpx.get(
        "https://api.backblazeb2.com/b2api/v2/b2_authorize_account",
        headers={"Authorization": f"Basic {basic}"},
        timeout=20.0,
    )
    if resp.status_code != 200:
        die(f"b2_authorize_account failed (HTTP {resp.status_code}): {resp.text[:300]}")
    auth = resp.json()
    account_id = auth["accountId"]
    api_url = auth["apiUrl"]
    token = auth["authorizationToken"]
    s3_api_url = auth.get("s3ApiUrl", "")
    m = re.search(r"s3\.([a-z0-9-]+)\.backblazeb2\.com", s3_api_url)
    if not m:
        die(f"could not parse region from s3ApiUrl {s3_api_url!r}")
    region = m.group(1)
    print(f"authorized account {account_id}; S3 region {region}")

    def api(endpoint: str, payload: dict) -> httpx.Response:
        return httpx.post(
            f"{api_url}/b2api/v2/{endpoint}",
            headers={"Authorization": token},
            json=payload,
            timeout=30.0,
        )

    # Existing buckets, for idempotency.
    resp = api("b2_list_buckets", {"accountId": account_id})
    if resp.status_code != 200:
        die(f"b2_list_buckets failed: {resp.text[:300]}")
    existing = {b["bucketName"]: b for b in resp.json()["buckets"]}

    # 2. Buckets ---------------------------------------------------------------
    suffix = account_id[-6:].lower()
    chosen: dict[str, str] = {}
    for role, (env_var, base, lock) in BUCKETS.items():
        configured = (env.get(env_var) or "").strip()
        candidates = [configured] if configured else [base, f"{base}-{suffix}"]
        bucket = None
        for name in candidates:
            if not name:
                continue
            if name in existing:
                bucket = existing[name]
                if lock and not bucket.get("fileLockConfiguration", {}).get(
                    "value", {}
                ).get("isFileLockEnabled"):
                    die(
                        f"bucket {name} exists WITHOUT Object Lock. The lock can "
                        "only be enabled at creation — delete the bucket in the "
                        "B2 console (or choose another name in .env) and rerun."
                    )
                print(f"{role}: reusing existing bucket {name}")
                break
            payload = {
                "accountId": account_id,
                "bucketName": name,
                "bucketType": "allPrivate",
            }
            if lock:
                payload["fileLockEnabled"] = True
            resp = api("b2_create_bucket", payload)
            if resp.status_code == 200:
                bucket = resp.json()
                print(f"{role}: created bucket {name}" + (" (Object Lock ON)" if lock else ""))
                break
            err = resp.json().get("code", "")
            if err == "duplicate_bucket_name":
                print(f"{role}: name {name} is taken globally, trying next candidate")
                continue
            die(f"b2_create_bucket {name} failed: {resp.text[:300]}")
        if bucket is None:
            die(f"could not create a bucket for {role}: all candidate names taken")
        chosen[role] = bucket["bucketName"]

        if lock:
            # COMPLIANCE default retention — per-object headers from the server
            # set explicit dates anyway; the default is belt and braces.
            days = int((env.get("VAULT_RETENTION_DAYS") or "7").strip() or "7")
            resp = api(
                "b2_update_bucket",
                {
                    "accountId": account_id,
                    "bucketId": bucket["bucketId"],
                    "defaultRetention": {
                        "mode": "compliance",
                        "period": {"duration": days, "unit": "days"},
                    },
                },
            )
            if resp.status_code == 200:
                print(
                    f"{role}: default retention set to COMPLIANCE {days} days "
                    "(irreversible per object once written)"
                )
            else:
                die(f"b2_update_bucket (default retention) failed: {resp.text[:300]}")

    # 3. Runtime key -----------------------------------------------------------
    resp = api(
        "b2_create_key",
        {
            "accountId": account_id,
            "keyName": "litmus-runtime",
            "capabilities": RUNTIME_KEY_CAPABILITIES,
        },
    )
    if resp.status_code != 200:
        die(f"b2_create_key failed: {resp.text[:300]}")
    key = resp.json()
    print(f"minted runtime application key {key['applicationKeyId']} (litmus-runtime)")

    # 4. Write .env ------------------------------------------------------------
    updates = {
        "B2_REGION": region,
        "B2_KEY_ID": key["applicationKeyId"],
        "B2_APP_KEY": key["applicationKey"],
        "B2_ASSETS_BUCKET": chosen["assets"],
        "B2_VAULT_BUCKET": chosen["vault"],
        "B2_STATE_BUCKET": chosen["state"],
    }
    for k, v in updates.items():
        set_key(str(ENV_PATH), k, v, quote_mode="never")
    print(f"wrote region, runtime key, and bucket names to {ENV_PATH}")
    print("bootstrap complete — restart the server and check /api/health")
    return 0


if __name__ == "__main__":
    sys.exit(main())
