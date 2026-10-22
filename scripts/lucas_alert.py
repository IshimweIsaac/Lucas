#!/usr/bin/env python3
"""CLI for scheduled reminders: notify, sound, trigger, optional wake + snooze."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core import alert_delivery as ad  # noqa: E402
from core import snooze as snooze_mod  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="LUCAS alert delivery")
    parser.add_argument("--message", "-m", required=True, help="Alert text")
    parser.add_argument("--source", default="reminder")
    parser.add_argument("--no-sound", action="store_true")
    parser.add_argument("--no-wake", action="store_true")
    parser.add_argument("--urgent", action="store_true")
    parser.add_argument("--snooze-minutes", type=int, default=0, help="Re-fire after N minutes")
    args = parser.parse_args()

    if args.snooze_minutes > 0:
        snooze_mod.schedule_snooze(args.snooze_minutes, args.message)
        ad.desktop_notify(
            "LUCAS",
            f"Snoozed {args.snooze_minutes} min: {args.message[:80]}",
        )
        return 0

    ad.deliver_alert(
        args.message,
        source=args.source,
        sound=not args.no_sound,
        try_wake=not args.no_wake,
        urgent=args.urgent,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
