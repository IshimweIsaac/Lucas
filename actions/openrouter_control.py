"""Query OpenRouter for models and live pricing."""

from __future__ import annotations

import datetime
import json
import time

from core.logger import get_logger
from memory.config_manager import get_base_dir
from memory.openrouter_text import fetch_models, generate_text_openrouter

logger = get_logger(__name__)

_CACHE_FILE = get_base_dir() / "memory" / "openrouter_prices.json"
_META_FILE = get_base_dir() / "memory" / "openrouter_prices_meta.json"
_TTL = 21600

TOOL_SCHEMA = {
    "name": "openrouter_control",
    "description": (
        "Query OpenRouter for new models and live pricing (input/output/cache). "
        "No key needed for prices; chat requires openrouter key."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action: list_models | latest | price | compare | trends | chat | check_updates",
                "enum": [
                    "list_models",
                    "latest",
                    "price",
                    "compare",
                    "trends",
                    "chat",
                    "check_updates",
                ],
            },
            "model": {
                "type": "STRING",
                "description": "Model id for price/chat e.g. anthropic/claude-3.5-sonnet",
            },
            "model_a": {
                "type": "STRING",
                "description": "First model id for compare",
            },
            "model_b": {
                "type": "STRING",
                "description": "Second model id for compare",
            },
            "n": {
                "type": "NUMBER",
                "description": "Limit for latest/list (default 10 or 5)",
            },
            "query": {
                "type": "STRING",
                "description": "Substring filter on id/name for list_models",
            },
            "message": {
                "type": "STRING",
                "description": "User message for chat action",
            },
            "force_refresh": {
                "type": "BOOLEAN",
                "description": "Bypass cache and fetch live from OpenRouter",
            },
        },
        "required": ["action"],
    },
}


def _price_val(pricing: dict, key: str) -> float:
    raw = pricing.get(key)
    if raw is None or raw == "":
        return 0.0
    try:
        v = float(str(raw)) * 1_000_000
        if v < 0:
            return 0.0
        return v
    except (ValueError, TypeError):
        return 0.0


def _fmt_price(pricing: dict, key: str) -> str:
    v = _price_val(pricing, key)
    if v == 0:
        return "--"
    return f"${v:.2f}/M"


def _fmt_date(ts: int | float | None) -> str:
    if not ts:
        return "--"
    try:
        dt = datetime.datetime.fromtimestamp(int(ts), tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return "--"


def _days_ago(ts: int | float | None) -> str:
    if not ts:
        return "--"
    try:
        delta = time.time() - float(ts)
        days = int(delta // 86400)
        if days <= 0:
            return "today"
        if days == 1:
            return "1d ago"
        return f"{days}d ago"
    except Exception:
        return "--"


def _find_model(models: list[dict], target: str) -> dict | None:
    t = (target or "").strip()
    if t.startswith("openrouter/"):
        t = t[len("openrouter/") :]
    low = t.lower()
    for m in models:
        if str(m.get("id") or "").strip() == t:
            return m
    for m in models:
        mid = str(m.get("id") or "").lower()
        name = str(m.get("name") or "").lower()
        if low in mid or low in name:
            return m
    return None


def _is_stale() -> bool:
    try:
        if not _CACHE_FILE.exists() or not _META_FILE.exists():
            return True
        meta = json.loads(_META_FILE.read_text(encoding="utf-8"))
        fetched = float(meta.get("fetched_at", 0))
        return (time.time() - fetched) > _TTL
    except Exception:
        return True


def _load_cache() -> list[dict] | None:
    try:
        if not _CACHE_FILE.exists():
            return None
        data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("data"), list):
            return data["data"]
        return None
    except Exception:
        return None


def _save_cache(models: list[dict]) -> None:
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(models, indent=2), encoding="utf-8")
        tmp.replace(_CACHE_FILE)
        meta_tmp = _META_FILE.with_suffix(".tmp")
        meta_tmp.write_text(
            json.dumps({"fetched_at": int(time.time())}, indent=2),
            encoding="utf-8",
        )
        meta_tmp.replace(_META_FILE)
    except Exception as exc:
        logger.warning("Cache write failed: %s", exc)


