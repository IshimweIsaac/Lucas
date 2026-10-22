#!/usr/bin/env python3
"""Google Calendar: browser login + sync into Lucas."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core import google_calendar as gc  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Google Calendar → Lucas")
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="OAuth only, do not import events",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Import horizon in days (default 60)",
    )
    args = parser.parse_args()

    if args.login_only:
        print(gc.login())
        return 0

    print(gc.login_and_sync(horizon_days=args.days))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
