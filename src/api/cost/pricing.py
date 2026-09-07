"""
Build a PriceBook / DiskBook from the public Azure Retail Prices API
(prices.azure.com) for `cost.compute_cost`. Network lives here only.

  book = fetch_pricebook(["Standard_D4s_v5", ...], "swedencentral")
  # -> {"Standard_D4s_v5": {"linux": {"payg": h, "ri1y": h, "ri3y": h},
  #                         "windows": {...}}}
  disks = fetch_diskbook(["P10", "P20", ...], "swedencentral")   # -> {"P10": monthly_usd}
  price_date = last_price_date(book)
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

_URL = "https://prices.azure.com/api/retail/prices"
_TERM_YEARS = {"1 Year": 1, "3 Years": 3}


def _fetch(odata: str, max_pages: int = 6) -> list[dict]:
    url = f"{_URL}?currencyCode=USD&$filter={urllib.parse.quote(odata)}"
    out: list[dict] = []
    for _ in range(max_pages):
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = json.load(resp)
        out.extend(data.get("Items", []))
        url = data.get("NextPageLink")
        if not url:
            break
    return out


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


def fetch_pricebook(skus: list[str], region: str) -> dict:
    book: dict = {}
    uniq = sorted(set(s for s in skus if s))
    for chunk in _chunks(uniq, 12):
        ors = " or ".join(f"armSkuName eq '{s}'" for s in chunk)
        odata = (f"serviceName eq 'Virtual Machines' and armRegionName eq '{region}' "
                 f"and ({ors})")
        for it in _fetch(odata):
            sku = it.get("armSkuName")
            name = f"{it.get('skuName', '')} {it.get('meterName', '')} {it.get('productName', '')}"
            if not sku or "Spot" in name or "Low Priority" in name:
                continue
            lic = "windows" if "Windows" in (it.get("productName") or "") else "linux"
            entry = book.setdefault(sku, {}).setdefault(lic, {})
            price = it.get("retailPrice")
            if price is None:
                continue
            typ = it.get("type")
            if typ in ("Consumption", "DevTestConsumption"):
                if typ == "Consumption" or "payg" not in entry:
                    entry["payg" if typ == "Consumption" else "devtest"] = price
            elif typ == "Reservation":
                years = _TERM_YEARS.get(it.get("reservationTerm") or "")
                if not years:
                    continue
                # VM reservations in the retail API price the WHOLE term as a lump
                # sum — amortise to an hourly-equivalent.
                entry[f"ri{years}y"] = round(price / (years * 8760), 5)
            if it.get("effectiveStartDate"):
                book.setdefault("_meta", {}).setdefault("dates", set()).add(
                    it["effectiveStartDate"][:10])
    return book


def fetch_diskbook(tiers: list[str], region: str) -> dict:
    out: dict = {}
    uniq = sorted(set(t for t in tiers if t))
    ors = " or ".join(f"skuName eq '{t} LRS'" for t in uniq)
    odata = (f"serviceName eq 'Storage' and armRegionName eq '{region}' "
             f"and priceType eq 'Consumption' and productName eq 'Premium SSD Managed Disks' "
             f"and ({ors})")
    for it in _fetch(odata):
        sku = (it.get("skuName") or "").split(" ")[0]
        if (it.get("unitOfMeasure") or "").startswith("1/Month") and it.get("retailPrice") is not None:
            out[sku] = it["retailPrice"]
    return out


def last_price_date(book: dict) -> str | None:
    dates = (book.get("_meta") or {}).get("dates") or set()
    return max(dates) if dates else None
