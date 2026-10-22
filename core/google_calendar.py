"""Google Calendar OAuth (read-only) → Lucas memory/calendar.json."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

from memory.config_manager import get_base_dir

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
CLIENT_FILE = get_base_dir() / "config" / "google_calendar_client.json"
TOKEN_FILE = Path.home() / ".lucas" / "google_calendar_token.json"

SETUP_HELP = """
Google Calendar login (one-time setup)
======================================
1. Open https://console.cloud.google.com/apis/credentials
2. Create project (or pick one) → Enable "Google Calendar API"
3. Credentials → Create credentials → OAuth client ID → Desktop app
4. Download JSON → save as:
   {client_path}
5. OAuth consent screen: add your Gmail as a test user (if app is in Testing)

Then run again:
  python scripts/google_calendar_sync.py
"""


def _ensure_client() -> Path:
    if not CLIENT_FILE.is_file():
        raise FileNotFoundError(SETUP_HELP.format(client_path=CLIENT_FILE))
    return CLIENT_FILE


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if TOKEN_FILE.is_file():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        return creds

    _ensure_client()
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_FILE), SCOPES)
    print("Opening browser for Google sign-in…")
    creds = flow.run_local_server(port=0, open_browser=True)
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved token to {TOKEN_FILE}")
    return creds


def login() -> str:
    """Run OAuth in browser; return status message."""
    try:
        _load_credentials()
    except FileNotFoundError as e:
        return str(e).strip()
    except ImportError:
        return (
            "Missing packages. Run:\n"
            "  pip install google-auth-oauthlib google-api-python-client"
        )
    return "Google Calendar connected. Run sync to import events."


def _parse_api_datetime(value: str, date_only: bool = False) -> tuple[str, str]:
    if date_only:
        d = value[:10]
        return d, "00:00"
    if "T" in value:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
    return value[:10], "00:00"


def sync_to_lucas(*, horizon_days: int = 60) -> tuple[int, str]:
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return 0, "pip install google-auth-oauthlib google-api-python-client"

    try:
        creds = _load_credentials()
    except FileNotFoundError as e:
        return 0, str(e).strip()

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    now = datetime.utcnow()
    end = now + timedelta(days=horizon_days)
    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=end.isoformat() + "Z",
            singleEvents=True,
            orderBy="startTime",
            maxResults=250,
        )
        .execute()
    )

    from core import calendar_store as cs

    data = cs.load()
    by_date = data.setdefault("events_by_date", {})
    added = 0
    for item in result.get("items", []):
        start = item.get("start", {})
        if "dateTime" in start:
            date_str, time_str = _parse_api_datetime(start["dateTime"])
        elif "date" in start:
            date_str, time_str = _parse_api_datetime(start["date"], date_only=True)
        else:
            continue
        desc = (item.get("summary") or "Event").strip()[:200]
        tag = f"[Google] {desc}"
        by_date.setdefault(date_str, [])
        if any(e.get("description") == tag and e.get("time") == time_str for e in by_date[date_str]):
            continue
        by_date[date_str].append(
            {"id": str(uuid.uuid4())[:8], "time": time_str, "description": tag}
        )
        added += 1
        by_date[date_str] = sorted(by_date[date_str], key=lambda x: x["time"])

    cs.save(data)
    return added, f"Synced {added} Google Calendar event(s) for the next {horizon_days} days."


def login_and_sync(horizon_days: int = 60) -> str:
    msg = login()
    if "connected" not in msg.lower() and "Saved token" not in msg:
        if "Missing packages" in msg or "one-time setup" in msg or "google_calendar_client" in msg:
            return msg
    n, sync_msg = sync_to_lucas(horizon_days=horizon_days)
    return f"{msg}\n{sync_msg}" if n or "Synced" in sync_msg else sync_msg
