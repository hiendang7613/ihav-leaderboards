"""Write ``report.html``: one static page with the data inline and interactive charts."""

from __future__ import annotations

import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

TEMPLATE = Path(__file__).with_name("report_template.html")


def _clean(value: Any) -> Any:
    """Replace NaN and infinity, which JSON cannot carry, with null."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def to_html(final: Dict[str, Any]) -> str:
    data = dict(final)
    data.setdefault("generated_at", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    payload = json.dumps(_clean(data), ensure_ascii=False, allow_nan=False)
    # Keep the JSON inert inside <script>: no closing tag and no HTML comment opener.
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    title = "Best %s" % final["query"] if final.get("query") else "Leaderboard"
    page = TEMPLATE.read_text(encoding="utf-8")
    return page.replace("__TITLE__", html.escape(title)).replace("__DATA__", payload)
