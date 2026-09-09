"""
Playwright driver for the Azure Pricing Calculator (PRD E11.16 / E11.19).

    result = build_estimate(spec)   # spec = lz.calculator_spec output

Opens https://azure.microsoft.com/pricing/calculator/, adds one product module
per spec line item, applies the adapter's fields **scoped to that module**, sets
the estimate name / currency / licensing program, clicks Export, and returns:

    { "xlsx_b64": ..., "screenshot_b64": ..., "applied": [...], "skipped": [...],
      "monthly_header": "$12,345", "calculator": "https://azure.microsoft.com/..." }

Every calculator module renders as a ``div.row.product-module``; modules are
appended in add order, so the one just added is the last. Field-setting uses the
native value setter + input/change events (the calculator is a React SPA and that
is what makes it recompute). Everything is best-effort per line item: a product
that can't be added, or an adapter whose controls no longer resolve, is recorded
in ``skipped`` / ``applied[].fields_not_set`` and the run continues — a broken
adapter never blocks the rest and never invents a price.
"""
from __future__ import annotations

import base64
import logging

from adapters import adapter_for

CALCULATOR_URL = "https://azure.microsoft.com/pricing/calculator/"
_NAV_TIMEOUT = 60_000
_SETTLE_MS = 1_400
_MODULE_SEL = ".row.product-module"
# a "configured" module has at least one named control; the calculator ships one
# empty placeholder .row.product-module that the first added product fills.
_CONFIGURED = "[...document.querySelectorAll('.row.product-module')].filter(m => m.querySelector('select[name], input[name]'))"

