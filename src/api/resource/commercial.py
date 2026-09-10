"""
Commercial Resource Cost Module (PRD E15C.14).

Calculates commercial services cost based on deterministic role demand and configuration-governed
rate cards across delivery models (Onshore, Nearshore, Offshore, Partner, Customer).
Never hallucinates consulting rates.
"""
from __future__ import annotations

from typing import Any

from cost.config import load_config
from resource.model import DeliveryModel, STANDARD_ROLES

# Default role rate weights relative to the firm blended day rate
ROLE_RATE_WEIGHTS: dict[str, float] = {
    "Migration Programme Manager": 1.15,
    "Lead Cloud Architect": 1.30,
    "Infrastructure / Migration Engineer": 0.95,
    "Network Engineer": 1.05,
    "Security & Compliance Lead": 1.25,
    "Database Administrator (DBA)": 1.10,
    "Application Owner / SME": 0.0,  # Customer internal role ($0 services billable)
    "Test Lead": 0.90,
    "DevOps & Operations Lead": 1.00,
    "FinOps Analyst": 0.85,
    "Change Manager": 0.0,  # Customer internal role ($0 services billable)
}

# Delivery model multipliers
DELIVERY_MODEL_FACTORS: dict[str, float] = {
    DeliveryModel.ONSHORE.value: 1.0,
    DeliveryModel.NEARSHORE.value: 0.70,
    DeliveryModel.OFFSHORE.value: 0.45,
    DeliveryModel.PARTNER.value: 1.20,
    DeliveryModel.CUSTOMER.value: 0.0,
    DeliveryModel.MICROSOFT.value: 0.0,
}


def calculate_commercial_cost(
    demand: dict[str, Any],
    rates_override: dict[str, float] | None = None,
    cfg: dict | None = None,
) -> dict[str, Any]:
    """
    Calculates role-by-role and month-by-month commercial resource costs.

    Args:
        demand: The output dict from `derive_resource_demand`.
        rates_override: Optional explicit mapping of {role_title: day_rate}.
        cfg: Optional firm estimation configuration.

    Returns:
        Structured commercial cost breakdown by role, delivery model, and monthly burn.
    """
    cfg = cfg or load_config()
    rates_cfg = cfg.get("rates", {})
    base_blended_rate = float(rates_cfg.get("blended_day_rate", 780) or 780)
    currency = str(rates_cfg.get("currency", "USD"))

    role_pds = demand.get("role_demand", {}).get("by_role_pd", {})
    monthly_schedule = demand.get("monthly_schedule", {})
    month_keys = monthly_schedule.get("month_keys", [])
    role_month_pd = monthly_schedule.get("role_month_pd", {})

    configured_rates: dict[str, float] = {}
    role_costs: list[dict[str, Any]] = []
    total_commercial_cost = 0.0
    billable_person_days = 0.0
    non_billable_person_days = 0.0

    for r_def in STANDARD_ROLES:
        title = r_def.title
        pd = role_pds.get(title, 0.0)

        # Resolve day rate
        if rates_override and title in rates_override:
            day_rate = float(rates_override[title])
        elif "role_day_rates" in rates_cfg and title in rates_cfg["role_day_rates"]:
            day_rate = float(rates_cfg["role_day_rates"][title])
        else:
            weight = ROLE_RATE_WEIGHTS.get(title, 1.0)
            model_factor = DELIVERY_MODEL_FACTORS.get(r_def.default_delivery_model.value, 1.0)
            day_rate = round(base_blended_rate * weight * model_factor)

        configured_rates[title] = day_rate
        cost = round(pd * day_rate, 2)
        total_commercial_cost += cost

        if day_rate > 0:
            billable_person_days += pd
        else:
            non_billable_person_days += pd

        role_costs.append({
            "role": title,
            "category": r_def.category,
            "delivery_model": r_def.default_delivery_model.value,
            "person_days": pd,
            "day_rate": day_rate,
            "currency": currency,
            "cost": cost,
            "is_billable": day_rate > 0,
        })

    # Monthly commercial spend run-rate
    monthly_costs: list[dict[str, Any]] = []
    for m_key in month_keys:
        m_cost = 0.0
        by_role_m_cost = {}
        for r_title, r_pd_map in role_month_pd.items():
            pd = r_pd_map.get(m_key, 0.0)
            rate = configured_rates.get(r_title, 0.0)
            c = round(pd * rate, 2)
            m_cost += c
            if c > 0:
                by_role_m_cost[r_title] = c

        monthly_costs.append({
            "month": m_key,
            "cost": round(m_cost, 2),
            "currency": currency,
            "by_role_cost": by_role_m_cost,
        })

    effective_day_rate = round(total_commercial_cost / billable_person_days) if billable_person_days > 0 else base_blended_rate

    return {
        "currency": currency,
        "base_blended_day_rate": base_blended_rate,
        "effective_day_rate": effective_day_rate,
        "total_commercial_cost": round(total_commercial_cost, 2),
        "billable_person_days": round(billable_person_days, 1),
        "non_billable_person_days": round(non_billable_person_days, 1),
        "role_costs": role_costs,
        "monthly_costs": monthly_costs,
        "day_rates": configured_rates,
        "basis": (
            f"Configured rates derived from base {currency} {base_blended_rate}/day with delivery model "
            "and functional role multipliers. Client SME & Change Manager billed at $0 (Customer internal)."
        ),
    }
