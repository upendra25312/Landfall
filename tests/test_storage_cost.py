"""Cycle 5 — estimate_storage_cost (E2.3). Pure rate math; rates are injected."""
import csv
import io

from conftest import sample_bytes

from cost.config import load_config
from cost.storage_cost import classify, estimate_storage_cost

RATES = {
    "files_premium": 0.16, "files_standard_hot": 0.06,
    "anf_standard": 0.15, "anf_premium": 0.30, "anf_ultra": 0.39,
    "db_sql_mi": 0.12, "db_sql_hyperscale": 0.10, "db_flex_postgresql": 0.115,
    "db_flex_mysql": 0.115, "db_oracle": 0.16,
    "blob_hot_lrs": 0.02, "blob_cool_lrs": 0.01,
    "managed_premium_ssd_v2": 0.08,
}


def _cfg(**storage):
    return load_config(overrides={"storage": storage} if storage else None)


def test_classify_picks_service_from_target_service():
    assert classify({"type": "file", "target_service": "Azure NetApp Files Ultra"}) == ("file", "anf_ultra")
    assert classify({"type": "file", "target_service": "Azure Files Premium"}) == ("file", "files_premium")
    assert classify({"type": "db", "target_service": "SQL Managed Instance"}) == ("db", "db_sql_mi")
    assert classify({"type": "db", "target_service": "Azure SQL DB Hyperscale"}) == ("db", "db_sql_hyperscale")
    assert classify({"type": "db", "target_service": "PostgreSQL Flexible Server"}) == ("db", "db_flex_postgresql")
    assert classify({"type": "block", "target_service": "Premium SSD v2"})[0] == "block"


def test_block_volumes_excluded_by_default_and_reported():
    rows = [
        {"storage_id": "s1", "type": "block", "size_gb": 128, "target_service": "Premium SSD P10"},
        {"storage_id": "s2", "type": "file", "size_gb": 4096, "target_service": "Azure Files Premium"},
    ]
    r = estimate_storage_cost(rows, RATES, _cfg())
    assert len(r["line_items"]) == 1
    assert r["excluded"]["block_volumes"] == 1
    assert r["excluded"]["block_gb"] == 128.0
    assert r["totals"]["file_monthly"] == round(4096 * 0.16, 2)


def test_price_block_from_storage_table_includes_block():
    rows = [{"storage_id": "s1", "type": "block", "size_gb": 100, "target_service": "Premium SSD v2"}]
    r = estimate_storage_cost(rows, RATES, _cfg(price_block_from_storage_table=True))
    assert len(r["line_items"]) == 1
    assert r["excluded"]["block_volumes"] == 0
    assert r["line_items"][0]["monthly"] == round(100 * 0.08, 2)


def test_files_premium_min_provision_floor():
    rows = [{"storage_id": "s1", "type": "file", "size_gb": 40, "target_service": "Azure Files Premium"}]
    r = estimate_storage_cost(rows, RATES, _cfg())
    li = r["line_items"][0]
    assert li["billable_gb"] == 100.0            # floored
    assert li["monthly"] == round(100 * 0.16, 2)


def test_db_growth_headroom_applied():
    rows = [{"storage_id": "s1", "type": "db", "size_gb": 1000, "target_service": "PostgreSQL Flexible Server"}]
    r = estimate_storage_cost(rows, RATES, _cfg(db_growth_headroom_pct=20))
    li = r["line_items"][0]
    assert li["billable_gb"] == 1200.0
    assert li["monthly"] == round(1200 * 0.115, 2)


def test_injected_rate_overrides_config():
    rows = [{"storage_id": "s1", "type": "file", "size_gb": 8192, "target_service": "Azure NetApp Files Premium"}]
    r = estimate_storage_cost(rows, {"anf_premium": 0.50}, _cfg())
    assert r["line_items"][0]["rate_usd_gb_month"] == 0.5
    assert r["line_items"][0]["monthly"] == round(8192 * 0.5, 2)


def test_range_ordered_and_totals_reconcile():
    rows = _sample_rows()
    r = estimate_storage_cost(rows, RATES, _cfg())
    t = r["totals"]
    assert t["range"]["low_monthly"] <= t["range"]["expected_monthly"] <= t["range"]["high_monthly"]
    assert t["monthly"] == round(sum(x["monthly"] for x in r["line_items"]), 2)
    assert t["annual"] == round(t["monthly"] * 12, 2)
    assert t["monthly"] == round(t["file_monthly"] + t["db_monthly"] + t["object_monthly"], 2)


def test_missing_size_flagged_not_fatal():
    rows = [
        {"storage_id": "bad", "type": "file", "size_gb": "", "target_service": "Azure Files Premium"},
        {"storage_id": "ok", "type": "file", "size_gb": 200, "target_service": "Azure Files Premium"},
    ]
    r = estimate_storage_cost(rows, RATES, _cfg())
    assert len(r["line_items"]) == 1
    assert any("bad" in m for m in r["not_costed"])


def test_deterministic_over_full_sample():
    rows = _sample_rows()
    a = estimate_storage_cost(rows, RATES, _cfg())
    b = estimate_storage_cost(rows, RATES, _cfg())
    assert a["totals"] == b["totals"] and a["line_items"] == b["line_items"]
    # sample has file + db rows, no object
    assert a["totals"]["file_monthly"] > 0 and a["totals"]["db_monthly"] > 0


def _sample_rows():
    text = sample_bytes("storage.csv").decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))