# Apply one module's fields, scoped to modules[idx]. Args:
#   { idx, region, fields:[[name,value,kind], ...] }
# kinds: select | number | radio | typeahead | accordion
# Returns { missing:[names], applied:[names] }
_APPLY_MODULE = r"""
async ({ idx, region, fields }) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // re-resolve every time — the calculator can replace a module node on re-render
  const M = () => document.querySelectorAll('.row.product-module')[idx];
  if (!M()) return { missing: ['__module__'], applied: [] };

  const setNative = (el, v) => {
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, String(v));
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };

  const applied = [];

  // region first (every module has select[name=region])
  const rsel = M() && M().querySelector('select[name="region"]');
  if (rsel && region) {
    if ([...rsel.options].some(o => o.value === region)) { setNative(rsel, region); await sleep(150); }
  }

  const applyOne = async ([name, value, kind]) => {
    const mod = M();
    if (!mod) return false;
    if (kind === 'accordion') {
      const btn = [...mod.querySelectorAll('button')]
        .find(b => (b.innerText || '').toLowerCase().includes(String(name).toLowerCase()));
      if (btn) { btn.click(); await sleep(800); return true; }
      return false;
    }
    if (kind === 'radio') {
      const rb = [...mod.querySelectorAll('input[type=radio]')]
        .find(r => (r.name || '').toLowerCase().replace(/radiobutton-[0-9a-f-]{36}-/, '')
                      === String(name).toLowerCase() && r.value === String(value));
      if (rb) { rb.click(); await sleep(150); return true; }
      return false;
    }
    const el = mod.querySelector(`select[name="${name}"], input[name="${name}"]`);
    if (!el) return false;
    if (kind === 'select') {
      if (![...el.options].some(o => o.value === String(value))) return false;
      setNative(el, value);
      await sleep(700);          // a select can re-render the rest of the module
    } else if (kind === 'typeahead') {
      const box = el.parentElement && el.parentElement.querySelector('input[type=text]:not([name])');
      if (box) {
        setNative(box, value);
        await sleep(700);
        const opt = [...document.querySelectorAll('[role=option], .ms-List-cell, li')]
          .find(o => (o.innerText || '').trim().toLowerCase() === String(value).toLowerCase())
          || document.querySelector('[role=option], .ms-List-cell');
        if (opt) opt.click();
      }
      setNative(el, value);
      await sleep(300);
    } else {
      setNative(el, value);
      await sleep(200);
    }
    return true;
  };

  let pending = fields.slice();
  for (let pass = 0; pass < 2 && pending.length; pass++) {
    if (pass) await sleep(1500);            // let a layout-changing select settle
    const still = [];
    for (const f of pending) {
      let ok = false;
      try { ok = await applyOne(f); } catch (e) { /* retry next pass */ }
      if (ok) applied.push(f[0]); else still.push(f);
    }
    pending = still;
  }
  await sleep(600);
  return { missing: pending.map(f => f[0] + (f[2] === 'select' ? '=' + f[1] : '')), applied };
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
        await _clear_estimate(page)   # the calculator preloads sample modules

        for i, item in enumerate(spec.get("line_items", [])):
            svc = item.get("service")
            ad = adapter_for(svc)
            if not ad:
                skipped.append({"what": item.get("note") or svc, "why": f"no adapter for '{svc}'"})
                continue
            try:
                before = await page.evaluate(f"() => {_CONFIGURED}.length")
                await _add_with_retry(page, ad["product"], before)
                await page.wait_for_timeout(_SETTLE_MS)

                # index (within all .row.product-module) of the last configured module
                idx = await page.evaluate(
                    f"""() => {{
                          const all = [...document.querySelectorAll('{_MODULE_SEL}')];
                          for (let i = all.length - 1; i >= 0; i--)
                            if (all[i].querySelector('select[name], input[name]')) return i;
                          return all.length - 1;
                        }}""")
                fields = [[str(n), v, k] for (n, v, k) in ad["fields"](item.get("config", {}))]
                res = await page.evaluate(_APPLY_MODULE, {
                    "idx": idx, "region": item.get("region") or region_default, "fields": fields})
                await page.wait_for_timeout(_SETTLE_MS)

                rec = {"service": svc, "note": item.get("note"),
                       "verified_adapter": ad.get("verified", False)}
                if res.get("missing"):
                    rec["fields_not_set"] = res["missing"]
                applied.append(rec)
            except Exception as exc:  # noqa: BLE001
                logging.exception("line item %s (%s) failed", i, svc)
                skipped.append({"what": item.get("note") or svc, "why": f"driver error: {exc}"})

        # global: estimate name / currency / licensing program
        await _set_global(page, "input[name=estimate-name]", spec.get("estimate_name", ""))
        cur = (spec.get("currency") or "USD").upper()
        await page.evaluate(_SET_GLOBAL_SELECT, ["currentCurrency", cur])
        lic = spec.get("licensing_program_calc") or "mca"
        await page.evaluate(_SET_GLOBAL_SELECT, ["discountLevel", lic])
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


_SET_GLOBAL_SELECT = """
([name, value]) => {
  const el = document.querySelector(`select[name="${name}"]`);
  if (!el || ![...el.options].some(o => o.value === String(value))) return false;
  const s = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value').set;
  s.call(el, String(value));
  el.dispatchEvent(new Event('input',  { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
};
"""


async def _add_with_retry(page, product: str, before: int, tries: int = 3) -> None:
    """Add `product` and wait for a new configured module. The picker is flaky
    under load, so retry the search+click a couple of times before giving up."""
    last: Exception | None = None
    for attempt in range(tries):
        try:
            await _add_product(page, product)
            await page.wait_for_function(
                f"n => {_CONFIGURED}.length > n", arg=before, timeout=25_000)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
            await page.wait_for_timeout(1500)
    raise RuntimeError(f"could not add '{product}' after {tries} tries: {last}")


async def _clear_estimate(page) -> None:
    """Empty the estimate if the calculator preloaded sample *configured* modules.
    A fresh load usually has only one empty placeholder .row.product-module (which
    the first added product fills) — nothing to do there."""
    try:
        page.on("dialog", lambda d: d.accept())
        configured = await page.evaluate(f"() => {_CONFIGURED}.length")
        if not configured:
            return
        did = await page.evaluate(
            """() => {
                 const b = document.querySelector('button[title="Delete all" i]');
                 if (b) { b.click(); return true; }
                 [...document.querySelectorAll('button[title="Delete" i], button.calculator-button.delete')]
                   .forEach(x => x.click());
                 return false;
               }""")
        await page.wait_for_timeout(500)
        await page.evaluate(
            """() => [...document.querySelectorAll('button')]
                      .filter(b => /^(yes|delete|confirm|ok)$/i.test((b.innerText||'').trim()))
                      .forEach(b => b.click())""")
        await page.wait_for_function(f"() => {_CONFIGURED}.length === 0", timeout=15_000)
    except Exception:  # noqa: BLE001
        logging.warning("could not fully clear the starter estimate", exc_info=True)


async def _add_product(page, product: str) -> None:
    """Search the picker for `product` and click the matching 'Add to estimate'."""
    box = page.locator('input[placeholder*="Search products" i]').first
    if await box.count():
        await box.fill("")
        await box.type(product, delay=20)
        await page.wait_for_timeout(800)
    clicked = await page.evaluate(
        """(name) => {
             const want = name.toLowerCase();
             // the product name for an add-button sits on an h3/h4/product-content
             // element a few parents up from the button.
             const nameFor = (b) => {
               let n = b;
               for (let i = 0; i < 6 && n; i++) {
                 n = n.parentElement;
                 const el = n && n.querySelector('h3, h4, [class*=product-content]');
                 if (el) return (el.innerText || '').split('\\n')[0].trim().toLowerCase();
               }
               return '';
             };
             const btns = [...document.querySelectorAll('button.pickerItem__button--add, .service-info-picker-button')];
             const exact = btns.find(b => nameFor(b) === want);
             if (exact) { exact.click(); return true; }
             const starts = btns.find(b => nameFor(b).startsWith(want) || want.startsWith(nameFor(b)));
             if (starts) { starts.click(); return true; }
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
