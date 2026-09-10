"""Core chat-page journeys under a real browser + real CSP (PRD §4.17 / E13.15).

`TestClient` proves the response body; these prove the page renders and works with
real JS execution, real fetch calls, and the strict Content-Security-Policy — a
CSP violation or a syntax error in a static asset shows up as a console/page error
here. (The first run of this harness caught a fatal `\\'` in `chat.js` that had
broken the whole chat page since C41 — `TestClient` substring checks never saw it.)

    BROWSER=1 ./.venv2/Scripts/python.exe -m pytest tests/browser -q

Note: `page.wait_for_function(<string>)` is NOT usable here — evaluating a string as
JS violates `script-src 'self'`. Use auto-retrying `expect()` locator assertions.
"""
from __future__ import annotations

import re

from playwright.sync_api import expect

# The BROWSER=1 gate + the serve.py subprocess fixture live in conftest.py.


def _goto(page, base_url):
    page.goto(base_url + "/", wait_until="networkidle")
    # chat.js parsed and ran -> it populates the engagement <select>
    page.locator("#engsel option[value='contoso-ltd/dc-exit']").wait_for(state="attached", timeout=5000)


def _select(page, eid):
    page.select_option("#engsel", eid)
    expect(page.locator("#pipeline")).to_be_visible()
    expect(page.locator("#pipeline .step")).to_have_count(4)


# journey (a) — the page loads under the strict CSP with zero console/page errors
def test_chat_page_loads_clean(page, base_url, console_errors):
    _goto(page, base_url)
    assert page.title() == "Landfall"
    assert page.locator("link[href='/static/chat.css']").count() == 1
    # chat.js ran end-to-end: welcome content + prompt cards rendered
    expect(page.locator("#welcome .intro h2")).to_be_visible()
    assert console_errors == [], f"console/page errors on load: {console_errors}"


# journey (b) — the engagement picker is populated from /api/engagements and the
# choice persists (the user never types the <customer>/<project> id)
def test_engagement_picker_is_populated(page, base_url):
    _goto(page, base_url)
    values = page.locator("#engsel option").evaluate_all(
        "els => els.map(e => e.value).filter(Boolean)")
    assert "contoso-ltd/dc-exit" in values and "northwind/pilot" in values

    page.select_option("#engsel", "northwind/pilot")
    assert page.evaluate("localStorage.getItem('landfall.eng')") == "northwind/pilot"
    page.reload(wait_until="networkidle")
    page.locator("#engsel option[value='northwind/pilot']").wait_for(state="attached", timeout=5000)
    expect(page.locator("#engsel")).to_have_value("northwind/pilot")


# journey (d) — the guided pipeline strip reflects the engagement's real state
def test_pipeline_strip_reflects_state(page, base_url, console_errors):
    _goto(page, base_url)

    _select(page, "contoso-ltd/dc-exit")
    expect(page.locator("#pipeline .step.done")).to_have_count(3)   # inventory + analysis + estimate

    _select(page, "northwind/pilot")
    expect(page.locator("#pipeline .step.done")).to_have_count(0)
    expect(page.locator("#pipeline .hint")).to_contain_text("Upload the client inventory")
    assert console_errors == [], f"console/page errors: {console_errors}"


# journey (f) — asking before analysis gets a one-time, NON-blocking hint, not a block
def test_pre_analysis_chat_gets_a_nonblocking_hint(page, base_url, console_errors):
    _goto(page, base_url)
    _select(page, "northwind/pilot")

    page.fill("#q", "what is the run-rate cost?")
    page.click("#send")

    log = page.locator("#log")
    expect(log.get_by_text("what is the run-rate cost?")).to_be_visible()
    expect(log.get_by_text(re.compile("no inventory has been analysed", re.I))).to_be_visible()
    # non-blocking: the agent answer still arrives
    expect(log.get_by_text(re.compile("Confidence: Medium", re.I))).to_be_visible(timeout=10000)
    assert console_errors == [], f"console/page errors: {console_errors}"

    # the hint is one-time per engagement
    page.fill("#q", "and the effort?")
    page.click("#send")
    expect(log.get_by_text("and the effort?")).to_be_visible()
    expect(log.get_by_text(re.compile("Confidence: Medium", re.I))).to_have_count(2, timeout=10000)
    assert log.get_by_text(re.compile("no inventory has been analysed", re.I)).count() == 1
