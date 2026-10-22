"""Daily OpenRouter price watcher — diff live models vs cache and notify."""

from __future__ import annotations

import json
import time

from core.logger import get_logger
from memory.config_manager import get_base_dir
from memory.openrouter_text import fetch_models

logger = get_logger(__name__)

CACHE = get_base_dir() / "memory" / "openrouter_prices.json"
META = get_base_dir() / "memory" / "openrouter_prices_meta.json"

_PRICING_KEYS = [
    "prompt",
    "completion",
    "input_cache_read",
    "input_cache_write",
    "image",
    "request",
]

_LABELS = {
    "prompt": "input",
    "completion": "output",
    "input_cache_read": "cache read",
    "input_cache_write": "cache write",
    "image": "image",
    "request": "request",
}


def _price_float(v: object) -> float:
    try:
        return float(str(v))  # type: ignore[arg-type]
    except (ValueError, TypeError, AttributeError):
        return 0.0


def _load_prev() -> dict[str, dict]:
    try:
        if not CACHE.exists():
            return {}
        data = json.loads(CACHE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            items = data["data"]
        elif isinstance(data, list):
            items = data
        else:
            return {}
        out: dict[str, dict] = {}
        for m in items:
            mid = str(m.get("id") or "").strip()
            if mid:
                out[mid] = m
        return out
    except Exception as exc:
        logger.warning("openrouter_watcher _load_prev failed: %s", exc)
        return {}


def _extract_pricing(model: dict) -> dict[str, float]:
    pricing = model.get("pricing") or {}
    out: dict[str, float] = {}
    for k in _PRICING_KEYS:
        # raw per-token price -> convert to $/M for display and pct calc
        raw = _price_float(pricing.get(k))
        out[k] = raw * 1_000_000
    return out


def _fmt_per_m(v: float) -> str:
    if v == 0:
        return "--"
    return f"${v:.2f}/M"


def _pct_change(old: float, new: float) -> float | None:
    if old == 0 and new == 0:
        return 0.0
    if old == 0 and new > 0:
        return None
    return (new - old) / old * 100


def _save_cache(models: list[dict]) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(models, indent=2), encoding="utf-8")
        tmp.replace(CACHE)
        meta_tmp = META.with_suffix(".tmp")
        meta_tmp.write_text(
            json.dumps({"fetched_at": int(time.time())}, indent=2),
            encoding="utf-8",
        )
        meta_tmp.replace(META)
    except Exception as exc:
        logger.warning("openrouter_watcher cache write failed: %s", exc)


def check_for_updates(*, force: bool = False) -> str:  # noqa: ARG001
    try:
        live_models = fetch_models()
    except Exception as exc:
        return f"OpenRouter error: {exc}"

    prev = _load_prev()
    live: dict[str, dict] = {}
    for m in live_models:
        mid = str(m.get("id") or "").strip()
        if mid:
            live[mid] = m

    new_models = [mid for mid in live if mid not in prev]
    removed = [mid for mid in prev if mid not in live]

    price_changed: list[dict] = []
    for mid, model in live.items():
        if mid not in prev:
            continue
        old_p = _extract_pricing(prev[mid])
        new_p = _extract_pricing(model)
        changes: list[tuple[str, float, float, float | None]] = []
        for k in _PRICING_KEYS:
            old_v = old_p[k]
            new_v = new_p[k]
            pct = _pct_change(old_v, new_v)
            if pct is None:
                changes.append((k, old_v, new_v, None))
            elif pct == 0:
                continue
            elif abs(pct) > 1.0:
                changes.append((k, old_v, new_v, pct))
        if changes:
            price_changed.append(
                {
                    "id": mid,
                    "old_pricing": old_p,
                    "new_pricing": new_p,
                    "changes": changes,
                }
            )

    if not new_models and not removed and not price_changed:
        return f"No changes \u2014 {len(live)} models checked at {time.strftime('%Y-%m-%d %H:%M')}"

    _save_cache(live_models)

    header_parts = [f"{len(new_models)} new", f"{len(price_changed)} price changes"]
    if removed:
        header_parts.append(f"{len(removed)} removed")
    header = f"\U0001f514 OpenRouter update ({', '.join(header_parts)}):"

    lines: list[str] = [header]

    # new models — limit 10
    for mid in sorted(new_models)[:10]:
        m = live[mid]
        pricing = _extract_pricing(m)
        ctx = m.get("context_length")
        ctx_s = str(ctx) if ctx is not None else "--"
        lines.append(
            f"- NEW: {mid} \u2014 input {_fmt_per_m(pricing['prompt'])}, "
            f"output {_fmt_per_m(pricing['completion'])}, context {ctx_s}"
        )
    if len(new_models) > 10:
        lines.append(f"  ... and {len(new_models) - 10} more new models")

    # price changes — limit 10
    for entry in price_changed[:10]:
        mid = entry["id"]
        changes = entry["changes"]
        parts: list[str] = []
        for k, old_v, new_v, pct in changes:
            label = _LABELS.get(k, k)
            old_s = _fmt_per_m(old_v)
            new_s = _fmt_per_m(new_v)
            if pct is None:
                parts.append(f"{label} {old_s} -> {new_s} (new)")
            else:
                parts.append(f"{label} {old_s} -> {new_s} ({pct:+.1f}%)")
        lines.append(f"- PRICE {mid}: " + ", ".join(parts))
    if len(price_changed) > 10:
        lines.append(f"  ... and {len(price_changed) - 10} more price changes")

    for mid in sorted(removed)[:10]:
        lines.append(f"- REMOVED: {mid}")
    if len(removed) > 10:
        lines.append(f"  ... and {len(removed) - 10} more removed")

    message = "\n".join(lines)
    if len(message) > 1500:
        message = message[:1497] + "..."

    try:
        from core.alert_delivery import write_trigger

        write_trigger(message, source="openrouter_watcher")
    except Exception as exc:
        logger.warning("openrouter_watcher write_trigger failed: %s", exc)

    logger.info("openrouter_watcher: %s", message.replace("\n", " | "))

    return message


check_and_notify = check_for_updates

if __name__ == "__main__":
    print(check_for_updates())
