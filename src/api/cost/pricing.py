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


# --- storage rate book for cost.storage_cost (E2.3) -------------------------

def _to_gb_month(price: float, unit: str) -> float | None:
    u = (unit or "").lower()
    if "gb/month" in u or "gib/month" in u or u in ("1/month",):
        return price
    if "gb/hour" in u or "gib/hour" in u:
        return price * 730.0
    return None


# meters that look like capacity but aren't the baseline LRS stored-data rate:
# backups, geo/zone redundancy premiums, per-operation charges, higher DB tiers.
_STORED_EXCLUDE = ("backup", "geo", "grs", "gzrs", "zrs", "zone redundan",
                   "restore", "snapshot", "read", "write", "operation",
                   "transaction", "retrieval", "metadata", "early delete", "index",
                   "change feed", "free", "pitr", "ltr", "point-in-time",
                   "long-term", "business critical", "memory optimized")


def _cheapest_stored(items: list[dict], needles: tuple[str, ...]) -> float | None:
    """Cheapest GB-month rate among meters matching a needle. After the exclude
    list drops backups and redundancy premiums, the cheapest survivor is the
    baseline LRS stored-data rate — which is what a first-pass estimate wants."""
    best = None
    for it in items:
        name = f"{it.get('meterName', '')} {it.get('productName', '')} {it.get('skuName', '')}".lower()
        if it.get("type") != "Consumption" or "spot" in name:
            continue
        if not any(n in name for n in needles) or any(x in name for x in _STORED_EXCLUDE):
            continue
        gm = _to_gb_month(it.get("retailPrice"), it.get("unitOfMeasure", ""))
        if gm is not None and gm > 0 and (best is None or gm < best):
            best = gm
    return best


_STORAGE_QUERIES: dict[str, tuple[str, tuple[str, ...]]] = {
    # category -> (serviceName, meter/product-name needles)
    "files_premium":       ("Storage", ("premium lrs provisioned",)),
    "files_standard_hot":  ("Storage", ("hot lrs data stored",)),
    "anf_standard":        ("Azure NetApp Files", ("standard capacity",)),
    "anf_premium":         ("Azure NetApp Files", ("premium capacity",)),
    "anf_ultra":           ("Azure NetApp Files", ("ultra capacity",)),
    "db_sql_mi":           ("SQL Managed Instance", ("storage", "data stored")),
    "db_sql_hyperscale":   ("SQL Database", ("hyperscale data stored",)),
    "db_flex_postgresql":  ("Azure Database for PostgreSQL", ("general purpose data stored", "storage data stored")),
    "db_flex_mysql":       ("Azure Database for MySQL", ("general purpose data stored", "storage data stored")),
    "blob_hot_lrs":        ("Storage", ("hot lrs data stored",)),
    "blob_cool_lrs":       ("Storage", ("cool lrs data stored",)),
}


def _sane(cat: str, rate: float) -> bool:
    """Reject a live rate that's wildly off the documented baseline — a mis-matched
    meter (backup tier, free tier, per-GiB-vs-per-GB slip) shouldn't silently
    replace a defensible config rate."""
    from .config import DEFAULTS

    base = DEFAULTS["storage"]["rates_usd_gb_month"].get(cat)
    if not base:
        return True
    return 0.4 * base <= rate <= 2.5 * base


def fetch_storagebook(region: str, categories: list[str] | None = None) -> dict:
    """{category: USD/GB-month}. Best-effort — a category that can't be resolved (or
    resolves to an implausible value) is left out so cost.storage_cost falls back
    to its estimation_config.json rate."""
    want = set(categories or _STORAGE_QUERIES)
    by_service: dict[str, list[str]] = {}
    for cat in want:
        q = _STORAGE_QUERIES.get(cat)
        if q:
            by_service.setdefault(q[0], []).append(cat)

    out: dict = {}
    for service, cats in by_service.items():
        odata = (f"serviceName eq '{service}' and armRegionName eq '{region}' "
                 f"and priceType eq 'Consumption'")
        try:
            items = _fetch(odata, max_pages=4)
        except Exception:                               # noqa: BLE001
            continue
        for cat in cats:
            rate = _cheapest_stored(items, _STORAGE_QUERIES[cat][1])
            if rate is not None and _sane(cat, rate):
                out[cat] = round(rate, 5)
        for it in items:
            if it.get("effectiveStartDate"):
                out.setdefault("_meta", {}).setdefault("dates", set()).add(
                    it["effectiveStartDate"][:10])
    return out
