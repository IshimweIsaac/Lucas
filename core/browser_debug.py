"""Chrome DevTools Protocol (CDP) browser control via HTTP endpoints.

Allows listing, closing, activating, and navigating browser tabs through
the Chrome DevTools Protocol HTTP API. Requires the target browser to be
started with --remote-debugging-port=<port>.
"""

from __future__ import annotations

import requests

from core.logger import get_logger

logger = get_logger(__name__)

BROWSER_DEBUG_PORTS: dict[str, int] = {
    "chrome": 9222,
    "firefox": 9222,
    "brave": 9222,
    "edge": 9222,
}


def _debug_url(port: int) -> str:
    """Build the CDP JSON endpoint URL for the given port."""
    return f"http://localhost:{port}/json"


def _get_port(browser: str) -> int:
    """Return the debug port for the given browser name."""
    return BROWSER_DEBUG_PORTS.get(browser.lower(), 9222)


def _fetch_json(url: str) -> list | dict:
    """Fetch JSON from a URL with a short timeout."""
    resp = requests.get(url, timeout=5)
    resp.raise_for_status()
    return resp.json()


def _connect_error(browser: str, port: int) -> str:
    """Build a helpful message when CDP connection fails."""
    return (
        f"Chrome remote debugging not enabled for '{browser}'. "
        f"Start it with --remote-debugging-port={port}"
    )


def list_browser_tabs(browser: str = "chrome") -> str:
    """List all open tabs in the browser via CDP.

    Returns formatted list with titles, URLs, and tab IDs.
    """
    port = _get_port(browser)
    try:
        data = _fetch_json(_debug_url(port))
    except requests.ConnectionError:
        return _connect_error(browser, port)
    except requests.RequestException as e:
        return f"Failed to connect to '{browser}' CDP: {e}"
    except Exception as e:
        logger.error("list_browser_tabs error: %s", e)
        return f"Failed to list tabs: {e}"

    if isinstance(data, dict):
        data = data.get("data", [data])

    if not data:
        return f"No tabs found in {browser}."

    lines: list[str] = [f"Tabs ({len(data)}):"]
    for i, tab in enumerate(data, 1):
        title = tab.get("title", "Untitled") or "Untitled"
        url = tab.get("url", "") or ""
        tab_id = tab.get("id", "") or ""
        short_id = tab_id[:12] if len(tab_id) > 12 else tab_id
        lines.append(f'  {i}. "{title}"')
        lines.append(f"     URL: {url}")
        lines.append(f"     ID: {short_id}")
    return "\n".join(lines)


def close_browser_tab(tab_id: str, browser: str = "chrome") -> str:
    """Close a browser tab by its CDP tab ID."""
    port = _get_port(browser)
    short_id = tab_id[:12] if len(tab_id) > 12 else tab_id
    try:
        resp = requests.post(f"http://localhost:{port}/json/close/{tab_id}", timeout=5)
        resp.raise_for_status()
        return f"Tab {short_id}... closed in {browser}."
    except requests.ConnectionError:
        return _connect_error(browser, port) + (f"\n(Tried to close tab {short_id}...)")
    except requests.RequestException as e:
        return f"Failed to close tab {short_id}...: {e}"
    except Exception as e:
        logger.error("close_browser_tab error: %s", e)
        return f"Failed to close tab: {e}"


def activate_browser_tab(tab_id: str, browser: str = "chrome") -> str:
    """Bring a browser tab to focus via CDP."""
    port = _get_port(browser)
    short_id = tab_id[:12] if len(tab_id) > 12 else tab_id
    try:
        resp = requests.post(
            f"http://localhost:{port}/json/activate/{tab_id}", timeout=5
        )
        resp.raise_for_status()
        return f"Tab {short_id}... activated in {browser}."
    except requests.ConnectionError:
        return _connect_error(browser, port) + (
            f"\n(Tried to activate tab {short_id}...)"
        )
    except requests.RequestException as e:
        return f"Failed to activate tab {short_id}...: {e}"
    except Exception as e:
        logger.error("activate_browser_tab error: %s", e)
        return f"Failed to activate tab: {e}"


def navigate_tab(tab_id: str, url: str, browser: str = "chrome") -> str:
    """Navigate a specific browser tab to the given URL."""
    port = _get_port(browser)
    short_id = tab_id[:12] if len(tab_id) > 12 else tab_id
    try:
        resp = requests.post(
            f"http://localhost:{port}/json/navigate/{tab_id}?url={url}",
            timeout=5,
        )
        resp.raise_for_status()
        return f"Navigated tab {short_id}... to {url}."
    except requests.ConnectionError:
        return _connect_error(browser, port) + (
            f"\n(Tried to navigate tab {short_id}... to {url})"
        )
    except requests.RequestException as e:
        return f"Failed to navigate tab: {e}"
    except Exception as e:
        logger.error("navigate_tab error: %s", e)
        return f"Failed to navigate tab: {e}"
