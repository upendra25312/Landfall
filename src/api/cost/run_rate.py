"""
Run-rate extras + one-time migration cost (PRD E2.4).

    result = estimate_run_rate_extras(servers, monthly_infra_cost, cfg)

The lines that sit beyond compute (estimate_compute_cost) and storage
(estimate_storage_cost) but still land on the client's monthly Azure bill —
backup, internet egress, monitoring (Log Analytics + Defender), a support plan —
plus the one-time cost of the migration itself (tooling, replication egress,
dual-running on-prem and Azure during cutover).

Deterministic, pure. Every rate comes from estimation_config.json ["extras"];
nothing is fetched. `monthly_infra_cost` (compute + storage) drives the
spend-proportional lines (dual-run).
"""
from __future__ import annotations

from .config import load_config

_OFF_STATES = ("poweredoff", "stopped", "deallocated", "off")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_on(server: dict) -> bool:
    return (server.get("powerstate") or "").strip().lower().replace(" ", "") not in _OFF_STATES


def estimate_run_rate_extras(
    servers: list[dict],
    monthly_infra_cost: float = 0.0,
    cfg: dict | None = None,
    price_date: str | None = None,
) -> dict:
    cfg = cfg or load_config()
    ex = cfg["extras"]
    live = [s for s in servers if _is_on(s)]
    n = len(live)

    # --- backup --------------------------------------------------------------
    bk = ex["backup"]
    protected_gb = sum(_num(s.get("used_disk_gb")) or _num(s.get("provisioned_disk_gb")) or 0.0
                       for s in live)
    vault_gb = protected_gb * bk.get("backup_size_factor", 1.0)
    backup_storage_fee = vault_gb * bk.get("vault_storage_usd_gb_month", 0.0)
    backup_instance_fee = n * bk.get("protected_instance_usd_month", 0.0)
    backup_monthly = (backup_storage_fee + backup_instance_fee) if bk.get("enabled", True) else 0.0

    # --- internet egress ---------------------------------------------------
    eg = ex["egress"]
    net_out_30d = sum(_num(s.get("net_out_gb_30d")) or 0.0 for s in live)
    internet_gb = net_out_30d * eg.get("internet_fraction_of_net_out", 1.0)
    billable_gb = max(0.0, internet_gb - eg.get("free_gb_month", 0))
    egress_monthly = billable_gb * eg.get("usd_per_gb", 0.0)

    # --- monitoring ------------------------------------------------------
    mon = ex["monitoring"]
    la_gb_month = n * mon.get("log_analytics_gb_per_server_day", 0.0) * 30
    la_monthly = la_gb_month * mon.get("log_analytics_usd_gb", 0.0)
    defender_monthly = (n * mon.get("defender_usd_server_month", 0.0)
                        if mon.get("defender_for_servers") else 0.0)
    monitoring_monthly = la_monthly + defender_monthly

    # --- support --------------------------------------------------------
    sp = ex["support"]
    plan = (sp.get("plan") or "none").lower()
    support_monthly = float(sp.get("flat_usd_month", {}).get(plan, 0.0))

    run_rate_monthly = round(backup_monthly + egress_monthly + monitoring_monthly + support_monthly, 2)

    # --- one-time ------------------------------------------------------
    ot = ex["one_time"]
    free_months = ot.get("migration_tooling_free_days", 0) / 30.0
    billable_months = max(0.0, ot.get("avg_migration_months_per_server", 0) - free_months)
    tooling_cost = n * billable_months * ot.get("migration_tooling_usd_server_month", 0.0)
    repl_egress_cost = protected_gb * ot.get("replication_egress_usd_per_gb", 0.0)
    dual_run_cost = (monthly_infra_cost * ot.get("dual_run_fraction_of_infra", 0.0)
                     * ot.get("dual_run_overlap_months", 0.0))
    one_time_total = round(tooling_cost + repl_egress_cost + dual_run_cost, 2)

    return {
        "currency": cfg["pricing"].get("currency", "USD"),
        "region": cfg["pricing"].get("region"),
        "price_date": price_date,
        "servers_counted": n,
        "servers_excluded_powered_off": len(servers) - n,
        "run_rate_monthly": {
            "backup": {
                "protected_instances": n,
                "protected_data_gb": round(protected_gb, 1),
                "vault_storage_gb": round(vault_gb, 1),
                "storage_fee": round(backup_storage_fee, 2),
                "protected_instance_fee": round(backup_instance_fee, 2),
                "monthly": round(backup_monthly, 2),
            },
            "egress": {
                "net_out_gb_30d": round(net_out_30d, 1),
                "internet_gb_month": round(internet_gb, 1),
                "free_gb": eg.get("free_gb_month", 0),
                "billable_gb": round(billable_gb, 1),
                "monthly": round(egress_monthly, 2),
                "basis": f"{eg.get('internet_fraction_of_net_out', 1.0) * 100:.0f}% of "
                         f"net_out_gb_30d treated as internet egress at ${eg.get('usd_per_gb', 0)}/GB",
            },
            "monitoring": {
                "log_analytics_gb_month": round(la_gb_month, 1),
                "log_analytics_monthly": round(la_monthly, 2),
                "defender_servers": n if mon.get("defender_for_servers") else 0,
                "defender_monthly": round(defender_monthly, 2),
                "monthly": round(monitoring_monthly, 2),
            },
            "support": {"plan": plan, "monthly": round(support_monthly, 2)},
            "total_monthly": run_rate_monthly,
            "annual": round(run_rate_monthly * 12, 2),
        },
        "one_time": {
            "migration_tooling": {
                "servers": n,
                "free_months": round(free_months, 1),
                "billable_months_per_server": round(billable_months, 2),
                "cost": round(tooling_cost, 2),
            },
            "replication_egress": {
                "data_gb": round(protected_gb, 1),
                "cost": round(repl_egress_cost, 2),
                "basis": "on-prem -> Azure is ingress (free) unless replication_egress_usd_per_gb is set",
            },
            "dual_run": {
                "overlap_months": ot.get("dual_run_overlap_months", 0.0),
                "fraction_of_infra": ot.get("dual_run_fraction_of_infra", 0.0),
                "monthly_infra_cost": round(monthly_infra_cost, 2),
                "cost": round(dual_run_cost, 2),
            },
            "total": one_time_total,
        },
        "totals": {
            "run_rate_monthly": run_rate_monthly,
            "run_rate_annual": round(run_rate_monthly * 12, 2),
            "one_time": one_time_total,
            "first_year_extras": round(run_rate_monthly * 12 + one_time_total, 2),
        },
        "assumptions": [
            f"{n} powered-on servers counted ({len(servers) - n} powered-off excluded)",
            f"backup: protected data x{bk.get('backup_size_factor', 1)} at "
            f"${bk.get('vault_storage_usd_gb_month', 0)}/GB-month + "
            f"${bk.get('protected_instance_usd_month', 0)}/instance",
            f"monitoring: {mon.get('log_analytics_gb_per_server_day', 0)} GB/server/day to Log "
            f"Analytics at ${mon.get('log_analytics_usd_gb', 0)}/GB"
            + (" + Defender for Servers" if mon.get("defender_for_servers") else ""),
            f"support plan: {plan}",
            f"one-time: dual-run {ot.get('dual_run_overlap_months', 0)} months at "
            f"{ot.get('dual_run_fraction_of_infra', 0) * 100:.0f}% of the ${monthly_infra_cost:,.0f}/mo "
            f"infra bill; migration tooling free for {ot.get('migration_tooling_free_days', 0)} days/server",
            "excludes ExpressRoute / VPN, landing-zone fixed services, and DB compute "
            "(replatform) — those are separate proposal lines",
        ],
        "config": {"source": cfg.get("_source"), "extras": ex},
    }
