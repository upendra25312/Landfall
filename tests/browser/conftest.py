"""Playwright browser-automation harness (PRD §4.17 / E13.15).

Skipped in the normal suite. Run it explicitly:

    BROWSER=1 ./.venv2/Scripts/python.exe -m pytest tests/browser -q

Needs `pytest-playwright` + a Chromium build (`python -m playwright install chromium`).
A session fixture boots `tests/browser/serve.py` (the app with in-memory blob +
a canned agent) on a free port and tears it down after.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))

_ENABLED = os.environ.get("BROWSER") == "1"


def pytest_collection_modifyitems(config, items):
    if _ENABLED:
        return
    skip = pytest.mark.skip(reason="set BROWSER=1 to run the Playwright browser harness (E13.15)")
    for item in items:
        if _HERE in str(item.fspath):
            item.add_marker(skip)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def base_url() -> str:
    if not _ENABLED:
        pytest.skip("BROWSER != 1")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, os.path.join(_HERE, "serve.py"), "--port", str(port)],
        cwd=_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.time() + 30
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"serve.py exited early:\n{proc.stdout.read()}")
            try:
                with urllib.request.urlopen(f"{url}/healthz", timeout=1) as r:
                    if r.status == 200:
                        break
            except (urllib.error.URLError, ConnectionError, socket.timeout):
                time.sleep(0.3)
        else:
            raise RuntimeError("serve.py did not become healthy within 30s")
        yield url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture()
def console_errors(page):
    """Collects console errors + page errors; assert it is empty at the end of a
    spec — a strict-CSP violation surfaces here."""
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    return errors
