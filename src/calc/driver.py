"""
Playwright driver for the Azure Pricing Calculator (PRD E11.16).

    result = build_estimate(spec)   # spec = lz.calculator_spec output

Opens https://azure.microsoft.com/pricing/calculator/, adds one product module
per spec line item, applies the adapter's fields, sets the estimate name /
currency / licensing program, clicks Export, and returns:

    { "xlsx_b64": ..., "screenshot_b64": ..., "applied": [...], "skipped": [...],
      "monthly_header": "$12,345", "calculator": "https://azure.microsoft.com/..." }

The field-setting uses the native value setter + input/change events — the
calculator is a React SPA and that is what makes it recompute (verified
2026-09-08). Everything is best-effort per line item: a product that can't be
added, or an adapter with no verified field map that fails, is recorded in
`skipped` and the run continues.
"""
from __future__ import annotations

import base64
import logging

from adapters import adapter_for

CALCULATOR_URL = "https://azure.microsoft.com/pricing/calculator/"
_NAV_TIMEOUT = 60_000
_SETTLE_MS = 1_200

_SET_NATIVE = """
([name, value, kind, root]) => {
  const scope = root || document;
  const set = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;
    setter.call(el, String(v));
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  if (kind === 'radio') {
    const rb = [...scope.querySelectorAll('input[type=radio]')]
      .find(r => (r.name||'').toLowerCase().includes(name.toLowerCase()) && r.value === String(value));
    if (rb) { rb.click(); return true; }
    return false;
  }
  let el = scope.querySelector(`select[name="${name}"], input[name="${name}"]`);
  if (!el) return false;
  if (kind === 'typeahead') {
    set(el, value);
    // let the typeahead list open, then pick the exact/first match
    return new Promise(res => setTimeout(() => {
      const opt = [...document.querySelectorAll('[role=option], .ms-List-cell, li')]
        .find(o => (o.innerText||'').trim().toLowerCase() === String(value).toLowerCase())
        || document.querySelector('[role=option], .ms-List-cell');
      if (opt) opt.click();
      res(true);
    }, 600));
  }
  set(el, value);
  return true;
};
"""


async def build_estimate(spec: dict) -> dict:
    from playwright.async_api import async_playwright

    applied: list[dict] = []
    skipped: list[dict] = list(spec.get("skipped", []))
    region_default = spec.get("region_default") or "sweden-central"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1200})
        page.set_default_timeout(_NAV_TIMEOUT)
        await page.goto(CALCULATOR_URL, wait_until="domcontentloaded")
        await page.wait_for_selector("button.pickerItem__button--add, .service-info-picker-button",
                                     timeout=_NAV_TIMEOUT)

        for i, item in enumerate(spec.get("line_items", [])):
            svc = item.get("service")
            ad = adapter_for(svc)
            if not ad:
                skipped.append({"what": item.get("note") or svc, "why": f"no adapter for '{svc}'"})
                continue
            try:
                await _add_product(page, ad["product"])
                await page.wait_for_timeout(_SETTLE_MS)
                mod = "form.wingtip-component, .fui-FluentProvider, form"
                # region first
                await page.evaluate(_SET_NATIVE, ["region",
                                    item.get("region") or region_default, "select", None])
                miss = []
                for name, value, kind in ad["fields"](item.get("config", {})):
                    ok = await page.evaluate(_SET_NATIVE, [name, value, kind, None])
                    if not ok:
                        miss.append(name)
                    await page.wait_for_timeout(180)
                await page.wait_for_timeout(_SETTLE_MS)
                rec = {"service": svc, "note": item.get("note"),
                       "verified_adapter": ad.get("verified", False)}
                if miss:
                    rec["fields_not_set"] = miss
                applied.append(rec)
            except Exception as exc:  # noqa: BLE001
                logging.exception("line item %s (%s) failed", i, svc)
                skipped.append({"what": item.get("note") or svc, "why": f"driver error: {exc}"})

        # global: estimate name / currency / licensing program
        await _set_global(page, "input[name=estimate-name]", spec.get("estimate_name", ""))
        cur = (spec.get("currency") or "USD").upper()
        await page.evaluate(_SET_NATIVE, ["currentCurrency", cur, "select", None])
        lic = spec.get("licensing_program_calc") or "mca"
        await page.evaluate(_SET_NATIVE, ["discountLevel", lic, "select", None])
        await page.wait_for_timeout(_SETTLE_MS)

        header = await page.evaluate(
            "() => (document.querySelector('[class*=stickyCostHeader]')||{}).innerText || ''")

        shot = await page.screenshot(full_page=True)

        async with page.expect_download(timeout=_NAV_TIMEOUT) as dl:
            await page.click("button.export-button")
        path = await (await dl.value).path()
        with open(path, "rb") as fh:
            xlsx = fh.read()

        await browser.close()

    return {
        "xlsx_b64": base64.b64encode(xlsx).decode(),
        "screenshot_b64": base64.b64encode(shot).decode(),
        "applied": applied,
        "skipped": skipped,
        "monthly_header": " ".join((header or "").split()),
        "calculator": CALCULATOR_URL,
    }


async def _add_product(page, product: str) -> None:
    """Search the picker for `product` and click its 'Add to estimate'."""
    box = page.locator('input[placeholder*="Search products" i]').first
    if await box.count():
        await box.fill("")
        await box.type(product, delay=20)
        await page.wait_for_timeout(700)
    clicked = await page.evaluate(
        """(name) => {
             const cards = [...document.querySelectorAll('[class*=pickerItem]')];
             for (const card of cards) {
               if ((card.innerText||'').toLowerCase().includes(name.toLowerCase())) {
                 const b = card.querySelector('button.pickerItem__button--add, .service-info-picker-button');
                 if (b) { b.click(); return true; }
               }
             }
             const any = document.querySelector('button.pickerItem__button--add, .service-info-picker-button');
             if (any) { any.click(); return true; }
             return false;
           }""", product)
    if not clicked:
        raise RuntimeError(f"could not add product '{product}'")


async def _set_global(page, selector: str, value: str) -> None:
    try:
        await page.evaluate(
            """([sel, v]) => {
                 const el = document.querySelector(sel); if (!el) return;
                 const s = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                 s.call(el, v);
                 el.dispatchEvent(new Event('input', {bubbles:true}));
                 el.dispatchEvent(new Event('change', {bubbles:true}));
               }""", [selector, value])
    except Exception:  # noqa: BLE001
        logging.warning("could not set %s", selector)