def _get_models(force: bool) -> list[dict]:
    if not force and not _is_stale():
        cached = _load_cache()
        if cached is not None:
            logger.info("OpenRouter cache hit: %d models", len(cached))
            return cached
    models = fetch_models()
    _save_cache(models)
    logger.info("OpenRouter fetched live: %d models", len(models))
    return models


def _table_header() -> str:
    return "| Model | Context | Input $/M | Output $/M | Cache In $/M | Created |"


def _table_sep() -> str:
    return "|---|---|---|---|---|---|"


def _row(m: dict) -> str:
    mid = str(m.get("id") or "--")
    ctx = m.get("context_length")
    ctx_s = str(ctx) if ctx is not None else "--"
    pricing = m.get("pricing") or {}
    inp = _fmt_price(pricing, "prompt")
    out = _fmt_price(pricing, "completion")
    cache = _fmt_price(pricing, "input_cache_read")
    created = _fmt_date(m.get("created"))
    return f"| {mid} | {ctx_s} | {inp} | {out} | {cache} | {created} |"


def _row_latest(m: dict) -> str:
    mid = str(m.get("id") or "--")
    ctx = m.get("context_length")
    ctx_s = str(ctx) if ctx is not None else "--"
    pricing = m.get("pricing") or {}
    inp = _fmt_price(pricing, "prompt")
    out = _fmt_price(pricing, "completion")
    age = _days_ago(m.get("created"))
    return f"| {mid} | {ctx_s} | {inp} | {out} | {age} |"


def _handle_list(models: list[dict], params: dict) -> str:
    n = int(params.get("n") or 10)
    query = (params.get("query") or "").strip().lower()
    filtered = models
    if query:
        filtered = [
            m
            for m in models
            if query in str(m.get("id") or "").lower()
            or query in str(m.get("name") or "").lower()
        ]
    filtered = sorted(filtered, key=lambda x: str(x.get("id") or ""))
    total = len(filtered)
    shown = filtered[:n]
    lines = [_table_header(), _table_sep()]
    for m in shown:
        lines.append(_row(m))
    lines.append("")
    lines.append(f"Showing {len(shown)} of {total} live from OpenRouter")
    if query:
        lines.append(f"Filter: '{params.get('query')}'")
    return "\n".join(lines)


def _handle_latest(models: list[dict], params: dict) -> str:
    n = int(params.get("n") or 5)
    sorted_models = sorted(
        models, key=lambda x: float(x.get("created") or 0), reverse=True
    )
    shown = sorted_models[:n]
    lines = [
        "| Model | Context | Input $/M | Output $/M | Age |",
        "|---|---|---|---|---|",
    ]
    for m in shown:
        lines.append(_row_latest(m))
    lines.append("")
    lines.append(f"Showing {len(shown)} newest of {len(models)} live from OpenRouter")
    return "\n".join(lines)


def _handle_price(models: list[dict], params: dict) -> str:
    target = (params.get("model") or "").strip()
    if not target:
        return "Missing 'model' param for price action."
    found = _find_model(models, target)
    if not found:
        return f"Model not found: {target}"
    pricing = found.get("pricing") or {}
    mid = found.get("id") or target
    name = found.get("name") or "--"
    ctx = found.get("context_length") or "--"
    created = _fmt_date(found.get("created"))
    lines = [
        f"**{mid}**",
        f"Name: {name}",
        f"Context: {ctx}",
        f"Created: {created}",
        "",
        "Pricing per 1M tokens:",
        f"- Input (prompt): {_fmt_price(pricing, 'prompt')}",
        f"- Output (completion): {_fmt_price(pricing, 'completion')}",
        f"- Image: {_fmt_price(pricing, 'image')}",
        f"- Request: {_fmt_price(pricing, 'request')}",
        f"- Cache read: {_fmt_price(pricing, 'input_cache_read')}",
        f"- Cache write: {_fmt_price(pricing, 'input_cache_write')}",
        "",
        f"Raw pricing: `{json.dumps(pricing)}`",
    ]
    return "\n".join(lines)


