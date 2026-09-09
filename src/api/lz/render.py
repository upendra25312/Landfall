"""
Rasterise the landing-zone SVG to PNG via the `ca-drawio` container (E11.22 / C27b).

Best-effort and optional: with `DRAWIO_RENDER_URL` unset (local dev, or before
`ca-drawio` is provisioned) `rasterize` returns None and callers just skip the
`.png` — the `.drawio` + `.svg` still ship, and the dashboard renders the SVG
inline regardless. The PNG only matters for the `.pptx` / `.docx` embed.
"""
from __future__ import annotations

import logging
import os
import time
import urllib.request

_TIMEOUT = 45          # ca-drawio runs at minReplicas 0 — the first call cold-starts the container
_ATTEMPTS = 2


def rasterize(svg: str | bytes, *, scale: float = 2.0) -> bytes | None:
    url = os.environ.get("DRAWIO_RENDER_URL")
    if not url:
        return None
    data = svg.encode() if isinstance(svg, str) else svg
    last: Exception | None = None
    for attempt in range(_ATTEMPTS):
        req = urllib.request.Request(
            f"{url.rstrip('/')}/render?scale={scale}", data=data, method="POST",
            headers={"Content-Type": "image/svg+xml",
                     "X-Drawio-Key": os.environ.get("DRAWIO_RENDER_KEY", "")})
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:  # noqa: S310 - fixed internal URL
                png = resp.read()
            return png if png[:8] == b"\x89PNG\r\n\x1a\n" else None
        except Exception as exc:  # noqa: BLE001
            last = exc
            if attempt + 1 < _ATTEMPTS:
                time.sleep(3)   # let the cold container finish starting, then retry once
    logging.warning("ca-drawio rasterise skipped: %s", last)
    return None
