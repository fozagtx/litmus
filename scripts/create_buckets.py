#!/usr/bin/env python3
"""Create the three Litmus buckets on Backblaze B2 (idempotent).

- B2_ASSETS_BUCKET, B2_STATE_BUCKET: plain buckets.
- B2_VAULT_BUCKET: created WITH Object Lock enabled (cannot be added later),
  then a default COMPLIANCE retention of VAULT_RETENTION_DAYS is applied.

WARNING — COMPLIANCE MODE IS IRREVERSIBLE PER OBJECT. Once an object is
written with a COMPLIANCE retention date, NOBODY — not you, not Litmus, not
Backblaze support — can delete or overwrite it until that date passes.
That is the product. Do not point this at a bucket name you care about
reusing within the retention window.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import boto3  # noqa: E402
from botocore.exceptions import ClientError  # noqa: E402

from server import config  # noqa: E402
from server.config import ConfigError  # noqa: E402


def _client():
    region = config.b2_region()
    return boto3.client(
        "s3",
        endpoint_url=f"https://s3.{region}.backblazeb2.com",
        region_name=region,
        aws_access_key_id=config.b2_key_id(),
        aws_secret_access_key=config.b2_app_key(),
    )


def _create_bucket(client, name: str, object_lock: bool) -> None:
    try:
        kwargs = {"Bucket": name}
        if object_lock:
            kwargs["ObjectLockEnabledForBucket"] = True
        client.create_bucket(**kwargs)
        print(f"  created bucket {name!r}" + (" (Object Lock enabled)" if object_lock else ""))
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  bucket {name!r} already exists — leaving it as is")
            if object_lock:
                _assert_lock_enabled(client, name)
        else:
            raise


def _assert_lock_enabled(client, name: str) -> None:
    try:
        client.get_object_lock_configuration(Bucket=name)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code", "")
        if code == "ObjectLockConfigurationNotFoundError":
            print(
                f"  ERROR: existing bucket {name!r} does NOT have Object Lock enabled.\n"
                "  Object Lock can only be enabled at bucket creation. Choose a new\n"
                "  B2_VAULT_BUCKET name and re-run."
            )
            sys.exit(1)
        raise


def main() -> int:
    for sub in ("b2_assets", "b2_vault", "b2_state"):
        try:
            config.require(sub)
        except ConfigError as exc:
            print(f"ERROR: {exc}")
            return 1

    retention_days = config.vault_retention_days()
    assets, vault, state = config.assets_bucket(), config.vault_bucket(), config.state_bucket()

    print("=" * 72)
    print("WARNING: the vault bucket uses Object Lock in COMPLIANCE mode.")
    print(f"Every sealed object is undeletable for {retention_days} days — by anyone,")
    print("including you and Backblaze support. This is irreversible per object.")
    print("=" * 72)

    client = _client()
    print(f"\nCreating buckets in region {config.b2_region()}:")
    _create_bucket(client, assets, object_lock=False)
    _create_bucket(client, state, object_lock=False)
    _create_bucket(client, vault, object_lock=True)

    client.put_object_lock_configuration(
        Bucket=vault,
        ObjectLockConfiguration={
            "ObjectLockEnabled": "Enabled",
            "Rule": {
                "DefaultRetention": {"Mode": "COMPLIANCE", "Days": retention_days}
            },
        },
    )
    print(
        f"  default retention on {vault!r}: COMPLIANCE, {retention_days} days "
        "(per-object headers are also set on every sealed write)"
    )

    print("\nConfirm these lines in your .env:")
    print(f"  B2_REGION={config.b2_region()}")
    print(f"  B2_ASSETS_BUCKET={assets}")
    print(f"  B2_VAULT_BUCKET={vault}")
    print(f"  B2_STATE_BUCKET={state}")
    print(f"  VAULT_RETENTION_DAYS={retention_days}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
