#!/usr/bin/env python3
"""Rebuild the SQLite index from lm-vault manifests and anchors."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from server.config import ConfigError  # noqa: E402
from server.index import reindex_from_vault  # noqa: E402


def main() -> int:
    try:
        count = reindex_from_vault()
    except ConfigError as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"Reindexed {count} manifests from the vault.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