def _handle_compare(models: list[dict], params: dict) -> str:
    a_id = (params.get("model_a") or "").strip()
    b_id = (params.get("model_b") or "").strip()
    if not a_id or not b_id:
        return "Missing 'model_a' and 'model_b' for compare."
    a = _find_model(models, a_id)
    b = _find_model(models, b_id)
    if not a:
        return f"Model not found: {a_id}"
    if not b:
        return f"Model not found: {b_id}"
    pa = a.get("pricing") or {}
    pb = b.get("pricing") or {}
    keys = [
        "prompt",
        "completion",
        "image",
        "request",
        "input_cache_read",
        "input_cache_write",
    ]
    labels = {
        "prompt": "Input",
        "completion": "Output",
        "image": "Image",
        "request": "Request",
        "input_cache_read": "Cache read",
        "input_cache_write": "Cache write",
    }
    lines = [
        f"| Metric | {a.get('id')} | {b.get('id')} | Diff % |",
        "|---|---|---|---|",
    ]
    for k in keys:
        va = _price_val(pa, k)
        vb = _price_val(pb, k)
        fa = _fmt_price(pa, k)
        fb = _fmt_price(pb, k)
        if va > 0:
            diff = (vb - va) / va * 100
            ds = f"{diff:+.1f}%"
        else:
            ds = "--" if vb == 0 else "inf"
        lines.append(f"| {labels[k]} | {fa} | {fb} | {ds} |")
    return "\n".join(lines)


def _handle_trends(models: list[dict]) -> str:
    by_input = sorted(
        models, key=lambda x: _price_val(x.get("pricing") or {}, "prompt")
    )
    by_output = sorted(
        models, key=lambda x: _price_val(x.get("pricing") or {}, "completion")
    )
    newest = sorted(models, key=lambda x: float(x.get("created") or 0), reverse=True)

    def cheapest_block(title: str, sorted_list: list[dict], key: str) -> list[str]:
        out = [f"### {title}", _table_header(), _table_sep()]
        count = 0
        for m in sorted_list:
            if _price_val(m.get("pricing") or {}, key) == 0:
                continue
            out.append(_row(m))
            count += 1
            if count >= 5:
                break
        return out

    lines: list[str] = []
    lines.extend(cheapest_block("Cheapest by input $/M", by_input, "prompt"))
    lines.append("")
    lines.extend(cheapest_block("Cheapest by output $/M", by_output, "completion"))
    lines.append("")
    lines.append("### Newest 5")
    lines.append("| Model | Context | Input $/M | Output $/M | Age |")
    lines.append("|---|---|---|---|---|")
    for m in newest[:5]:
        lines.append(_row_latest(m))
    return "\n".join(lines)


def _handle_chat(params: dict) -> str:
    msg = (params.get("message") or "").strip()
    model = (params.get("model") or "").strip()
    if not msg:
        return "Missing 'message' for chat action."
    if not model:
        model = "openai/gpt-4o-mini"
    try:
        return generate_text_openrouter(model, msg)
    except RuntimeError as exc:
        if "No OpenRouter API key" in str(exc):
            return (
                "No OpenRouter API key. Add to config/agent_keys.json under openrouter."
            )
        return f"OpenRouter error: {exc}"
    except Exception as exc:
        return f"OpenRouter error: {exc}"


def openrouter_control(*, parameters: dict, player=None, speak=None) -> str:
    """Dispatch OpenRouter actions."""
    try:
        params = parameters or {}
        action = (params.get("action") or "").strip().lower()
        force = bool(params.get("force_refresh"))

        if action == "chat":
            return _handle_chat(params)

        if action == "check_updates":
            from core.openrouter_watcher import check_for_updates

            return check_for_updates(force=force)

        models = _get_models(force)

        if action == "list_models":
            return _handle_list(models, params)
        if action == "latest":
            return _handle_latest(models, params)
        if action == "price":
            return _handle_price(models, params)
        if action == "compare":
            return _handle_compare(models, params)
        if action == "trends":
            return _handle_trends(models)
        return "Unknown action. Use one of: list_models, latest, price, compare, trends, chat, check_updates."
    except Exception as exc:
        logger.exception("openrouter_control failed: %s", exc)
        return f"OpenRouter error: {exc}"
