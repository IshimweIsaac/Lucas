"""Slide generation engine for Lucas visual presentations.

Generates beautiful dark-themed HTML slides with embedded CSS.
Each slide function returns a full slide body HTML string.
Use build_presentation() to assemble slides into a payload dict
suitable for WebSocketPlayer.open_presentation_slides().
"""

from __future__ import annotations

_SLIDE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, sans-serif;
  background: #0a0e14; color: #e1e4e8;
  padding: 40px; line-height: 1.6;
}
h1 { font-size: 2.5em; font-weight: 800; color: #fff; margin-bottom: 16px; letter-spacing: -0.02em; }
h2 { font-size: 1.6em; font-weight: 700; color: #58a6ff; margin-bottom: 12px; }
h3 { font-size: 1.2em; font-weight: 600; color: #f0f6fc; margin-bottom: 8px; }
p { margin-bottom: 12px; color: #c9d1d9; }
ul { list-style: none; padding: 0; }
li { padding: 6px 0; color: #c9d1d9; display: flex; align-items: center; gap: 10px; }
li::before { content: '\u25b8'; color: #58a6ff; font-weight: bold; }
table { width: 100%; border-collapse: collapse; margin: 16px 0; }
th { background: #1a1f2e; color: #58a6ff; padding: 10px 14px; text-align: left; font-weight: 600; border-bottom: 2px solid #30363d; }
td { padding: 10px 14px; border-bottom: 1px solid #21262d; color: #c9d1d9; }
tr:hover td { background: #161b22; }
.stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 20px 0; }
.stat-card { background: linear-gradient(135deg, #1a1f2e, #0d1117); border: 1px solid #30363d; border-radius: 12px; padding: 20px; text-align: center; }
.stat-value { font-size: 2.2em; font-weight: 800; color: #58a6ff; display: block; }
.stat-label { font-size: 0.85em; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 4px; }
.progress-bar { background: #21262d; border-radius: 20px; height: 24px; overflow: hidden; margin: 8px 0; }
.progress-fill { height: 100%; border-radius: 20px; background: linear-gradient(90deg, #58a6ff, #1f6feb); transition: width 0.3s; display: flex; align-items: center; justify-content: center; font-size: 0.8em; color: #fff; font-weight: 600; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.8em; font-weight: 600; }
.badge-done { background: #1a3a2a; color: #3fb950; }
.badge-todo { background: #1a1f2e; color: #8b949e; }
.badge-progress { background: #1a2d3a; color: #58a6ff; }
.badge-urgent { background: #3a1a1a; color: #f85149; }
.badge-high { background: #3a2a1a; color: #d29922; }
pre { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; overflow-x: auto; font-family: 'JetBrains Mono', 'Fira Code', monospace; font-size: 0.9em; color: #c9d1d9; }
code { font-family: 'JetBrains Mono', monospace; background: #161b22; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; color: #ffa657; }
.title-slide { display: flex; flex-direction: column; justify-content: center; align-items: center; height: 70vh; text-align: center; }
.title-slide h1 { font-size: 3em; margin-bottom: 16px; }
.title-slide p { font-size: 1.2em; color: #8b949e; }
.footer-note { position: fixed; bottom: 20px; right: 30px; font-size: 0.75em; color: #484f58; }
"""


def _slide(html_content: str) -> str:
    """Wrap HTML content in a slide div."""
    return f'<div class="slide">{html_content}</div>'


def title_slide(title: str, subtitle: str = "") -> str:
    """Create a title slide."""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    return _slide(f'<div class="title-slide"><h1>{title}</h1>{sub}</div>')


def list_slide(title: str, items: list[str]) -> str:
    """Create a slide with a bullet list."""
    items_html = "".join(f"<li>{item}</li>" for item in items)
    return _slide(f"<h2>{title}</h2><ul>{items_html}</ul>")


def stats_slide(title: str, stats: list[tuple[str, str]]) -> str:
    """Create a slide with stat cards.

    *stats* is a list of (value, label) tuples, e.g. [("42", "Tasks")].
    """
    cards = "".join(
        '<div class="stat-card">'
        f'<span class="stat-value">{val}</span>'
        f'<span class="stat-label">{lbl}</span>'
        "</div>"
        for val, lbl in stats
    )
    return _slide(f'<h2>{title}</h2><div class="stats-grid">{cards}</div>')


def table_slide(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """Create a slide with a table."""
    hdr = "".join(f"<th>{h}</th>" for h in headers)
    rows_html = "".join(
        f"<tr>{''.join(f'<td>{c}</td>' for c in row)}</tr>" for row in rows
    )
    return _slide(
        f"<h2>{title}</h2><table><thead><tr>{hdr}</tr></thead>"
        f"<tbody>{rows_html}</tbody></table>"
    )


def text_slide(title: str, body: str) -> str:
    """Create a slide with text content."""
    return _slide(f"<h2>{title}</h2><p>{body}</p>")


def progress_slide(title: str, items: list[tuple[str, int]]) -> str:
    """Create a slide with progress bars.

    *items* is a list of (label, percent) tuples.
    """
    bars = "".join(
        '<div style="margin:12px 0">'
        '<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
        f"<span>{lbl}</span><span>{pct}%</span>"
        "</div>"
        '<div class="progress-bar">'
        f'<div class="progress-fill" style="width:{pct}%">{pct}%</div>'
        "</div>"
        "</div>"
        for lbl, pct in items
    )
    return _slide(f"<h2>{title}</h2>{bars}")


def code_slide(title: str, code: str, language: str = "") -> str:
    """Create a slide with a code block."""
    return _slide(f"<h2>{title}</h2><pre><code>{code}</code></pre>")


def build_presentation(
    title: str, slides: list[str], labels: list[str] | None = None
) -> dict:
    """Build a full presentation payload ready for open_presentation_slides.

    Args:
        title: Presentation title.
        slides: List of slide body HTML strings (output of slide functions).
        labels: Optional list of slide labels (strings). Defaults to "1", "2", ...

    Returns:
        Dict with keys: title, slide_css, slide_bodies, slide_labels,
        slide_index, slide_count.
    """
    if labels is None:
        labels = [str(i) for i in range(1, len(slides) + 1)]
    return {
        "title": title,
        "slide_css": _SLIDE_CSS,
        "slide_bodies": slides,
        "slide_labels": labels,
        "slide_index": 0,
        "slide_count": len(slides),
    }
