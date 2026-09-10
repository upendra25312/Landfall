"""Cycle 63 — Playwright browser tests for Execution-Readiness Experience (Epic E15.4 / §E15D).

Validates:
  - 15 Assessment-First Dashboard Areas navigation and anchor sections (§E15D.1)
  - Interactive 5-state MEG readiness table with click-to-expand drill-down (§E15D.2)
  - 6 simplified prompt cards on the chat welcome view (§E15D.3)
  - Strict Content Security Policy (zero console errors, zero CSP violations)
"""
from __future__ import annotations

from playwright.sync_api import expect


def test_chat_page_renders_six_simplified_prompt_cards(page, base_url, console_errors):
    """Chat page welcome view must render exactly the 6 focused prompt cards per §E15D.3."""
    page.goto(base_url + "/", wait_until="networkidle")

    # Prompt cards grid uses button.pc inside .cardgrid
    cards = page.locator(".cardgrid .pc")
    expect(cards).to_have_count(6)

    expected_labels = [
        "Full assessment",
        "Azure architecture",
        "Cost & POE",
        "Migration plan",
        "Resource plan",
        "Ask Microsoft",
    ]
    card_texts = [cards.nth(i).inner_text() for i in range(6)]
    for label in expected_labels:
        assert any(label in t for t in card_texts), f"Prompt card '{label}' not found on welcome view"

    assert console_errors == []


def test_dashboard_renders_fifteen_assessment_first_areas(page, base_url, console_errors):
    """Dashboard must render all 15 assessment-first areas with navigation bar (§E15D.1)."""
    page.goto(base_url + "/dashboard?e=contoso-ltd/dc-exit", wait_until="networkidle")

    # Verify Area navigation bar
    nav = page.locator(".area-nav")
    expect(nav).to_be_visible()
    nav_buttons = page.locator(".area-btn")
    expect(nav_buttons).to_have_count(15)

    # Verify all 15 area section anchors
    area_ids = [
        "area-overview",
        "area-data-discovery",
        "area-current-estate",
        "area-target-arch",
        "area-cost-poe",
        "area-strategy",
        "area-waves",
        "area-timeline",
        "area-resource-plan",
        "area-capacity",
        "area-readiness",
        "area-risks",
        "area-deliverables",
        "area-guidance",
        "area-evidence",
    ]
    for aid in area_ids:
        loc = page.locator(f"#{aid}")
        expect(loc).to_be_visible()

    # Click navigation button for Area 11 (Readiness) and verify active state
    btn_readiness = page.locator('.area-btn[data-area="readiness"]')
    btn_readiness.click()
    expect(btn_readiness).to_have_class("area-btn active")

    assert console_errors == []


def test_dashboard_interactive_readiness_drill_down(page, base_url, console_errors):
    """MEG 21-criterion readiness table must support click-to-expand drill-downs (§E15D.2)."""
    page.goto(base_url + "/dashboard?e=contoso-ltd/dc-exit", wait_until="networkidle")

    readiness_host = page.locator("#readinessHost")
    expect(readiness_host).to_be_visible()

    # Wait for the async readiness table to load
    drill_btns = readiness_host.locator(".drill-btn")
    expect(drill_btns.first).to_be_visible(timeout=5000)

    # Verify drill-down rows initially hidden
    drill_row_0 = readiness_host.locator("#drill-row-0")
    assert drill_row_0.is_hidden()

    # Click first Inspect Drill-Down button -> expands
    drill_btns.first.click()
    expect(drill_row_0).to_be_visible()

    # Verify 4-part drill-down structure
    detail = drill_row_0.locator(".readiness-detail")
    expect(detail).to_contain_text("Evidence:")
    expect(detail).to_contain_text("Missing Decision:")
    expect(detail).to_contain_text("Responsible Role:")
    expect(detail).to_contain_text("Recommended Action:")

    # Click again -> collapses
    drill_btns.first.click()
    assert drill_row_0.is_hidden()

    # Check 5-state pill badges exist
    pills = readiness_host.locator(".state-pill")
    expect(pills.first).to_be_visible()

    assert console_errors == []


def test_dashboard_deliverable_pack_and_resource_plan_download(page, base_url, console_errors):
    """Deliverables hub must expose download links including resource-plan-xlsx (§E15D.7)."""
    page.goto(base_url + "/dashboard?e=contoso-ltd/dc-exit", wait_until="networkidle")

    # Resource plan download link in Area 9
    rp_link = page.locator('a[href*="/dashboard/download/resource-plan-xlsx"]')
    expect(rp_link.first).to_be_visible()

    # Deliverables hub cards in Area 13
    deliv_cards = page.locator("#area-deliverables .dl-card")
    expect(deliv_cards).to_have_count(6)

    assert console_errors == []
