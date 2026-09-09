"""
Weekly Playwright adapter smoke for the Azure Pricing Calculator (PRD E11.19).

    python src/calc/smoke.py               # human table + exit code
    python src/calc/smoke.py --json out.json

For every adapter in ``adapters.ADAPTERS`` it opens the live calculator, adds the
product, applies the adapter's fields against a representative config, and records
which controls still resolve. A calculator UI change that breaks an adapter shows
up here with the adapter and the unresolved control(s) named.

Exit code:
  0  every adapter marked ``verified: True`` resolved all its controls
  1  at least one verified adapter regressed (or the calculator failed to load)

Unverified adapters are reported but never fail the job — they degrade to
``skipped[]`` in a real run rather than mispricing a line item.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from adapters import ADAPTERS

CALCULATOR_URL = "https://azure.microsoft.com/pricing/calculator/"
_MODULE_SEL = ".row.product-module"

# one representative config per service — enough to exercise every branch of
# each adapter's fields() (tiers, capacities, hours, billing options).
SAMPLE: dict[str, dict] = {
    "virtual-machines": {"operatingSystem": "windows", "type": "os-only", "tier": "standard",
                         "category": "General purpose", "size": "d4sv5", "size_name": "D4s v5",
                         "count": 10, "hours": 730, "computeBillingOption": "three-year",
                         "osBillingOption": "ahb"},
    "managed-disks": {"tier": "prem-ssd", "size": "p20", "size_name": "P20", "count": 10},
    "storage-accounts": {"type": "block-blob", "tier": "standard", "access": "hot",
                         "redundancy": "lrs", "capacity_gb": 8192},
    "azure-files": {"tier": "premium", "redundancy": "lrs", "capacity_gb": 8192},
    "azure-netapp-files": {"service_level": "premium", "capacity_gb": 4096},
    "sql-managed-instance": {"tier": "general-purpose", "vcores": 8, "capacity_gb": 512, "count": 1},
    "sql-database": {"tier": "hyperscale", "vcores": 8, "capacity_gb": 512, "count": 1},
    "azure-database-for-postgresql": {"compute_tier": "generalpurpose", "capacity_gb": 256, "count": 1},
    "azure-database-for-mysql": {"compute_tier": "generalpurpose", "capacity_gb": 256, "count": 1},
    "bandwidth": {"internet_egress_gb": 2048},
    "vpn-gateway": {"tier": "vpngw1az", "hours": 730},
    "expressroute": {"gateway": "erGw1AZ", "circuit": "metered",
                     "circuit_bandwidth_mbps": 1000, "hours": 730},
    "azure-firewall": {"tier": "premium", "deployments": 1, "hours": 730, "data_processed_gb": 4096},
    "azure-bastion": {"tier": "standard", "hours": 730, "outbound_data_gb": 5},
    "ddos-protection-plan": {"plans": 1, "protected_public_ips": 5},
    "azure-dns": {"public_zones": 1, "private_zones": 4, "queries_millions": 5},
    "azure-monitor": {"log_data_ingestion_gb": 90, "interactive_retention_months": 3, "basic_logs_gb": 0},
    "key-vault": {"vault_type": "standard", "operations_10k": 20, "certificate_renewals": 5},
    "load-balancer": {"tier": "standard", "rules": 5, "data_processed_gb": 1024},
    "application-gateway": {"tier": "standard", "hours": 730, "capacity_units": 2, "data_processed_gb": 1024},
    "azure-site-recovery": {"protected_instances": 20, "target": "azure", "source": "azure"},
}


async def _run(headless: bool = True) -> list[dict]:
    from playwright.async_api import async_playwright
    from driver import _APPLY_MODULE, _CONFIGURED, _add_with_retry, _clear_estimate

    rows: list[dict] = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless,
                                           args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1440, "height": 1200})
        page.set_default_timeout(60_000)
        await page.goto(CALCULATOR_URL, wait_until="domcontentloaded")
        await page.wait_for_selector("button.pickerItem__button--add, .service-info-picker-button")
        await _clear_estimate(page)

        for svc, ad in ADAPTERS.items():
            row = {"service": svc, "product": ad["product"], "verified": ad.get("verified", False),
                   "added": False, "missing": [], "error": None}
            try:
                before = await page.evaluate(f"() => {_CONFIGURED}.length")
                await _add_with_retry(page, ad["product"], before)
                await page.wait_for_timeout(1200)
                row["added"] = True

                idx = await page.evaluate(
                    f"""() => {{ const all=[...document.querySelectorAll('{_MODULE_SEL}')];
                          for (let i=all.length-1;i>=0;i--) if (all[i].querySelector('select[name],input[name]')) return i;
                          return all.length-1; }}""")
                fields = [[str(n), v, k] for (n, v, k) in ad["fields"](SAMPLE.get(svc, {}))]
                res = await page.evaluate(_APPLY_MODULE,
                                          {"idx": idx, "region": "sweden-central", "fields": fields})
                row["missing"] = res.get("missing", [])
            except Exception as exc:  # noqa: BLE001
                row["error"] = str(exc)
            rows.append(row)

        await browser.close()
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", metavar="PATH", help="write the full result as JSON")
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()

    rows = asyncio.run(_run(headless=not args.headed))

    broke = [r for r in rows if r["verified"] and (r["error"] or not r["added"] or r["missing"])]
    warn = [r for r in rows if not r["verified"] and (r["error"] or not r["added"] or r["missing"])]

    w = max(len(r["service"]) for r in rows)
    print(f"\nAzure Pricing Calculator — adapter smoke ({len(rows)} adapters)\n")
    for r in rows:
        status = "OK "
        if r["error"] or not r["added"]:
            status = "FAIL"
        elif r["missing"]:
            status = "WARN"
        tag = "" if r["verified"] else "  (unverified)"
        detail = r["error"] or (", ".join(r["missing"]) if r["missing"] else "")
        print(f"  [{status}] {r['service']:<{w}}  {detail}{tag}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"rows": rows, "broke": [r["service"] for r in broke]}, fh, indent=2)

    if broke:
        print(f"\n{len(broke)} VERIFIED adapter(s) regressed: {', '.join(r['service'] for r in broke)}")
        return 1
    if warn:
        print(f"\n{len(warn)} unverified adapter(s) need attention (non-blocking): "
              f"{', '.join(r['service'] for r in warn)}")
    print("\nall verified adapters resolved their controls.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
